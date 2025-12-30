from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8000
    reload: bool = True

    data_dir: Path = Path("./data")
    downloads_dir: Path = Path("./data/downloads")
    db_path: Path = Path("./data/playgram.sqlite3")

    telegram_api_id: int | None = None
    telegram_api_hash: str | None = None
    telegram_session_path: Path = Path("./data/telegram.session")
    telegram_chat: str | None = None

    sync_limit: int = 200
    sync_read_delay_seconds: float = 0.05  # Задержка между чтением сообщений (защита от rate limit)
    download_delay_seconds: float = 1.0  # Задержка между скачиваниями файлов (для безопасности от rate limiting)
    sync_telegram_enabled: bool = True  # False = skip TG phase, only run local scan


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.downloads_dir.mkdir(parents=True, exist_ok=True)
    settings.telegram_session_path.parent.mkdir(parents=True, exist_ok=True)
    return settings
