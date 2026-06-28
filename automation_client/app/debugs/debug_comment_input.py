from __future__ import annotations

import argparse
import random
import threading
import time
from datetime import datetime
from pathlib import Path

from app.appium_driver import AppiumDeviceConfig, AppiumDriverFactory
from app.config import settings
from app.douyin_actions import DouyinActions, LocatorRepository, LocatorSpec
from app.logger import configure_logging, sanitize_filename

DEFAULT_COMMENT_BUTTON_XPATH = (
    '//android.widget.ImageView[contains(@content-desc,"评论") and contains(@content-desc,"按钮")]'
)
DEFAULT_COMMENT_INPUT_ID = "com.ss.android.ugc.aweme:id/ep0"
DEFAULT_SEND_COMMENT_ID = "com.ss.android.ugc.aweme:id/es7"


def log_step(message: str) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Only test inputting text into Douyin comment box."
    )
    parser.add_argument("--udid", required=True)
    parser.add_argument("--device-name", default="device_03")
    parser.add_argument("--system-port", type=int, default=8203)
    parser.add_argument("--text", default="测试评论输入")
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--skip-click-comment", action="store_true")
    parser.add_argument("--comment-button-xpath", default=DEFAULT_COMMENT_BUTTON_XPATH)
    parser.add_argument("--comment-input-id", default=DEFAULT_COMMENT_INPUT_ID)
    parser.add_argument("--send-comment-id", default=DEFAULT_SEND_COMMENT_ID)
    parser.add_argument("--pre-input-click-min-seconds", type=float, default=2)
    parser.add_argument("--pre-input-click-max-seconds", type=float, default=5)
    parser.add_argument("--focus-wait-seconds", type=float, default=3)
    parser.add_argument("--after-input-wait-seconds", type=float, default=3)
    parser.add_argument("--before-send-min-seconds", type=float, default=1)
    parser.add_argument("--before-send-max-seconds", type=float, default=3)
    parser.add_argument("--package-name", default=settings.douyin_package_name)
    parser.add_argument("--app-activity", default=settings.douyin_app_activity)
    parser.add_argument("--app", default=settings.douyin_app_path)
    parser.add_argument("--wait-timeout-seconds", type=int, default=12)
    parser.add_argument("--quit-timeout-seconds", type=int, default=5)
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


def quit_with_timeout(driver, timeout_seconds: int) -> None:
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


def build_locators(args: argparse.Namespace) -> LocatorRepository:
    return LocatorRepository(
        {
            "comment_button": [
                LocatorSpec("comment_button", "xpath", args.comment_button_xpath),
            ],
            "comment_input": [
                LocatorSpec(
                    "comment_input",
                    "resource-id",
                    args.comment_input_id,
                ),
                LocatorSpec(
                    "comment_input",
                    "resource-id",
                    "com.ss.android.ugc.aweme:id/eoy",
                ),
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
                    args.send_comment_id,
                ),
                LocatorSpec(
                    "send_comment_button",
                    "resource-id",
                    "com.ss.android.ugc.aweme:id/es6",
                ),
            ],
        }
    )


def save_debug_screenshot(driver, udid: str) -> str:
    screenshot_dir = Path("runtime/screenshots")
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = screenshot_dir / f"{sanitize_filename(udid)}_comment_input_{timestamp}.png"
    driver.save_screenshot(str(path))
    return str(path)


def main() -> None:
    args = parse_args()
    configure_logging(debug=args.debug)
    app_path = str(Path(args.app).resolve()) if args.app else None

    log_step("评论输入框单项测试启动")
    log_step(
        f"设备：udid={args.udid}, deviceName={args.device_name}, systemPort={args.system_port}"
    )
    log_step(f"测试文字：{args.text}")
    device = AppiumDeviceConfig(
        udid=args.udid,
        system_port=args.system_port,
        device_name=args.device_name,
        app=app_path,
        app_package=args.package_name,
        app_activity=args.app_activity,
    )
    log_step("创建 Appium driver")
    managed_driver = AppiumDriverFactory(settings.appium_server_url, retries=1).create(device)
    log_step("Appium driver 创建成功")
    try:
        actions = DouyinActions(
            driver=managed_driver.driver,
            locators=build_locators(args),
            udid=args.udid,
            package_name=args.package_name,
            wait_timeout_seconds=args.wait_timeout_seconds,
            task_id="debug_comment_input",
        )
        log_step("预点击评论输入框")
        input_element = actions._wait_visible("comment_input")
        input_element.click()
        wait_seconds = random.uniform(
            args.pre_input_click_min_seconds,
            args.pre_input_click_max_seconds,
        )
        log_step(f"预点击后等待：{wait_seconds:.2f}s")
        time.sleep(wait_seconds)
        actions.input_comment_text_only(
            args.text,
            focus_wait_seconds=args.focus_wait_seconds,
            after_input_wait_seconds=args.after_input_wait_seconds,
            click_comment_button=not args.skip_click_comment,
        )
        input_element = actions._wait_visible("comment_input")
        current_text = actions._read_element_text(input_element)
        screenshot_path = save_debug_screenshot(managed_driver.driver, args.udid)
        log_step(f"输入框当前文本：{current_text!r}")
        log_step(f"输入后截图已保存：{screenshot_path}")
        if args.send:
            wait_seconds = random.uniform(
                args.before_send_min_seconds,
                args.before_send_max_seconds,
            )
            log_step(f"发送前等待：{wait_seconds:.2f}s")
            time.sleep(wait_seconds)
            log_step("开始点击发送按钮")
            actions._click("send_comment_button")
            after_send_screenshot = save_debug_screenshot(managed_driver.driver, args.udid)
            log_step(f"发送后截图已保存：{after_send_screenshot}")
            log_step("评论输入并发送单项测试成功")
        else:
            log_step("评论输入框单项测试成功，未发送")
    finally:
        quit_with_timeout(managed_driver.driver, args.quit_timeout_seconds)


if __name__ == "__main__":
    main()
