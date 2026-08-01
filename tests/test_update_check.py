"""FEAT-006: update-available check against GitHub Releases."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response

from stream_viewer import app as viewer
from stream_viewer.app import is_newer_version, parse_semver
from tests.db_fixtures import build_viewer_db

ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "stream_viewer" / "static" / "app.js"
INDEX_HTML = ROOT / "stream_viewer" / "templates" / "index.html"
GITHUB_LATEST = viewer.GITHUB_RELEASES_LATEST_URL


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1.2.3", (1, 2, 3)),
        ("v0.4.0", (0, 4, 0)),
        ("V10.0.1", (10, 0, 1)),
        ("1.2", None),
        ("nope", None),
        ("", None),
    ],
)
def test_parse_semver(raw: str, expected: tuple[int, int, int] | None):
    assert parse_semver(raw) == expected


@pytest.mark.parametrize(
    ("latest", "current", "newer"),
    [
        ("0.5.0", "0.4.0", True),
        ("0.4.1", "0.4.0", True),
        ("1.0.0", "0.9.9", True),
        ("0.4.0", "0.4.0", False),
        ("0.3.9", "0.4.0", False),
        ("v0.5.0", "0.4.0", True),
        ("bad", "0.4.0", False),
        ("0.5.0", "bad", False),
    ],
)
def test_is_newer_version(latest: str, current: str, newer: bool):
    assert is_newer_version(latest, current) is newer


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    export = tmp_path / "iptv_export"
    export.mkdir()
    (export / "epg").mkdir()
    csv_path = export / "streams_enriched.csv"
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
    viewer.clear_update_cache()
    with TestClient(viewer.app) as test_client:
        yield test_client
    viewer.clear_update_cache()


def _release_payload(tag: str, html_url: str | None = None) -> dict:
    return {
        "tag_name": tag,
        "html_url": html_url
        or f"https://github.com/cscortes/StreamingViewerTV/releases/tag/{tag}",
    }


@respx.mock
def test_api_update_reports_newer_release(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(viewer, "__version__", "0.4.0")
    respx.get(GITHUB_LATEST).mock(
        return_value=Response(200, json=_release_payload("v0.5.0"))
    )
    data = client.get("/api/update").json()
    assert data["current"] == "0.4.0"
    assert data["latest"] == "0.5.0"
    assert data["update_available"] is True
    assert data["release_url"].endswith("/v0.5.0")


@respx.mock
def test_api_update_same_version_not_available(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(viewer, "__version__", "0.5.0")
    respx.get(GITHUB_LATEST).mock(
        return_value=Response(200, json=_release_payload("v0.5.0"))
    )
    data = client.get("/api/update").json()
    assert data["latest"] == "0.5.0"
    assert data["update_available"] is False


@respx.mock
def test_api_update_older_remote_not_available(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(viewer, "__version__", "0.5.0")
    respx.get(GITHUB_LATEST).mock(
        return_value=Response(200, json=_release_payload("v0.4.0"))
    )
    data = client.get("/api/update").json()
    assert data["update_available"] is False


@respx.mock
def test_api_update_network_error_is_fail_soft(client: TestClient):
    respx.get(GITHUB_LATEST).mock(side_effect=ConnectionError("offline"))
    data = client.get("/api/update").json()
    assert data["current"] == viewer.__version__
    assert data["latest"] is None
    assert data["update_available"] is False
    assert data["release_url"] is None


@respx.mock
def test_api_update_caches_successful_response(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(viewer, "__version__", "0.4.0")
    route = respx.get(GITHUB_LATEST).mock(
        return_value=Response(200, json=_release_payload("v0.5.0"))
    )
    first = client.get("/api/update").json()
    second = client.get("/api/update").json()
    assert first == second
    assert first["update_available"] is True
    assert route.call_count == 1


def test_index_html_has_update_available_chip(client: TestClient):
    html = client.get("/").text
    assert 'id="updateAvailable"' in html
    assert 'id="updateAvailableLink"' in html
    assert 'id="updateAvailableDismiss"' in html
    assert 'id="statusVersionValue"' in html


def test_update_check_ui_wiring_present():
    html = INDEX_HTML.read_text(encoding="utf-8")
    js = APP_JS.read_text(encoding="utf-8")
    assert 'id="updateAvailable"' in html
    assert "function checkForUpdate" in js
    assert 'fetch("/api/update")' in js
    assert "dismissedUpdateVersion" in js
    assert "showUpdateNotice" in js
    assert "checkForUpdate()" in js
