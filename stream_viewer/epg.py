"""EPG channel-key helpers for StreamingViewerTV.

Programme data lives in viewer.db (written by stream-viewer-build).
The viewer never parses XMLTV files at runtime.
"""

from __future__ import annotations

import re
from typing import Any

PLUTO_ID_RE = re.compile(r"(?:plu-|/channels/)([a-f0-9]{24})", re.I)


def extract_pluto_id(stream: dict[str, Any]) -> str | None:
    for field in ("url", "tvg_logo"):
        match = PLUTO_ID_RE.search(stream.get(field) or "")
        if match:
            return match.group(1).lower()
    return None


def stream_epg_keys(stream: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    pluto = extract_pluto_id(stream)
    if pluto:
        keys.append(f"pluto:{pluto}")
    tvg = (stream.get("tvg_id") or "").strip()
    if tvg:
        keys.append(f"tvg:{tvg}")
        base = tvg.split("@", 1)[0].strip()
        if base and base != tvg:
            keys.append(f"tvg:{base}")
    seen: set[str] = set()
    out: list[str] = []
    for key in keys:
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out
