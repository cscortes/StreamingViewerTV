"""Import streams CSV + XMLTV guides into viewer.db (prepare stage only)."""

from __future__ import annotations

import csv
import gzip
import io
import re
import sqlite3
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from stream_viewer.db import STREAM_COLUMNS, set_meta

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS streams (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  url TEXT NOT NULL,
  tvg_id TEXT NOT NULL DEFAULT '',
  tvg_logo TEXT NOT NULL DEFAULT '',
  group_title TEXT NOT NULL DEFAULT '',
  http_referrer TEXT NOT NULL DEFAULT '',
  http_user_agent TEXT NOT NULL DEFAULT '',
  country TEXT NOT NULL DEFAULT '',
  country_name TEXT NOT NULL DEFAULT '',
  language TEXT NOT NULL DEFAULT '',
  language_name TEXT NOT NULL DEFAULT '',
  maturity TEXT NOT NULL DEFAULT '',
  is_nsfw TEXT NOT NULL DEFAULT '',
  topics TEXT NOT NULL DEFAULT '',
  video_quality TEXT NOT NULL DEFAULT '',
  stream_quality TEXT NOT NULL DEFAULT '',
  popularity TEXT NOT NULL DEFAULT '',
  probe_http_status TEXT NOT NULL DEFAULT '',
  probe_latency_ms TEXT NOT NULL DEFAULT '',
  probe_notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS programmes (
  id INTEGER PRIMARY KEY,
  channel_key TEXT NOT NULL,
  start_utc TEXT NOT NULL,
  stop_utc TEXT NOT NULL,
  title TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_programmes_key_time
  ON programmes(channel_key, start_utc, stop_utc);

CREATE TABLE IF NOT EXISTS guide_sources (
  name TEXT PRIMARY KEY,
  path TEXT NOT NULL,
  imported_at REAL NOT NULL,
  programme_count INTEGER NOT NULL DEFAULT 0
);
"""


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def parse_xmltv_time(value: str) -> datetime | None:
    if not value:
        return None
    parts = value.strip().split()
    raw = parts[0]
    if len(raw) < 14:
        return None
    try:
        naive = datetime.strptime(raw[:14], "%Y%m%d%H%M%S")
    except ValueError:
        return None
    if len(parts) < 2:
        return naive.replace(tzinfo=timezone.utc)
    offset = parts[1]
    if offset in {"UTC", "GMT", "Z"}:
        return naive.replace(tzinfo=timezone.utc)
    match = re.fullmatch(r"([+-])(\d{2})(\d{2})", offset)
    if not match:
        return naive.replace(tzinfo=timezone.utc)
    sign = 1 if match.group(1) == "+" else -1
    hours = int(match.group(2))
    minutes = int(match.group(3))
    delta = timedelta(hours=sign * hours, minutes=sign * minutes)
    return (naive - delta).replace(tzinfo=timezone.utc)


def is_pluto_guide_path(path: Path) -> bool:
    return path.name.lower().startswith("pluto_")


def clear_streams(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM streams")


def clear_programmes(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM programmes")
    conn.execute("DELETE FROM guide_sources")


def import_streams_csv(conn: sqlite3.Connection, csv_path: Path) -> int:
    text = csv_path.read_text(encoding="utf-8", errors="replace").replace("\x00", "")
    reader = csv.DictReader(text.splitlines())
    rows: list[tuple[Any, ...]] = []
    for index, raw in enumerate(reader):
        name = (raw.get("name") or "").strip()
        url = (raw.get("url") or "").strip()
        if not name or not url:
            continue
        values = [index, name, url]
        for col in STREAM_COLUMNS[2:]:
            values.append((raw.get(col) or "").strip())
        rows.append(tuple(values))

    clear_streams(conn)
    placeholders = ",".join("?" for _ in range(len(STREAM_COLUMNS) + 1))
    columns = "id," + ",".join(STREAM_COLUMNS)
    conn.executemany(
        f"INSERT INTO streams({columns}) VALUES({placeholders})",
        rows,
    )
    set_meta(conn, "streams_source", str(csv_path.name))
    set_meta(conn, "streams_count", str(len(rows)))
    set_meta(conn, "streams_imported_at", datetime.now(timezone.utc).isoformat())
    conn.commit()
    return len(rows)


def _read_maybe_gzip(path: Path) -> bytes:
    data = path.read_bytes()
    if path.suffix == ".gz" or data[:2] == b"\x1f\x8b":
        return gzip.decompress(data)
    return data


def _iter_programme_rows(
    payload: bytes, *, source: str, pluto_mode: bool
) -> Iterable[tuple[str, str, str, str, str]]:
    try:
        root = ET.parse(io.BytesIO(payload)).getroot()
    except ET.ParseError:
        return

    aliases: dict[str, list[str]] = {}
    for channel in root.findall("channel"):
        cid = (channel.get("id") or "").strip()
        if not cid:
            continue
        keys: list[str] = []
        if pluto_mode:
            keys.append(f"pluto:{cid.lower()}")
        keys.append(f"tvg:{cid}")
        aliases[cid] = keys

    for programme in root.findall("programme"):
        cid = (programme.get("channel") or "").strip()
        start = parse_xmltv_time(programme.get("start") or "")
        stop = parse_xmltv_time(programme.get("stop") or "")
        title = (programme.findtext("title") or "").strip()
        if not cid or not start or not stop or not title:
            continue
        keys = aliases.get(cid) or (
            [f"pluto:{cid.lower()}"] if pluto_mode else [f"tvg:{cid}"]
        )
        start_s = start.isoformat()
        stop_s = stop.isoformat()
        for key in keys:
            yield (key, start_s, stop_s, title, source)


def import_epg_dir(conn: sqlite3.Connection, epg_dir: Path) -> tuple[int, int]:
    """Import all local XMLTV guides. Returns (files, programmes)."""
    clear_programmes(conn)
    if not epg_dir.is_dir():
        conn.commit()
        return 0, 0

    files = 0
    total = 0
    batch: list[tuple[str, str, str, str, str]] = []

    def flush() -> None:
        nonlocal batch, total
        if not batch:
            return
        conn.executemany(
            "INSERT INTO programmes(channel_key, start_utc, stop_utc, title, source) "
            "VALUES(?,?,?,?,?)",
            batch,
        )
        total += len(batch)
        batch = []

    for path in sorted(epg_dir.iterdir()):
        if not path.is_file():
            continue
        name = path.name.lower()
        if not (name.endswith((".xml", ".xml.gz")) or path.suffix.lower() == ".gz"):
            continue
        source = path.name
        try:
            payload = _read_maybe_gzip(path)
        except OSError:
            continue
        count = 0
        for row in _iter_programme_rows(
            payload, source=source, pluto_mode=is_pluto_guide_path(path)
        ):
            batch.append(row)
            count += 1
            if len(batch) >= 5000:
                flush()
        flush()
        conn.execute(
            "INSERT INTO guide_sources(name, path, imported_at, programme_count) "
            "VALUES(?,?,?,?) "
            "ON CONFLICT(name) DO UPDATE SET "
            "path=excluded.path, imported_at=excluded.imported_at, "
            "programme_count=excluded.programme_count",
            (source, str(path), time.time(), count),
        )
        files += 1

    set_meta(conn, "programmes_count", str(total))
    set_meta(conn, "guide_files", str(files))
    set_meta(conn, "epg_imported_at", datetime.now(timezone.utc).isoformat())
    conn.commit()
    return files, total
