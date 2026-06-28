from __future__ import annotations

import pytest


def pytest_generate_tests(metafunc):
    if "page_spec" not in metafunc.fixturenames:
        return
    config = metafunc.config
    from douyin_auto.config import load_config

    test_config = load_config(config.getoption("--config"))
    ids = [page.name for page in test_config.pages]
    metafunc.parametrize("page_spec", test_config.pages, ids=ids)


@pytest.mark.appium
@pytest.mark.page_spec
def test_page_matches_spec(driver, test_config, page_spec):
    pytest.importorskip("appium", reason="Appium-Python-Client is not installed")
    from douyin_auto.ui import assert_page_spec

    assert_page_spec(driver, test_config, page_spec)
