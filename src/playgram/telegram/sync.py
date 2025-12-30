from __future__ import annotations

import asyncio
import random
from pathlib import Path
from typing import Any, Optional

from telethon.tl.types import DocumentAttributeAudio, Message

from playgram.db.library import upsert_track
from playgram.db.sync_jobs import (
    create_job,
    finish_job,
    get_active_job,
    get_job,
    get_last_job,
    update_job_progress,
)
from playgram.library.scanner import scan_local_library
from playgram.settings import get_settings
from playgram.telegram.client import build_client


def _safe_filename(name: str) -> str:
    # Minimal Windows-friendly cleanup
    bad = '<>:\\"/|?*'
    for ch in bad:
        name = name.replace(ch, "_")
    return name.strip() or "audio"


def _audio_attrs(message: Message) -> tuple[str | None, str | None, int | None]:
    doc = getattr(message, "document", None)
    if not doc:
        return None, None, None

    artist: str | None = None
    title: str | None = None
    duration: int | None = None

    for attr in doc.attributes or []:
        if isinstance(attr, DocumentAttributeAudio):
            duration = getattr(attr, "duration", None)
            artist = getattr(attr, "performer", None) or None
            title = getattr(attr, "title", None) or None

    return artist, title, duration


# NOTE: chat search removed — rely on Telethon's get_entity by id/username/title.
# The previous implementation attempted to search dialogs if get_entity failed;
# that behaviour was removed per request to avoid expensive dialog iteration.


_lock = asyncio.Lock()
_current_task: Optional[asyncio.Task[Any]] = None
_current_job_id: Optional[int] = None


async def start_sync_job() -> dict[str, Any]:
    """Idempotent entrypoint for API: start if idle, otherwise return status."""
    async with _lock:
        # If a task is running, just return current status
        if _current_task and not _current_task.done():
            return await get_sync_status()

        # If DB says running but there's no live task, mark it stale and reset
        existing = get_active_job()
        if existing:
            if _current_task and not _current_task.done():
                return await get_sync_status()
            finish_job(existing["id"], "failed", last_error="stale active job reset")

        job_id = create_job()
        _start_background_sync(job_id)
        return await get_sync_status()


def _start_background_sync(job_id: int) -> None:
    global _current_task, _current_job_id
    _current_job_id = job_id
    _current_task = asyncio.create_task(_run_sync_job(job_id))

    def _cleanup(_: asyncio.Task[Any]) -> None:
        # Reset state when task finishes
        nonlocal job_id
        global _current_task, _current_job_id
        _current_task = None
        _current_job_id = None

    _current_task.add_done_callback(_cleanup)


async def get_sync_status() -> dict[str, Any]:
    settings = get_settings()
    # Prefer in-memory running job id if present
    active = None
    if _current_task and not _current_task.done() and _current_job_id:
        active = get_job(_current_job_id)
    else:
        active = get_active_job()

    last = get_last_job()
    return {
        "active": active,
        "last": last,
        "telegram_enabled": settings.sync_telegram_enabled,
    }


async def _run_sync_job(job_id: int) -> None:
    settings = get_settings()

    messages_scanned = 0
    downloaded = 0
    failed = 0

    # Phase 1: Telegram sync (optional)
    if settings.sync_telegram_enabled:
        if not settings.telegram_chat:
            finish_job(job_id, "failed", last_error="Telegram chat is not configured")
            return

        client = build_client()
        try:
            await client.start()
            entity = await client.get_entity(settings.telegram_chat)

            async for msg in client.iter_messages(entity, limit=settings.sync_limit):
                if not msg:
                    continue

                messages_scanned += 1

                if settings.sync_read_delay_seconds > 0:
                    await asyncio.sleep(settings.sync_read_delay_seconds)

                if not (getattr(msg, "audio", None) or getattr(msg, "document", None)):
                    continue
                if not getattr(msg, "audio", None):
                    continue

                file_name = None
                if msg.file and msg.file.name:
                    file_name = str(msg.file.name)
                else:
                    artist, title, _ = _audio_attrs(msg)
                    base = " - ".join([p for p in [artist, title] if p])
                    ext = None
                    if msg.file and getattr(msg.file, "ext", None):
                        ext = str(msg.file.ext)
                    file_name = (base or f"tg_{msg.id}") + (ext or ".mp3")

                file_name = _safe_filename(file_name)

                chat_folder = settings.downloads_dir / str(getattr(entity, "id", settings.telegram_chat))
                chat_folder.mkdir(parents=True, exist_ok=True)

                local_path: Path = chat_folder / _safe_filename(f"{msg.id}_{file_name}")
                expected_size = getattr(msg.file, "size", None) if msg.file else None

                artist, title, duration = _audio_attrs(msg)

                local_exists = local_path.exists()
                if local_exists and expected_size:
                    try:
                        if local_path.stat().st_size != expected_size:
                            local_path.unlink(missing_ok=True)
                            local_exists = False
                    except FileNotFoundError:
                        local_exists = False

                # Only insert/update after we have a valid local file
                if local_exists:
                    # File already exists - just ensure DB record is present
                    upsert_track(
                        local_path=str(local_path),
                        file_name=file_name,
                        tg_chat_id=str(getattr(entity, "id", settings.telegram_chat)),
                        tg_message_id=int(msg.id),
                        mime_type=getattr(msg.file, "mime_type", None) if msg.file else None,
                        size_bytes=expected_size,
                        duration_seconds=duration,
                        artist=artist,
                        title=title,
                        created_at=msg.date.isoformat() if getattr(msg, "date", None) else None,
                    )

                try:
                    if not local_exists:
                        downloaded_path = await client.download_media(msg, file=str(local_path))
                        if downloaded_path:
                            if expected_size is not None:
                                actual_size = local_path.stat().st_size if local_path.exists() else 0
                                if actual_size != expected_size:
                                    raise ValueError(
                                        f"size mismatch: got {actual_size}, expected {expected_size}"
                                    )

                            downloaded += 1
                            upsert_track(
                                local_path=str(local_path),
                                file_name=file_name,
                                tg_chat_id=str(getattr(entity, "id", settings.telegram_chat)),
                                tg_message_id=int(msg.id),
                                mime_type=getattr(msg.file, "mime_type", None) if msg.file else None,
                                size_bytes=expected_size,
                                duration_seconds=duration,
                                artist=artist,
                                title=title,
                                created_at=msg.date.isoformat() if getattr(msg, "date", None) else None,
                            )
                            if settings.download_delay_seconds > 0:
                                jitter = random.uniform(0, settings.download_delay_seconds * 0.3)
                                await asyncio.sleep(settings.download_delay_seconds + jitter)
                except Exception as dl_err:  # noqa: BLE001
                    failed += 1
                    try:
                        local_path.unlink(missing_ok=True)
                    except FileNotFoundError:
                        pass
                    update_job_progress(
                        job_id,
                        messages_scanned=messages_scanned,
                        tracks_downloaded=downloaded,
                        tracks_failed=failed,
                        last_message_id=int(msg.id),
                        last_error=str(dl_err),
                        log_line=f"fail msg {msg.id}: {dl_err}",
                    )
                    continue

                update_job_progress(
                    job_id,
                    messages_scanned=messages_scanned,
                    tracks_downloaded=downloaded,
                    tracks_failed=failed,
                    last_message_id=int(msg.id),
                )

        except Exception as exc:  # noqa: BLE001
            finish_job(job_id, "failed", last_error=str(exc))
            return
        finally:
            await client.disconnect()
    else:
        # TG sync disabled, update phase to skip
        update_job_progress(job_id, phase="tg_skipped")

    # Phase 2: Local library scan (metadata extraction + orphan cleanup)
    update_job_progress(job_id, phase="local_scan")
    try:
        scan_stats = scan_local_library()
        update_job_progress(
            job_id,
            local_files_found=scan_stats.files_found,
            local_files_created=scan_stats.files_created,
            local_files_updated=scan_stats.files_updated,
            local_files_skipped=scan_stats.files_skipped,
            local_orphans_deleted=scan_stats.orphans_deleted,
        )
    except Exception as scan_err:  # noqa: BLE001
        update_job_progress(
            job_id,
            last_error=f"local scan error: {scan_err}",
            log_line=f"local scan failed: {scan_err}",
        )
        # Continue to finish job even if scan fails

    finish_job(job_id, "success")

