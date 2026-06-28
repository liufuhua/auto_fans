from __future__ import annotations

import argparse
import random
import re
import subprocess
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any

from appium.webdriver.common.appiumby import AppiumBy

from app.api_client import ClaimTaskResult
from app.douyin_actions import DouyinActions, LocatorRepository, LocatorSpec
from app.logger import append_current_device_log, format_log_step


DEFAULT_INPUT_XPATH = (
    '//android.widget.EditText[@resource-id="com.ss.android.ugc.aweme:id/et_search_kw"]'
)
DEFAULT_SEARCH_BUTTON_XPATH = (
    '//android.widget.Button[@content-desc="搜索" and @clickable="true"]'
)
DEFAULT_SUBMIT_XPATH = '//android.widget.TextView[@resource-id="com.ss.android.ugc.aweme:id/4un"]'
DEFAULT_VIDEO_TAB_XPATH = (
    '//androidx.appcompat.app.ActionBar$Tab'
    '[.//android.widget.Button[@resource-id="android:id/text1" and @text="视频"]]'
)
DEFAULT_AUTHOR_XPATH = '//android.widget.TextView[@resource-id="com.ss.android.ugc.aweme:id/+j"]'
DEFAULT_SEARCH_RESULT_LIKE_XPATH = (
    '//android.widget.LinearLayout[contains(@content-desc,"喜欢") '
    'and contains(@content-desc,"按钮")]'
)
DEFAULT_LIKE_XPATH = (
    '//android.widget.LinearLayout[contains(@content-desc,"未点赞") '
    'and contains(@content-desc,"喜欢") and contains(@content-desc,"按钮")]'
)
DEFAULT_FAVORITE_XPATH = (
    '//android.widget.LinearLayout[contains(@content-desc,"未选中") '
    'and contains(@content-desc,"收藏") and contains(@content-desc,"按钮")]'
)
DEFAULT_COMMENT_BUTTON_XPATH = (
    '//android.widget.ImageView[contains(@content-desc,"评论") and contains(@content-desc,"按钮")]'
)
DEFAULT_COMMENT_INPUT_XPATH = (
    '//android.widget.EditText['
    '@resource-id="com.ss.android.ugc.aweme:id/eoy" '
    'or @resource-id="com.ss.android.ugc.aweme:id/ep0" '
    'or contains(@text,"期待你的评论")'
    ']'
)
DEFAULT_SEND_COMMENT_XPATH = (
    '//android.widget.TextView[@resource-id="com.ss.android.ugc.aweme:id/es7"]'
)
DEFAULT_LINK_COPIED_CLOSE_XPATH = (
    '//android.widget.ImageView[@resource-id="com.ss.android.ugc.aweme:id/zks"]'
)


def log_step(message: str) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    line = f"[{timestamp}] {format_log_step(message)}"
    print(line, flush=True)
    append_current_device_log(line)


def quit_with_timeout(driver, timeout_seconds: int) -> None:
    log_step("释放 Appium driver")
    done = threading.Event()

    def quit_driver() -> None:
        try:
            driver.quit()
        finally:
            done.set()

    thread = threading.Thread(target=quit_driver, daemon=True)
    thread.start()
    if not done.wait(timeout_seconds):
        log_step(f"警告：driver.quit() 超过 {timeout_seconds}s 未返回，继续退出")
        return
    log_step("Appium driver 已释放")


def sleep_random(min_seconds: float, max_seconds: float, label: str) -> None:
    seconds = random.uniform(min_seconds, max_seconds)
    log_step(f"等待 {label}：{seconds:.2f}s")
    time.sleep(seconds)


def random_seconds(min_seconds: float, max_seconds: float, label: str) -> float:
    seconds = random.uniform(min_seconds, max_seconds)
    log_step(f"计划等待 {label}：{seconds:.2f}s")
    return seconds


def format_wait(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    return f"{seconds:.2f}s"


def build_result_summary(
    *,
    task: ClaimTaskResult,
    keyword: str,
    matched_author: str | None,
    like_success: bool,
    favorite_success: bool,
    comment_success: bool,
    backend_status: str,
    result_id: int | None,
    waits: dict[str, float],
    video_link: str | None = None,
) -> str:
    return "\n".join(
        [
            f"任务：taskId={task.task_id}, taskItemId={task.task_item_id}",
            f"医生：{task.doctor_name}",
            f"关键词：{keyword}",
            f"作者：{matched_author or '-'}",
            f"点赞：{'成功' if like_success else '未完成'}",
            f"收藏：{'成功' if favorite_success else '未完成'}",
            f"评论：{'成功' if comment_success else '未完成'}",
            f"视频链接：{video_link or '-'}",
            f"页面等待：搜索前={format_wait(waits.get('before_input'))}",
            f"页面等待：输入后={format_wait(waits.get('after_input'))}",
            f"页面等待：搜索后={format_wait(waits.get('after_search'))}",
            f"页面等待：切换视频Tab后={format_wait(waits.get('after_video_tab'))}",
            f"页面等待：视频观看={format_wait(waits.get('watch_video'))}",
            f"页面等待：点赞后={format_wait(waits.get('after_like'))}",
            f"页面等待：收藏后={format_wait(waits.get('after_favorite'))}",
            f"页面等待：评论输入框预点击后={format_wait(waits.get('comment_pre_input_click'))}",
            f"页面等待：评论框聚焦后={format_wait(waits.get('comment_focus'))}",
            f"页面等待：评论输入后={format_wait(waits.get('after_comment_input'))}",
            f"页面等待：发送评论前={format_wait(waits.get('before_send_comment'))}",
            f"后端回传：{backend_status}",
            f"resultId={result_id or '-'}",
        ]
    )


def build_search_locators(args: argparse.Namespace) -> LocatorRepository:
    return LocatorRepository(
        {
            "search_button": [
                LocatorSpec(
                    "search_button",
                    "resource-id",
                    "com.ss.android.ugc.aweme:id/2ei",
                ),
                LocatorSpec("search_button", "xpath", args.search_button_xpath),
                LocatorSpec(
                    "search_button",
                    "content-desc",
                    "搜索",
                ),
                LocatorSpec("search_button", "coordinate", x=990, y=164),
            ],
            "search_input": [
                LocatorSpec(
                    "search_input", "resource-id", "com.ss.android.ugc.aweme:id/et_search_kw"
                ),
                LocatorSpec("search_input", "xpath", args.input_xpath),
            ],
            "search_submit_button": [
                LocatorSpec(
                    "search_submit_button",
                    "resource-id",
                    "com.ss.android.ugc.aweme:id/4un",
                ),
                LocatorSpec("search_submit_button", "xpath", args.submit_xpath),
            ],
            "video_tab": [
                LocatorSpec("video_tab", "xpath", args.video_tab_xpath),
                LocatorSpec("video_tab", "coordinate", x=288, y=304),
            ],
            "video_author_name": [
                LocatorSpec(
                    "video_author_name",
                    "resource-id",
                    "com.ss.android.ugc.aweme:id/+j",
                ),
                LocatorSpec("video_author_name", "xpath", args.author_xpath),
            ],
            "like_button": [
                LocatorSpec("like_button", "xpath", args.like_xpath),
            ],
            "favorite_button": [
                LocatorSpec("favorite_button", "xpath", args.favorite_xpath),
            ],
            "comment_button": [
                LocatorSpec("comment_button", "xpath", args.comment_button_xpath),
            ],
            "comment_input": [
                LocatorSpec(
                    "comment_input",
                    "resource-id",
                    "com.ss.android.ugc.aweme:id/ep0",
                ),
                LocatorSpec(
                    "comment_input",
                    "resource-id",
                    "com.ss.android.ugc.aweme:id/eoy",
                ),
                LocatorSpec("comment_input", "xpath", args.comment_input_xpath),
                LocatorSpec(
                    "comment_input",
                    "xpath",
                    '//android.widget.EditText[contains(@text,"期待你的评论")]',
                ),
                LocatorSpec(
                    "comment_input",
                    "class_name",
                    "android.widget.EditText",
                ),
            ],
            "send_comment_button": [
                LocatorSpec(
                    "send_comment_button",
                    "xpath",
                    '//*[@text="发送" or @content-desc="发送"]',
                ),
                LocatorSpec(
                    "send_comment_button",
                    "resource-id",
                    "com.ss.android.ugc.aweme:id/es7",
                ),
                LocatorSpec("send_comment_button", "xpath", args.send_comment_xpath),
                LocatorSpec(
                    "send_comment_button",
                    "resource-id",
                    "com.ss.android.ugc.aweme:id/es6",
                ),
                LocatorSpec(
                    "send_comment_button",
                    "xpath",
                    '//android.widget.TextView[@resource-id="com.ss.android.ugc.aweme:id/es6"]',
                ),
            ],
            "link_copied_close_button": [
                LocatorSpec(
                    "link_copied_close_button",
                    "resource-id",
                    "com.ss.android.ugc.aweme:id/zks",
                ),
                LocatorSpec(
                    "link_copied_close_button",
                    "xpath",
                    args.link_copied_close_xpath,
                ),
            ],
        }
    )


def read_content_desc(element: Any) -> str:
    for attr in ("content-desc", "contentDescription", "name"):
        try:
            value = element.get_attribute(attr)
            if value:
                return str(value)
        except Exception:
            continue
    return ""


def center_y(element: Any) -> float:
    rect = element.rect
    return float(rect["y"]) + float(rect["height"]) / 2


def center_x(element: Any) -> float:
    rect = element.rect
    return float(rect["x"]) + float(rect["width"]) / 2


def nearest_like_desc(author_element: Any, like_elements: list[Any]) -> str:
    if not like_elements:
        return ""
    author_x = center_x(author_element)
    author_y = center_y(author_element)
    nearest = min(
        like_elements,
        key=lambda item: _like_distance_key(
            author_x=author_x,
            author_y=author_y,
            like_x=center_x(item),
            like_y=center_y(item),
        ),
    )
    return read_content_desc(nearest)


def _parse_bounds(bounds: str | None) -> tuple[int, int, int, int] | None:
    if not bounds:
        return None
    match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds)
    if not match:
        return None
    left, top, right, bottom = (int(item) for item in match.groups())
    return left, top, right, bottom


def _bounds_center(bounds: tuple[int, int, int, int]) -> tuple[int, int]:
    left, top, right, bottom = bounds
    return int((left + right) / 2), int((top + bottom) / 2)


def _like_distance_key(
    *,
    author_x: float,
    author_y: float,
    like_x: float,
    like_y: float,
) -> tuple[float, int, float]:
    horizontal_distance = abs(like_x - author_x)
    is_left_of_author = int(like_x < author_x)
    return abs(like_y - author_y), is_left_of_author, horizontal_distance


class PageSourceTapTarget:
    def __init__(self, driver: Any, x: int, y: int) -> None:
        self.driver = driver
        self.x = x
        self.y = y

    def click(self) -> None:
        capabilities = getattr(self.driver, "capabilities", {}) or {}
        udid = str(
            capabilities.get("udid")
            or capabilities.get("deviceUDID")
            or capabilities.get("appium:udid")
            or ""
        ).strip()
        if udid:
            result = subprocess.run(
                ["adb", "-s", udid, "shell", "input", "tap", str(self.x), str(self.y)],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return
        self.driver.execute_script("mobile: clickGesture", {"x": self.x, "y": self.y})


def _collect_matched_author_elements_from_source(
    actions: DouyinActions,
    *,
    target_author: str,
) -> list[tuple[str, bool, str, Any]]:
    try:
        source = str(actions.driver.page_source or "")
    except Exception as exc:  # noqa: BLE001 - caller can continue to the next swipe.
        log_step(f"读取页面 XML 失败，跳过本页作者解析：{type(exc).__name__}: {exc}")
        return []
    try:
        root = ET.fromstring(source)
    except ET.ParseError as exc:
        log_step(f"解析页面 XML 失败，跳过本页作者解析：{exc}")
        return []

    authors: list[tuple[str, tuple[int, int, int, int]]] = []
    likes: list[tuple[str, tuple[int, int, int, int]]] = []
    for node in root.iter():
        attrib = node.attrib
        resource_id = attrib.get("resource-id", "")
        bounds = _parse_bounds(attrib.get("bounds"))
        if not bounds:
            continue
        text = (attrib.get("text") or "").strip()
        content_desc = (attrib.get("content-desc") or "").strip()
        if resource_id == "com.ss.android.ugc.aweme:id/+j" and text:
            authors.append((text, bounds))
        if "喜欢" in content_desc or "鍠滄" in content_desc:
            likes.append((content_desc, bounds))

    matched_items: list[tuple[str, bool, str, Any]] = []
    for text, bounds in authors:
        matched = target_author in text
        if not matched:
            continue
        author_x, author_y = _bounds_center(bounds)
        like_desc = ""
        if likes:
            like_desc = min(
                likes,
                key=lambda item: _like_distance_key(
                    author_x=author_x,
                    author_y=author_y,
                    like_x=_bounds_center(item[1])[0],
                    like_y=_bounds_center(item[1])[1],
                ),
            )[0]
        liked = (
            "已点赞" in like_desc
            or "已点" in like_desc
            or "宸茬偣璧?" in like_desc
            or like_desc.startswith("宸?")
        )
        x, y = _bounds_center(bounds)
        log_step(
            "作者项："
            f"text={text!r}, matched={matched}, liked={liked}, likeDesc={like_desc!r}, "
            f"tap=({x},{y})"
        )
        matched_items.append((text, liked, like_desc, PageSourceTapTarget(actions.driver, x, y)))
    return matched_items


def collect_matched_author_elements(
    actions: DouyinActions,
    *,
    target_author: str,
) -> list[tuple[str, bool, str, Any]]:
    source_items = _collect_matched_author_elements_from_source(
        actions,
        target_author=target_author,
    )
    if source_items:
        return source_items
    return []

    author_elements = actions.driver.find_elements(
        AppiumBy.ID,
        "com.ss.android.ugc.aweme:id/+j",
    )
    like_elements = actions.driver.find_elements(AppiumBy.XPATH, DEFAULT_SEARCH_RESULT_LIKE_XPATH)
    matched_items: list[tuple[str, bool, str, Any]] = []
    for element in author_elements:
        text = (getattr(element, "text", "") or "").strip()
        if not text:
            continue
        like_desc = nearest_like_desc(element, like_elements)
        liked = "已点赞" in like_desc or like_desc.startswith("已")
        matched = target_author in text
        log_step(
            "作者项："
            f"text={text!r}, matched={matched}, liked={liked}, likeDesc={like_desc!r}"
        )
        if matched:
            matched_items.append((text, liked, like_desc, element))
    return matched_items
