from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local", "../.env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "local"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:4173,http://127.0.0.1:4173"

    database_url: str = "sqlite+aiosqlite:///./backend/data/housing.db"
    db_auto_create: bool = True

    data_go_kr_service_key: str = ""
    applyhome_api_base_url: str = "https://api.odcloud.kr/api"
    lh_api_base_url: str = "https://apis.data.go.kr/B552555"
    admin_api_token: str = ""

    document_storage_path: Path = Path("./backend/data/documents")
    pdf_download_enabled: bool = True
    pdf_max_bytes: int = 50 * 1024 * 1024

    collection_lookback_days: int = 30
    collection_future_days: int = 90
    collection_page_size: int = 100
    collection_http_timeout_seconds: float = 20
    collection_max_retries: int = 3

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def has_service_key(self) -> bool:
        return bool(
            self.data_go_kr_service_key
            and not self.data_go_kr_service_key.startswith("replace_with_")
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
