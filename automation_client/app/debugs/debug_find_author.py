from __future__ import annotations

import argparse
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.appium_driver import AppiumDeviceConfig, AppiumDriverFactory
from app.config import settings
from app.douyin_actions import DouyinActions, LocatorRepository, LocatorSpec
from app.logger import configure_logging
from appium.webdriver.common.appiumby import AppiumBy

DEFAULT_AUTHOR_XPATH = '//android.widget.TextView[@resource-id="com.ss.android.ugc.aweme:id/+j"]'
DEFAULT_LIKE_XPATH = (
    '//android.widget.LinearLayout[contains(@content-desc,"喜欢") '
    'and contains(@content-desc,"按钮")]'
)


@dataclass(frozen=True)
class SearchResultAuthor:
    text: str
    liked: bool
    like_desc: str
    element: Any


def log_step(message: str) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Debug finding a target author on current Douyin search result page."
    )
    parser.add_argument("--udid", required=True)
    parser.add_argument("--device-name", default="device_03")
    parser.add_argument("--system-port", type=int, default=8203)
    parser.add_argument("--target-author", default="张明山")
    parser.add_argument("--max-swipes", type=int, default=2)
    parser.add_argument("--swipe-percent", type=float, default=0.45)
    parser.add_argument("--after-swipe-seconds", type=float, default=2)
    parser.add_argument("--scan-only", action="store_true")
    parser.add_argument("--open-liked", action="store_true")
    parser.add_argument("--wait-timeout-seconds", type=int, default=8)
    parser.add_argument("--quit-timeout-seconds", type=int, default=5)
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


def build_locators() -> LocatorRepository:
    return LocatorRepository(
        {
            "video_author_name": [
                LocatorSpec(
                    "video_author_name",
                    "resource-id",
                    "com.ss.android.ugc.aweme:id/+j",
                ),
                LocatorSpec("video_author_name", "xpath", DEFAULT_AUTHOR_XPATH),
            ],
            "search_result_like": [
                LocatorSpec("search_result_like", "xpath", DEFAULT_LIKE_XPATH),
            ],
        }
    )


def quit_with_timeout(driver: Any, timeout_seconds: int) -> None:
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


def read_element_text(element: Any) -> str:
    return (getattr(element, "text", "") or "").strip()


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


def nearest_like_desc(author_element: Any, like_elements: list[Any]) -> str:
    if not like_elements:
        return ""
    author_y = center_y(author_element)
    nearest = min(like_elements, key=lambda item: abs(center_y(item) - author_y))
    return read_content_desc(nearest)


def collect_authors(driver: Any, target_author: str) -> list[SearchResultAuthor]:
    author_elements = driver.find_elements(AppiumBy.ID, "com.ss.android.ugc.aweme:id/+j")
    like_elements = driver.find_elements(AppiumBy.XPATH, DEFAULT_LIKE_XPATH)
    results: list[SearchResultAuthor] = []
    for element in author_elements:
        text = read_element_text(element)
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
            results.append(
                SearchResultAuthor(
                    text=text,
                    liked=liked,
                    like_desc=like_desc,
                    element=element,
                )
            )
    return results


def find_and_optionally_open_author(
    actions: DouyinActions,
    *,
    target_author: str,
    max_swipes: int,
    swipe_percent: float,
    after_swipe_seconds: float,
    scan_only: bool,
    open_liked: bool,
) -> SearchResultAuthor | None:
    for attempt in range(max_swipes + 1):
        log_step(f"扫描搜索结果：第 {attempt + 1} 次")
        visible_authors = actions.get_texts("video_author_name")
        log_step(f"当前可见作者文本：{visible_authors}")

        matched_authors = collect_authors(actions.driver, target_author)
        for item in matched_authors:
            if item.liked and not open_liked:
                log_step(f"跳过已点赞视频：{item.text}，likeDesc={item.like_desc!r}")
                continue
            if scan_only:
                log_step(f"命中可打开视频，但当前是 scan-only：{item.text}")
                return item
            log_step(f"打开未点赞命中视频：{item.text}，likeDesc={item.like_desc!r}")
            item.element.click()
            return item

        if attempt >= max_swipes:
            break

        log_step(f"当前页没有可打开的未点赞命中视频，向上滑动 percent={swipe_percent}")
        actions.swipe_up(percent=swipe_percent)
        log_step(f"滑动后等待：{after_swipe_seconds:.2f}s")
        time.sleep(after_swipe_seconds)
    return None


def main() -> None:
    args = parse_args()
    configure_logging(debug=args.debug)

    log_step("搜索结果作者查找单项测试启动")
    log_step(
        f"设备：udid={args.udid}, deviceName={args.device_name}, systemPort={args.system_port}"
    )
    log_step(
        f"目标作者：{args.target_author}, maxSwipes={args.max_swipes}, "
        f"swipePercent={args.swipe_percent}, scanOnly={args.scan_only}"
    )

    device = AppiumDeviceConfig(
        udid=args.udid,
        system_port=args.system_port,
        device_name=args.device_name,
        app_package=settings.douyin_package_name,
        app_activity=settings.douyin_app_activity,
    )
    log_step("创建 Appium driver")
    managed_driver = AppiumDriverFactory(settings.appium_server_url, retries=1).create(device)
    log_step("Appium driver 创建成功")
    try:
        actions = DouyinActions(
            driver=managed_driver.driver,
            locators=build_locators(),
            udid=args.udid,
            package_name=settings.douyin_package_name,
            wait_timeout_seconds=args.wait_timeout_seconds,
            task_id="debug_find_author",
        )
        matched = find_and_optionally_open_author(
            actions,
            target_author=args.target_author,
            max_swipes=args.max_swipes,
            swipe_percent=args.swipe_percent,
            after_swipe_seconds=args.after_swipe_seconds,
            scan_only=args.scan_only,
            open_liked=args.open_liked,
        )
        if matched is None:
            log_step("没有找到可打开的未点赞命中视频")
        else:
            log_step(
                "测试完成："
                f"text={matched.text!r}, liked={matched.liked}, likeDesc={matched.like_desc!r}"
            )
    finally:
        quit_with_timeout(managed_driver.driver, args.quit_timeout_seconds)


if __name__ == "__main__":
    main()
