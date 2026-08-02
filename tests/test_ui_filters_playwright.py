"""Playwright UI checks — Category filters must be reachable in the browser.

BUG-010/011/012 kept slipping through API-only tests. This opens a real Chromium
page against a local uvicorn server and asserts the Category select is available
via the compact Filters sheet.
"""

from __future__ import annotations

import csv
import re
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


def _open_filter_sheet(page: Page) -> None:
    """Compact chrome keeps filters in a sheet until the Filters button is pressed."""
    toggle = page.locator("#filtersToggleBtn")
    expect(toggle).to_be_visible()
    if toggle.get_attribute("aria-expanded") != "true":
        toggle.click()
    expect(page.locator("#filterSheetPanel")).to_be_visible()
    expect(page.locator("#filter-topics")).to_be_visible()


def test_category_and_core_filters_are_visible(ui_server: str, page: Page) -> None:
    """BUG-012 regression: Category must be visible in Chromium, not only in /api/meta."""
    page.goto(ui_server, wait_until="networkidle")

    filter_bar = page.locator("#filterBar")
    expect(filter_bar).to_be_visible()
    _open_filter_sheet(page)

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

    _open_filter_sheet(page)
    page.locator("#filter-topics").select_option("movies")
    page.wait_for_function(
        "() => document.getElementById('streamListWrap').scrollTop === 0"
    )
    expect(page.locator("#streamList")).to_contain_text("Demo Movie")


def test_favorites_filter_and_reset_preserve_stars(ui_server: str, page: Page) -> None:
    """FEAT-007 / BUG-023: star by URL hash; Favorites narrows; Reset keeps stars."""
    page.goto(ui_server, wait_until="networkidle")
    page.wait_for_selector("#streamList .stream-item")

    news_row = page.locator("#streamList .stream-item").filter(has_text="Demo News")
    fav_btn = news_row.locator(".favorite-btn")
    expect(fav_btn).to_have_attribute("aria-label", "Add to favorites")
    fav_btn.click()
    expect(fav_btn).to_have_attribute("aria-label", "Remove from favorites")

    stored = page.evaluate("() => localStorage.getItem('svtv_favorites_v2')")
    assert stored is not None
    assert stored != "[]"
    keys = page.evaluate("() => JSON.parse(localStorage.getItem('svtv_favorites_v2'))")
    assert isinstance(keys, list) and len(keys) == 1
    assert re.fullmatch(r"[0-9a-f]{64}", keys[0])
    expect(fav_btn).to_have_attribute("data-fav-key", keys[0])

    page.locator("#favoritesToggleBtn").click()
    expect(page.locator("#favoritesToggleBtn")).to_have_attribute("aria-pressed", "true")
    expect(page.locator("#streamList")).to_contain_text("Demo News")
    expect(page.locator("#streamList")).not_to_contain_text("Demo Movie")

    _open_filter_sheet(page)
    page.locator("#filter-topics").select_option("movies")
    # Favorites ∩ movies is empty for this fixture.
    page.wait_for_function(
        "() => document.querySelectorAll('#streamList .stream-item').length === 0"
    )
    page.locator("#filterSheetDoneBtn").click()
    expect(page.locator("#filterSheetPanel")).to_be_hidden()

    page.locator("#resetFiltersBtnCompact").click()
    # Reset clears category but keeps Favorites mode and starred keys.
    expect(page.locator("#favoritesToggleBtn")).to_have_attribute("aria-pressed", "true")
    expect(page.locator("#streamList")).to_contain_text("Demo News")
    expect(page.locator("#streamList")).not_to_contain_text("Demo Movie")
    assert page.evaluate("() => localStorage.getItem('svtv_favorites_v2')") == stored


def test_favorites_survive_reload_and_wipe_legacy_ints(ui_server: str, page: Page) -> None:
    """BUG-023: hash favorites persist; legacy int svtv_favorites is cleared."""
    page.goto(ui_server, wait_until="networkidle")
    page.wait_for_selector("#streamList .stream-item")
    page.evaluate(
        """() => {
          localStorage.setItem('svtv_favorites', JSON.stringify([0, 1, 2]));
        }"""
    )
    page.reload(wait_until="networkidle")
    page.wait_for_selector("#streamList .stream-item")
    assert page.evaluate("() => localStorage.getItem('svtv_favorites')") is None

    page.locator("#streamList .stream-item").filter(has_text="Demo News").locator(
        ".favorite-btn"
    ).click()
    stored = page.evaluate("() => localStorage.getItem('svtv_favorites_v2')")
    page.reload(wait_until="networkidle")
    page.wait_for_selector("#streamList .stream-item")
    assert page.evaluate("() => localStorage.getItem('svtv_favorites_v2')") == stored
    news_btn = page.locator("#streamList .stream-item").filter(
        has_text="Demo News"
    ).locator(".favorite-btn")
    expect(news_btn).to_have_attribute("aria-label", "Remove from favorites")


def test_favorites_listing_is_proxy_quiet_until_play(ui_server: str, page: Page) -> None:
    """BUG-023: Favorites mode must not storm /api/proxy until a channel is clicked."""
    page.goto(ui_server, wait_until="networkidle")
    page.wait_for_selector("#streamList .stream-item")

    proxy_hits: list[str] = []

    def on_request(request) -> None:
        if "/api/proxy" in request.url:
            proxy_hits.append(request.url)

    page.on("request", on_request)

    for name in ("Demo News", "Demo Movie"):
        page.locator("#streamList .stream-item").filter(has_text=name).locator(
            ".favorite-btn"
        ).click()

    page.locator("#favoritesToggleBtn").click()
    expect(page.locator("#favoritesToggleBtn")).to_have_attribute("aria-pressed", "true")
    page.wait_for_selector("#streamList .stream-item")
    expect(page.locator("#streamList .stream-item")).to_have_count(2)
    assert proxy_hits == []

    with page.expect_request(lambda req: "/api/proxy" in req.url, timeout=10000):
        page.locator("#streamList .stream-item").filter(has_text="Demo News").click()
    assert any("/api/proxy" in url for url in proxy_hits)


def test_share_dialog_opens_with_releases_qr(ui_server: str, page: Page) -> None:
    """FEAT-008: Share opens an offline QR dialog to GitHub Releases."""
    page.goto(ui_server, wait_until="networkidle")

    page.locator("#shareBtn").click()
    dialog = page.locator("#shareDialog")
    expect(dialog).to_be_visible()
    qr = page.locator("#shareQr")
    expect(qr).to_be_visible()
    expect(qr).to_have_attribute("src", "/static/share-releases-qr.png")
    link = page.locator("#shareReleaseLink")
    expect(link).to_have_attribute(
        "href", "https://github.com/cscortes/StreamingViewerTV/releases/latest"
    )

    page.locator("#shareDialogCloseBtn").click()
    expect(dialog).to_be_hidden()


def test_status_details_toggle(ui_server: str, page: Page) -> None:
    """FEAT-004: status bar Details expands catalog/guide extras."""
    page.goto(ui_server, wait_until="networkidle")
    details_btn = page.locator("#statusDetailsBtn")
    expect(details_btn).to_be_visible()
    expect(details_btn).to_have_attribute("aria-expanded", "false")

    details_btn.click()
    expect(details_btn).to_have_attribute("aria-expanded", "true")
    expect(page.locator("body")).to_have_class(re.compile(r"status-details-open"))

    details_btn.click()
    expect(details_btn).to_have_attribute("aria-expanded", "false")


def test_narrow_hide_channels_slides_sidebar_offscreen(ui_server: str, page: Page) -> None:
    """BUG-022: rise-in animation fill must not pin sidebar transform on narrow/Android."""
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(ui_server, wait_until="networkidle")
    page.wait_for_selector("#streamList .stream-item")

    expect(page.locator("body")).to_have_class(re.compile(r"is-narrow"))
    expect(page.locator("body")).to_have_class(re.compile(r"is-phone"))
    # Phone browse uses an in-flow full-width list (layout padding may offset x slightly).
    metrics = page.evaluate(
        """() => {
          const s = document.getElementById('sidebar');
          const r = s.getBoundingClientRect();
          return {
            x: r.x,
            width: r.width,
            ratio: r.width / window.innerWidth,
            inline: document.getElementById('layout').style.getPropertyValue('--sidebar-width'),
          };
        }"""
    )
    assert metrics["x"] < 24
    assert metrics["ratio"] >= 0.9
    assert metrics["inline"] in ("", "100%")

    page.locator("#browseToggleBtn").click()
    expect(page.locator("#browseToggleBtn")).to_have_text("Show")
    expect(page.locator("body")).to_have_class(re.compile(r"watch-first"))

    page.wait_for_function(
        """() => {
          const r = document.getElementById('sidebar').getBoundingClientRect();
          return r.right <= 1;
        }"""
    )

    page.locator("#browseToggleBtn").click()
    expect(page.locator("#browseToggleBtn")).to_have_text("Hide")
    page.wait_for_function(
        """() => {
          const r = document.getElementById('sidebar').getBoundingClientRect();
          return r.x < 24 && r.width / window.innerWidth >= 0.9;
        }"""
    )


def test_narrow_search_focus_keeps_sidebar_hidden(ui_server: str, page: Page) -> None:
    """Android/narrow: focusing search must not reopen a hidden channel drawer."""
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(ui_server, wait_until="networkidle")
    page.wait_for_selector("#streamList .stream-item")

    expect(page.locator("body")).to_have_class(re.compile(r"is-narrow"))

    page.locator("#browseToggleBtn").click()
    expect(page.locator("#browseToggleBtn")).to_have_text("Show")
    expect(page.locator("body")).to_have_class(re.compile(r"watch-first"))
    page.wait_for_function(
        """() => {
          const r = document.getElementById('sidebar').getBoundingClientRect();
          return r.right <= 1;
        }"""
    )

    page.locator("#searchInput").evaluate("(el) => el.focus()")
    expect(page.locator("#searchInput")).to_be_focused()
    expect(page.locator("body")).to_have_class(re.compile(r"watch-first"))
    expect(page.locator("#browseToggleBtn")).to_have_text("Show")
    page.wait_for_function(
        """() => {
          const r = document.getElementById('sidebar').getBoundingClientRect();
          return r.right <= 1;
        }"""
    )
    assert "channels-open" not in (page.locator("body").get_attribute("class") or "")


def test_phone_more_menu_holds_overflow_actions(ui_server: str, page: Page) -> None:
    """Phone two-row chrome: Filters/Reset/Favorites/Hide inline; Fullscreen under More."""
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(ui_server, wait_until="networkidle")
    page.wait_for_selector("#streamList .stream-item")

    expect(page.locator("body")).to_have_class(re.compile(r"is-phone"))
    expect(page.locator("#phoneMoreBtn")).to_be_visible()
    expect(page.locator("#filtersToggleBtn")).to_be_visible()
    expect(page.locator("#resetFiltersBtnCompact")).to_be_visible()
    expect(page.locator("#favoritesToggleBtn")).to_be_visible()
    expect(page.locator("#browseToggleBtn")).to_be_visible()

    layout = page.evaluate(
        """() => {
          const bar = document.getElementById('filterBar');
          const search = document.querySelector('.search-wrap');
          const actions = document.getElementById('compactActions');
          const panel = document.getElementById('phoneMorePanel');
          const full = document.getElementById('fullscreenBtn');
          const br = bar.getBoundingClientRect();
          const sr = search.getBoundingClientRect();
          const ar = actions.getBoundingClientRect();
          return {
            areas: getComputedStyle(bar).gridTemplateAreas.replace(/\\s+/g, ' ').trim(),
            actionsAboveSearch: ar.bottom <= sr.top + 1,
            searchFullWidth: sr.width / br.width >= 0.9,
            fullscreenInMore: Boolean(panel && full && full.parentElement === panel),
            resetInActions: document.getElementById('resetFiltersBtnCompact')?.parentElement === actions,
            favInActions: document.getElementById('favoritesToggleBtn')?.parentElement === actions,
          };
        }"""
    )
    assert "actions" in layout["areas"] and "search" in layout["areas"]
    assert layout["actionsAboveSearch"]
    assert layout["searchFullWidth"]
    assert layout["fullscreenInMore"]
    assert layout["resetInActions"]
    assert layout["favInActions"]

    page.locator("#phoneMoreBtn").click()
    expect(page.locator("body")).to_have_class(re.compile(r"phone-more-open"))
    expect(page.locator("#fullscreenBtn")).to_be_visible()
    page.locator("#phoneMoreBtn").click()
    expect(page.locator("body")).not_to_have_class(re.compile(r"phone-more-open"))


def test_phone_browse_channel_names_are_readable(ui_server: str, page: Page) -> None:
    """Phone browse must not clamp the drawer to the desktop ~220px sidebar width."""
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(ui_server, wait_until="networkidle")
    page.wait_for_selector("#streamList .stream-item")

    expect(page.locator("body")).to_have_class(re.compile(r"is-phone"))
    expect(page.locator("body")).not_to_have_class(re.compile(r"watch-first"))

    info = page.evaluate(
        """() => {
          const item = document.querySelector('#streamList .stream-item .stream-title-row strong');
          const meta = document.querySelector('#streamList .stream-item .stream-meta');
          const sidebar = document.getElementById('sidebar');
          const stage = document.getElementById('stage');
          return {
            title: item ? item.textContent : '',
            metaWidth: meta ? meta.getBoundingClientRect().width : 0,
            sidebarWidth: sidebar.getBoundingClientRect().width,
            stageDisplay: stage ? getComputedStyle(stage).display : '',
            inline: document.getElementById('layout').style.getPropertyValue('--sidebar-width').trim(),
          };
        }"""
    )
    assert info["stageDisplay"] == "none"
    assert info["sidebarWidth"] >= 350
    assert info["metaWidth"] >= 220
    assert info["title"]
    assert info["inline"] in ("", "100%")


def test_tablet_keeps_inline_toolbar_actions(ui_server: str, page: Page) -> None:
    """Tablet narrow mode should not use the phone overflow menu."""
    page.set_viewport_size({"width": 820, "height": 1180})
    page.goto(ui_server, wait_until="networkidle")
    page.wait_for_selector("#streamList .stream-item")

    expect(page.locator("body")).to_have_class(re.compile(r"is-narrow"))
    expect(page.locator("body")).not_to_have_class(re.compile(r"is-phone"))
    expect(page.locator("#phoneMoreBtn")).to_be_hidden()
    expect(page.locator("#resetFiltersBtnCompact")).to_be_visible()
    expect(page.locator("#favoritesToggleBtn")).to_be_visible()
    expect(page.locator("#fullscreenBtn")).to_be_visible()
    expect(page.locator("#browseToggleBtn")).to_have_text("Hide channels")


def test_fullscreen_falls_back_to_css_immersive(ui_server: str, page: Page) -> None:
    """When Fullscreen API rejects (typical Android WebView), use body.is-fullscreen."""
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(ui_server, wait_until="networkidle")
    page.wait_for_selector("#streamList .stream-item")

    page.evaluate(
        """() => {
          const reject = () => Promise.reject(new Error('fullscreen blocked'));
          Element.prototype.requestFullscreen = reject;
          HTMLVideoElement.prototype.requestFullscreen = reject;
          const video = document.getElementById('video');
          if (video) video.webkitEnterFullscreen = undefined;
        }"""
    )

    page.locator("#phoneMoreBtn").click()
    page.locator("#fullscreenBtn").click()
    expect(page.locator("body")).to_have_class(re.compile(r"is-fullscreen"))
    expect(page.locator("#fullscreenBtn")).to_have_text("Exit fullscreen")

    # Filter bar is hidden while immersive — toggle via the same keyboard shortcut.
    page.keyboard.press("f")
    expect(page.locator("body")).not_to_have_class(re.compile(r"is-fullscreen"))
    expect(page.locator("#fullscreenBtn")).to_have_text("Fullscreen")


def test_filters_while_watching_keeps_sheet_usable(ui_server: str, page: Page) -> None:
    """BUG-026: Filters while playing must not exit watch-first or leave UI stuck."""
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(ui_server, wait_until="networkidle")
    page.wait_for_selector("#streamList .stream-item")

    expect(page.locator("body")).to_have_class(re.compile(r"is-phone"))

    page.locator("#streamList .stream-item").first.click()
    page.locator("#browseToggleBtn").click()
    expect(page.locator("body")).to_have_class(re.compile(r"watch-first"))

    play_state = page.evaluate(
        """async () => {
          const v = document.getElementById('video');
          const c = document.createElement('canvas');
          c.width = 64;
          c.height = 64;
          c.getContext('2d').fillRect(0, 0, 64, 64);
          v.srcObject = c.captureStream(10);
          await v.play().catch(() => {});
          return { paused: v.paused };
        }"""
    )
    assert play_state["paused"] is False

    page.locator("#filtersToggleBtn").click()
    expect(page.locator("body")).to_have_class(re.compile(r"filter-sheet-open"))
    # Must stay in watch mode so phone does not display:none the playing stage.
    expect(page.locator("body")).to_have_class(re.compile(r"watch-first"))
    expect(page.locator("body")).to_have_class(re.compile(r"overlay-suspend-video"))
    expect(page.locator("#filterSheetPanel")).to_be_visible()
    expect(page.locator("#filter-topics")).to_be_visible()

    stage = page.evaluate(
        """() => ({
          display: getComputedStyle(document.getElementById('stage')).display,
          videoPaused: document.getElementById('video').paused,
          videoVisibility: getComputedStyle(document.getElementById('video')).visibility,
        })"""
    )
    assert stage["display"] != "none"
    assert stage["videoPaused"] is True
    assert stage["videoVisibility"] == "hidden"

    page.locator("#filter-topics").select_option("news")
    page.locator("#filterSheetDoneBtn").click()
    expect(page.locator("body")).not_to_have_class(re.compile(r"filter-sheet-open"))
    expect(page.locator("body")).not_to_have_class(re.compile(r"overlay-suspend-video"))
    expect(page.locator("body")).to_have_class(re.compile(r"watch-first"))

    # UI remains interactive after closing the sheet.
    page.locator("#browseToggleBtn").click()
    expect(page.locator("body")).not_to_have_class(re.compile(r"watch-first"))
    expect(page.locator("#streamList .stream-item").first).to_be_visible()
