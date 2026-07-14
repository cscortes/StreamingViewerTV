"""Read-only SQLite catalog access for StreamingViewerTV (`iptv_export/viewer.db`)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STREAM_COLUMNS = [
    "name",
    "url",
    "tvg_id",
    "tvg_logo",
    "group_title",
    "http_referrer",
    "http_user_agent",
    "country",
    "country_name",
    "language",
    "language_name",
    "maturity",
    "is_nsfw",
    "topics",
    "video_quality",
    "stream_quality",
    "popularity",
    "probe_http_status",
    "probe_latency_ms",
    "probe_notes",
]


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def get_meta(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return str(row["value"]) if row else default


def load_streams(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, " + ", ".join(STREAM_COLUMNS) + " FROM streams ORDER BY id"
    ).fetchall()
    return [
        {key: (row[key] if row[key] is not None else "") for key in row.keys()}
        for row in rows
    ]


def stream_count(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS n FROM streams").fetchone()
    return int(row["n"]) if row else 0


def programme_count(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS n FROM programmes").fetchone()
    return int(row["n"]) if row else 0


def now_playing_for_keys(
    conn: sqlite3.Connection,
    keys: list[str],
    *,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    if not keys:
        return None
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    now_s = current.astimezone(timezone.utc).isoformat()
    placeholders = ",".join("?" for _ in keys)
    row = conn.execute(
        f"""
        SELECT channel_key, start_utc, stop_utc, title
        FROM programmes
        WHERE channel_key IN ({placeholders})
          AND start_utc <= ?
          AND stop_utc > ?
        ORDER BY start_utc DESC
        LIMIT 1
        """,
        [*keys, now_s, now_s],
    ).fetchone()
    if not row:
        return None
    return {
        "title": row["title"],
        "start": row["start_utc"],
        "stop": row["stop_utc"],
        "key": row["channel_key"],
    }


def db_status(conn: sqlite3.Connection) -> dict[str, Any]:
    return {
        "streams": stream_count(conn),
        "programmes": programme_count(conn),
        "streams_source": get_meta(conn, "streams_source"),
        "guide_files": get_meta(conn, "guide_files"),
        "streams_imported_at": get_meta(conn, "streams_imported_at"),
        "epg_imported_at": get_meta(conn, "epg_imported_at"),
    }
