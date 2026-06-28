from app.services.automation_timing import DEFAULT_TIMING_SETTINGS


def test_default_timing_settings_include_runtime_window_and_restart_interval() -> None:
    settings_by_key = {item.key: item for item in DEFAULT_TIMING_SETTINGS}

    assert "runtime_start_hour" not in settings_by_key
    assert "runtime_end_hour" not in settings_by_key
    assert settings_by_key["runtime_start_time"].max_seconds == 8 * 60
    assert settings_by_key["runtime_end_time"].max_seconds == 23 * 60
    assert settings_by_key["douyin_restart_interval"].max_seconds == 30
