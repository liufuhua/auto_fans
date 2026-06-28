from __future__ import annotations

import subprocess
import time

from app.appium_driver import AppiumDeviceConfig, AppiumDriverFactory
from app.config import settings


UDID = "10AG3R2JNF001KK"
DEVICE_NAME = "device_02"
SYSTEM_PORT = 8202


def log(message: str) -> None:
    print(time.strftime("[%H:%M:%S]"), message, flush=True)


def adb(*args: str) -> None:
    subprocess.run(["adb", "-s", UDID, *args], check=False)


def adb_back() -> None:
    adb("shell", "input", "keyevent", "4")


def adb_screenshot(path: str) -> None:
    with open(path, "wb") as output:
        subprocess.run(["adb", "-s", UDID, "exec-out", "screencap", "-p"], stdout=output, check=False)


def describe_element(element) -> str:
    attrs: dict[str, object] = {}
    for name in ("resourceId", "contentDescription", "text", "className", "clickable", "enabled"):
        try:
            attrs[name] = element.get_attribute(name)
        except Exception as exc:  # noqa: BLE001 - diagnostic output only.
            attrs[name] = f"<{type(exc).__name__}>"
    try:
        attrs["rect"] = element.rect
    except Exception as exc:  # noqa: BLE001 - diagnostic output only.
        attrs["rect"] = f"<{type(exc).__name__}>"
    return ", ".join(f"{key}={value}" for key, value in attrs.items())


def pick_top_right(elements: list[object]) -> object:
    def score(element) -> tuple[float, float]:
        rect = element.rect
        return (float(rect.get("x", 0)) + float(rect.get("width", 0)) / 2, -float(rect.get("y", 0)))

    return sorted(elements, key=score, reverse=True)[0]


def click_by_ratio(driver, *, x_ratio: float, y_ratio: float) -> tuple[int, int, dict[str, int]]:
    size = driver.get_window_size()
    x = int(size["width"] * x_ratio)
    y = int(size["height"] * y_ratio)
    driver.execute_script("mobile: clickGesture", {"x": x, "y": y})
    return x, y, size


def main() -> None:
    factory = AppiumDriverFactory(settings.appium_server_url, retries=0)
    device = AppiumDeviceConfig(
        udid=UDID,
        device_name=DEVICE_NAME,
        system_port=SYSTEM_PORT,
        app_package=settings.douyin_package_name,
        app_activity=settings.douyin_app_activity,
    )
    managed = factory.create(device)
    driver = managed.driver
    try:
        log("driver created")
        try:
            driver.implicitly_wait(0)
            driver.update_settings(
                {
                    "waitForIdleTimeout": 0,
                    "waitForSelectorTimeout": 3000,
                }
            )
            log("uiautomator2 settings updated: waitForIdleTimeout=0 waitForSelectorTimeout=3000")
        except Exception as exc:  # noqa: BLE001 - continue to expose the original behavior if unsupported.
            log(f"uiautomator2 settings update skipped: {type(exc).__name__}: {exc}")
        time.sleep(1)
        log("press back once to close possible left drawer")
        adb_back()
        time.sleep(1)

        started_at = time.monotonic()
        x, y, size = click_by_ratio(driver, x_ratio=0.925, y_ratio=0.082)
        log(
            "ratio search click returned "
            f"after {time.monotonic() - started_at:.2f}s: "
            f"size={size}, x={x}, y={y}, ratio=(0.925, 0.082)"
        )
        time.sleep(2)
        screenshot_path = "/private/tmp/device02_search_click_ratio.png"
        adb_screenshot(screenshot_path)
        log(f"ratio search click screenshot saved: {screenshot_path}")
    finally:
        managed.quit()
        log("driver quit")


if __name__ == "__main__":
    main()
