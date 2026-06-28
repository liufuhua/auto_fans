from __future__ import annotations

import pytest


@pytest.mark.appium
def test_douyin_app_launches(driver, test_config):
    package = driver.current_package
    if test_config.app_package:
        assert package == test_config.app_package
    assert driver.page_source
