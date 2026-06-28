from __future__ import annotations

from appium import webdriver
from appium.options.android import UiAutomator2Options

from .config import TestConfig


def create_driver(config: TestConfig) -> webdriver.Remote:
    options = UiAutomator2Options().load_capabilities(config.capabilities)
    driver = webdriver.Remote(command_executor=config.server_url, options=options)
    driver.implicitly_wait(config.implicit_wait_seconds)
    return driver
