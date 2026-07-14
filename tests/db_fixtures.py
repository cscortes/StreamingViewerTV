"""Helpers to build a tiny viewer.db for tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from builder.import_catalog import import_epg_dir, import_streams_csv, init_schema
from stream_viewer import db as catalog_db


def write_stub_epg_xml(path: Path, channel_id: str, title: str) -> None:
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=1)
    stop = now + timedelta(hours=2)

    def fmt(value: datetime) -> str:
        return value.strftime("%Y%m%d%H%M%S") + " +0000"

    path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<tv>
  <channel id="{channel_id}">
    <display-name>Demo</display-name>
  </channel>
  <programme start="{fmt(start)}" stop="{fmt(stop)}" channel="{channel_id}">
    <title>{title}</title>
  </programme>
</tv>
""",
        encoding="utf-8",
    )


def build_viewer_db(export_dir: Path, csv_path: Path | None = None) -> Path:
    """Create export_dir/viewer.db from CSV + epg/."""
    db_path = export_dir / "viewer.db"
    if db_path.exists():
        db_path.unlink()
    source = csv_path
    if source is None:
        for name in ("streams_probed.csv", "streams_enriched.csv", "streams.csv"):
            candidate = export_dir / name
            if candidate.is_file():
                source = candidate
                break
    if source is None or not source.is_file():
        raise FileNotFoundError(f"No streams CSV under {export_dir}")

    conn = catalog_db.connect(db_path)
    try:
        init_schema(conn)
        import_streams_csv(conn, source)
        import_epg_dir(conn, export_dir / "epg")
    finally:
        conn.close()
    return db_path
