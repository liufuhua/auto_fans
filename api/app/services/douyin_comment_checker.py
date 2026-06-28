from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.core.config import settings
from app.core.exceptions import AppException
from app.services.douyin_playwright_session import douyin_playwright_session_manager

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CommentCheckResult:
    status: str
    fail_reason: str | None = None


def check_douyin_comment(video_link: str, comment_content: str) -> CommentCheckResult:
    logger.info(
        "start douyin comment check: link=%s context=%s",
        video_link,
        douyin_playwright_session_manager.context_debug_info(),
    )
    try:
        return douyin_playwright_session_manager.run_with_authenticated_page(
            lambda page: _check_comment_on_page(page, video_link, comment_content)
        )
    except AppException as exc:
        if exc.code == "DOUYIN_LOGIN_REQUIRED":
            return CommentCheckResult(
                "login_required",
                f"抖音未登录或登录已失效；{douyin_playwright_session_manager.context_debug_info()}",
            )
        raise


def _check_comment_on_page(page, video_link: str, comment_content: str) -> CommentCheckResult:
    target = _normalize_text(comment_content)
    if not target:
        return CommentCheckResult("failed", "待校验评论内容为空")

    try:
        page.goto(
            video_link,
            wait_until="domcontentloaded",
            timeout=settings.douyin_playwright_page_timeout_seconds * 1000,
        )
        logger.info("douyin video page opened: url=%s", page.url)
    except Exception as exc:
        return CommentCheckResult("failed", f"视频页面打开失败：{exc}")

    _wait_for_page_idle(page)
    _dismiss_login_dialog(page)

    page_state = _detect_page_state(page)
    if page_state is not None:
        return page_state

    for _ in range(10):
        body_text = _read_body_text(page)
        if _text_contains_comment(body_text, target):
            return CommentCheckResult("exists")

        page_state = _detect_page_state(page)
        if page_state is not None:
            return page_state

        _dismiss_login_dialog(page)
        _scroll_comment_area(page)

    return CommentCheckResult("missing", "页面已打开，但未找到目标评论")


def _detect_page_state(page) -> CommentCheckResult | None:
    current_url = ""
    try:
        current_url = page.url or ""
    except Exception:
        pass

    if "verifycenter/captcha" in current_url or _visible_text(page, "请完成下列验证"):
        return CommentCheckResult("captcha_required", "抖音要求完成验证码或滑块验证")
    if _visible_text(page, "视频不存在") or _visible_text(page, "该视频已删除"):
        return CommentCheckResult("failed", "视频不存在或已删除")
    return None


def _dismiss_login_dialog(page) -> None:
    if not (_visible_text(page, "扫码登录") or _visible_text(page, "登录后免费畅享高清视频")):
        return

    selectors = [
        "button[aria-label='关闭']",
        "[aria-label='关闭']",
        "[class*='close']",
        "[class*='Close']",
    ]
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.is_visible(timeout=500):
                locator.click(timeout=800)
                page.wait_for_timeout(800)
                return
        except Exception:
            continue

    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(800)
    except Exception:
        pass


def _visible_text(page, text: str) -> bool:
    try:
        return page.get_by_text(text, exact=False).first.is_visible(timeout=800)
    except Exception:
        return False


def _read_body_text(page) -> str:
    try:
        return page.locator("body").inner_text(timeout=5000)
    except Exception:
        try:
            return page.content()
        except Exception:
            return ""


def _scroll_comment_area(page) -> None:
    selectors = [
        "[class*='comment']",
        "[data-e2e*='comment']",
        "[class*='Comment']",
    ]
    for selector in selectors:
        locator = page.locator(selector).last
        try:
            if locator.is_visible(timeout=500):
                locator.hover(timeout=500)
                page.mouse.wheel(0, 1200)
                page.wait_for_timeout(1200)
                return
        except Exception:
            continue

    try:
        page.mouse.wheel(0, 1200)
        page.wait_for_timeout(1200)
    except Exception:
        pass


def _wait_for_page_idle(page) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass
    try:
        page.wait_for_timeout(1500)
    except Exception:
        pass


def _text_contains_comment(text: str, normalized_target: str) -> bool:
    normalized_text = _normalize_text(text)
    if normalized_target in normalized_text:
        return True

    if len(normalized_target) <= 20:
        return False

    head = normalized_target[: min(18, len(normalized_target))]
    tail = normalized_target[-min(18, len(normalized_target)) :]
    return head in normalized_text and tail in normalized_text


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", value or "").strip()
