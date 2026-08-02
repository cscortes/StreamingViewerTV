"""FEAT-004 compact chrome + FEAT-008 share dialog UI contracts."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "stream_viewer" / "static" / "app.js"
APP_CSS = ROOT / "stream_viewer" / "static" / "app.css"
INDEX_HTML = ROOT / "stream_viewer" / "templates" / "index.html"
SHARE_QR = ROOT / "stream_viewer" / "static" / "share-releases-qr.png"
RELEASES_LATEST = "https://github.com/cscortes/StreamingViewerTV/releases/latest"


def test_compact_chrome_toolbar_wired():
    html = INDEX_HTML.read_text(encoding="utf-8")
    js = APP_JS.read_text(encoding="utf-8")
    css = APP_CSS.read_text(encoding="utf-8")

    assert 'class="ui-chrome-compact"' in html or "ui-chrome-compact" in html
    assert 'id="filtersToggleBtn"' in html
    assert 'id="filterSheetPanel"' in html
    assert 'id="channelsToggleBtn"' not in html
    assert 'id="browseToggleBtn"' in html
    assert 'id="showSidebarBtn"' in html
    assert 'id="statusDetailsBtn"' in html
    assert 'id="fullscreenBtn"' in html
    assert 'id="moreControlsBtn"' not in html
    assert 'id="theaterBtn"' not in html
    assert 'id="openRaw"' not in html
    assert 'id="viewControls"' not in html

    assert "function openFilterSheet" in js
    assert "function closeFilterSheet" in js
    assert "function placeFilterForm" in js
    assert "NARROW_MQ" in js
    assert "matchMedia" in js
    assert "status-details-open" in js or "statusDetailsBtn" in js
    assert "channelsToggleBtn" not in js
    assert "moreControlsBtn" not in js
    assert "theaterBtn" not in js
    assert "openRaw" not in js

    assert "body.ui-chrome-compact" in css
    assert "filter-sheet-open" in css
    assert "channels-open" in css
    assert "#channelsToggleBtn" not in css
    assert ".more-btn" not in css
    assert ".view-controls" not in css


def test_compact_actions_order_and_share_beside_details():
    html = INDEX_HTML.read_text(encoding="utf-8")
    compact = html[html.index('id="compactActions"') : html.index("favorites-hint")]
    assert compact.index("filtersToggleBtn") < compact.index("resetFiltersBtnCompact")
    assert compact.index("resetFiltersBtnCompact") < compact.index("favoritesToggleBtn")
    assert compact.index("favoritesToggleBtn") < compact.index("browseToggleBtn")
    assert compact.index("browseToggleBtn") < compact.index("fullscreenBtn")
    assert compact.index("fullscreenBtn") < compact.index("phoneMoreBtn")
    assert "shareBtn" not in compact
    assert 'id="fullscreenBtn"' in compact
    assert 'id="phoneMoreBtn"' in compact
    assert 'id="phoneMorePanel"' in compact

    now = html[html.index('id="playerFrame"') : html.index('id="playerStatus"')]
    assert 'id="nowPlaying"' in now
    assert 'id="fullscreenBtn"' not in now

    footer = html[html.index('id="statusBar"') :]
    assert footer.index("shareBtn") < footer.index("statusDetailsBtn")


def test_narrow_breakpoint_driven_by_match_media():
    """Do not hardcode phone-only CSS that breaks the desktop docked sidebar."""
    js = APP_JS.read_text(encoding="utf-8")
    assert "const NARROW_MQ" in js or "NARROW_MQ =" in js
    assert "matchMedia(" in js
    assert "function isNarrow" in js
    assert "NARROW_MQ.matches" in js


def test_phone_tier_overflow_menu_wired():
    """Phones get is-phone + More overflow; tablets stay on shared is-narrow chrome."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    js = APP_JS.read_text(encoding="utf-8")
    css = APP_CSS.read_text(encoding="utf-8")

    assert 'id="phoneMoreBtn"' in html
    assert 'id="phoneMorePanel"' in html
    assert "phone-overflow-item" in html

    assert "const PHONE_MQ" in js or "PHONE_MQ =" in js
    assert "function isPhone" in js
    assert "function placePhoneOverflowItems" in js
    assert "function openPhoneMoreMenu" in js
    assert "function closePhoneMoreMenu" in js
    assert "function clearLayoutSidebarWidthVar" in js
    assert 'classList.toggle("is-phone"' in js or "is-phone" in js
    assert "clearLayoutSidebarWidthVar" in js
    assert "els.fullscreenBtn" in js[js.index("function phoneOverflowItems") : js.index("function closePhoneMoreMenu")]

    assert "body.is-phone" in css
    assert ".phone-more-panel" in css
    assert 'grid-template-areas:\n    "actions"\n    "search"' in css or (
        'grid-template-areas:' in css and '"actions"' in css and '"search"' in css
    )
    assert "body.is-phone.ui-chrome-compact .filter-bar" in css
    assert "body.is-phone.watch-first .player-frame" in css
    assert "body.is-phone:not(.watch-first) .sidebar" in css
    assert "body.is-phone:not(.watch-first) .stage" in css
    assert "min-height: 0" in css
    assert "background: var(--ink-soft)" in css


def test_fullscreen_fallback_wired():
    """Android WebView needs custom-view chrome + JS CSS fallback for Fullscreen."""
    js = APP_JS.read_text(encoding="utf-8")
    main = (
        ROOT
        / "android"
        / "app"
        / "src"
        / "main"
        / "java"
        / "com"
        / "streamingviewertv"
        / "app"
        / "MainActivity.kt"
    ).read_text(encoding="utf-8")

    assert "function enterCssFullscreen" in js
    assert "function requestDomFullscreen" in js
    assert "function toggleFullscreen" in js
    assert "webkitEnterFullscreen" in js
    assert "dataset.cssFullscreen" in js

    assert "onShowCustomView" in main
    assert "onHideCustomView" in main
    assert "enterImmersiveMode" in main


def test_filters_while_playing_does_not_exit_watch_first():
    """BUG-026: Filters must overlay watch mode and suspend the video surface."""
    js = APP_JS.read_text(encoding="utf-8")
    css = APP_CSS.read_text(encoding="utf-8")

    assert "function suspendVideoForOverlay" in js
    assert "function resumeVideoAfterOverlay" in js
    assert "overlay-suspend-video" in js
    assert "overlay-suspend-video" in css
    assert "body.overlay-suspend-video #video" in css
    assert "BUG-026" in js
    # Filters click must not tear down watch-first before opening the sheet.
    click_idx = js.index('filtersToggleBtn?.addEventListener("click"')
    click_block = js[click_idx : click_idx + 120]
    assert "toggleFilterSheet()" in click_block
    assert "exitWatchFirst()" not in click_block
    assert "suspendVideoForOverlay()" in js[js.index("function openFilterSheet") :]

def test_rise_in_animation_does_not_pin_sidebar_transform():
    """BUG-022: forwards fill on rise-in kept translateY(0) and blocked hide/show."""
    css = APP_CSS.read_text(encoding="utf-8")
    assert "animation: rise-in 420ms ease backwards" in css
    assert "animation: rise-in 420ms ease both" not in css
    assert "body.watch-first .sidebar" in css
    assert "animation: none" in css


def test_share_dialog_wiring_and_qr_asset():
    html = INDEX_HTML.read_text(encoding="utf-8")
    js = APP_JS.read_text(encoding="utf-8")

    assert 'id="shareBtn"' in html
    assert 'id="shareDialog"' in html
    assert 'id="shareQr"' in html
    assert "/static/share-releases-qr.png" in html
    assert RELEASES_LATEST in html
    assert SHARE_QR.is_file()
    assert SHARE_QR.stat().st_size > 0

    assert "function openShareDialog" in js
    assert "function closeShareDialog" in js
    assert "function toggleShareDialog" in js
    assert "share-dialog-open" in js
