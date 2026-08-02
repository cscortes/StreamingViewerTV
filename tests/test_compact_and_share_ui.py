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
    assert 'id="channelsToggleBtn"' in html
    assert 'id="browseToggleBtn"' in html
    assert 'id="statusDetailsBtn"' in html
    assert 'id="moreControlsBtn"' in html

    assert "function openFilterSheet" in js
    assert "function closeFilterSheet" in js
    assert "function placeFilterForm" in js
    assert "NARROW_MQ" in js
    assert "matchMedia" in js
    assert "status-details-open" in js or "statusDetailsBtn" in js

    assert "body.ui-chrome-compact" in css
    assert "filter-sheet-open" in css
    assert "channels-open" in css


def test_narrow_breakpoint_driven_by_match_media():
    """Do not hardcode phone-only CSS that breaks the desktop docked sidebar."""
    js = APP_JS.read_text(encoding="utf-8")
    assert "const NARROW_MQ" in js or "NARROW_MQ =" in js
    assert "matchMedia(" in js
    assert "function isNarrow" in js
    assert "NARROW_MQ.matches" in js


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
