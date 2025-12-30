from __future__ import annotations

import datetime as dt
from typing import Any, Optional

from playgram.db.core import db


def _now() -> str:
    return dt.datetime.utcnow().isoformat()


def create_job() -> int:
    with db() as conn:
        cur = conn.execute(
            """
            INSERT INTO sync_jobs (status, phase, started_at, messages_scanned, tracks_downloaded, tracks_failed)
            VALUES ('running', 'telegram', ?, 0, 0, 0)
            """,
            (_now(),),
        )
        return int(cur.lastrowid)


def update_job_progress(
    job_id: int,
    *,
    phase: Optional[str] = None,
    messages_scanned: Optional[int] = None,
    tracks_downloaded: Optional[int] = None,
    tracks_failed: Optional[int] = None,
    last_message_id: Optional[int] = None,
    last_error: Optional[str] = None,
    log_line: Optional[str] = None,
    local_files_found: Optional[int] = None,
    local_files_created: Optional[int] = None,
    local_files_updated: Optional[int] = None,
    local_files_skipped: Optional[int] = None,
    local_orphans_deleted: Optional[int] = None,
) -> None:
    sets: list[str] = []
    params: list[Any] = []
    if phase is not None:
        sets.append("phase = ?")
        params.append(phase)
    if messages_scanned is not None:
        sets.append("messages_scanned = ?")
        params.append(messages_scanned)
    if tracks_downloaded is not None:
        sets.append("tracks_downloaded = ?")
        params.append(tracks_downloaded)
    if tracks_failed is not None:
        sets.append("tracks_failed = ?")
        params.append(tracks_failed)
    if last_message_id is not None:
        sets.append("last_message_id = ?")
        params.append(last_message_id)
    if last_error is not None:
        sets.append("last_error = ?")
        params.append(last_error)
    if log_line is not None:
        sets.append("log = COALESCE(log, '') || ?")
        params.append(log_line + "\n")
    if local_files_found is not None:
        sets.append("local_files_found = ?")
        params.append(local_files_found)
    if local_files_created is not None:
        sets.append("local_files_created = ?")
        params.append(local_files_created)
    if local_files_updated is not None:
        sets.append("local_files_updated = ?")
        params.append(local_files_updated)
    if local_files_skipped is not None:
        sets.append("local_files_skipped = ?")
        params.append(local_files_skipped)
    if local_orphans_deleted is not None:
        sets.append("local_orphans_deleted = ?")
        params.append(local_orphans_deleted)

    if not sets:
        return

    params.append(job_id)
    with db() as conn:
        conn.execute(f"UPDATE sync_jobs SET {', '.join(sets)} WHERE id = ?", params)


def finish_job(job_id: int, status: str, *, last_error: Optional[str] = None) -> None:
    with db() as conn:
        conn.execute(
            """
            UPDATE sync_jobs
            SET status = ?, finished_at = ?, last_error = COALESCE(?, last_error)
            WHERE id = ?
            """,
            (status, _now(), last_error, job_id),
        )


def get_job(job_id: int) -> Optional[dict[str, Any]]:
    with db() as conn:
        row = conn.execute("SELECT * FROM sync_jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row) if row else None


def get_active_job() -> Optional[dict[str, Any]]:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM sync_jobs WHERE status = 'running' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def get_last_job() -> Optional[dict[str, Any]]:
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM sync_jobs WHERE status != 'running' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def list_recent_jobs(limit: int = 20) -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM sync_jobs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
