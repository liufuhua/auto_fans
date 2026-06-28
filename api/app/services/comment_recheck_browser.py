from __future__ import annotations

import html
import logging
import os
import re
import threading
import time
from pathlib import Path
from urllib.request import Request, urlopen

from sqlalchemy import select

from app.core.datetime_utils import now_beijing
from app.db.session import SessionLocal
from app.models.automation_result import AutomationResult
from app.models.comment_recheck import CommentRecheckRecord
from app.models.daily_task import DailyTask

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0 Safari/537.36"
)
_BROWSER_LOCK = threading.Lock()


class VerificationRequiredError(RuntimeError):
    pass


def schedule_comment_rechecks_for_results(
    automation_result_ids: list[int], task_date=None
) -> None:
    unique_ids = list(dict.fromkeys(automation_result_ids))
    if not unique_ids:
        logger.info("skip scheduling comment recheck: empty result ids")
        return

    target_date = task_date or now_beijing().date()
    logger.info(
        "schedule comment recheck browser job: count=%s task_date=%s",
        len(unique_ids),
        target_date,
    )
    thread = threading.Thread(
        target=run_comment_rechecks_for_results,
        args=(unique_ids,),
        kwargs={"task_date": target_date},
        name="comment-recheck-browser",
        daemon=True,
    )
    thread.start()


def run_pending_comment_rechecks(limit: int = 100) -> None:
    if not _BROWSER_LOCK.acquire(blocking=False):
        logger.info("comment recheck browser job already running")
        return

    try:
        _run_pending_comment_rechecks(
            limit=limit,
            automation_result_ids=None,
            task_date=now_beijing().date(),
        )
    finally:
        _BROWSER_LOCK.release()


def run_comment_rechecks_for_results(
    automation_result_ids: list[int], limit: int = 100, task_date=None
) -> None:
    if not automation_result_ids:
        return
    if not _BROWSER_LOCK.acquire(blocking=False):
        logger.info("comment recheck browser job already running")
        return

    try:
        _run_pending_comment_rechecks(
            limit=limit,
            automation_result_ids=list(dict.fromkeys(automation_result_ids)),
            task_date=task_date or now_beijing().date(),
        )
    finally:
        _BROWSER_LOCK.release()


def _run_pending_comment_rechecks(
    limit: int,
    automation_result_ids: list[int] | None,
    task_date,
) -> None:
    with SessionLocal() as db:
        statement = (
            select(CommentRecheckRecord, AutomationResult)
            .join(AutomationResult, AutomationResult.id == CommentRecheckRecord.automation_result_id)
            .join(DailyTask, DailyTask.id == AutomationResult.task_id)
            .where(CommentRecheckRecord.status.in_(["queued", "pending"]))
            .where(AutomationResult.status == "success")
            .where(AutomationResult.video_link.is_not(None))
            .where(AutomationResult.video_link != "")
            .where(DailyTask.task_date == task_date)
        )
        if automation_result_ids is not None:
            statement = statement.where(AutomationResult.id.in_(automation_result_ids))
        rows = db.execute(statement.order_by(AutomationResult.id.desc()).limit(limit)).all()

    if not rows:
        logger.info("no pending comment recheck records")
        return

    try:
        driver = _create_driver()
    except Exception as exc:  # noqa: BLE001 - record environment failures in DB.
        logger.exception("failed to start browser for comment recheck")
        _mark_records_failed([record.id for record, _ in rows], f"浏览器启动失败：{exc}")
        return

    try:
        for record, result in rows:
            driver = _check_one_record(
                driver=driver,
                record_id=record.id,
                video_link=result.video_link or "",
                comment_content=result.comment_content,
            )
    finally:
        driver.quit()


def _check_one_record(driver, record_id: int, video_link: str, comment_content: str):
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            exists = _check_one_record_once(driver, video_link, comment_content)
            if exists:
                _update_record(record_id, "exists", None)
            else:
                _update_record(record_id, "missing", "页面已打开，但未找到目标评论")
            return driver
        except Exception as exc:  # noqa: BLE001 - keep processing other records.
            last_exc = exc
            if isinstance(exc, VerificationRequiredError):
                logger.warning("comment recheck requires verification: record_id=%s", record_id)
                _update_record(record_id, "captcha_required", str(exc))
                return driver
            if attempt == 0 and _is_browser_session_error(exc):
                logger.warning(
                    "comment recheck browser session lost, restart browser: record_id=%s error=%s",
                    record_id,
                    exc,
                )
                _safe_quit_driver(driver)
                driver = _create_driver()
                continue

            logger.exception("comment recheck failed: record_id=%s", record_id)
            _update_record(record_id, "failed", f"校验失败：{exc}")
            return driver

    if last_exc is not None:
        logger.exception("comment recheck failed after browser restart: record_id=%s", record_id)
        _update_record(record_id, "failed", f"校验失败：{last_exc}")
    return driver


def _check_one_record_once(driver, video_link: str, comment_content: str) -> bool:
    video_page_url = _to_pc_video_url_safe(video_link)
    return _page_contains_comment(driver, video_page_url, comment_content)


def _is_browser_session_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        "invalid session id" in message
        or "failed to establish a new connection" in message
        or "connection refused" in message
        or "max retries exceeded" in message
        or "httpconnectionpool" in message
    )


def _safe_quit_driver(driver) -> None:
    try:
        driver.quit()
    except Exception:  # noqa: BLE001 - the session is already gone.
        return


def _create_driver():
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.edge.options import Options as EdgeOptions

    debugger_address = os.getenv("CHROME_DEBUGGER_ADDRESS", "").strip()
    if debugger_address:
        options = ChromeOptions()
        options.add_experimental_option("debuggerAddress", debugger_address)
        return webdriver.Chrome(options=options)

    browser_name, browser_binary = _detect_browser_binary()
    if browser_name == "edge":
        options = EdgeOptions()
    else:
        options = ChromeOptions()

    if browser_binary:
        options.binary_location = browser_binary
    user_data_dir = os.getenv("CHROME_USER_DATA_DIR", "").strip()
    if user_data_dir:
        options.add_argument(f"--user-data-dir={user_data_dir}")
    profile_directory = os.getenv("CHROME_PROFILE_DIRECTORY", "").strip()
    if profile_directory:
        options.add_argument(f"--profile-directory={profile_directory}")
    options.page_load_strategy = "none"
    if os.getenv("CHROME_HEADLESS", "true").strip().lower() not in {"0", "false", "no"}:
        options.add_argument("--headless=new")
    options.add_argument("--remote-debugging-port=0")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-notifications")
    options.add_argument("--blink-settings=imagesEnabled=false")
    options.add_argument("--window-size=1280,900")
    options.add_argument(f"--user-agent={_USER_AGENT}")
    if browser_name == "edge":
        return webdriver.Edge(options=options)
    return webdriver.Chrome(options=options)


def _detect_browser_binary() -> tuple[str, str | None]:
    env_path = os.getenv("CHROME_BINARY_PATH", "").strip()
    local_app_data = os.getenv("LOCALAPPDATA", "").strip()
    local_chrome = (
        str(Path(local_app_data) / "Google" / "Chrome" / "Application" / "chrome.exe")
        if local_app_data
        else ""
    )
    candidates = [
        env_path,
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        local_chrome,
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            browser_name = "edge" if Path(candidate).name.lower() == "msedge.exe" else "chrome"
            return browser_name, candidate
    return "chrome", None


def _to_pc_video_url(video_link: str) -> str:
    aweme_id = _extract_aweme_id(video_link)
    if aweme_id:
        return f"https://www.douyin.com/video/{aweme_id}"

    final_url = _resolve_redirect_url(video_link)
    aweme_id = _extract_aweme_id(final_url)
    if not aweme_id:
        raise ValueError("无法从视频链接中解析视频 ID")
    return f"https://www.douyin.com/video/{aweme_id}"


def _resolve_redirect_url(video_link: str) -> str:
    request = Request(video_link, headers={"User-Agent": _USER_AGENT})
    with urlopen(request, timeout=20) as response:
        return response.geturl()


def _to_pc_video_url_safe(video_link: str) -> str:
    try:
        return _to_pc_video_url(video_link)
    except Exception as exc:  # noqa: BLE001 - let the logged-in browser follow short links.
        logger.warning("resolve douyin redirect failed, use original link: %s", exc)
        return video_link


def _extract_aweme_id(value: str) -> str | None:
    match = re.search(r"/(?:video|share/video)/(\d+)", value)
    return match.group(1) if match else None


def _page_contains_comment(driver, video_page_url: str, comment_content: str) -> bool:
    from selenium.webdriver.common.keys import Keys
    from selenium.common.exceptions import TimeoutException

    target = _normalize_text(comment_content)
    driver.set_page_load_timeout(20)
    try:
        driver.get(video_page_url)
    except TimeoutException:
        logger.warning("comment recheck page load timed out, continue with current page source")

    for _ in range(24):
        time.sleep(2)
        source = driver.page_source
        _raise_if_verification_page(driver, source)
        _raise_if_not_logged_in(driver)
        if target and target in _normalize_text(source):
            return True
        _scroll_comment_page(driver, Keys.PAGE_DOWN)
    return False


def _scroll_comment_page(driver, page_down_key: str) -> None:
    driver.execute_script(
        """
        window.scrollBy(0, Math.max(600, window.innerHeight * 0.8));
        const nodes = Array.from(document.querySelectorAll('*'));
        for (const node of nodes) {
          const style = window.getComputedStyle(node);
          const canScroll = node.scrollHeight > node.clientHeight + 20;
          const overflowY = style.overflowY || style.overflow;
          if (canScroll && /(auto|scroll|overlay)/.test(overflowY)) {
            node.scrollTop = Math.min(
              node.scrollTop + Math.max(500, node.clientHeight * 0.85),
              node.scrollHeight
            );
          }
        }
        """
    )
    try:
        driver.switch_to.active_element.send_keys(page_down_key)
    except Exception:  # noqa: BLE001 - scrolling by JavaScript is enough when key input fails.
        return


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", html.unescape(value or ""))


def _raise_if_verification_page(driver, source: str) -> None:
    current_url = getattr(driver, "current_url", "") or ""
    title = getattr(driver, "title", "") or ""
    if (
        "verifycenter/captcha" in current_url
        or "verifycenter/captcha" in source
        or "验证码中间页" in title
        or "验证码中间页" in source
        or "login_status%22%3A0" in source
        or "login_status\":0" in source
    ):
        raise VerificationRequiredError("页面进入验证码/风控校验，无法判断评论是否存在")


def _raise_if_not_logged_in(driver) -> None:
    login_cookie_names = {
        "sessionid",
        "sessionid_ss",
        "sid_guard",
        "sid_tt",
        "uid_tt",
        "uid_tt_ss",
    }
    cookies = driver.get_cookies()
    cookie_names = {
        str(cookie.get("name", "")).lower()
        for cookie in cookies
        if str(cookie.get("value", "")).strip()
    }
    if cookie_names.intersection(login_cookie_names):
        return

    raise VerificationRequiredError("浏览器未登录抖音，无法可靠判断评论是否存在")


def _mark_records_failed(record_ids: list[int], reason: str) -> None:
    for record_id in record_ids:
        _update_record(record_id, "failed", reason)


def _update_record(record_id: int, status: str, fail_reason: str | None) -> None:
    with SessionLocal() as db:
        record = db.get(CommentRecheckRecord, record_id)
        if record is None:
            return
        record.status = status
        record.checked_at = now_beijing()
        record.fail_reason = fail_reason
        db.add(record)
        db.commit()
