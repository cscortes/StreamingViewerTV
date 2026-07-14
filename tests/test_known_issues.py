"""Regression tests for known StreamingViewerTV failures."""

from __future__ import annotations

import csv
from pathlib import Path
from urllib.parse import urljoin

import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response  # respx still types mocked returns as httpx.Response

from builder.probe import sanitize_text
from stream_viewer import app as viewer
from stream_viewer.app import (
    available_sources,
    create_proxy_session,
    proxy_path,
    resolve_hls_uri,
    resolve_source,
    rewrite_m3u8,
    video_quality_rank,
)
from tests.db_fixtures import build_viewer_db


LONG_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    + ("a" * 400)
    + ".signature"
)


@pytest.fixture(autouse=True)
def _reset_proxy_state():
    with viewer._proxy_lock:
        viewer._proxy_sessions.clear()
    yield
    with viewer._proxy_lock:
        viewer._proxy_sessions.clear()


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    export = tmp_path / "iptv_export"
    export.mkdir()
    path = export / "streams.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
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
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "name": "Demo News",
                "url": "https://jmp2.example/short.m3u8",
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
        writer.writerow(
            {
                "name": "Demo Movie",
                "url": "https://cdn.example/movie.m3u8",
                "tvg_id": "movie",
                "tvg_logo": "",
                "group_title": "Movies",
                "http_referrer": "https://referrer.example/",
                "http_user_agent": "CustomAgent/1.0",
                "country_name": "Canada",
                "language_name": "French",
                "topics": "movies",
                "video_quality": "1080p",
                "stream_quality": "okay",
                "maturity": "Family",
            }
        )
    epg_dir = export / "epg"
    epg_dir.mkdir(exist_ok=True)
    (epg_dir / "stub.xml").write_text(
        '<?xml version="1.0"?><tv></tv>\n',
        encoding="utf-8",
    )
    build_viewer_db(export, path)
    return path


@pytest.fixture
def client(sample_csv: Path, monkeypatch: pytest.MonkeyPatch):
    export = sample_csv.parent
    root = export.parent
    monkeypatch.setattr(viewer, "ROOT", root)
    monkeypatch.setattr(viewer, "EXPORT_DIR", export)
    viewer._catalog.clear()
    viewer._catalog.update(
        {"source": None, "streams": [], "by_id": {}, "filters": {}, "total": 0}
    )
    with TestClient(viewer.app) as test_client:
        yield test_client


class TestImportCsvNulBytes:
    """Prepare-stage CSV import used to crash with: _csv.Error: line contains NUL."""

    def test_import_streams_csv_strips_nul_bytes(self, tmp_path: Path):
        from builder.import_catalog import import_streams_csv, init_schema
        from stream_viewer import db as catalog_db

        path = tmp_path / "streams_probed.csv"
        path.write_bytes(
            b"name,url,group_title\n"
            b"Bad\x00Channel,https://example.com/a.m3u8,News\n"
            b"Good Channel,https://example.com/b.m3u8,Sports\n"
        )
        db_path = tmp_path / "viewer.db"
        conn = catalog_db.connect(db_path)
        try:
            init_schema(conn)
            count = import_streams_csv(conn, path)
            streams = catalog_db.load_streams(conn)
        finally:
            conn.close()
        assert count == 2
        assert streams[0]["name"] == "BadChannel"


class TestProbeNoteSanitization:
    """SSL/TLS errors used to embed NULs into probe_notes and corrupt the CSV."""

    def test_sanitize_removes_nuls_and_binary(self):
        dirty = "error: G\x00\x15\x00\x00" + "\x00" * 5 + " boom"
        clean = sanitize_text(dirty)
        assert "\x00" not in clean
        assert "error:" in clean
        assert "boom" in clean


class TestProxyUriLength:
    """Long stream URLs in /api/proxy?url=... caused local 414 Request-URI Too Long."""

    def test_play_url_uses_short_session_path(self, client: TestClient):
        response = client.get("/api/streams/0")
        assert response.status_code == 200
        play_url = response.json()["play_url"]
        assert play_url.startswith("/api/proxy/s/")
        assert "url=" not in play_url
        assert len(play_url) < 120

    def test_rewritten_playlist_entries_stay_short(self):
        session = create_proxy_session(referrer="", user_agent="test")
        base = (
            "https://stitcher.example/v2/channel/abc/master.m3u8?"
            f"authToken={LONG_TOKEN}&us_privacy=1YNY"
        )
        body = (
            "#EXTM3U\n"
            "#EXT-X-STREAM-INF:BANDWIDTH=2000000\n"
            f"2142297/playlist.m3u8?authToken={LONG_TOKEN}&us_privacy=1YNY\n"
        )
        rewritten = rewrite_m3u8(body, base, session)
        for line in rewritten.splitlines():
            if not line or line.startswith("#"):
                continue
            assert line.startswith("/api/proxy/s/")
            assert len(line) < 120
            assert LONG_TOKEN not in line


class TestRedirectBaseUrlBug:
    """
    Recreates the jmp2 → Pluto failure:

    Master fetch follows redirects and returns 200, but playlist child URIs were
    resolved against the *original* jmp2.uk URL. That invented
    https://jmp2.uk/2142297/playlist.m3u8?<huge-token>, which jmp2 rejects with 414.
    """

    def test_wrong_base_recreates_414_host(self):
        redirector = "https://jmp2.example/short.m3u8"
        final = (
            "https://stitcher.example/v2/channel/abc/master.m3u8?"
            f"authToken={LONG_TOKEN}"
        )
        child = f"2142297/playlist.m3u8?authToken={LONG_TOKEN}"

        wrong = resolve_hls_uri(redirector, child)
        right = resolve_hls_uri(final, child)

        assert wrong.startswith("https://jmp2.example/2142297/")
        assert right.startswith("https://stitcher.example/")
        assert len(wrong) > 400

    @respx.mock
    def test_proxy_uses_final_url_after_redirect(self, client: TestClient):
        redirector = "https://jmp2.example/short.m3u8"
        final = (
            "https://stitcher.example/v2/channel/abc/master.m3u8?"
            f"authToken={LONG_TOKEN}"
        )
        child_path = f"2142297/playlist.m3u8?authToken={LONG_TOKEN}"
        child_ok = urljoin(final, child_path)
        child_bad = urljoin(redirector, child_path)

        master_body = (
            "#EXTM3U\n"
            "#EXT-X-STREAM-INF:BANDWIDTH=2000000\n"
            f"{child_path}\n"
        )
        media_body = (
            "#EXTM3U\n"
            "#EXT-X-TARGETDURATION:6\n"
            "#EXTINF:6.0,\n"
            "segment000.ts\n"
        )

        respx.get(redirector).mock(
            return_value=Response(302, headers={"location": final})
        )
        respx.get(final).mock(
            return_value=Response(
                200,
                text=master_body,
                headers={"content-type": "application/vnd.apple.mpegurl"},
            )
        )
        respx.get(child_bad).mock(return_value=Response(414, text="URI Too Long"))
        respx.get(child_ok).mock(
            return_value=Response(
                200,
                text=media_body,
                headers={"content-type": "application/vnd.apple.mpegurl"},
            )
        )
        segment = urljoin(child_ok, "segment000.ts")
        respx.get(segment).mock(
            return_value=Response(
                200,
                content=b"FAKE_TS",
                headers={"content-type": "video/mp2t"},
            )
        )

        play = client.get("/api/streams/0").json()["play_url"]
        master = client.get(play)
        assert master.status_code == 200, master.text
        rewritten = master.text
        assert "/api/proxy/s/" in rewritten

        child_proxy = next(
            line for line in rewritten.splitlines() if line.startswith("/api/proxy/s/")
        )
        parts = child_proxy.split("/")
        session_id, url_id = parts[-2], parts[-1]
        target = viewer._proxy_sessions[session_id]["urls"][url_id]
        assert target.startswith("https://stitcher.example/")
        assert not target.startswith("https://jmp2.example/2142297")

        child_resp = client.get(child_proxy)
        assert child_resp.status_code == 200, child_resp.text
        assert "/api/proxy/s/" in child_resp.text


class TestUpstream414MappedTo502:
    """Upstream 414 used to be forwarded, making logs look like a local URI problem."""

    @respx.mock
    def test_upstream_414_becomes_502(self, client: TestClient):
        respx.get("https://jmp2.example/short.m3u8").mock(
            return_value=Response(414, text="Request-URI Too Long")
        )
        play = client.get("/api/streams/0").json()["play_url"]
        response = client.get(play)
        assert response.status_code == 502
        assert "too long" in response.json()["detail"].lower()


class TestUpstreamRetries:
    """Transient upstream failures should be retried by the proxy."""

    @respx.mock
    def test_retries_transient_502_then_succeeds(self, client: TestClient):
        master = "https://jmp2.example/short.m3u8"
        body = "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1000\nmedia.m3u8\n"
        respx.get(master).mock(
            side_effect=[
                Response(502, text="Bad Gateway"),
                Response(502, text="Bad Gateway"),
                Response(
                    200,
                    text=body,
                    headers={"content-type": "application/vnd.apple.mpegurl"},
                ),
            ]
        )
        play = client.get("/api/streams/0").json()["play_url"]
        response = client.get(play)
        assert response.status_code == 200, response.text
        assert response.text.lstrip().startswith("#EXTM3U")

    @respx.mock
    def test_dead_upstream_404_is_not_silently_ok(self, client: TestClient):
        respx.get("https://jmp2.example/short.m3u8").mock(
            return_value=Response(404, text="missing")
        )
        play = client.get("/api/streams/0").json()["play_url"]
        response = client.get(play)
        assert response.status_code == 502
        assert "404" in response.json()["detail"]


class TestMinQualityFilters:
    def test_video_quality_is_at_least(self, client: TestClient):
        low = client.get("/api/streams", params={"video_quality": "720p"}).json()
        high = client.get("/api/streams", params={"video_quality": "1080p"}).json()
        assert low["total"] == 2
        assert high["total"] == 1
        assert high["items"][0]["name"] == "Demo Movie"

    def test_stream_quality_is_at_least(self, client: TestClient):
        ok = client.get("/api/streams", params={"stream_quality": "okay"}).json()
        excellent = client.get(
            "/api/streams", params={"stream_quality": "excellent"}
        ).json()
        assert ok["total"] == 2
        assert excellent["total"] == 1

    def test_video_rank_helpers(self):
        assert video_quality_rank("1080p") > video_quality_rank("720p")
        assert video_quality_rank("HD") == 720


def test_index_html_server_renders_category_filter(client: TestClient):
    """BUG-012: Category controls must be in the initial HTML, not JS-only."""
    html = client.get("/").text
    assert 'name="topics"' in html
    assert "Category" in html
    assert 'id="filter-topics"' in html
    assert "news" in html.lower() or "movies" in html.lower()


def test_index_html_shows_current_version_in_status_bar(client: TestClient):
    """The running app version (single source: stream_viewer/_version.py) must be visible."""
    html = client.get("/").text
    assert "status-version" in html
    assert viewer.__version__ in html


class TestCategoryFilters:
    """BUG-010/011: Category (topics) must appear in /api/meta with stream counts."""

    def test_meta_includes_category_filter(self, client: TestClient):
        meta = client.get("/api/meta").json()
        filters = meta["filters"]
        assert "topics" in filters
        assert filters["topics"]["label"] == "Category"
        values = {item["value"] for item in filters["topics"]["options"]}
        assert "news" in values
        assert "movies" in values
        for option in filters["topics"]["options"]:
            assert option["count"] >= 1

        news = client.get("/api/streams", params={"topics": "news"}).json()
        assert news["total"] == 1
        assert news["items"][0]["name"] == "Demo News"

    def test_index_html_server_renders_category_filter(self, client: TestClient):
        """BUG-012: Category controls must be in the initial HTML, not JS-only."""
        html = client.get("/").text
        assert 'name="topics"' in html
        assert "Category" in html
        assert 'id="filter-topics"' in html
        assert "news" in html.lower()
        assert "movies" in html.lower()


class TestStaleCatalogSource:
    """BUG-005: cookie still requesting streams_probed.csv after viewer.db migration."""

    def test_stale_csv_source_falls_back_to_viewer_db(self, client: TestClient, sample_csv: Path):
        export = sample_csv.parent
        assert (export / "viewer.db").is_file()
        assert not (export / "streams_probed.csv").is_file()

        sources = available_sources()
        assert [item["id"] for item in sources] == ["viewer.db"]
        assert resolve_source("streams_probed.csv").name == "viewer.db"

        meta = client.get("/api/meta", params={"source": "streams_probed.csv"})
        assert meta.status_code == 200
        assert meta.json()["source"] == "viewer.db"

        detail = client.get("/api/streams/0", params={"source": "streams_probed.csv"})
        assert detail.status_code == 200
        payload = detail.json()
        assert payload["name"] == "Demo News"
        assert payload["play_url"]

        listed = client.get("/api/streams", params={"source": "streams_probed.csv"})
        assert listed.status_code == 200
        assert listed.json()["source"] == "viewer.db"
        assert listed.json()["total"] >= 1


def test_ui_rewrites_stale_source_prefs():
    """BUG-005: frontend must refresh prefs when server returns a different source."""
    root = Path(__file__).resolve().parents[1]
    js = (root / "stream_viewer" / "static" / "app.js").read_text(encoding="utf-8")
    assert "if (source && data.source && source !== data.source)" in js
    assert "savePrefs()" in js
