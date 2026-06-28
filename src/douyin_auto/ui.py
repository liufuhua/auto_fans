from __future__ import annotations

from pathlib import Path
from time import sleep

from appium.webdriver.webdriver import WebDriver
from appium.webdriver.common.appiumby import AppiumBy
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait

from .config import PageSpec, TestConfig


def text_selector(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'new UiSelector().textContains("{escaped}")'


def find_text(driver: WebDriver, text: str):
    return driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, text_selector(text))


def text_exists(driver: WebDriver, text: str, timeout: int = 5) -> bool:
    try:
        WebDriverWait(driver, timeout).until(lambda _: find_text(driver, text))
        return True
    except (NoSuchElementException, TimeoutException):
        return False


def enter_page(driver: WebDriver, config: TestConfig, page: PageSpec) -> None:
    if page.entry.deep_link:
        package = config.app_package or None
        driver.execute_script(
            "mobile: shell",
            {
                "command": "am",
                "args": ["start", "-a", "android.intent.action.VIEW", "-d", page.entry.deep_link, *(["-p", package] if package else [])],
                "timeout": 15000,
            },
        )
        sleep(2)
        return

    if page.entry.tap_text:
        find_text(driver, page.entry.tap_text).click()
        sleep(2)


def assert_page_spec(driver: WebDriver, config: TestConfig, page: PageSpec) -> None:
    enter_page(driver, config, page)

    missing = [text for text in page.expected_texts if not text_exists(driver, text)]
    forbidden = [text for text in page.forbidden_texts if text_exists(driver, text, timeout=1)]

    if page.screenshot:
        screenshot_dir = Path("screenshots")
        screenshot_dir.mkdir(exist_ok=True)
        driver.save_screenshot(str(screenshot_dir / f"{page.name}.png"))

    assert not missing, f"{page.name} missing expected texts: {missing}"
    assert not forbidden, f"{page.name} contains forbidden texts: {forbidden}"
