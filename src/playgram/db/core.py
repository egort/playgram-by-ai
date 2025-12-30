from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Generator

from playgram.settings import get_settings


def _connect() -> sqlite3.Connection:
    settings = get_settings()
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def db() -> Generator[sqlite3.Connection, None, None]:
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tracks (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              tg_chat_id TEXT,
              tg_message_id INTEGER,
              file_name TEXT NOT NULL,
              local_path TEXT UNIQUE NOT NULL,
              mime_type TEXT,
              size_bytes INTEGER,
              duration_seconds INTEGER,
              artist TEXT,
              title TEXT,
              album TEXT,
              year INTEGER,
              created_at TEXT,
              added_at TEXT NOT NULL,
              rating INTEGER DEFAULT NULL
            );

            CREATE TABLE IF NOT EXISTS tags (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS track_tags (
              track_id INTEGER NOT NULL,
              tag_id INTEGER NOT NULL,
              PRIMARY KEY (track_id, tag_id),
              FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE,
              FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS history (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              track_id INTEGER NOT NULL,
              event TEXT NOT NULL,
              ts TEXT NOT NULL,
              FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS sync_jobs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              status TEXT NOT NULL,
              phase TEXT DEFAULT 'telegram',
              started_at TEXT NOT NULL,
              finished_at TEXT,
              messages_scanned INTEGER DEFAULT 0,
              tracks_downloaded INTEGER DEFAULT 0,
              tracks_failed INTEGER DEFAULT 0,
              last_message_id INTEGER,
              last_error TEXT,
              log TEXT,
              local_files_found INTEGER DEFAULT 0,
              local_files_updated INTEGER DEFAULT 0,
              local_files_skipped INTEGER DEFAULT 0,
              local_orphans_deleted INTEGER DEFAULT 0
            );
            """
        )
        # Migrate existing DBs: add album and year columns if missing
        _migrate_add_columns(conn)


def _migrate_add_columns(conn: "sqlite3.Connection") -> None:
    """Add new columns to existing tables if they don't exist."""
    # Migrate tracks table
    cursor = conn.execute("PRAGMA table_info(tracks)")
    tracks_cols = {row[1] for row in cursor.fetchall()}

    if "album" not in tracks_cols:
        conn.execute("ALTER TABLE tracks ADD COLUMN album TEXT")
    if "year" not in tracks_cols:
        conn.execute("ALTER TABLE tracks ADD COLUMN year INTEGER")

    # Migrate from old schema: make local_path UNIQUE if not already
    # Check existing indexes
    idx_cursor = conn.execute("PRAGMA index_list(tracks)")
    indexes = {row[1]: row for row in idx_cursor.fetchall()}

    # Create unique index on local_path if not exists
    if "idx_tracks_local_path" not in indexes:
        # First, ensure no nulls in local_path (delete orphaned rows)
        conn.execute("DELETE FROM tracks WHERE local_path IS NULL")
        try:
            conn.execute("CREATE UNIQUE INDEX idx_tracks_local_path ON tracks(local_path)")
        except Exception:  # noqa: BLE001
            # May fail if duplicates exist; log and continue
            pass

    # Migrate sync_jobs table
    cursor = conn.execute("PRAGMA table_info(sync_jobs)")
    sync_cols = {row[1] for row in cursor.fetchall()}

    if "phase" not in sync_cols:
        conn.execute("ALTER TABLE sync_jobs ADD COLUMN phase TEXT DEFAULT 'telegram'")
    if "local_files_found" not in sync_cols:
        conn.execute("ALTER TABLE sync_jobs ADD COLUMN local_files_found INTEGER DEFAULT 0")
    if "local_files_updated" not in sync_cols:
        conn.execute("ALTER TABLE sync_jobs ADD COLUMN local_files_updated INTEGER DEFAULT 0")
    if "local_files_skipped" not in sync_cols:
        conn.execute("ALTER TABLE sync_jobs ADD COLUMN local_files_skipped INTEGER DEFAULT 0")
    if "local_files_created" not in sync_cols:
        conn.execute("ALTER TABLE sync_jobs ADD COLUMN local_files_created INTEGER DEFAULT 0")
    if "local_orphans_deleted" not in sync_cols:
        conn.execute("ALTER TABLE sync_jobs ADD COLUMN local_orphans_deleted INTEGER DEFAULT 0")
