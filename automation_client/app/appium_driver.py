from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from typing import Protocol

from appium import webdriver
from appium.options.android import UiAutomator2Options

from app.device_manager import BackendDeviceConfig


class AppiumDriverError(RuntimeError):
    pass


class QuitableDriver(Protocol):
    def quit(self) -> None:
        pass


@dataclass(frozen=True)
class AppiumDeviceConfig:
    udid: str
    system_port: int
    device_name: str
    appium_server_url: str | None = None
    platform_name: str = "Android"
    automation_name: str = "UiAutomator2"
    no_reset: bool = True
    app: str | None = None
    app_package: str | None = None
    app_activity: str | None = None
    uiautomator2_server_launch_timeout_ms: int = 120000
    uiautomator2_server_install_timeout_ms: int = 120000
    uiautomator2_server_read_timeout_ms: int = 120000
    adb_exec_timeout_ms: int = 120000
    new_command_timeout_seconds: int = 3600
    skip_server_installation: bool = True
    skip_device_initialization: bool = True
    prewarm_appium_settings: bool = False
    appium_settings_wait_seconds: float = 3.0


@dataclass
class ManagedAppiumDriver:
    device: AppiumDeviceConfig
    driver: QuitableDriver

    def quit(self) -> None:
        self.driver.quit()

    def __enter__(self) -> ManagedAppiumDriver:
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.quit()


class AppiumDriverFactory:
    """Creates Appium drivers for Android devices."""

    def __init__(
        self,
        server_url: str,
        retries: int = 2,
        retry_interval_seconds: float = 1.0,
    ) -> None:
        self.server_url = server_url
        self.retries = retries
        self.retry_interval_seconds = retry_interval_seconds

    def create(self, device: AppiumDeviceConfig) -> ManagedAppiumDriver:
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 2):
            try:
                self._prewarm_appium_settings(device)
                server_url = device.appium_server_url or self.server_url
                driver = webdriver.Remote(
                    command_executor=server_url,
                    options=self.build_options(device),
                )
                return ManagedAppiumDriver(device=device, driver=driver)
            except Exception as exc:  # noqa: BLE001 - Appium may raise several transport errors.
                last_error = exc
                if attempt > self.retries:
                    break
                time.sleep(self._retry_interval_after_error(exc))

        raise AppiumDriverError(
            f"Failed to create Appium driver for {device.udid}: {last_error}"
        ) from last_error

    def build_options(self, device: AppiumDeviceConfig) -> UiAutomator2Options:
        options = UiAutomator2Options()
        options.set_capability("platformName", device.platform_name)
        options.set_capability("appium:automationName", device.automation_name)
        options.set_capability("appium:udid", device.udid)
        options.set_capability("appium:deviceName", device.device_name)
        options.set_capability("appium:systemPort", device.system_port)
        options.set_capability("appium:noReset", device.no_reset)
        if device.app:
            options.set_capability("appium:app", device.app)
        if device.app_package:
            options.set_capability("appium:appPackage", device.app_package)
        if device.app_activity:
            options.set_capability("appium:appActivity", device.app_activity)
        options.set_capability(
            "appium:uiautomator2ServerLaunchTimeout",
            device.uiautomator2_server_launch_timeout_ms,
        )
        options.set_capability(
            "appium:uiautomator2ServerInstallTimeout",
            device.uiautomator2_server_install_timeout_ms,
        )
        options.set_capability(
            "appium:uiautomator2ServerReadTimeout",
            device.uiautomator2_server_read_timeout_ms,
        )
        options.set_capability("appium:adbExecTimeout", device.adb_exec_timeout_ms)
        options.set_capability("appium:newCommandTimeout", device.new_command_timeout_seconds)
        options.set_capability("appium:skipServerInstallation", device.skip_server_installation)
        options.set_capability("appium:skipDeviceInitialization", device.skip_device_initialization)
        return options

    def _prewarm_appium_settings(self, device: AppiumDeviceConfig) -> None:
        if not device.prewarm_appium_settings:
            return
        try:
            subprocess.run(
                [
                    "adb",
                    "-s",
                    device.udid,
                    "shell",
                    "am",
                    "start",
                    "-n",
                    "io.appium.settings/.Settings",
                ],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
            deadline = time.monotonic() + device.appium_settings_wait_seconds
            while time.monotonic() < deadline:
                result = subprocess.run(
                    [
                        "adb",
                        "-s",
                        device.udid,
                        "shell",
                        "dumpsys",
                        "activity",
                        "services",
                        "io.appium.settings",
                    ],
                    check=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    timeout=10,
                )
                if "isForeground=true" in (result.stdout or ""):
                    return
                time.sleep(0.5)
        except Exception:
            return

    def _retry_interval_after_error(self, exc: Exception) -> float:
        if "Appium Settings app is not running after 5000ms" in str(exc):
            return max(self.retry_interval_seconds, 5.0)
        return self.retry_interval_seconds


def quit_driver(driver: QuitableDriver | None) -> None:
    if driver is not None:
        driver.quit()


def appium_config_from_backend_device(device: BackendDeviceConfig) -> AppiumDeviceConfig:
    return AppiumDeviceConfig(
        udid=device.udid,
        system_port=device.system_port,
        device_name=device.name,
        appium_server_url=device.appium_server_url,
    )
