#!/usr/bin/env python3
"""StreamingViewerTV — FastAPI UI for browsing and playing IPTV streams from viewer.db."""

from __future__ import annotations

import hashlib
import re
import secrets
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx2
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from stream_viewer import db as catalog_db
from stream_viewer._version import __version__
from stream_viewer.db import STREAM_COLUMNS
from stream_viewer.epg import stream_epg_keys


def resolve_app_paths(
    *,
    frozen: bool,
    executable: str,
    module_file: str,
    meipass: str | None,
) -> tuple[Path, Path, Path]:
    """Resolve (export_dir, static_dir, templates_dir) for both dev and PyInstaller-frozen runs.

    Frozen: data (viewer.db) lives next to the executable so it persists across app
    updates/reinstalls; bundled resources (static/templates) live under PyInstaller's
    extraction dir (_MEIPASS). Dev: everything resolves relative to this file, as before.
    """
    if frozen:
        root = Path(executable).resolve().parent
        resource_root = Path(meipass) if meipass else root
        app_dir = resource_root / "stream_viewer"
    else:
        root = Path(module_file).resolve().parent.parent
        app_dir = Path(module_file).resolve().parent

    export_dir = root / "iptv_export"
    return export_dir, app_dir / "static", app_dir / "templates"


EXPORT_DIR, STATIC_DIR, TEMPLATES_DIR = resolve_app_paths(
    frozen=getattr(sys, "frozen", False),
    executable=sys.executable,
    module_file=__file__,
    meipass=getattr(sys, "_MEIPASS", None),
)
ROOT = EXPORT_DIR.parent

USER_AGENT = "StreamingViewerTV/1.0"
PROXY_SESSION_TTL_SEC = 6 * 60 * 60
PROXY_MAX_RETRIES = 3
PROXY_RETRY_STATUSES = {408, 425, 429, 500, 502, 503, 504}
VIEWER_DB_ID = "viewer.db"


def viewer_db_path() -> Path:
    return EXPORT_DIR / VIEWER_DB_ID

# Filter dimensions shown in the UI when the column has at least one non-empty value.
# "Category" is IPTV topics (news/movies/…); playlist group-title is a separate axis.
FILTER_FIELDS: dict[str, dict[str, Any]] = {
    "topics": {"label": "Category", "multi": True},
    "country_name": {"label": "Country", "multi": False},
    "language_name": {"label": "Language", "multi": True},
    "group_title": {"label": "Playlist group", "multi": False},
    "video_quality": {
        "label": "Video quality",
        "multi": False,
        "mode": "min",
        "hint": "at least",
    },
    "stream_quality": {
        "label": "Stream quality",
        "multi": False,
        "mode": "min",
        "hint": "at least",
    },
    "maturity": {"label": "Maturity", "multi": False},
}

SPLIT_FIELDS = {"group_title", "language_name", "topics", "language"}

# Exact-match dropdowns stay usable (Category/Country/Language can be huge).
MAX_EXACT_FILTER_OPTIONS = 80

# Values that are not useful as Category picks (shown as empty / unknown upstream).
CATEGORY_SKIP_VALUES = {"", "undefined", "unknown", "none", "null"}

CATEGORY_FILTER_FIELD = "topics"

# Standard ladder for "at least" video quality filtering.
VIDEO_QUALITY_LADDER: list[tuple[str, int]] = [
    ("240p", 240),
    ("360p", 360),
    ("480p", 480),
    ("720p", 720),
    ("1080p", 1080),
    ("1440p", 1440),
    ("2160p", 2160),
]

STREAM_QUALITY_RANK: dict[str, int] = {
    "poor": 1,
    "okay": 2,
    "excellent": 3,
}

STREAM_QUALITY_LADDER: list[str] = ["poor", "okay", "excellent"]


def category_value_counts(streams: list[dict[str, Any]]) -> dict[str, int]:
    """Count non-empty Category (topics) values after skip-list filtering."""
    counts: dict[str, int] = {}
    for stream in streams:
        for value in field_values(stream, CATEGORY_FILTER_FIELD):
            if value.strip().lower() in CATEGORY_SKIP_VALUES:
                continue
            counts[value] = counts.get(value, 0) + 1
    return counts


def assert_catalog_has_categories(
    streams: list[dict[str, Any]],
    *,
    min_categories: int = 2,
    min_items_per_category: int = 1,
) -> dict[str, int]:
    """Raise ValueError unless the catalog has usable Category values with items."""
    counts = category_value_counts(streams)
    usable = {
        name: count
        for name, count in counts.items()
        if count >= min_items_per_category
    }
    if len(usable) < min_categories:
        raise ValueError(
            f"Catalog needs at least {min_categories} categories with "
            f">={min_items_per_category} stream(s) each; found {len(usable)}: "
            f"{sorted(usable.items(), key=lambda item: (-item[1], item[0].lower()))[:12]}"
        )
    return usable


def require_viewer_db() -> None:
    """Fail fast unless stream-viewer-build has produced viewer.db."""
    db_path = viewer_db_path()
    print("Catalog:")
    if not db_path.is_file():
        raise RuntimeError(
            f"Missing {db_path}. Run: uv run stream-viewer-build"
        )

    try:
        rel = db_path.relative_to(ROOT)
    except ValueError:
        rel = db_path
    print(f"  [ok] {rel} ({db_path.stat().st_size:,} bytes)")

    conn = catalog_db.connect(db_path)
    try:
        status = catalog_db.db_status(conn)
        streams = catalog_db.load_streams(conn)
    finally:
        conn.close()

    print(
        f"  [ok] streams={status['streams']} "
        f"programmes={status['programmes']} "
        f"built_from={status['streams_source'] or '?'}"
    )
    if status["streams"] <= 0:
        raise RuntimeError(
            f"{db_path} has no streams. Re-run: uv run stream-viewer-build"
        )

    try:
        usable = assert_catalog_has_categories(streams)
    except ValueError as exc:
        raise RuntimeError(
            f"{db_path} has no usable Category values. {exc} "
            "Re-run with enrichment: uv run stream-viewer-build"
        ) from exc
    sample = ", ".join(
        f"{name}({count})"
        for name, count in sorted(
            usable.items(), key=lambda item: (-item[1], item[0].lower())
        )[:5]
    )
    print(f"  [ok] categories={len(usable)} sample={sample}")


# Back-compat alias for older callers/tests.
require_local_data_files = require_viewer_db


def epg_status_from_db() -> dict[str, Any]:
    db_path = viewer_db_path()
    if not db_path.is_file():
        return {
            "state": "error",
            "detail": "viewer.db missing",
            "last_error": "viewer.db missing",
            "loading_source": "",
            "sources": [],
            "source_count": 0,
            "channel_keys": 0,
        }
    conn = catalog_db.connect(db_path)
    try:
        status = catalog_db.db_status(conn)
        sources = [
            row["name"]
            for row in conn.execute(
                "SELECT name FROM guide_sources ORDER BY name"
            ).fetchall()
        ]
        keys = conn.execute(
            "SELECT COUNT(DISTINCT channel_key) AS n FROM programmes"
        ).fetchone()
        channel_keys = int(keys["n"]) if keys else 0
    finally:
        conn.close()
    state = "loaded" if status["programmes"] > 0 else "idle"
    return {
        "state": state,
        "detail": (
            f"SQLite guide: {status['programmes']} programmes "
            f"from {status['guide_files'] or 0} file(s)"
        ),
        "last_error": "",
        "loading_source": "",
        "sources": sources,
        "source_count": len(sources),
        "channel_keys": channel_keys,
    }


def now_playing_for_stream(stream: dict[str, Any]) -> dict[str, Any] | None:
    db_path = viewer_db_path()
    if not db_path.is_file():
        return None
    conn = catalog_db.connect(db_path)
    try:
        return catalog_db.now_playing_for_keys(conn, stream_epg_keys(stream))
    finally:
        conn.close()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    require_viewer_db()
    try:
        ensure_catalog()
    except HTTPException as exc:
        raise RuntimeError(exc.detail) from exc
    yield


app = FastAPI(title="StreamingViewerTV", version=__version__, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

_catalog: dict[str, Any] = {
    "source": None,
    "streams": [],
    "by_id": {},
    "filters": {},
}

_proxy_lock = threading.Lock()
_proxy_sessions: dict[str, dict[str, Any]] = {}


def available_sources() -> list[dict[str, Any]]:
    """Runtime catalog sources shown in the UI (viewer.db only)."""
    sources: list[dict[str, Any]] = []
    db_path = viewer_db_path()
    if db_path.is_file():
        sources.append(
            {"id": VIEWER_DB_ID, "path": str(db_path), "size": db_path.stat().st_size}
        )
    return sources


def resolve_source(source: str | None = None) -> Path:
    """Always resolve to viewer.db. Unknown/stale source names are ignored."""
    _ = source  # stale cookie values like streams_probed.csv are deliberately ignored
    db_path = viewer_db_path()
    if db_path.is_file():
        return db_path
    raise HTTPException(
        status_code=404,
        detail="No viewer.db found. Run: uv run stream-viewer-build",
    )


def load_catalog(source: str | None = None) -> dict[str, Any]:
    path = resolve_source(source)
    conn = catalog_db.connect(path)
    try:
        streams = catalog_db.load_streams(conn)
        status = catalog_db.db_status(conn)
    finally:
        conn.close()
    fieldnames = list(STREAM_COLUMNS)
    return {
        "source": VIEWER_DB_ID,
        "streams": streams,
        "by_id": {stream["id"]: stream for stream in streams},
        "filters": build_filters(streams, fieldnames),
        "total": len(streams),
        "db_status": status,
    }

def split_values(raw: str) -> list[str]:
    if not raw:
        return []
    parts = re.split(r"[;|,/]+", raw)
    return [part.strip() for part in parts if part.strip()]


def field_values(row: dict[str, str], field: str) -> list[str]:
    raw = (row.get(field) or "").strip()
    if not raw:
        return []
    if field in SPLIT_FIELDS:
        return split_values(raw)
    return [raw]


def video_quality_rank(value: str) -> int:
    text = (value or "").strip().lower()
    if not text or text == "unknown":
        return 0
    if "2160" in text or "4k" in text or "uhd" in text:
        return 2160
    if "1440" in text:
        return 1440
    if "1080" in text or "fhd" in text:
        return 1080
    if "720" in text or re.search(r"(^|[^a-z])hd([^a-z]|$)", text):
        return 720
    if re.search(r"(^|[^a-z])sd([^a-z]|$)", text):
        return 480
    match = re.search(r"(\d{3,4})\s*p\b", text)
    if match:
        return int(match.group(1))
    return 0


def stream_quality_rank(value: str) -> int:
    return STREAM_QUALITY_RANK.get((value or "").strip().lower(), 0)


def build_min_filter_options(
    streams: list[dict[str, Any]],
    field: str,
) -> list[dict[str, Any]]:
    if field == "video_quality":
        ranks = [video_quality_rank(stream.get(field, "")) for stream in streams]
        options: list[dict[str, Any]] = []
        for label, threshold in VIDEO_QUALITY_LADDER:
            count = sum(1 for rank in ranks if rank >= threshold)
            if count:
                options.append({"value": label, "count": count, "label": f"{label}+"})
        return options

    if field == "stream_quality":
        ranks = [stream_quality_rank(stream.get(field, "")) for stream in streams]
        options = []
        for label in STREAM_QUALITY_LADDER:
            threshold = STREAM_QUALITY_RANK[label]
            count = sum(1 for rank in ranks if rank >= threshold)
            if count:
                options.append({"value": label, "count": count, "label": f"{label}+"})
        return options

    return []


def build_filters(streams: list[dict[str, Any]], fieldnames: list[str]) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    for field, meta in FILTER_FIELDS.items():
        if field not in fieldnames:
            continue

        mode = meta.get("mode", "exact")
        if mode == "min":
            options = build_min_filter_options(streams, field)
        else:
            counts: dict[str, int] = {}
            for stream in streams:
                for value in field_values(stream, field):
                    if (
                        field == CATEGORY_FILTER_FIELD
                        and value.strip().lower() in CATEGORY_SKIP_VALUES
                    ):
                        continue
                    counts[value] = counts.get(value, 0) + 1
            if not counts:
                continue
            ranked = sorted(
                counts.items(), key=lambda item: (-item[1], item[0].lower())
            )
            options = [
                {"value": value, "count": count, "label": value}
                for value, count in ranked[:MAX_EXACT_FILTER_OPTIONS]
            ]

        if len(options) < 2:
            # A single value can't narrow the list; treat like an empty category.
            continue

        filters[field] = {
            "label": meta["label"],
            "multi": meta["multi"],
            "mode": mode,
            "hint": meta.get("hint", ""),
            "options": options,
        }
    return filters


def ensure_catalog(source: str | None = None, force: bool = False) -> dict[str, Any]:
    global _catalog
    hint = source if source is not None else _catalog.get("source")
    desired = resolve_source(hint).name
    if force or not _catalog.get("streams") or _catalog.get("source") != desired:
        _catalog = load_catalog(desired)
    return _catalog


def matches_filters(
    stream: dict[str, Any],
    *,
    q: str,
    filters: dict[str, list[str]],
) -> bool:
    if q:
        haystack = " ".join(
            [
                stream.get("name", ""),
                stream.get("group_title", ""),
                stream.get("country_name", ""),
                stream.get("language_name", ""),
                stream.get("topics", ""),
                stream.get("tvg_id", ""),
            ]
        ).lower()
        if q not in haystack:
            return False

    for field, wanted in filters.items():
        if not wanted:
            continue
        mode = FILTER_FIELDS.get(field, {}).get("mode", "exact")
        if mode == "min":
            threshold = wanted[0]
            if field == "video_quality":
                if video_quality_rank(stream.get(field, "")) < video_quality_rank(threshold):
                    return False
            elif field == "stream_quality":
                if stream_quality_rank(stream.get(field, "")) < stream_quality_rank(threshold):
                    return False
            else:
                return False
            continue

        values = {value.lower() for value in field_values(stream, field)}
        if not values:
            return False
        if not any(item.lower() in values for item in wanted):
            return False
    return True


def public_stream(stream: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": stream["id"],
        "name": stream.get("name", ""),
        "url": stream.get("url", ""),
        "tvg_id": stream.get("tvg_id", ""),
        "tvg_logo": stream.get("tvg_logo", ""),
        "group_title": stream.get("group_title", ""),
        "country": stream.get("country", ""),
        "country_name": stream.get("country_name", ""),
        "language_name": stream.get("language_name", ""),
        "topics": stream.get("topics", ""),
        "video_quality": stream.get("video_quality", ""),
        "stream_quality": stream.get("stream_quality", ""),
        "maturity": stream.get("maturity", ""),
        "http_referrer": stream.get("http_referrer", ""),
        "http_user_agent": stream.get("http_user_agent", ""),
    }


def parse_filter_params(request: Request) -> dict[str, list[str]]:
    params: dict[str, list[str]] = {}
    for field in FILTER_FIELDS:
        values = request.query_params.getlist(field)
        cleaned = [value.strip() for value in values if value and value.strip()]
        if cleaned:
            params[field] = cleaned
    return params


def resolve_hls_uri(base_url: str, reference: str) -> str:
    """Resolve a playlist URI against a base URL (must be the post-redirect URL)."""
    return urljoin(base_url, reference)


def rewrite_m3u8(body: str, base_url: str, session_id: str) -> str:
    lines: list[str] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            if line.startswith("#EXT-X-KEY:") and "URI=" in line:
                def replace_uri(match: re.Match[str]) -> str:
                    absolute = resolve_hls_uri(base_url, match.group(1))
                    return f'URI="{proxy_path(session_id, absolute)}"'

                line = re.sub(r'URI="([^"]+)"', replace_uri, line)
            elif "URI=" in line and line.startswith("#EXT-X-MEDIA:"):
                def replace_media_uri(match: re.Match[str]) -> str:
                    absolute = resolve_hls_uri(base_url, match.group(1))
                    return f'URI="{proxy_path(session_id, absolute)}"'

                line = re.sub(r'URI="([^"]+)"', replace_media_uri, line)
            lines.append(raw if raw.startswith("#") else line)
            continue
        absolute = resolve_hls_uri(base_url, line)
        lines.append(proxy_path(session_id, absolute))
    return "\n".join(lines) + "\n"


def _prune_proxy_sessions(now: float | None = None) -> None:
    current = now if now is not None else time.time()
    expired = [
        token
        for token, session in _proxy_sessions.items()
        if current - float(session.get("created", 0)) > PROXY_SESSION_TTL_SEC
    ]
    for token in expired:
        _proxy_sessions.pop(token, None)


def create_proxy_session(*, referrer: str, user_agent: str) -> str:
    with _proxy_lock:
        _prune_proxy_sessions()
        token = secrets.token_urlsafe(12)
        _proxy_sessions[token] = {
            "created": time.time(),
            "referrer": referrer or "",
            "user_agent": user_agent or USER_AGENT,
            "urls": {},
        }
        return token


def register_proxy_url(session_id: str, target: str) -> str:
    validate_remote_url(target)
    url_id = hashlib.sha1(target.encode("utf-8")).hexdigest()[:16]
    with _proxy_lock:
        session = _proxy_sessions.get(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Proxy session expired")
        session["urls"][url_id] = target
        session["created"] = time.time()
    return url_id


def proxy_path(session_id: str, target: str) -> str:
    url_id = register_proxy_url(session_id, target)
    return f"/api/proxy/s/{session_id}/{url_id}"


def get_proxy_target(session_id: str, url_id: str) -> tuple[str, str, str]:
    with _proxy_lock:
        _prune_proxy_sessions()
        session = _proxy_sessions.get(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Proxy session expired")
        target = session["urls"].get(url_id)
        if not target:
            raise HTTPException(status_code=404, detail="Unknown proxy URL")
        session["created"] = time.time()
        return target, session.get("referrer", ""), session.get("user_agent", USER_AGENT)


def validate_remote_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Only http/https URLs are allowed")
    return url


async def fetch_upstream(
    target: str,
    headers: dict[str, str],
    *,
    retries: int = PROXY_MAX_RETRIES,
) -> httpx2.Response:
    """Fetch a remote URL, retrying transient network/CDN failures."""
    last_error: Exception | None = None
    async with httpx2.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        for attempt in range(1, max(1, retries) + 1):
            try:
                response = await client.get(target, headers=headers)
            except httpx2.HTTPError as exc:
                last_error = exc
                if attempt >= retries:
                    break
                await _async_sleep(0.2 * attempt)
                continue

            if response.status_code in PROXY_RETRY_STATUSES and attempt < retries:
                await _async_sleep(0.2 * attempt)
                continue
            return response

    if last_error is not None:
        raise HTTPException(
            status_code=502,
            detail=f"Upstream fetch failed: {last_error}",
        ) from last_error
    raise HTTPException(status_code=502, detail="Upstream fetch failed after retries")


async def _async_sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    catalog = ensure_catalog()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "source": catalog.get("source"),
            "total": catalog.get("total", 0),
            "sources": available_sources(),
            "filters": catalog.get("filters") or {},
            "version": __version__,
        },
    )


@app.get("/api/meta")
async def api_meta(source: str | None = None) -> dict[str, Any]:
    catalog = ensure_catalog(source)
    with_tvg = sum(1 for stream in catalog["streams"] if (stream.get("tvg_id") or "").strip())
    return {
        "source": catalog["source"],
        "total": catalog["total"],
        "tvg_id_count": with_tvg,
        "sources": available_sources(),
        "filters": catalog["filters"],
        "epg": epg_status_from_db(),
    }


@app.post("/api/reload")
async def api_reload(source: str | None = None) -> dict[str, Any]:
    catalog = ensure_catalog(source, force=True)
    return {"source": catalog["source"], "total": catalog["total"]}


@app.get("/api/streams")
async def api_streams(
    request: Request,
    q: str = Query(""),
    source: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(80, ge=1, le=300),
) -> dict[str, Any]:
    catalog = ensure_catalog(source)
    query = q.strip().lower()
    filters = parse_filter_params(request)
    matched = [
        public_stream(stream)
        for stream in catalog["streams"]
        if matches_filters(stream, q=query, filters=filters)
    ]
    page = matched[offset : offset + limit]
    return {
        "source": catalog["source"],
        "total": len(matched),
        "offset": offset,
        "limit": limit,
        "items": page,
    }


@app.get("/api/streams/{stream_id}")
async def api_stream(stream_id: int, source: str | None = None) -> dict[str, Any]:
    catalog = ensure_catalog(source)
    stream = catalog["by_id"].get(stream_id)
    if not stream:
        raise HTTPException(status_code=404, detail="Stream not found")
    payload = public_stream(stream)
    session_id = create_proxy_session(
        referrer=stream.get("http_referrer", ""),
        user_agent=stream.get("http_user_agent", "") or USER_AGENT,
    )
    payload["play_url"] = proxy_path(session_id, stream["url"])
    try:
        epg = now_playing_for_stream(stream)
    except Exception:  # noqa: BLE001
        epg = None
    payload["now_playing"] = epg
    return payload


@app.get("/api/epg/now")
async def api_epg_now(
    stream_ids: str = Query("", description="Comma-separated stream ids"),
    source: str | None = None,
) -> dict[str, Any]:
    catalog = ensure_catalog(source)
    items: dict[str, Any] = {}
    ids: list[int] = []
    for part in stream_ids.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            continue

    for stream_id in ids:
        stream = catalog["by_id"].get(stream_id)
        if not stream:
            items[str(stream_id)] = None
            continue
        try:
            items[str(stream_id)] = now_playing_for_stream(stream)
        except Exception:  # noqa: BLE001
            items[str(stream_id)] = None

    return {
        "items": items,
        "count": sum(1 for value in items.values() if value),
        "epg": epg_status_from_db(),
    }


@app.get("/api/epg/status")
async def api_epg_status() -> dict[str, Any]:
    return epg_status_from_db()


@app.get("/api/proxy/s/{session_id}/{url_id}")
async def api_proxy_session(session_id: str, url_id: str) -> Response:
    target, referrer, user_agent = get_proxy_target(session_id, url_id)
    headers = {
        "User-Agent": user_agent or USER_AGENT,
        "Accept": "*/*",
    }
    if referrer:
        headers["Referer"] = referrer

    upstream = await fetch_upstream(target, headers)

    # Upstream 414 means the *remote* URL is too long for that host — not our local path.
    if upstream.status_code == 414:
        raise HTTPException(
            status_code=502,
            detail=(
                "Upstream rejected the stream URL as too long (414). "
                "This channel's CDN URL/token is oversized for HTTP GET."
            ),
        )
    if upstream.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Upstream returned HTTP {upstream.status_code} for {target}",
        )

    # Critical: resolve playlist URIs against the *final* URL after redirects.
    # Joining against a short redirector (e.g. jmp2.uk) invents huge invalid child URLs
    # that the redirector rejects with 414.
    final_url = str(upstream.url)
    content_type = upstream.headers.get("content-type", "application/octet-stream")
    body = upstream.content
    path = urlparse(final_url).path.lower()
    is_playlist = (
        "mpegurl" in content_type.lower()
        or path.endswith(".m3u8")
        or path.endswith(".m3u")
        or body[:1] == b"#"
    )

    if is_playlist:
        text = body.decode("utf-8", errors="replace")
        rewritten = rewrite_m3u8(text, final_url, session_id)
        return Response(
            content=rewritten,
            media_type="application/vnd.apple.mpegurl",
            headers={"Cache-Control": "no-store"},
        )

    return Response(
        content=body,
        media_type=content_type,
        headers={"Cache-Control": "no-store"},
    )


def main() -> None:
    import os
    import webbrowser

    import uvicorn

    host = "127.0.0.1"
    port = 8787

    if not os.environ.get("STREAM_VIEWER_NO_BROWSER"):
        def _open_browser() -> None:
            time.sleep(1.0)
            webbrowser.open(f"http://{host}:{port}")

        threading.Thread(target=_open_browser, daemon=True).start()

    # Pass the app object (not an import string) — import strings can be
    # unreliable to resolve inside a PyInstaller-frozen executable.
    uvicorn.run(app, host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
