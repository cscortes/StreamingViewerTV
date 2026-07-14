"""Playwright UI checks — Category filters must be visible in the browser.

BUG-010/011/012 kept slipping through API-only tests. This opens a real Chromium
page against a local uvicorn server and asserts the Category select is on-screen.
"""

from __future__ import annotations

import csv
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import Page, expect

from stream_viewer import app as viewer
from tests.db_fixtures import build_viewer_db

pytestmark = pytest.mark.ui


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _write_streams_csv(path: Path) -> None:
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
                "url": "https://example.com/news.m3u8",
                "tvg_id": "news",
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
                "url": "https://example.com/movie.m3u8",
                "tvg_id": "movie",
                "tvg_logo": "",
                "group_title": "Movies",
                "http_referrer": "",
                "http_user_agent": "",
                "country_name": "Canada",
                "language_name": "French",
                "topics": "movies",
                "video_quality": "1080p",
                "stream_quality": "okay",
                "maturity": "Family",
            }
        )


@pytest.fixture()
def ui_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Serve a tiny viewer.db catalog over uvicorn for browser tests."""
    export = tmp_path / "iptv_export"
    export.mkdir()
    (export / "epg").mkdir()
    csv_path = export / "streams.csv"
    _write_streams_csv(csv_path)
    build_viewer_db(export, csv_path)

    monkeypatch.setattr(viewer, "ROOT", tmp_path)
    monkeypatch.setattr(viewer, "EXPORT_DIR", export)
    viewer._catalog.clear()
    viewer._catalog.update(
        {"source": None, "streams": [], "by_id": {}, "filters": {}, "total": 0}
    )

    port = _free_port()
    config = uvicorn.Config(
        viewer.app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="ui-uvicorn", daemon=True)
    thread.start()

    deadline = time.time() + 15
    while time.time() < deadline:
        if server.started:
            break
        time.sleep(0.05)
    else:
        server.should_exit = True
        thread.join(timeout=5)
        raise RuntimeError("uvicorn failed to start for Playwright UI test")

    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_category_and_core_filters_are_visible(ui_server: str, page: Page) -> None:
    """BUG-012 regression: Category must be visible in Chromium, not only in /api/meta."""
    page.goto(ui_server, wait_until="networkidle")

    filter_bar = page.locator("#filterBar")
    expect(filter_bar).to_be_visible()

    category = page.locator("#filter-topics")
    expect(category).to_be_visible()
    expect(page.locator('label[for="filter-topics"]')).to_contain_text("Category")

    box = category.bounding_box()
    assert box is not None
    assert box["width"] >= 80
    assert box["height"] >= 24

    # Options exist and include seeded categories.
    values = category.locator("option").evaluate_all(
        "els => els.map(el => el.value).filter(Boolean)"
    )
    assert "news" in values
    assert "movies" in values

    # Sibling filters that the empty-form bug also hid.
    for field in ("country_name", "language_name", "video_quality", "stream_quality"):
        select = page.locator(f"#filter-{field}")
        expect(select).to_be_visible()
        select_box = select.bounding_box()
        assert select_box is not None
        assert select_box["height"] >= 24

    # Selecting a category must narrow the sidebar list.
    category.select_option("news")
    page.wait_for_function(
        """() => {
          const items = document.querySelectorAll('#streamList .stream-item, #streamList button');
          return items.length >= 1;
        }"""
    )
    expect(page.locator("#streamList")).to_contain_text("Demo News")


def test_filter_change_jumps_stream_list_to_top(ui_server: str, page: Page) -> None:
    """FEAT: filter changes must scroll the left list back to the top."""
    page.goto(ui_server, wait_until="networkidle")
    page.wait_for_selector("#streamList .stream-item")

    # Make the wrap scrollable and push it off the top.
    page.evaluate(
        """() => {
          const wrap = document.getElementById('streamListWrap');
          wrap.style.maxHeight = '100px';
          wrap.style.overflow = 'auto';
          // Pad so scrollTop can be non-zero even with few streams.
          const pad = document.createElement('div');
          pad.id = 'scrollPad';
          pad.style.height = '400px';
          wrap.appendChild(pad);
          wrap.scrollTop = 250;
        }"""
    )
    assert page.evaluate("() => document.getElementById('streamListWrap').scrollTop") > 0

    page.locator("#filter-topics").select_option("movies")
    page.wait_for_function(
        "() => document.getElementById('streamListWrap').scrollTop === 0"
    )
    expect(page.locator("#streamList")).to_contain_text("Demo Movie")
