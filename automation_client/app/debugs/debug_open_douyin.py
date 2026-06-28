from __future__ import annotations

import argparse
import threading
import time
from pathlib import Path

from app.appium_driver import AppiumDeviceConfig, AppiumDriverFactory
from app.config import settings
from app.douyin_actions import DouyinActions, LocatorRepository
from app.logger import configure_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Open Douyin on a connected Android device.")
    parser.add_argument("--udid", required=True, help="ADB UDID, for example FMR0223830012928")
    parser.add_argument("--device-name", default="device_01", help="Device name used in logs")
    parser.add_argument("--system-port", type=int, default=8201, help="UiAutomator2 systemPort")
    parser.add_argument(
        "--package-name",
        default=settings.douyin_package_name,
        help="Douyin package name",
    )
    parser.add_argument(
        "--app",
        default=settings.douyin_app_path,
        help="Optional APK path. Leave empty to launch the installed app by package/activity.",
    )
    parser.add_argument(
        "--app-activity",
        default=settings.douyin_app_activity,
        help="Douyin launch activity",
    )
    parser.add_argument(
        "--keep-seconds",
        type=int,
        default=5,
        help="Seconds to keep the Appium session before quitting",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logs")
    parser.add_argument(
        "--quit-timeout-seconds",
        type=int,
        default=5,
        help="Seconds to wait for Appium session quit before exiting",
    )
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


def main() -> None:
    args = parse_args()
    configure_logging(debug=args.debug)

    factory = AppiumDriverFactory(settings.appium_server_url, retries=1)
    app_path = str(Path(args.app).resolve()) if args.app else None
    device = AppiumDeviceConfig(
        udid=args.udid,
        system_port=args.system_port,
        device_name=args.device_name,
        app=app_path,
        app_package=args.package_name,
        app_activity=args.app_activity,
    )

    managed_driver = factory.create(device)
    try:
        actions = DouyinActions(
            driver=managed_driver.driver,
            locators=LocatorRepository({}),
            udid=args.udid,
            package_name=args.package_name,
            task_id="debug",
        )
        actions.open_douyin()
        print(f"opened douyin: udid={args.udid}, package={args.package_name}")
        time.sleep(args.keep_seconds)
    finally:
        quit_with_timeout(managed_driver.driver, args.quit_timeout_seconds)


if __name__ == "__main__":
    main()
