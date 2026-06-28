from app.config import Settings


def test_settings_load_from_env_file() -> None:
    settings = Settings()

    assert settings.api_base_url == "http://127.0.0.1:8000/api"
    assert settings.appium_server_url == "http://127.0.0.1:4723"
    assert settings.poll_interval_seconds == 3
    assert settings.max_workers == 8
    assert settings.adb_path == "adb"
    assert settings.douyin_app_path == ""
    assert settings.douyin_package_name == "com.ss.android.ugc.aweme"
    assert settings.douyin_app_activity == ".splash.SplashActivity"
    assert settings.force_name_search_not_found is False


def test_settings_load_force_name_search_not_found_from_env(monkeypatch) -> None:
    monkeypatch.setenv("FORCE_NAME_SEARCH_NOT_FOUND", "true")

    settings = Settings()

    assert settings.force_name_search_not_found is True
