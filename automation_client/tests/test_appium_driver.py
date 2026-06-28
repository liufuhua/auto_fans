import pytest

from app import appium_driver
from app.appium_driver import (
    AppiumDeviceConfig,
    AppiumDriverError,
    AppiumDriverFactory,
    appium_config_from_backend_device,
)
from app.device_manager import BackendDeviceConfig


class FakeDriver:
    def __init__(self) -> None:
        self.quit_called = False

    def quit(self) -> None:
        self.quit_called = True


def test_build_options_contains_required_capabilities() -> None:
    factory = AppiumDriverFactory("http://127.0.0.1:4723")
    options = factory.build_options(
        AppiumDeviceConfig(
            udid="FMR0223830012928",
            system_port=8201,
            device_name="device_01",
            app="/tmp/douyin.apk",
            app_package="com.ss.android.ugc.aweme",
            app_activity=".splash.SplashActivity",
        )
    )

    capabilities = options.to_capabilities()
    assert capabilities["platformName"] == "Android"
    assert capabilities["appium:automationName"] == "UiAutomator2"
    assert capabilities["appium:udid"] == "FMR0223830012928"
    assert capabilities["appium:deviceName"] == "device_01"
    assert capabilities["appium:systemPort"] == 8201
    assert capabilities["appium:noReset"] is True
    assert capabilities["appium:app"] == "/tmp/douyin.apk"
    assert capabilities["appium:appPackage"] == "com.ss.android.ugc.aweme"
    assert capabilities["appium:appActivity"] == ".splash.SplashActivity"
    assert capabilities["appium:uiautomator2ServerLaunchTimeout"] == 120000
    assert capabilities["appium:uiautomator2ServerInstallTimeout"] == 120000
    assert capabilities["appium:uiautomator2ServerReadTimeout"] == 120000
    assert capabilities["appium:adbExecTimeout"] == 120000
    assert capabilities["appium:skipServerInstallation"] is True
    assert capabilities["appium:skipDeviceInitialization"] is True


def test_create_driver_retries_and_returns_managed_driver(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0
    fake_driver = FakeDriver()

    def fake_remote(command_executor, options):
        nonlocal calls
        calls += 1
        assert command_executor == "http://127.0.0.1:4723"
        assert options.to_capabilities()["appium:systemPort"] == 8201
        if calls == 1:
            raise RuntimeError("temporary appium error")
        return fake_driver

    monkeypatch.setattr(appium_driver.webdriver, "Remote", fake_remote)
    monkeypatch.setattr(appium_driver.time, "sleep", lambda _seconds: None)

    factory = AppiumDriverFactory("http://127.0.0.1:4723", retries=1)
    managed = factory.create(
        AppiumDeviceConfig(
            udid="FMR0223830012928",
            system_port=8201,
            device_name="device_01",
        )
    )

    assert calls == 2
    assert managed.driver is fake_driver
    managed.quit()
    assert fake_driver.quit_called is True


def test_create_driver_prewarms_appium_settings_before_remote(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str, list[str]]] = []
    fake_driver = FakeDriver()

    def fake_run(command, **_kwargs):
        calls.append(tuple(command))

        class FakeCompleted:
            stdout = "isForeground=true"

        return FakeCompleted()

    def fake_remote(command_executor, options):
        assert command_executor == "http://127.0.0.1:4723"
        return fake_driver

    monkeypatch.setattr(appium_driver.subprocess, "run", fake_run)
    monkeypatch.setattr(appium_driver.webdriver, "Remote", fake_remote)
    monkeypatch.setattr(appium_driver.time, "sleep", lambda _seconds: None)

    factory = AppiumDriverFactory("http://127.0.0.1:4723", retries=0)
    managed = factory.create(
        AppiumDeviceConfig(
            udid="R8594XIBXWXWKRVO",
            system_port=8201,
            device_name="vivo",
            prewarm_appium_settings=True,
        )
    )

    assert managed.driver is fake_driver
    assert calls[0] == (
        "adb",
        "-s",
        "R8594XIBXWXWKRVO",
        "shell",
        "am",
        "start",
        "-n",
        "io.appium.settings/.Settings",
    )
    assert calls[1] == (
        "adb",
        "-s",
        "R8594XIBXWXWKRVO",
        "shell",
        "dumpsys",
        "activity",
        "services",
        "io.appium.settings",
    )


def test_create_driver_uses_device_appium_server_url(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_driver = FakeDriver()

    def fake_remote(command_executor, options):
        assert command_executor == "http://127.0.0.1:4726"
        assert options.to_capabilities()["appium:systemPort"] == 8022
        return fake_driver

    monkeypatch.setattr(appium_driver.webdriver, "Remote", fake_remote)

    factory = AppiumDriverFactory("http://127.0.0.1:4723", retries=0)
    managed = factory.create(
        AppiumDeviceConfig(
            udid="MYQUT19C03003871",
            system_port=8022,
            device_name="multi_device_01",
            appium_server_url="http://127.0.0.1:4726",
        )
    )

    assert managed.driver is fake_driver


def test_create_driver_raises_after_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_remote(command_executor, options):
        raise RuntimeError("appium unavailable")

    monkeypatch.setattr(appium_driver.webdriver, "Remote", fake_remote)
    monkeypatch.setattr(appium_driver.time, "sleep", lambda _seconds: None)

    factory = AppiumDriverFactory("http://127.0.0.1:4723", retries=1)

    with pytest.raises(AppiumDriverError):
        factory.create(
            AppiumDeviceConfig(
                udid="FMR0223830012928",
                system_port=8201,
                device_name="device_01",
            )
        )


def test_appium_config_from_backend_device() -> None:
    config = appium_config_from_backend_device(
        BackendDeviceConfig(
            id=1,
            name="device_01",
            udid="FMR0223830012928",
            system_port=8201,
            enabled_status="enabled",
            appium_server_url="http://127.0.0.1:4726",
        )
    )

    assert config.udid == "FMR0223830012928"
    assert config.system_port == 8201
    assert config.device_name == "device_01"
    assert config.appium_server_url == "http://127.0.0.1:4726"
