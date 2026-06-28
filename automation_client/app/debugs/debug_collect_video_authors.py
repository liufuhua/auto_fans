from __future__ import annotations

import argparse
import json
import threading
from pathlib import Path

from app.appium_driver import AppiumDeviceConfig, AppiumDriverFactory
from app.config import settings
from app.douyin_actions import DouyinActions, LocatorRepository, LocatorSpec
from app.logger import configure_logging

DEFAULT_AUTHOR_XPATH = '//android.widget.TextView[@resource-id="com.ss.android.ugc.aweme:id/+j"]'


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect visible Douyin video author names.")
    parser.add_argument("--udid", required=True)
    parser.add_argument("--device-name", default="device_01")
    parser.add_argument("--system-port", type=int, default=8201)
    parser.add_argument("--limit", type=int, default=4)
    parser.add_argument("--xpath", default=DEFAULT_AUTHOR_XPATH)
    parser.add_argument("--package-name", default=settings.douyin_package_name)
    parser.add_argument("--app-activity", default=settings.douyin_app_activity)
    parser.add_argument("--app", default=settings.douyin_app_path)
    parser.add_argument("--wait-timeout-seconds", type=int, default=8)
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
        print(f"warning: driver.quit() timed out after {timeout_seconds}s; exiting")


def build_locators(args: argparse.Namespace) -> LocatorRepository:
    return LocatorRepository(
        {
            "video_author_name": [
                LocatorSpec("video_author_name", "resource-id", "com.ss.android.ugc.aweme:id/+j"),
                LocatorSpec("video_author_name", "xpath", args.xpath),
            ]
        }
    )


def main() -> None:
    args = parse_args()
    configure_logging(debug=args.debug)

    app_path = str(Path(args.app).resolve()) if args.app else None
    device = AppiumDeviceConfig(
        udid=args.udid,
        system_port=args.system_port,
        device_name=args.device_name,
        app=app_path,
        app_package=args.package_name,
        app_activity=args.app_activity,
    )
    managed_driver = AppiumDriverFactory(settings.appium_server_url, retries=1).create(device)
    try:
        actions = DouyinActions(
            driver=managed_driver.driver,
            locators=build_locators(args),
            udid=args.udid,
            package_name=args.package_name,
            wait_timeout_seconds=args.wait_timeout_seconds,
            task_id="debug_collect_video_authors",
        )
        authors = actions.get_texts("video_author_name", limit=args.limit)
        print(json.dumps({"authors": authors}, ensure_ascii=False, indent=2))
    finally:
        quit_with_timeout(managed_driver.driver, args.quit_timeout_seconds)


if __name__ == "__main__":
    main()
