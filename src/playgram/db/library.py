from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path

from playgram.db.core import db


_log = logging.getLogger(__name__)


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def upsert_track(
    *,
    local_path: str,
    file_name: str,
    tg_chat_id: str | None = None,
    tg_message_id: int | None = None,
    mime_type: str | None = None,
    size_bytes: int | None = None,
    duration_seconds: int | None = None,
    artist: str | None = None,
    title: str | None = None,
    album: str | None = None,
    year: int | None = None,
    created_at: str | None = None,
) -> int:
    """Insert or update track by local_path (unique key)."""
    with db() as conn:
        conn.execute(
            """
            INSERT INTO tracks(
              local_path, file_name, tg_chat_id, tg_message_id, mime_type, size_bytes,
              duration_seconds, artist, title, album, year, created_at, added_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(local_path) DO UPDATE SET
              file_name=excluded.file_name,
              tg_chat_id=COALESCE(excluded.tg_chat_id, tracks.tg_chat_id),
              tg_message_id=COALESCE(excluded.tg_message_id, tracks.tg_message_id),
              mime_type=COALESCE(excluded.mime_type, tracks.mime_type),
              size_bytes=COALESCE(excluded.size_bytes, tracks.size_bytes),
              duration_seconds=COALESCE(excluded.duration_seconds, tracks.duration_seconds),
              artist=COALESCE(excluded.artist, tracks.artist),
              title=COALESCE(excluded.title, tracks.title),
              album=COALESCE(excluded.album, tracks.album),
              year=COALESCE(excluded.year, tracks.year),
              created_at=COALESCE(excluded.created_at, tracks.created_at)
            """,
            (
                local_path,
                file_name,
                tg_chat_id,
                tg_message_id,
                mime_type,
                size_bytes,
                duration_seconds,
                artist,
                title,
                album,
                year,
                created_at,
                _now_iso(),
            ),
        )
        row = conn.execute(
            "SELECT id FROM tracks WHERE local_path=?",
            (local_path,),
        ).fetchone()
        assert row
        return int(row["id"])


def list_tracks(*, tag: str | None = None, rating: int | None = None) -> list[dict]:
    with db() as conn:
        if tag:
            rows = conn.execute(
                """
                SELECT t.* FROM tracks t
                JOIN track_tags tt ON tt.track_id = t.id
                JOIN tags g ON g.id = tt.tag_id
                WHERE g.name = ?
                ORDER BY COALESCE(t.artist, ''), COALESCE(t.title, t.file_name)
                """,
                (tag,),
            ).fetchall()
        elif rating is not None:
            rows = conn.execute(
                """
                SELECT * FROM tracks
                WHERE rating = ?
                ORDER BY COALESCE(artist, ''), COALESCE(title, file_name)
                """,
                (rating,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM tracks
                ORDER BY COALESCE(artist, ''), COALESCE(title, file_name)
                """
            ).fetchall()

        track_ids = [int(r["id"]) for r in rows]
        tags_by_track = _get_tags_by_track_ids(conn, track_ids)

        out: list[dict] = []
        for r in rows:
            track_id = int(r["id"])
            out.append(
                {
                    "id": track_id,
                    "file_name": r["file_name"],
                    "local_path": r["local_path"],
                    "mime_type": r["mime_type"],
                    "size_bytes": r["size_bytes"],
                    "duration_seconds": r["duration_seconds"],
                    "artist": r["artist"],
                    "title": r["title"],
                    "album": r["album"],
                    "year": r["year"],
                    "created_at": r["created_at"],
                    "added_at": r["added_at"],
                    "rating": r["rating"],
                    "tags": tags_by_track.get(track_id, []),
                }
            )
        return out


def get_track_by_id(track_id: int) -> dict | None:
    with db() as conn:
        r = conn.execute("SELECT * FROM tracks WHERE id=?", (track_id,)).fetchone()
        if not r:
            return None
        tags = _get_tags_by_track_ids(conn, [track_id]).get(track_id, [])
        return {
            "id": int(r["id"]),
            "file_name": r["file_name"],
            "local_path": r["local_path"],
            "mime_type": r["mime_type"],
            "size_bytes": r["size_bytes"],
            "duration_seconds": r["duration_seconds"],
            "artist": r["artist"],
            "title": r["title"],
            "album": r["album"],
            "year": r["year"],
            "created_at": r["created_at"],
            "added_at": r["added_at"],
            "rating": r["rating"],
            "tags": tags,
        }


def _get_tags_by_track_ids(conn, track_ids: list[int]) -> dict[int, list[str]]:
    if not track_ids:
        return {}
    q_marks = ",".join(["?"] * len(track_ids))
    rows = conn.execute(
        f"""
        SELECT tt.track_id, g.name
        FROM track_tags tt
        JOIN tags g ON g.id = tt.tag_id
        WHERE tt.track_id IN ({q_marks})
        ORDER BY g.name
        """,
        tuple(track_ids),
    ).fetchall()
    by: dict[int, list[str]] = {tid: [] for tid in track_ids}
    for r in rows:
        by[int(r["track_id"])].append(str(r["name"]))
    return {k: v for k, v in by.items() if v}


def list_tags() -> list[str]:
    with db() as conn:
        rows = conn.execute("SELECT name FROM tags ORDER BY name").fetchall()
        return [str(r["name"]) for r in rows]


def add_tag(*, track_id: int, tag: str) -> None:
    tag = tag.strip()
    if not tag:
        return
    with db() as conn:
        conn.execute("INSERT OR IGNORE INTO tags(name) VALUES (?)", (tag,))
        tag_id_row = conn.execute("SELECT id FROM tags WHERE name=?", (tag,)).fetchone()
        assert tag_id_row
        tag_id = int(tag_id_row["id"])
        conn.execute(
            "INSERT OR IGNORE INTO track_tags(track_id, tag_id) VALUES (?, ?)",
            (track_id, tag_id),
        )


def remove_tag(*, track_id: int, tag: str) -> None:
    tag = tag.strip()
    if not tag:
        return
    with db() as conn:
        tag_id_row = conn.execute("SELECT id FROM tags WHERE name=?", (tag,)).fetchone()
        if not tag_id_row:
            return
        tag_id = int(tag_id_row["id"])
        conn.execute("DELETE FROM track_tags WHERE track_id=? AND tag_id=?", (track_id, tag_id))


def record_play_event(*, track_id: int, event: str) -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO history(track_id, event, ts) VALUES (?, ?, ?)",
            (track_id, event, _now_iso()),
        )


def set_rating(*, track_id: int, rating: int | None) -> None:
    """Set track rating (1-3 stars) or None to clear. Also writes to file tags."""
    if rating is not None and not (1 <= rating <= 3):
        raise ValueError("rating must be 1, 2, or 3")

    with db() as conn:
        conn.execute("UPDATE tracks SET rating=? WHERE id=?", (rating, track_id))

        # Try to write rating to file
        if rating is not None:
            row = conn.execute("SELECT local_path FROM tracks WHERE id=?", (track_id,)).fetchone()
            if row and row["local_path"]:
                try:
                    from playgram.library.metadata import write_rating_to_file
                    write_rating_to_file(Path(row["local_path"]), rating)
                except Exception as e:  # noqa: BLE001
                    _log.warning("Failed to write rating to file for track %d: %s", track_id, e)


def get_history(*, limit: int = 50) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            """
            SELECT h.id, h.event, h.ts, t.id AS track_id, t.artist, t.title, t.file_name
            FROM history h
            JOIN tracks t ON t.id = h.track_id
            ORDER BY h.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            {
                "id": int(r["id"]),
                "event": str(r["event"]),
                "ts": str(r["ts"]),
                "track": {
                    "id": int(r["track_id"]),
                    "artist": r["artist"],
                    "title": r["title"],
                    "file_name": r["file_name"],
                },
            }
            for r in rows
        ]
