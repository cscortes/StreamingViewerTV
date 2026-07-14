#!/usr/bin/env python3
"""
Enrich streams.csv with country, language, maturity, topics, and video quality.

Reads iptv_export/streams.csv (from builder.download_streams), joins iptv-org
API metadata, and writes an enriched CSV.

Stream quality and popularity are not published by iptv-org; those columns are
filled with "unknown" so you can populate them later from probes / app usage.
"""

from __future__ import annotations

import csv
import json
import re
import urllib.request
from collections import defaultdict
from pathlib import Path

from builder.paths import STREAMS_CSV, STREAMS_ENRICHED_CSV

INPUT_CSV = STREAMS_CSV
OUTPUT_CSV = STREAMS_ENRICHED_CSV
USER_AGENT = "StreamingViewerTV/1.0"

CHANNELS_URL = "https://iptv-org.github.io/api/channels.json"
FEEDS_URL = "https://iptv-org.github.io/api/feeds.json"
STREAMS_URL = "https://iptv-org.github.io/api/streams.json"
COUNTRIES_URL = "https://iptv-org.github.io/api/countries.json"
LANGUAGES_URL = "https://iptv-org.github.io/api/languages.json"

ORIGINAL_COLUMNS = [
    "name",
    "url",
    "tvg_id",
    "tvg_logo",
    "group_title",
    "http_referrer",
    "http_user_agent",
]

EXTRA_COLUMNS = [
    "country",
    "country_name",
    "language",
    "language_name",
    "maturity",
    "is_nsfw",
    "topics",
    "video_quality",
    "stream_quality",
    "popularity",
]

OUTPUT_COLUMNS = ORIGINAL_COLUMNS + EXTRA_COLUMNS

RES_RE = re.compile(
    r"\(([^)]*?(?:2160|4k|1440|1080|720|576|540|480|360|240|SD|HD|FHD|UHD)[^)]*)\)|"
    r"\b(2160p|1440p|1080p|720p|576[ip]?|480p|360p|240p|4[Kk]|UHD|FHD|HD|SD)\b",
    re.I,
)


def fetch_json(url: str):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.load(response)


def channel_id_from_tvg(tvg_id: str) -> str:
    """Turn 'BBCNews.uk@SD' into 'BBCNews.uk'."""
    return (tvg_id or "").split("@", 1)[0].strip()


def normalize_video_quality(raw: str | None) -> str:
    if not raw:
        return ""
    text = raw.strip().lower()
    if "2160" in text or "4k" in text or "uhd" in text:
        return "2160p"
    if "1440" in text:
        return "1440p"
    if "1080" in text or "fhd" in text:
        return "1080p"
    if "720" in text:
        return "720p"
    if "576" in text or "540" in text:
        return "576p"
    if "480" in text:
        return "480p"
    if "360" in text:
        return "360p"
    if "240" in text:
        return "240p"
    if re.search(r"\bhd\b", text):
        return "HD"
    if re.search(r"\bsd\b", text):
        return "SD"
    return raw.strip()


def quality_from_name(name: str) -> str:
    match = RES_RE.search(name or "")
    if not match:
        return ""
    return normalize_video_quality(match.group(1) or match.group(2))


def load_api_indexes() -> dict:
    print(f"Downloading {CHANNELS_URL}")
    channels = {c["id"]: c for c in fetch_json(CHANNELS_URL) if c.get("id")}

    print(f"Downloading {FEEDS_URL}")
    feeds_by_channel: dict[str, list] = defaultdict(list)
    for feed in fetch_json(FEEDS_URL):
        channel = feed.get("channel")
        if channel:
            feeds_by_channel[channel].append(feed)

    print(f"Downloading {STREAMS_URL}")
    quality_by_url = {}
    for stream in fetch_json(STREAMS_URL):
        url = stream.get("url")
        if url and stream.get("quality"):
            quality_by_url[url] = stream["quality"]

    print(f"Downloading {COUNTRIES_URL}")
    countries = {
        c["code"]: c.get("name", "")
        for c in fetch_json(COUNTRIES_URL)
        if c.get("code")
    }

    print(f"Downloading {LANGUAGES_URL}")
    languages = {
        lang["code"]: lang.get("name", "")
        for lang in fetch_json(LANGUAGES_URL)
        if lang.get("code")
    }

    return {
        "channels": channels,
        "feeds_by_channel": feeds_by_channel,
        "quality_by_url": quality_by_url,
        "countries": countries,
        "languages": languages,
    }


def languages_for_channel(channel_id: str, feeds_by_channel: dict) -> list[str]:
    codes: set[str] = set()
    for feed in feeds_by_channel.get(channel_id, []):
        for code in feed.get("languages") or []:
            if code:
                codes.add(code)
    return sorted(codes)


def enrich_row(row: dict[str, str], indexes: dict) -> dict[str, str]:
    channel_id = channel_id_from_tvg(row.get("tvg_id", ""))
    channel = indexes["channels"].get(channel_id, {})

    country = channel.get("country") or ""
    country_name = indexes["countries"].get(country, "") if country else ""

    lang_codes = languages_for_channel(channel_id, indexes["feeds_by_channel"])
    language = ";".join(lang_codes)
    language_name = ";".join(
        indexes["languages"].get(code, code) for code in lang_codes
    )

    if channel:
        is_nsfw = "true" if channel.get("is_nsfw") else "false"
        maturity = "Adult" if channel.get("is_nsfw") else "Family"
    else:
        is_nsfw = ""
        maturity = ""

    topics = ";".join(channel.get("categories") or [])
    if not topics:
        # Fall back to playlist group titles, normalized to lowercase tokens
        topics = ";".join(
            part.strip().lower().replace(" ", "")
            for part in (row.get("group_title") or "").split(";")
            if part.strip() and part.strip().lower() != "undefined"
        )

    video_quality = normalize_video_quality(
        indexes["quality_by_url"].get(row.get("url", ""))
    ) or quality_from_name(row.get("name", ""))

    enriched = {col: row.get(col, "") for col in ORIGINAL_COLUMNS}
    enriched.update(
        {
            "country": country,
            "country_name": country_name,
            "language": language,
            "language_name": language_name,
            "maturity": maturity,
            "is_nsfw": is_nsfw,
            "topics": topics,
            "video_quality": video_quality,
            "stream_quality": "unknown",
            "popularity": "unknown",
        }
    )
    return enriched


def main() -> int:
    if not INPUT_CSV.exists():
        print(f"Missing {INPUT_CSV}. Run: uv run python -m builder.download_streams")
        return 1

    with INPUT_CSV.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    print(f"Loaded {len(rows)} rows from {INPUT_CSV}")
    indexes = load_api_indexes()

    enriched_rows = [enrich_row(row, indexes) for row in rows]

    matched = sum(1 for r in enriched_rows if r["country"])
    with_quality = sum(1 for r in enriched_rows if r["video_quality"])
    print(f"Matched country metadata: {matched}/{len(enriched_rows)}")
    print(f"With video_quality: {with_quality}/{len(enriched_rows)}")

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(enriched_rows)

    print(f"Wrote {len(enriched_rows)} rows to {OUTPUT_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
