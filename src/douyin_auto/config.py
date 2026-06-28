from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class PageEntry:
    deep_link: str = ""
    tap_text: str = ""


@dataclass
class PageSpec:
    name: str
    entry: PageEntry = field(default_factory=PageEntry)
    expected_texts: list[str] = field(default_factory=list)
    forbidden_texts: list[str] = field(default_factory=list)
    screenshot: bool = True


@dataclass
class TestConfig:
    server_url: str = "http://127.0.0.1:4723/wd/hub"
    platform_name: str = "Android"
    automation_name: str = "UiAutomator2"
    device_name: str = "Android"
    platform_version: str = ""
    app_package: str = ""
    app_activity: str = ""
    app_path: str = ""
    no_reset: bool = True
    new_command_timeout: int = 180
    implicit_wait_seconds: int = 3
    launch_timeout_seconds: int = 30
    pages: list[PageSpec] = field(default_factory=list)

    @property
    def capabilities(self) -> dict[str, Any]:
        caps: dict[str, Any] = {
            "platformName": self.platform_name,
            "appium:automationName": self.automation_name,
            "appium:deviceName": self.device_name,
            "appium:noReset": self.no_reset,
            "appium:newCommandTimeout": self.new_command_timeout,
        }
        if self.platform_version:
            caps["appium:platformVersion"] = self.platform_version
        if self.app_path:
            caps["appium:app"] = str(Path(self.app_path).expanduser())
        if self.app_package:
            caps["appium:appPackage"] = self.app_package
        if self.app_activity:
            caps["appium:appActivity"] = self.app_activity
        return caps


def _page_from_dict(raw: dict[str, Any]) -> PageSpec:
    entry_raw = raw.get("entry") or {}
    return PageSpec(
        name=str(raw["name"]),
        entry=PageEntry(
            deep_link=str(entry_raw.get("deep_link") or ""),
            tap_text=str(entry_raw.get("tap_text") or ""),
        ),
        expected_texts=[str(item) for item in raw.get("expected_texts", [])],
        forbidden_texts=[str(item) for item in raw.get("forbidden_texts", [])],
        screenshot=bool(raw.get("screenshot", True)),
    )


def load_config(path: str | os.PathLike[str] | None) -> TestConfig:
    data: dict[str, Any] = {}
    if path:
        config_path = Path(path).expanduser()
        if config_path.exists():
            data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

    config = TestConfig(
        server_url=str(os.getenv("APPIUM_SERVER_URL", data.get("server_url", TestConfig.server_url))),
        platform_name=str(data.get("platform_name", TestConfig.platform_name)),
        automation_name=str(data.get("automation_name", TestConfig.automation_name)),
        device_name=str(os.getenv("DEVICE_NAME", data.get("device_name", TestConfig.device_name))),
        platform_version=str(os.getenv("PLATFORM_VERSION", data.get("platform_version", ""))),
        app_package=str(os.getenv("DOUYIN_APP_PACKAGE", data.get("app_package", ""))),
        app_activity=str(os.getenv("DOUYIN_APP_ACTIVITY", data.get("app_activity", ""))),
        app_path=str(os.getenv("DOUYIN_APP_PATH", data.get("app_path", ""))),
        no_reset=bool(data.get("no_reset", True)),
        new_command_timeout=int(data.get("new_command_timeout", 180)),
        implicit_wait_seconds=int(data.get("implicit_wait_seconds", 3)),
        launch_timeout_seconds=int(data.get("launch_timeout_seconds", 30)),
        pages=[_page_from_dict(item) for item in data.get("pages", [])],
    )
    return config
