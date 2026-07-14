#!/usr/bin/env python3
"""Download the iptv-org M3U playlist and write a CSV of all streams."""

from __future__ import annotations

import csv
import re
import urllib.request
from pathlib import Path

PLAYLIST_URL = "https://iptv-org.github.io/iptv/index.m3u"
OUTPUT_CSV = Path("iptv_export/streams.csv")
USER_AGENT = "StreamingViewerTV/1.0"

ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')

CSV_COLUMNS = [
    "name",
    "url",
    "tvg_id",
    "tvg_logo",
    "group_title",
    "http_referrer",
    "http_user_agent",
]


def fetch_playlist(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def parse_extinf(line: str) -> tuple[dict[str, str], str]:
    payload = line[len("#EXTINF:") :]
    comma = payload.rfind(",")
    if comma == -1:
        return {}, payload.strip()
    attrs = dict(ATTR_RE.findall(payload[:comma]))
    return attrs, payload[comma + 1 :].strip()


def parse_streams(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    attrs: dict[str, str] = {}
    name = ""
    headers: dict[str, str] = {}

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#EXTINF:"):
            attrs, name = parse_extinf(line)
            headers = {}
            continue
        if line.startswith("#EXTVLCOPT:"):
            option = line[len("#EXTVLCOPT:") :]
            if "=" in option:
                key, value = option.split("=", 1)
                headers[key.strip()] = value.strip()
            continue
        if line.startswith("#"):
            continue

        rows.append(
            {
                "name": name or line,
                "url": line,
                "tvg_id": attrs.get("tvg-id", ""),
                "tvg_logo": attrs.get("tvg-logo", ""),
                "group_title": attrs.get("group-title", ""),
                "http_referrer": headers.get(
                    "http-referrer", attrs.get("http-referrer", "")
                ),
                "http_user_agent": headers.get(
                    "http-user-agent", attrs.get("http-user-agent", "")
                ),
            }
        )
        attrs, name, headers = {}, "", {}

    return rows


def write_csv(rows: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    print(f"Downloading {PLAYLIST_URL}")
    text = fetch_playlist(PLAYLIST_URL)
    rows = parse_streams(text)
    write_csv(rows, OUTPUT_CSV)
    print(f"Wrote {len(rows)} streams to {OUTPUT_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
