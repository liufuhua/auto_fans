from functools import cached_property

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Douyin Auto API"
    api_prefix: str = "/api"
    environment: str = "local"
    debug: bool = True

    database_url: str = "mysql+pymysql://root:yxylfh9986@127.0.0.1:3306/douyin_auto?charset=utf8mb4"

    jwt_secret_key: str = "change-me-in-local-env"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440

    backend_cors_origins: str = Field(
        default="http://127.0.0.1:5173,http://localhost:5173",
        description="Comma-separated CORS origins.",
    )
    douyin_playwright_profile_dir: str = "runtime/douyin_playwright_profile"
    douyin_playwright_qr_dir: str = "runtime/douyin_login_qr"
    douyin_playwright_headless: bool = False
    douyin_playwright_page_timeout_seconds: int = 45

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug(cls, value):
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "prod", "production"}:
                return False
            if normalized in {"debug", "dev", "development"}:
                return True
        return value

    @cached_property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]


settings = Settings()
