"""Tests for builder filtered_stream.csv blocklist at import time."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from builder import import_catalog
from builder import paths as builder_paths
from builder import prepare_db
from stream_viewer.db import connect, get_meta

FILTER_FIELDNAMES = ["filter_id", "which", "name", "url", "tvg_id"]

STREAM_FIELDNAMES = [
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


def _write_filter_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FILTER_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def _write_streams_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=STREAM_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            full = {key: "" for key in STREAM_FIELDNAMES}
            full.update(row)
            writer.writerow(full)


def test_load_rules_skips_invalid_rows(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    path = tmp_path / "filtered_stream.csv"
    _write_filter_csv(
        path,
        [
            {"filter_id": "", "which": "name", "name": "X", "url": "", "tvg_id": ""},
            {
                "filter_id": "not-a-number",
                "which": "name",
                "name": "X",
                "url": "",
                "tvg_id": "",
            },
            {
                "filter_id": "2",
                "which": "topic",
                "name": "",
                "url": "",
                "tvg_id": "",
            },
            {
                "filter_id": "3",
                "which": "url",
                "name": "",
                "url": "",
                "tvg_id": "",
            },
            {
                "filter_id": "1",
                "which": "name",
                "name": "Keep*",
                "url": "",
                "tvg_id": "",
            },
            {
                "filter_id": "1",
                "which": "name",
                "name": "Dup*",
                "url": "",
                "tvg_id": "",
            },
        ],
    )
    rules = import_catalog.load_filtered_stream_rules(path)
    assert rules == [(1, "name", "Keep*")]
    err = capsys.readouterr().out
    assert "empty filter_id" in err
    assert "non-numeric filter_id" in err
    assert "invalid which" in err
    assert "empty url pattern" in err
    assert "duplicate filter_id" in err


def test_load_rules_missing_file(tmp_path: Path):
    assert import_catalog.load_filtered_stream_rules(tmp_path / "nope.csv") == []


def test_name_rule_matches_all_duplicates():
    rules = [(1, "name", "Dating Naked UK")]
    rows = [
        {
            "name": "Dating Naked UK",
            "url": "https://a.example/1.m3u8",
            "tvg_id": "DatingNakedUK.se@DK",
        },
        {
            "name": "Dating Naked UK",
            "url": "https://a.example/2.m3u8",
            "tvg_id": "DatingNakedUK.se@NO",
        },
        {
            "name": "Dating Naked UK",
            "url": "https://a.example/3.m3u8",
            "tvg_id": "DatingNakedUK.se@SE",
        },
        {
            "name": "Demo News",
            "url": "https://example.com/news.m3u8",
            "tvg_id": "demo",
        },
    ]
    hits = [import_catalog.matching_filter_id(row, rules) for row in rows]
    assert hits == [1, 1, 1, None]


def test_name_and_url_wildcards_case_insensitive():
    rules = [
        (10, "name", "Adult*"),
        (20, "url", "*://cdn.example.com/*"),
    ]
    assert (
        import_catalog.matching_filter_id(
            {"name": "adult movies", "url": "https://ok.example/x.m3u8", "tvg_id": ""},
            rules,
        )
        == 10
    )
    assert (
        import_catalog.matching_filter_id(
            {
                "name": "News",
                "url": "HTTPS://CDN.EXAMPLE.COM/live.m3u8",
                "tvg_id": "",
            },
            rules,
        )
        == 20
    )
    assert (
        import_catalog.matching_filter_id(
            {"name": "News", "url": "https://other.example/x.m3u8", "tvg_id": ""},
            rules,
        )
        is None
    )


def test_tvg_id_exact_match_no_wildcard():
    rules = [(30, "tvg_id", "DemoChannel.us")]
    assert (
        import_catalog.matching_filter_id(
            {"name": "Demo", "url": "https://a/x", "tvg_id": "DemoChannel.us"},
            rules,
        )
        == 30
    )
    assert (
        import_catalog.matching_filter_id(
            {"name": "Demo", "url": "https://a/x", "tvg_id": "Demo*"},
            rules,
        )
        is None
    )
    # Pattern with * is treated literally for tvg_id
    star_rules = [(31, "tvg_id", "Demo*")]
    assert (
        import_catalog.matching_filter_id(
            {"name": "Demo", "url": "https://a/x", "tvg_id": "DemoChannel.us"},
            star_rules,
        )
        is None
    )
    assert (
        import_catalog.matching_filter_id(
            {"name": "Demo", "url": "https://a/x", "tvg_id": "Demo*"},
            star_rules,
        )
        == 31
    )


def test_import_streams_csv_excludes_all_name_matches(tmp_path: Path):
    streams = tmp_path / "streams.csv"
    filters = tmp_path / "filtered_stream.csv"
    _write_streams_csv(
        streams,
        [
            {
                "name": "Dating Naked UK",
                "url": "https://a.example/1.m3u8",
                "tvg_id": "DatingNakedUK.se@DK",
            },
            {
                "name": "Dating Naked UK",
                "url": "https://a.example/2.m3u8",
                "tvg_id": "DatingNakedUK.se@NO",
            },
            {
                "name": "Dating Naked UK",
                "url": "https://a.example/3.m3u8",
                "tvg_id": "DatingNakedUK.se@SE",
            },
            {
                "name": "Demo News",
                "url": "https://example.com/news.m3u8",
                "tvg_id": "demo",
            },
        ],
    )
    _write_filter_csv(
        filters,
        [
            {
                "filter_id": "1",
                "which": "name",
                "name": "Dating Naked UK",
                "url": "",
                "tvg_id": "",
            }
        ],
    )

    db_path = tmp_path / "viewer.db"
    log_path = tmp_path / "filtered_streams.log"
    conn = connect(db_path)
    try:
        import_catalog.init_schema(conn)
        count = import_catalog.import_streams_csv(
            conn, streams, filter_path=filters, log_path=log_path
        )
        assert count == 1
        names = [r[0] for r in conn.execute("SELECT name FROM streams ORDER BY id")]
        assert names == ["Demo News"]
        assert get_meta(conn, "streams_filtered_count") == "3"
        assert get_meta(conn, "streams_count") == "1"
    finally:
        conn.close()

    assert log_path.is_file()
    log_text = log_path.read_text(encoding="utf-8")
    assert "filtered=3" in log_text
    assert "1\tDating Naked UK\thttps://a.example/1.m3u8\tDatingNakedUK.se@DK" in log_text
    assert "1\tDating Naked UK\thttps://a.example/2.m3u8\tDatingNakedUK.se@NO" in log_text
    assert "1\tDating Naked UK\thttps://a.example/3.m3u8\tDatingNakedUK.se@SE" in log_text
    assert "Demo News" not in log_text


@pytest.fixture
def isolated_export_with_filter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Scratch export + blocklist that drops Dating Naked UK duplicates."""
    export = tmp_path / "iptv_export"
    epg_dir = export / "epg"
    epg_cache_dir = export / "epg_cache"
    epg_dir.mkdir(parents=True)
    epg_cache_dir.mkdir(parents=True)

    streams_csv = export / "streams.csv"
    _write_streams_csv(
        streams_csv,
        [
            {
                "name": "Dating Naked UK",
                "url": "https://a.example/1.m3u8",
                "tvg_id": "DatingNakedUK.se@DK",
            },
            {
                "name": "Dating Naked UK",
                "url": "https://a.example/2.m3u8",
                "tvg_id": "DatingNakedUK.se@NO",
            },
            {
                "name": "Demo News",
                "url": "https://example.com/news.m3u8",
                "tvg_id": "demo",
                "group_title": "News",
                "country_name": "United States",
                "language_name": "English",
                "topics": "news",
                "video_quality": "720p",
                "stream_quality": "excellent",
                "maturity": "Family",
            },
        ],
    )
    (epg_dir / "stub.xml").write_text(
        '<?xml version="1.0"?><tv></tv>\n', encoding="utf-8"
    )

    builder_dir = tmp_path / "builder"
    builder_dir.mkdir()
    filtered = builder_dir / "filtered_stream.csv"
    _write_filter_csv(
        filtered,
        [
            {
                "filter_id": "1",
                "which": "name",
                "name": "Dating Naked UK",
                "url": "",
                "tvg_id": "",
            }
        ],
    )

    streams_enriched_csv = export / "streams_enriched.csv"
    streams_probed_csv = export / "streams_probed.csv"
    viewer_db = export / "viewer.db"
    filtered_log = export / "filtered_streams.log"

    overrides = {
        "ROOT": tmp_path,
        "EXPORT_DIR": export,
        "EPG_DIR": epg_dir,
        "EPG_CACHE_DIR": epg_cache_dir,
        "VIEWER_DB": viewer_db,
        "STREAMS_CSV": streams_csv,
        "STREAMS_ENRICHED_CSV": streams_enriched_csv,
        "STREAMS_PROBED_CSV": streams_probed_csv,
        "FILTERED_STREAM_CSV": filtered,
        "FILTERED_STREAMS_LOG": filtered_log,
    }
    for name, value in overrides.items():
        monkeypatch.setattr(builder_paths, name, value, raising=False)
        monkeypatch.setattr(prepare_db, name, value, raising=False)
        monkeypatch.setattr(import_catalog, name, value, raising=False)

    monkeypatch.setattr(
        builder_paths,
        "STREAM_CSV_CANDIDATES",
        (streams_probed_csv, streams_enriched_csv, streams_csv),
        raising=False,
    )
    return export


def test_prepare_db_applies_blocklist(isolated_export_with_filter: Path):
    exit_code = prepare_db.main(["--skip-download"])
    assert exit_code == 0

    viewer_db = isolated_export_with_filter / "viewer.db"
    assert viewer_db.is_file()
    conn = connect(viewer_db)
    try:
        names = [r[0] for r in conn.execute("SELECT name FROM streams ORDER BY id")]
        assert names == ["Demo News"]
        assert get_meta(conn, "streams_filtered_count") == "2"
    finally:
        conn.close()

    log_path = isolated_export_with_filter / "filtered_streams.log"
    assert log_path.is_file()
    log_text = log_path.read_text(encoding="utf-8")
    assert "filtered=2" in log_text
    assert "Dating Naked UK" in log_text
    assert "Demo News" not in log_text
