from __future__ import annotations

import argparse
import multiprocessing as mp
import subprocess
import time
import traceback
from dataclasses import dataclass
from typing import Any

from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.webdriver.common.appiumby import AppiumBy

from app.config import settings


UDID = "10AG3R2JNF001KK"
DEVICE_NAME = "device_02"
SYSTEM_PORT = 8202


@dataclass(frozen=True)
class ProbeCase:
    name: str
    by: str
    value: str


CASES = [
    ProbeCase(
        "search_xpath",
        AppiumBy.XPATH,
        '//android.widget.LinearLayout[@resource-id="com.ss.android.ugc.aweme:id/t6k"]'
        '/android.widget.Button[@content-desc="搜索"]',
    ),
    ProbeCase("sidebar_xpath", AppiumBy.XPATH, '//android.widget.Button[@content-desc="侧边栏"]'),
    ProbeCase("wrong_sidebar_id_2ei", AppiumBy.ID, "com.ss.android.ugc.aweme:id/2ei"),
    ProbeCase("search_accessibility_id", AppiumBy.ACCESSIBILITY_ID, "搜索"),
]

TEXT_CONTAINS_CASES = [
    ProbeCase(
        "text_contains_cao_yingming",
        AppiumBy.ANDROID_UIAUTOMATOR,
        'new UiSelector().textContains("曹迎明")',
    )
]


def log(message: str) -> None:
    print(time.strftime("[%H:%M:%S]"), message, flush=True)


def adb(*args: str) -> None:
    subprocess.run(["adb", "-s", UDID, *args], check=False, stdout=subprocess.DEVNULL)


def clear_session() -> None:
    subprocess.run(
        ["scripts/clear_session.sh", UDID, str(SYSTEM_PORT)],
        cwd="/Users/liu/crewai/android_auto_test/automation_client",
        check=False,
    )


def build_options(profile: str) -> UiAutomator2Options:
    options = UiAutomator2Options()
    options.set_capability("platformName", "Android")
    options.set_capability("appium:automationName", "UiAutomator2")
    options.set_capability("appium:udid", UDID)
    options.set_capability("appium:deviceName", DEVICE_NAME)
    options.set_capability("appium:systemPort", SYSTEM_PORT)
    options.set_capability("appium:noReset", True)
    options.set_capability("appium:newCommandTimeout", 300)
    options.set_capability("appium:uiautomator2ServerLaunchTimeout", 30000)
    options.set_capability("appium:uiautomator2ServerInstallTimeout", 30000)
    options.set_capability("appium:uiautomator2ServerReadTimeout", 30000)
    options.set_capability("appium:adbExecTimeout", 30000)
    options.set_capability("appium:ignoreHiddenApiPolicyError", True)
    options.set_capability("appium:disableWindowAnimation", True)
    options.set_capability("appium:settings[waitForIdleTimeout]", 0)
    options.set_capability("appium:settings[waitForSelectorTimeout]", 3000)

    if profile == "current":
        options.set_capability("appium:appPackage", settings.douyin_package_name)
        options.set_capability("appium:appActivity", settings.douyin_app_activity)
    elif profile == "inspector_like":
        options.set_capability("appium:skipDeviceInitialization", True)
        options.set_capability("appium:skipServerInstallation", True)
        options.set_capability("appium:dontStopAppOnReset", True)
        options.set_capability("appium:autoLaunch", False)
    elif profile == "attach_package":
        options.set_capability("appium:appPackage", settings.douyin_package_name)
        options.set_capability("appium:appActivity", settings.douyin_app_activity)
        options.set_capability("appium:dontStopAppOnReset", True)
        options.set_capability("appium:skipDeviceInitialization", True)
    else:
        raise ValueError(f"unknown profile: {profile}")

    return options


def describe(element: Any) -> dict[str, Any]:
    attrs: dict[str, Any] = {"rect": element.rect}
    for name in ("resourceId", "contentDescription", "text", "className", "clickable", "enabled"):
        try:
            attrs[name] = element.get_attribute(name)
        except Exception as exc:  # noqa: BLE001 - diagnostic only.
            attrs[name] = f"<{type(exc).__name__}>"
    return attrs


def child(profile: str, case: ProbeCase, queue: mp.Queue, *, multiple: bool) -> None:
    driver = None
    started = time.monotonic()
    try:
        driver = webdriver.Remote(
            command_executor=settings.appium_server_url,
            options=build_options(profile),
        )
        created = time.monotonic()
        driver.implicitly_wait(0)
        elements = (
            driver.find_elements(case.by, case.value)
            if multiple
            else [driver.find_element(case.by, case.value)]
        )
        found = time.monotonic()
        queue.put(
            {
                "status": "ok",
                "profile": profile,
                "case": case.name,
                "createSeconds": round(created - started, 2),
                "findSeconds": round(found - created, 2),
                "count": len(elements),
                "elements": [describe(element) for element in elements[:10]],
            }
        )
    except Exception as exc:  # noqa: BLE001 - diagnostic only.
        queue.put(
            {
                "status": "error",
                "profile": profile,
                "case": case.name,
                "seconds": round(time.monotonic() - started, 2),
                "errorType": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(limit=4),
            }
        )
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


def run_one(
    profile: str,
    case: ProbeCase,
    timeout_seconds: int,
    *,
    multiple: bool,
) -> dict[str, Any]:
    queue: mp.Queue = mp.Queue()
    process = mp.Process(target=child, args=(profile, case, queue), kwargs={"multiple": multiple})
    process.start()
    process.join(timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join(5)
        return {
            "status": "timeout",
            "profile": profile,
            "case": case.name,
            "seconds": timeout_seconds,
        }
    if queue.empty():
        return {
            "status": "empty",
            "profile": profile,
            "case": case.name,
            "exitCode": process.exitcode,
        }
    return queue.get()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profiles",
        nargs="+",
        default=["inspector_like", "attach_package", "current"],
    )
    parser.add_argument("--timeout-seconds", type=int, default=45)
    parser.add_argument("--text-contains-cao", action="store_true")
    parser.add_argument("--no-initial-back", action="store_true")
    args = parser.parse_args()

    cases = TEXT_CONTAINS_CASES if args.text_contains_cao else CASES
    if not args.no_initial_back:
        adb("shell", "input", "keyevent", "4")
        time.sleep(1)

    for profile in args.profiles:
        for case in cases:
            log(f"run profile={profile} case={case.name}")
            clear_session()
            result = run_one(
                profile,
                case,
                args.timeout_seconds,
                multiple=args.text_contains_cao,
            )
            log(str(result))
            clear_session()


if __name__ == "__main__":
    mp.set_start_method("spawn")
    main()
