"""FEAT-007: channel favorites (localStorage + /api/streams?ids=)."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from stream_viewer import app as viewer
from stream_viewer.app import MAX_STREAM_ID_FILTER, parse_stream_id_filter
from tests.db_fixtures import build_viewer_db

ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "stream_viewer" / "static" / "app.js"
INDEX_HTML = ROOT / "stream_viewer" / "templates" / "index.html"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    export = tmp_path / "iptv_export"
    export.mkdir()
    (export / "epg").mkdir()
    csv_path = export / "streams.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["name", "url", "group_title", "topics"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "name": "Demo News",
                "url": "https://example.com/a.m3u8",
                "group_title": "News",
                "topics": "news",
            }
        )
        writer.writerow(
            {
                "name": "Demo Movie",
                "url": "https://example.com/b.m3u8",
                "group_title": "Movies",
                "topics": "movies",
            }
        )
    build_viewer_db(export, csv_path)
    monkeypatch.setattr(viewer, "ROOT", tmp_path)
    monkeypatch.setattr(viewer, "EXPORT_DIR", export)
    viewer._catalog.clear()
    viewer._catalog.update(
        {"source": None, "streams": [], "by_id": {}, "filters": {}, "total": 0}
    )
    with TestClient(viewer.app) as test_client:
        yield test_client


def test_api_streams_ids_filter_returns_only_requested(client: TestClient):
    listed = client.get("/api/streams").json()
    assert listed["total"] == 2
    by_name = {item["name"]: item["id"] for item in listed["items"]}
    news_id = by_name["Demo News"]

    filtered = client.get("/api/streams", params={"ids": str(news_id)}).json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["name"] == "Demo News"
    assert filtered["items"][0]["id"] == news_id


def test_api_streams_ids_accepts_comma_and_repeated_params(client: TestClient):
    listed = client.get("/api/streams").json()
    ids = [item["id"] for item in listed["items"]]
    assert len(ids) == 2

    comma = client.get("/api/streams", params={"ids": f"{ids[0]},{ids[1]}"}).json()
    assert comma["total"] == 2

    repeated = client.get(
        "/api/streams", params=[("ids", str(ids[0])), ("ids", str(ids[1]))]
    ).json()
    assert repeated["total"] == 2


def test_api_streams_ids_ignores_unknown_and_invalid(client: TestClient):
    listed = client.get("/api/streams").json()
    known = listed["items"][0]["id"]
    data = client.get(
        "/api/streams", params={"ids": f"{known},999999,not-an-id,-1"}
    ).json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == known


def test_parse_stream_id_filter_none_without_param():
    class _Params:
        def __contains__(self, key: object) -> bool:
            return False

        def getlist(self, key: str) -> list[str]:
            return []

    class _Request:
        query_params = _Params()

    assert parse_stream_id_filter(_Request()) is None  # type: ignore[arg-type]


def test_parse_stream_id_filter_caps_at_max():
    huge = ",".join(str(i) for i in range(MAX_STREAM_ID_FILTER + 50))

    class _Params:
        def __contains__(self, key: object) -> bool:
            return key == "ids"

        def getlist(self, key: str) -> list[str]:
            return [huge] if key == "ids" else []

    class _Request:
        query_params = _Params()

    result = parse_stream_id_filter(_Request())  # type: ignore[arg-type]
    assert result is not None
    assert len(result) == MAX_STREAM_ID_FILTER


def test_favorites_ui_wiring_present():
    html = INDEX_HTML.read_text(encoding="utf-8")
    js = APP_JS.read_text(encoding="utf-8")
    assert 'id="favoritesToggleBtn"' in html
    assert 'id="favoritesHint"' in html
    assert "svtv_favorites" in js
    assert "favorite-btn" in js
    assert "function toggleFavorite" in js
    assert 'params.set("ids"' in js


def test_reset_filters_preserves_favorites():
    """Reset clears search/filters only — not starred channels or Favorites mode."""
    js = APP_JS.read_text(encoding="utf-8")
    reset_start = js.index("function resetFilters()")
    reset_body = js[reset_start : js.index("\n  }", reset_start) + 4]
    assert "state.favoritesOnly = false" not in reset_body
    assert "state.favorites.clear" not in reset_body
    assert "state.favorites =" not in reset_body
    assert "localStorage.removeItem" not in reset_body
    assert "kept.favoritesOnly = true" in reset_body
    assert "els.filterForm.reset()" in reset_body
