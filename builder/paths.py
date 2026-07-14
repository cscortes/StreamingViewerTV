"""Shared filesystem paths for the build pipeline."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPORT_DIR = ROOT / "iptv_export"
EPG_DIR = EXPORT_DIR / "epg"
EPG_CACHE_DIR = EXPORT_DIR / "epg_cache"
EPG_CHANNELS_DIR = EXPORT_DIR / "epg_channels"
VIEWER_DB = EXPORT_DIR / "viewer.db"
STREAMS_CSV = EXPORT_DIR / "streams.csv"
STREAMS_ENRICHED_CSV = EXPORT_DIR / "streams_enriched.csv"
STREAMS_PROBED_CSV = EXPORT_DIR / "streams_probed.csv"

STREAM_CSV_CANDIDATES = (
    STREAMS_PROBED_CSV,
    STREAMS_ENRICHED_CSV,
    STREAMS_CSV,
)


def choose_streams_csv() -> Path | None:
    for path in STREAM_CSV_CANDIDATES:
        if path.is_file() and path.stat().st_size > 0:
            return path
    return None
