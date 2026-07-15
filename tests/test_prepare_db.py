"""Regression tests for builder.prepare_db (BUG-013)."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from builder import paths as builder_paths
from builder import prepare_db

CSV_FIELDNAMES = [
    "name",
    "url",
    "tvg_id",
    "tvg_logo",
    "group_title",
    "http_referrer",
    "http_user_agent",
    "country_name",
    "language_name",
    "topics",
    "video_quality",
    "stream_quality",
    "maturity",
]


def _write_stub_streams_csv(path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerow(
            {
                "name": "Demo News",
                "url": "https://example.com/news.m3u8",
                "tvg_id": "demo",
                "tvg_logo": "",
                "group_title": "News",
                "http_referrer": "",
                "http_user_agent": "",
                "country_name": "United States",
                "language_name": "English",
                "topics": "news",
                "video_quality": "720p",
                "stream_quality": "excellent",
                "maturity": "Family",
            }
        )


@pytest.fixture
def isolated_export(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point builder.paths / builder.prepare_db at a scratch iptv_export/, with a
    minimal streams.csv + epg/ already in place, so main() never needs the network."""
    export = tmp_path / "iptv_export"
    epg_dir = export / "epg"
    epg_cache_dir = export / "epg_cache"
    epg_dir.mkdir(parents=True)
    epg_cache_dir.mkdir(parents=True)

    streams_csv = export / "streams.csv"
    _write_stub_streams_csv(streams_csv)
    (epg_dir / "stub.xml").write_text(
        '<?xml version="1.0"?><tv></tv>\n', encoding="utf-8"
    )

    streams_enriched_csv = export / "streams_enriched.csv"
    streams_probed_csv = export / "streams_probed.csv"
    viewer_db = export / "viewer.db"

    overrides = {
        "ROOT": tmp_path,
        "EXPORT_DIR": export,
        "EPG_DIR": epg_dir,
        "EPG_CACHE_DIR": epg_cache_dir,
        "VIEWER_DB": viewer_db,
        "STREAMS_CSV": streams_csv,
        "STREAMS_ENRICHED_CSV": streams_enriched_csv,
        "STREAMS_PROBED_CSV": streams_probed_csv,
    }
    for name, value in overrides.items():
        monkeypatch.setattr(builder_paths, name, value, raising=False)
        monkeypatch.setattr(prepare_db, name, value, raising=False)

    # choose_streams_csv() reads this tuple from builder.paths at call time.
    monkeypatch.setattr(
        builder_paths,
        "STREAM_CSV_CANDIDATES",
        (streams_probed_csv, streams_enriched_csv, streams_csv),
        raising=False,
    )

    return export


def test_prepare_db_main_completes_without_crashing(isolated_export: Path):
    """BUG-013: main() raised NameError after successfully writing viewer.db because
    stream_count/programme_count were referenced but never imported. --skip-download
    keeps this fully offline."""
    exit_code = prepare_db.main(["--skip-download"])
    assert exit_code == 0

    viewer_db = isolated_export / "viewer.db"
    assert viewer_db.is_file()


def test_prepare_db_module_imports_count_helpers():
    """Cheap guard against reintroducing the missing import directly."""
    assert hasattr(prepare_db, "stream_count")
    assert hasattr(prepare_db, "programme_count")
