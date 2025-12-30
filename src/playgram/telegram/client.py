from __future__ import annotations

from telethon import TelegramClient, connection

from playgram.settings import get_settings


def build_client() -> TelegramClient:
    settings = get_settings()
    if not settings.telegram_api_id or not settings.telegram_api_hash:
        raise RuntimeError(
            "Telegram is not configured. Set TELEGRAM_API_ID and TELEGRAM_API_HASH in .env (see .env.example)."
        )
    return TelegramClient(
        str(settings.telegram_session_path),
        settings.telegram_api_id,
        settings.telegram_api_hash,
        connection=connection.ConnectionTcpObfuscated
    )
