"""Local library scanning: file discovery and metadata sync."""
from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from playgram.db.core import db
from playgram.db.library import upsert_track
from playgram.library.metadata import extract_metadata, write_rating_to_file
from playgram.settings import get_settings


AUDIO_EXTENSIONS = frozenset({".mp3", ".m4a", ".mp4", ".flac", ".ogg", ".opus", ".wav", ".aac"})

_log = logging.getLogger(__name__)


@dataclass
class ScanStats:
    """Statistics from a local library scan."""

    files_found: int = 0
    files_created: int = 0
    files_updated: int = 0
    files_skipped: int = 0
    orphans_deleted: int = 0
    rating_sync_errors: int = 0


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _guess_mime_type(file_path: Path) -> str | None:
    """Guess MIME type from file extension."""
    ext = file_path.suffix.lower()
    mime_map = {
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".mp4": "audio/mp4",
        ".flac": "audio/flac",
        ".ogg": "audio/ogg",
        ".opus": "audio/opus",
        ".wav": "audio/wav",
        ".aac": "audio/aac",
    }
    return mime_map.get(ext)


def iter_audio_files(downloads_dir: Path) -> Iterator[Path]:
    """Recursively yield audio files from downloads directory."""
    if not downloads_dir.exists():
        return
    for path in downloads_dir.rglob("*"):
        if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS:
            yield path


def scan_local_library() -> ScanStats:
    """
    Scan local audio files and sync metadata to database.

    Phase 1: Scan all files, extract metadata, update tracks
    Phase 2: Delete orphaned records (tracks with missing files)

    Returns ScanStats with counters.
    """
    settings = get_settings()
    downloads_dir = settings.downloads_dir
    stats = ScanStats()

    # Collect all local file paths (normalized for comparison)
    existing_files: set[str] = set()

    with db() as conn:
        # Phase 1: Update metadata from files
        for file_path in iter_audio_files(downloads_dir):
            stats.files_found += 1
            abs_path = str(file_path.resolve())
            existing_files.add(abs_path)

            # Check if track exists in DB by local_path
            row = conn.execute(
                "SELECT id, artist, title, album, year, duration_seconds, rating FROM tracks WHERE local_path = ?",
                (abs_path,),
            ).fetchone()

            # Extract metadata from file
            meta = extract_metadata(file_path)

            if not row:
                # File not in DB - create new record
                file_size = file_path.stat().st_size if file_path.exists() else None
                upsert_track(
                    local_path=abs_path,
                    file_name=file_path.name,
                    mime_type=_guess_mime_type(file_path),
                    size_bytes=file_size,
                    duration_seconds=meta.duration_seconds if meta else None,
                    artist=meta.artist if meta else None,
                    title=meta.title if meta else None,
                    album=meta.album if meta else None,
                    year=meta.year if meta else None,
                )
                stats.files_created += 1
                continue

            # Update track with file metadata (file tags take priority)
            track_id = int(row["id"])
            updates = []
            params = []

            # File metadata always overwrites (priority A)
            if meta.artist is not None:
                updates.append("artist = ?")
                params.append(meta.artist)
            if meta.title is not None:
                updates.append("title = ?")
                params.append(meta.title)
            if meta.album is not None:
                updates.append("album = ?")
                params.append(meta.album)
            if meta.year is not None:
                updates.append("year = ?")
                params.append(meta.year)
            if meta.duration_seconds is not None:
                updates.append("duration_seconds = ?")
                params.append(meta.duration_seconds)

            if updates:
                params.append(track_id)
                conn.execute(
                    f"UPDATE tracks SET {', '.join(updates)} WHERE id = ?",
                    tuple(params),
                )
                stats.files_updated += 1
            else:
                stats.files_skipped += 1

            # Sync rating from DB to file (DB is authoritative)
            db_rating = row["rating"]
            if db_rating is not None:
                try:
                    write_rating_to_file(file_path, db_rating)
                except Exception as e:  # noqa: BLE001
                    _log.warning("Failed to write rating to %s: %s", file_path.name, e)
                    stats.rating_sync_errors += 1

        # Phase 2: Delete orphaned records (tracks with missing files)
        all_tracks = conn.execute(
            "SELECT id, local_path FROM tracks WHERE local_path IS NOT NULL"
        ).fetchall()

        orphan_ids = []
        for track in all_tracks:
            local_path = track["local_path"]
            if local_path and local_path not in existing_files:
                # File doesn't exist - mark for deletion
                orphan_ids.append(int(track["id"]))

        if orphan_ids:
            q_marks = ",".join(["?"] * len(orphan_ids))
            conn.execute(f"DELETE FROM tracks WHERE id IN ({q_marks})", tuple(orphan_ids))
            stats.orphans_deleted = len(orphan_ids)

    return stats


def scan_and_get_report() -> dict:
    """Run scan and return a structured report."""
    stats = scan_local_library()
    return {
        "phase": "local_scan",
        "status": "completed",
        "files_found": stats.files_found,
        "files_updated": stats.files_updated,
        "files_skipped": stats.files_skipped,
        "orphans_deleted": stats.orphans_deleted,
    }
