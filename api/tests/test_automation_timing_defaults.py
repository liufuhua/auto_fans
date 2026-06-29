from app.services.automation_timing import (
    DEFAULT_TIMING_SETTINGS,
    DEPRECATED_TIMING_KEYS,
)


def test_default_timing_settings_include_runtime_window_and_douyin_exit_reopen_intervals() -> None:
    settings_by_key = {item.key: item for item in DEFAULT_TIMING_SETTINGS}

    assert "runtime_start_hour" not in settings_by_key
    assert "runtime_end_hour" not in settings_by_key
    assert settings_by_key["runtime_start_time"].max_seconds == 8 * 60
    assert settings_by_key["runtime_end_time"].max_seconds == 23 * 60
    assert settings_by_key["douyin_exit_interval"].max_seconds == 20
    assert settings_by_key["douyin_reopen_interval"].max_seconds == 20
    assert "douyin_restart_interval" not in settings_by_key


def test_default_timing_settings_exclude_legacy_search_waits() -> None:
    keys = {item.key for item in DEFAULT_TIMING_SETTINGS}

    assert "before_input" not in keys
    assert "after_input" not in keys
    assert "after_search" not in keys


def test_deprecated_timing_keys_include_legacy_search_waits() -> None:
    assert {"before_input", "after_input", "after_search"} <= DEPRECATED_TIMING_KEYS
    assert "douyin_restart_interval" in DEPRECATED_TIMING_KEYS
