"""FEAT-007 / BUG-023: URL-hash favorites (localStorage + favorite_keys)."""

from __future__ import annotations

import csv
import hashlib
import re
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from stream_viewer import app as viewer
from stream_viewer.app import (
    MAX_FAVORITE_KEY_FILTER,
    MAX_STREAM_ID_FILTER,
    parse_favorite_key_filter,
    parse_stream_id_filter,
)
from stream_viewer.db import favorite_key
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
    with viewer._proxy_lock:
        viewer._proxy_sessions.clear()
    with TestClient(viewer.app) as test_client:
        yield test_client
    with viewer._proxy_lock:
        viewer._proxy_sessions.clear()


def test_favorite_key_strips_and_full_hex():
    assert favorite_key("  https://example.com/x  ") == hashlib.sha256(
        b"https://example.com/x"
    ).hexdigest()
    key = favorite_key("https://example.com/x")
    assert re.fullmatch(r"[0-9a-f]{64}", key)
    assert favorite_key("https://example.com/x") == favorite_key(
        "https://example.com/x"
    )
    assert favorite_key("https://example.com/a") != favorite_key(
        "https://example.com/b"
    )


def test_import_stores_favorite_key_and_index(tmp_path: Path):
    export = tmp_path / "iptv_export"
    export.mkdir()
    (export / "epg").mkdir()
    csv_path = export / "streams.csv"
    url = "https://example.com/stable.m3u8"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["name", "url"])
        writer.writeheader()
        writer.writerow({"name": "Stable", "url": f"  {url}  "})
    db_path = build_viewer_db(export, csv_path)
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT favorite_key, url FROM streams WHERE name=?", ("Stable",)
        ).fetchone()
        assert row is not None
        assert row[0] == favorite_key(url)
        idx = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
            ("idx_streams_favorite_key",),
        ).fetchone()
        assert idx is not None
    finally:
        conn.close()


def test_api_streams_include_favorite_key(client: TestClient):
    listed = client.get("/api/streams").json()
    assert listed["total"] == 2
    for item in listed["items"]:
        assert re.fullmatch(r"[0-9a-f]{64}", item["favorite_key"])
        assert item["favorite_key"] == favorite_key(item["url"])


def test_api_streams_favorite_keys_filter(client: TestClient):
    listed = client.get("/api/streams").json()
    by_name = {item["name"]: item for item in listed["items"]}
    news_key = by_name["Demo News"]["favorite_key"]

    filtered = client.get(
        "/api/streams", params={"favorite_keys": news_key}
    ).json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["name"] == "Demo News"
    assert filtered["items"][0]["favorite_key"] == news_key


def test_api_streams_favorite_keys_caps_and_ignores_invalid(client: TestClient):
    listed = client.get("/api/streams").json()
    known = listed["items"][0]["favorite_key"]
    junk = "not-a-hash," + known + ",zzzz"
    data = client.get("/api/streams", params={"favorite_keys": junk}).json()
    assert data["total"] == 1
    assert data["items"][0]["favorite_key"] == known

    huge = ",".join(f"{i:064x}" for i in range(MAX_FAVORITE_KEY_FILTER + 40))

    class _Params:
        def __contains__(self, key: object) -> bool:
            return key == "favorite_keys"

        def getlist(self, key: str) -> list[str]:
            return [huge] if key == "favorite_keys" else []

    class _Request:
        query_params = _Params()

    result = parse_favorite_key_filter(_Request())  # type: ignore[arg-type]
    assert result is not None
    assert len(result) == MAX_FAVORITE_KEY_FILTER


def test_favorite_keys_listing_does_not_open_proxy(client: TestClient):
    listed = client.get("/api/streams").json()
    keys = ",".join(item["favorite_key"] for item in listed["items"])
    with viewer._proxy_lock:
        before = len(viewer._proxy_sessions)
    client.get("/api/streams", params={"favorite_keys": keys})
    with viewer._proxy_lock:
        assert len(viewer._proxy_sessions) == before


def test_favorite_key_stable_across_id_shift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Same URLs keep the same favorite_key when CSV row order (ids) changes."""
    export = tmp_path / "iptv_export"
    export.mkdir()
    (export / "epg").mkdir()
    csv_path = export / "streams.csv"

    def write_csv(rows: list[tuple[str, str, str]]) -> None:
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=["name", "url", "group_title", "topics"]
            )
            writer.writeheader()
            for name, url, topics in rows:
                writer.writerow(
                    {
                        "name": name,
                        "url": url,
                        "group_title": topics.title(),
                        "topics": topics,
                    }
                )

    write_csv(
        [
            ("Alpha", "https://example.com/alpha.m3u8", "news"),
            ("Beta", "https://example.com/beta.m3u8", "movies"),
        ]
    )
    build_viewer_db(export, csv_path)
    monkeypatch.setattr(viewer, "ROOT", tmp_path)
    monkeypatch.setattr(viewer, "EXPORT_DIR", export)
    viewer._catalog.clear()
    with TestClient(viewer.app) as client:
        first = {item["name"]: item for item in client.get("/api/streams").json()["items"]}

    write_csv(
        [
            ("Beta", "https://example.com/beta.m3u8", "movies"),
            ("Alpha", "https://example.com/alpha.m3u8", "news"),
        ]
    )
    build_viewer_db(export, csv_path)
    viewer._catalog.clear()
    with TestClient(viewer.app) as client:
        second = {item["name"]: item for item in client.get("/api/streams").json()["items"]}

    assert first["Alpha"]["id"] != second["Alpha"]["id"]
    assert first["Alpha"]["favorite_key"] == second["Alpha"]["favorite_key"]
    assert first["Beta"]["favorite_key"] == second["Beta"]["favorite_key"]


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
    assert "svtv_favorites_v2" in js
    assert "FAVORITES_LEGACY_KEY" in js
    assert "MAX_FAVORITES = 100" in js
    assert "favorite-btn" in js
    assert "function toggleFavorite" in js
    assert 'params.set("favorite_keys"' in js
    assert 'params.set("ids"' not in js
    assert "FAVORITE_KEY_RE" in js
    assert "data-fav-key" in js or "dataset.favKey" in js


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


def test_selected_filters_skips_form_and_search_in_favorites_mode():
    """Favorites mode sends source + favorite_keys only — not Filters-sheet fields or q."""
    js = APP_JS.read_text(encoding="utf-8")
    start = js.index("function selectedFilters()")
    body = js[start : js.index("\n  }", start) + 4]
    fav_return = body.index("if (state.favoritesOnly)")
    form_loop = body.index("new FormData(els.filterForm)")
    search_q = body.index('params.set("q", q)')
    assert fav_return < form_loop
    assert "return params;" in body[fav_return:form_loop]
    assert search_q > form_loop
    assert 'params.set("favorite_keys"' in body[fav_return:form_loop]
