from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    api_base_url: str = "http://127.0.0.1:8000/api"
    appium_server_url: str = "http://127.0.0.1:4723"
    poll_interval_seconds: int = 3
    max_workers: int = 8
    adb_path: str = "adb"
    douyin_app_path: str = ""
    douyin_package_name: str = "com.ss.android.ugc.aweme"
    douyin_app_activity: str = ".splash.SplashActivity"
    force_name_search_not_found: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
