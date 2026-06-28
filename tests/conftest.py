from __future__ import annotations

import pytest

from douyin_auto.config import load_config


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--config",
        action="store",
        default="config/local.yaml",
        help="Path to Douyin Appium test config.",
    )


@pytest.fixture(scope="session")
def test_config(pytestconfig: pytest.Config):
    return load_config(pytestconfig.getoption("--config"))


@pytest.fixture(scope="session")
def driver(test_config):
    pytest.importorskip("appium", reason="Appium-Python-Client is not installed")
    from douyin_auto.driver_factory import create_driver

    if not test_config.app_package and not test_config.app_path:
        pytest.skip("Set app_package/app_activity or app_path in config/local.yaml")

    app_driver = create_driver(test_config)
    yield app_driver
    app_driver.quit()
