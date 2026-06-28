from __future__ import annotations

import argparse
import time
from pathlib import Path

from app.appium_driver import AppiumDeviceConfig, AppiumDriverFactory
from app.config import settings
from app.douyin_actions import DouyinActions
from app.douyin_page_state import (
    DEFAULT_LINK_COPIED_CLOSE_XPATH,
    DEFAULT_SEARCH_BACK_XPATH,
    DEFAULT_VIDEO_BACK_XPATH,
    build_return_home_locators as build_locators,
    get_page_source,
    has_link_copied_popup,
    has_search_page,
    has_video_back,
    is_home_page,
    press_android_back,
    safe_click,
)
from app.douyin_search_support import log_step, quit_with_timeout
from app.logger import configure_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Return Douyin from comment/video/search page back to home."
    )
    parser.add_argument("--udid", required=True)
    parser.add_argument("--device-name", default="device_03")
    parser.add_argument("--system-port", type=int, default=8203)
    parser.add_argument("--package-name", default=settings.douyin_package_name)
    parser.add_argument("--app-activity", default=settings.douyin_app_activity)
    parser.add_argument("--app", default=settings.douyin_app_path)
    parser.add_argument("--link-copied-close-xpath", default=DEFAULT_LINK_COPIED_CLOSE_XPATH)
    parser.add_argument("--video-back-xpath", default=DEFAULT_VIDEO_BACK_XPATH)
    parser.add_argument("--search-back-xpath", default=DEFAULT_SEARCH_BACK_XPATH)
    parser.add_argument("--wait-timeout-seconds", type=int, default=3)
    parser.add_argument("--step-wait-seconds", type=float, default=1.5)
    parser.add_argument("--max-back-presses", type=int, default=4)
    parser.add_argument("--quit-timeout-seconds", type=int, default=5)
    parser.add_argument("--debug", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging(debug=args.debug)
    app_path = str(Path(args.app).resolve()) if args.app else None

    log_step("回到抖音首页单项测试启动")
    log_step(
        f"设备：udid={args.udid}, deviceName={args.device_name}, systemPort={args.system_port}"
    )

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
        driver = managed_driver.driver
        actions = DouyinActions(
            driver=driver,
            locators=build_locators(args),
            udid=args.udid,
            package_name=args.package_name,
            wait_timeout_seconds=args.wait_timeout_seconds,
            task_id="debug_return_home",
        )

        source = get_page_source(driver)
        if is_home_page(source):
            log_step("当前已经是抖音首页，无需返回")
            return

        # 主流程成功复制链接后会停在“链接已复制成功”弹窗。先关闭弹窗。
        if has_link_copied_popup(source):
            if safe_click(actions, "link_copied_close_button", "关闭链接复制成功弹窗"):
                time.sleep(args.step_wait_seconds)
                source = get_page_source(driver)
                if is_home_page(source):
                    log_step("关闭链接复制成功弹窗后已经回到首页")
                    return

        # 关闭链接复制成功弹窗后通常在视频播放页。再点击左上角返回。
        if has_video_back(source):
            if safe_click(actions, "video_back_button", "退出视频页，返回搜索页"):
                time.sleep(args.step_wait_seconds)
                source = get_page_source(driver)
                if is_home_page(source):
                    log_step("退出视频页后已经回到首页")
                    return

        # 搜索页的左上角返回有时只会回到搜索历史页，所以后面继续用系统返回兜底。
        if has_search_page(source):
            if safe_click(actions, "search_back_button", "退出搜索页"):
                time.sleep(args.step_wait_seconds)
                source = get_page_source(driver)
                if is_home_page(source):
                    log_step("退出搜索页后已经回到首页")
                    return

        for index in range(1, args.max_back_presses + 1):
            if is_home_page(source):
                log_step("已回到抖音首页")
                return
            press_android_back(driver, index)
            time.sleep(args.step_wait_seconds)
            source = get_page_source(driver)

        if is_home_page(source):
            log_step("已回到抖音首页")
            return

        raise RuntimeError("多次返回后仍未识别到抖音首页，请手动观察当前页面")
    finally:
        quit_with_timeout(managed_driver.driver, args.quit_timeout_seconds)


if __name__ == "__main__":
    main()
