"""Catalog Category coverage — DB must expose categories with stream items."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from stream_viewer import app as viewer
from stream_viewer import db as catalog_db
from stream_viewer.app import (
    CATEGORY_FILTER_FIELD,
    assert_catalog_has_categories,
    category_value_counts,
)
from stream_viewer.app import app
from tests.db_fixtures import build_viewer_db

VIEWER_DB = Path("iptv_export/viewer.db")


def _write_catalog_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
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
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_assert_catalog_has_categories_requires_multiple_populated_topics():
    empty = [{"topics": ""}, {"topics": "undefined"}, {"topics": "news"}]
    with pytest.raises(ValueError, match="at least 2 categories"):
        assert_catalog_has_categories(empty, min_categories=2)

    ok = [
        {"topics": "news"},
        {"topics": "news"},
        {"topics": "movies"},
    ]
    counts = assert_catalog_has_categories(ok, min_categories=2)
    assert counts["news"] == 2
    assert counts["movies"] == 1


def test_fixture_db_has_categories_with_items(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    export = tmp_path / "iptv_export"
    export.mkdir()
    (export / "epg").mkdir()
    csv_path = export / "streams.csv"
    _write_catalog_csv(
        csv_path,
        [
            {
                "name": "News One",
                "url": "https://example.com/n1.m3u8",
                "tvg_id": "n1",
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
            },
            {
                "name": "Movie One",
                "url": "https://example.com/m1.m3u8",
                "tvg_id": "m1",
                "tvg_logo": "",
                "group_title": "Movies",
                "http_referrer": "",
                "http_user_agent": "",
                "country_name": "Canada",
                "language_name": "English",
                "topics": "movies",
                "video_quality": "1080p",
                "stream_quality": "okay",
                "maturity": "Family",
            },
            {
                "name": "Movie Two",
                "url": "https://example.com/m2.m3u8",
                "tvg_id": "m2",
                "tvg_logo": "",
                "group_title": "Movies",
                "http_referrer": "",
                "http_user_agent": "",
                "country_name": "Canada",
                "language_name": "French",
                "topics": "movies",
                "video_quality": "720p",
                "stream_quality": "poor",
                "maturity": "Family",
            },
        ],
    )
    build_viewer_db(export, csv_path)

    conn = catalog_db.connect(export / "viewer.db")
    try:
        streams = catalog_db.load_streams(conn)
    finally:
        conn.close()

    counts = assert_catalog_has_categories(streams, min_categories=2)
    assert counts["news"] >= 1
    assert counts["movies"] >= 2

    monkeypatch.setattr(viewer, "ROOT", tmp_path)
    monkeypatch.setattr(viewer, "EXPORT_DIR", export)
    viewer._catalog.clear()
    viewer._catalog.update(
        {"source": None, "streams": [], "by_id": {}, "filters": {}, "total": 0}
    )
    with TestClient(app) as client:
        meta = client.get("/api/meta").json()
        category = meta["filters"][CATEGORY_FILTER_FIELD]
        assert category["label"] == "Category"
        by_name = {item["value"]: item["count"] for item in category["options"]}
        assert by_name["news"] >= 1
        assert by_name["movies"] >= 2

        movies = client.get("/api/streams", params={"topics": "movies"}).json()
        assert movies["total"] == 2


def test_local_viewer_db_has_categories_with_items():
    """Live catalog under iptv_export/ must expose Category values with items."""
    if not VIEWER_DB.is_file():
        pytest.skip("iptv_export/viewer.db missing — run: make build")

    conn = catalog_db.connect(VIEWER_DB)
    try:
        streams = catalog_db.load_streams(conn)
    finally:
        conn.close()

    assert streams, "viewer.db has zero streams"
    counts = category_value_counts(streams)
    assert counts, (
        "viewer.db has no Category (topics) values; rebuild with enrichment "
        "(make build / stream-viewer-build)"
    )
    usable = assert_catalog_has_categories(
        streams, min_categories=2, min_items_per_category=1
    )
    assert sum(usable.values()) >= 2
