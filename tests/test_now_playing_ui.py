"""UI contract checks for always-visible Now-playing placeholders (BUG-003 / BUG-004)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "stream_viewer" / "static" / "app.js"
INDEX_HTML = ROOT / "stream_viewer" / "templates" / "index.html"


def test_now_line_always_shows_fetching_title_or_no_data():
    source = APP_JS.read_text(encoding="utf-8")
    assert "Now: Fetching…" in source
    assert "Now: No data" in source
    assert "function setStreamNowLine" in source
    # New sidebar rows must start visible in the pending state, not hidden blank.
    assert 'nowLine.textContent = "Now: Fetching…"' in source
    assert "nowLine.hidden = false" in source
    assert "nowLine.hidden = true" not in source


def test_viewer_pane_shows_programme_beside_stream_name():
    html = INDEX_HTML.read_text(encoding="utf-8")
    js = APP_JS.read_text(encoding="utf-8")
    assert 'id="nowProgramme"' in html
    assert 'id="nowTitle"' in html
    assert "function setViewerProgramme" in js
    assert "els.nowProgramme" in js
    # Programme title must be wired into the player header, not only the sidebar.
    assert "setViewerProgramme(hasNow ? stream.now_playing : null" in js
    assert "setViewerProgramme(info, { pending: false })" in js


def test_no_duplicate_match_count_beside_reset():
    """BUG-006: match totals live in the status bar only, not next to Reset."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    js = APP_JS.read_text(encoding="utf-8")
    css = (ROOT / "stream_viewer" / "static" / "app.css").read_text(encoding="utf-8")
    assert 'id="resetFiltersBtn"' in html
    assert 'id="resultCount"' not in html
    assert "resultCount" not in js
    assert ".result-count" not in css
    assert "statusMessage" in js
    assert "match" in js


def test_no_header_source_picker_or_reload():
    """BUG-007: runtime catalog is viewer.db — no Source/Reload chrome in the header."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    js = APP_JS.read_text(encoding="utf-8")
    css = (ROOT / "stream_viewer" / "static" / "app.css").read_text(encoding="utf-8")
    assert 'id="sourceSelect"' not in html
    assert 'id="reloadBtn"' not in html
    assert "source-picker" not in html
    assert "sourceSelect" not in js
    assert "reloadBtn" not in js
    assert "/api/reload" not in js
    assert ".source-picker" not in css


def test_brand_has_no_source_or_stream_subtitle():
    """BUG-008: brand is name-only; stream count lives in the status bar."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    js = APP_JS.read_text(encoding="utf-8")
    css = (ROOT / "stream_viewer" / "static" / "app.css").read_text(encoding="utf-8")
    assert "StreamingViewerTV" in html
    assert 'id="sourceLabel"' not in html
    assert "brand-sub" not in html
    assert ".brand-sub" not in css
    assert "sourceLabel" not in js
    assert 'id="statusCatalog"' in html
    assert "Streams" in html
    assert "statusSource" not in js
    assert 'id="statusSource"' not in html


def test_filter_bar_gives_filters_full_width_row():
    """BUG-010: Category/filter selects must not be squeezed beside search."""
    css = (ROOT / "stream_viewer" / "static" / "app.css").read_text(encoding="utf-8")
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert 'id="filterForm"' in html
    assert 'grid-area: filters' in css or "grid-area: filters;" in css
    assert '"filters filters"' in css


def test_filter_change_scrolls_stream_list_to_top():
    """FEAT: changing filters/search resets the left list scroll position."""
    js = APP_JS.read_text(encoding="utf-8")
    assert "streamListWrap.scrollTop = 0" in js
    assert "loadStreams({ reset: true })" in js


def test_buffering_status_shows_percent():
    """Playback buffer progress is surfaced as a percent while buffering."""
    js = APP_JS.read_text(encoding="utf-8")
    assert "function getBufferStats" in js
    assert "BUFFER_TARGET_SEC" in js
    assert "Buffering ${who}… ${percent}%" in js or "Buffering" in js and "${percent}%" in js
    assert "bufferPercent" in js
    assert "refreshBufferProgress" in js
