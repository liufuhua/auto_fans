from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from time import time
from typing import Callable, TypeVar

from app.core.config import settings
from app.core.exceptions import AppException
from app.schemas.comment_recheck import CommentRecheckLoginStatusRead

DOUYIN_HOME_URL = "https://www.douyin.com/"
DOUYIN_LOGIN_URL = "https://www.douyin.com/?modal_id=login"
LOGIN_COOKIE_NAMES = {"sessionid", "sid_guard", "sso_uid_tt", "uid_tt"}
T = TypeVar("T")
logger = logging.getLogger(__name__)


@dataclass
class _PlaywrightState:
    playwright: object | None = None
    context: object | None = None
    page: object | None = None
    session_id: str | None = None
    qr_path: Path | None = None
    profile_dir: Path | None = None


class DouyinPlaywrightSessionManager:
    def __init__(self) -> None:
        self._lock = RLock()
        self._state = _PlaywrightState()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="douyin-playwright")
        self._thread_id: int | None = None

    def get_login_status(self) -> CommentRecheckLoginStatusRead:
        return self._run_on_playwright_thread(self._get_login_status)

    def _get_login_status(self) -> CommentRecheckLoginStatusRead:
        with self._lock:
            if self._state.context is None:
                return CommentRecheckLoginStatusRead(
                    logged_in=False,
                    session_id=None,
                    qr_code_url=None,
                    message="尚未启动抖音登录会话",
                )

            if self._is_logged_in():
                return CommentRecheckLoginStatusRead(
                    logged_in=True,
                    session_id=self._state.session_id,
                    qr_code_url=None,
                    message="已登录抖音",
                )

            return CommentRecheckLoginStatusRead(
                logged_in=False,
                session_id=self._state.session_id,
                qr_code_url=self._qr_code_url(self._state.session_id),
                message="请扫码登录抖音",
            )

    def ensure_login_status(self) -> CommentRecheckLoginStatusRead:
        return self._run_on_playwright_thread(self._ensure_login_status)

    def _ensure_login_status(self) -> CommentRecheckLoginStatusRead:
        with self._lock:
            self._ensure_context()
            if self._is_logged_in():
                return CommentRecheckLoginStatusRead(
                    logged_in=True,
                    session_id=self._state.session_id,
                    qr_code_url=None,
                    message="已登录抖音",
                )
            return CommentRecheckLoginStatusRead(
                logged_in=False,
                session_id=self._state.session_id,
                qr_code_url=self._qr_code_url(self._state.session_id),
                message="请扫码登录抖音",
            )

    def create_login_session(self) -> CommentRecheckLoginStatusRead:
        return self._run_on_playwright_thread(self._create_login_session)

    def _create_login_session(self) -> CommentRecheckLoginStatusRead:
        with self._lock:
            self._ensure_context()
            self._open_login_page()
            logger.info("douyin login session opened: %s", self.context_debug_info())
            if self._is_logged_in():
                return CommentRecheckLoginStatusRead(
                    logged_in=True,
                    session_id=self._state.session_id,
                    qr_code_url=None,
                    message="已登录抖音",
                )

            self._state.session_id = str(int(time() * 1000))
            self._state.qr_path = self._capture_login_qr(self._state.session_id)
            return CommentRecheckLoginStatusRead(
                logged_in=False,
                session_id=self._state.session_id,
                qr_code_url=self._qr_code_url(self._state.session_id),
                message=self._login_prompt_message(),
            )

    def confirm_login(self, session_id: str | None = None) -> CommentRecheckLoginStatusRead:
        return self._run_on_playwright_thread(lambda: self._confirm_login(session_id))

    def _confirm_login(self, session_id: str | None = None) -> CommentRecheckLoginStatusRead:
        with self._lock:
            if self._state.context is None:
                return CommentRecheckLoginStatusRead(
                    logged_in=False,
                    session_id=session_id,
                    qr_code_url=None,
                    message="尚未启动 Playwright 登录会话",
                )

            if session_id and self._state.session_id and session_id != self._state.session_id:
                return CommentRecheckLoginStatusRead(
                    logged_in=False,
                    session_id=self._state.session_id,
                    qr_code_url=self._qr_code_url(self._state.session_id),
                    message="登录会话已刷新，请使用最新二维码",
                )

            page = self._state.page
            if page is not None:
                self._wait_for_page_idle(page)

            if self._is_logged_in():
                logger.info("douyin login confirmed: %s", self.context_debug_info())
                return CommentRecheckLoginStatusRead(
                    logged_in=True,
                    session_id=self._state.session_id,
                    qr_code_url=None,
                    message="登录成功",
                )

            if self._state.session_id:
                self._state.qr_path = self._capture_login_qr(self._state.session_id)

            return CommentRecheckLoginStatusRead(
                logged_in=False,
                session_id=self._state.session_id,
                qr_code_url=self._qr_code_url(self._state.session_id),
                message=self._login_prompt_message(default="尚未检测到登录成功，请扫码后重试"),
            )

    def run_with_authenticated_page(self, callback: Callable[[object], T]) -> T:
        return self._run_on_playwright_thread(lambda: self._run_with_authenticated_page(callback))

    def _run_with_authenticated_page(self, callback: Callable[[object], T]) -> T:
        with self._lock:
            self._ensure_context()
            if not self.has_login_cookie() and not self._is_logged_in():
                raise AppException("抖音未登录", code="DOUYIN_LOGIN_REQUIRED", status_code=409)

            page = self._state.page
            if page is None:
                raise AppException("Playwright 浏览器未初始化", code="PLAYWRIGHT_NOT_READY")

            logger.info("douyin check uses login page context: %s", self.context_debug_info())
            page.set_default_timeout(settings.douyin_playwright_page_timeout_seconds * 1000)
            return callback(page)

    def has_login_cookie(self) -> bool:
        if self._thread_id != threading.get_ident():
            return self._run_on_playwright_thread(self._has_login_cookie)
        return self._has_login_cookie()

    def _has_login_cookie(self) -> bool:
        context = self._state.context
        if context is None:
            return False
        try:
            cookies = context.cookies([DOUYIN_HOME_URL])
        except Exception:
            return False
        return any(cookie.get("name") in LOGIN_COOKIE_NAMES and cookie.get("value") for cookie in cookies)

    def get_qr_path(self, session_id: str) -> Path:
        return self._run_on_playwright_thread(lambda: self._get_qr_path(session_id))

    def _get_qr_path(self, session_id: str) -> Path:
        with self._lock:
            if not self._state.session_id or session_id != self._state.session_id:
                raise AppException("登录二维码已过期，请刷新", code="QR_EXPIRED", status_code=404)
            if self._state.qr_path is None or not self._state.qr_path.exists():
                self._state.qr_path = self._capture_login_qr(session_id)
            return self._state.qr_path

    def close(self) -> None:
        if self._thread_id == threading.get_ident():
            self._close_playwright()
            return

        executor = self._executor
        future = executor.submit(self._close_playwright_on_current_thread)
        future.result()
        executor.shutdown(wait=True)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="douyin-playwright")
        self._thread_id = None

    def _close_playwright_on_current_thread(self) -> None:
        self._thread_id = threading.get_ident()
        self._close_playwright()

    def _close_playwright(self) -> None:
        with self._lock:
            context = self._state.context
            playwright = self._state.playwright
            debug_info = self._context_debug_info()
            if context is None and playwright is None:
                return

            try:
                if context is not None:
                    context.close()
            except Exception:
                logger.exception("failed to close douyin playwright context: %s", debug_info)
            finally:
                try:
                    if playwright is not None:
                        playwright.stop()
                except Exception:
                    logger.exception("failed to stop douyin playwright: %s", debug_info)
                self._state = _PlaywrightState()
                logger.info("douyin playwright context closed: %s", debug_info)

    def _ensure_context(self) -> None:
        if self._state.context is not None:
            return

        try:
            from playwright.sync_api import sync_playwright
        except ModuleNotFoundError as exc:
            raise AppException(
                "Playwright 未安装，请先安装 api 依赖并执行 playwright install chromium",
                code="PLAYWRIGHT_NOT_INSTALLED",
                status_code=500,
            ) from exc

        profile_dir = self._resolve_path(settings.douyin_playwright_profile_dir)
        profile_dir.mkdir(parents=True, exist_ok=True)

        playwright = sync_playwright().start()
        try:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=settings.douyin_playwright_headless,
                viewport={"width": 1280, "height": 900},
                locale="zh-CN",
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-default-browser-check",
                ],
            )
        except Exception:
            playwright.stop()
            raise

        context.set_default_timeout(settings.douyin_playwright_page_timeout_seconds * 1000)
        self._state.playwright = playwright
        self._state.context = context
        self._state.page = context.pages[0] if context.pages else context.new_page()
        self._state.profile_dir = profile_dir
        logger.info("douyin playwright context started: %s", self.context_debug_info())

    def _open_login_page(self) -> None:
        page = self._state.page
        if page is None:
            raise AppException("Playwright 页面未初始化", code="PLAYWRIGHT_PAGE_NOT_READY")
        page.goto(DOUYIN_LOGIN_URL, wait_until="domcontentloaded")
        self._wait_for_page_idle(page)
        self._try_click_login_entry(page)

    def _is_logged_in(self) -> bool:
        context = self._state.context
        page = self._state.page
        if context is None:
            return False

        if self._has_login_cookie():
            return True

        if page is None:
            return False

        try:
            if page.get_by_text("登录", exact=True).first.is_visible(timeout=1000):
                return False
        except Exception:
            pass

        try:
            return page.locator('[data-e2e="user-avatar"], img[alt*="头像"]').first.is_visible(
                timeout=1000
            )
        except Exception:
            return False

    def _capture_login_qr(self, session_id: str) -> Path:
        page = self._state.page
        if page is None:
            raise AppException("Playwright 页面未初始化", code="PLAYWRIGHT_PAGE_NOT_READY")

        qr_dir = self._resolve_path(settings.douyin_playwright_qr_dir)
        qr_dir.mkdir(parents=True, exist_ok=True)
        qr_path = qr_dir / f"{session_id}.png"

        selectors = ["[class*='qrcode']", "[class*='qr-code']", "[class*='QRCode']"]
        for selector in selectors:
            try:
                locators = page.locator(selector)
                count = min(locators.count(), 10)
            except Exception:
                continue
            for index in range(count):
                locator = locators.nth(index)
                try:
                    if not locator.is_visible(timeout=1000):
                        continue
                    box = locator.bounding_box(timeout=1000)
                    if not box or box["width"] < 120 or box["height"] < 120:
                        continue
                    locator.screenshot(path=str(qr_path))
                    return qr_path
                except Exception:
                    continue

        page.screenshot(path=str(qr_path), full_page=False)
        return qr_path

    def _try_click_login_entry(self, page) -> None:
        candidates = ["登录", "扫码登录"]
        for text in candidates:
            try:
                locator = page.get_by_text(text, exact=False).first
                if locator.is_visible(timeout=1000):
                    locator.click(timeout=1000)
                    self._wait_for_page_idle(page)
                    return
            except Exception:
                continue

    def _wait_for_page_idle(self, page) -> None:
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass

    def _login_prompt_message(self, default: str = "请扫码登录抖音") -> str:
        page = self._state.page
        if page is None:
            return default
        try:
            if page.get_by_text("请完成下列验证", exact=False).first.is_visible(timeout=1000):
                return "抖音要求先完成验证，请在浏览器窗口完成后刷新二维码"
        except Exception:
            pass
        return default

    def _qr_code_url(self, session_id: str | None) -> str | None:
        if not session_id:
            return None
        return f"/api/comment-results/recheck/login-qr?sessionId={session_id}"

    def _resolve_path(self, value: str) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return Path.cwd() / path

    def context_debug_info(self) -> str:
        if self._thread_id != threading.get_ident():
            return self._run_on_playwright_thread(self._context_debug_info)
        return self._context_debug_info()

    def _context_debug_info(self) -> str:
        context = self._state.context
        page = self._state.page
        cookie_count = 0
        if context is not None:
            try:
                cookie_count = len(context.cookies([DOUYIN_HOME_URL]))
            except Exception:
                cookie_count = -1
        return (
            f"context_id={id(context)} page_id={id(page)} "
            f"profile_dir={self._state.profile_dir} cookies={cookie_count} "
            f"session_id={self._state.session_id}"
        )

    def _run_on_playwright_thread(self, action: Callable[[], T]) -> T:
        if self._thread_id == threading.get_ident():
            return action()

        def wrapped() -> T:
            self._thread_id = threading.get_ident()
            return action()

        return self._executor.submit(wrapped).result()


douyin_playwright_session_manager = DouyinPlaywrightSessionManager()
