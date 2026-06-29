from __future__ import annotations

import argparse
import random
import threading
import time
from datetime import datetime

from app.douyin_actions import LocatorRepository, LocatorSpec
from app.logger import append_current_device_log, format_log_step


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


def build_search_locators(args: argparse.Namespace) -> LocatorRepository:
    locators = {
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

    return LocatorRepository(locators)
