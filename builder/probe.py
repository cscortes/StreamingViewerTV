#!/usr/bin/env python3
"""
Probe HLS stream URLs to fill video_quality and stream_quality in the CSV.

Reads streams_enriched.csv (or streams.csv), fetches each playlist, parses
resolution from HLS tags, grades responsiveness, and writes an updated CSV.

Grades:
  excellent — playlist OK, responds quickly, looks like valid HLS
  okay      — playlist OK but slow, thin, or resolution unclear
  poor      — timeout, HTTP error, or not a usable playlist

By default only rows with stream_quality=unknown are probed.
Use --limit while testing; use --all to probe every matching row.
"""

from __future__ import annotations

import argparse
import csv
import re
import ssl
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

from builder.paths import STREAMS_CSV, STREAMS_ENRICHED_CSV, STREAMS_PROBED_CSV

DEFAULT_INPUT = STREAMS_ENRICHED_CSV
FALLBACK_INPUT = STREAMS_CSV
DEFAULT_OUTPUT = STREAMS_PROBED_CSV
DEFAULT_USER_AGENT = "StreamingViewerTV/1.0"

STREAM_INF_RE = re.compile(r"#EXT-X-STREAM-INF:([^\n]+)", re.I)
RESOLUTION_RE = re.compile(r"RESOLUTION=(\d+)x(\d+)", re.I)
URI_LINE_RE = re.compile(r"^(?!#)(\S+)", re.M)
EXTINF_RE = re.compile(r"#EXTINF:", re.I)

# Columns we always try to preserve / write
PROBE_COLUMNS = [
    "name",
    "url",
    "tvg_id",
    "tvg_logo",
    "group_title",
    "http_referrer",
    "http_user_agent",
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
    "probe_http_status",
    "probe_latency_ms",
    "probe_notes",
]


@dataclass
class ProbeResult:
    video_quality: str
    stream_quality: str
    http_status: str
    latency_ms: str
    notes: str


def height_to_label(height: int) -> str:
    if height >= 2160:
        return "2160p"
    if height >= 1440:
        return "1440p"
    if height >= 1080:
        return "1080p"
    if height >= 720:
        return "720p"
    if height >= 576:
        return "576p"
    if height >= 480:
        return "480p"
    if height >= 360:
        return "360p"
    if height >= 240:
        return "240p"
    if height > 0:
        return f"{height}p"
    return ""


def parse_max_resolution(playlist_text: str) -> int:
    heights = [int(h) for _, h in RESOLUTION_RE.findall(playlist_text)]
    return max(heights) if heights else 0


def first_playlist_uri(playlist_text: str, base_url: str) -> str | None:
    """Return first media/variant URI after a STREAM-INF block, else first non-tag URI."""
    lines = [ln.strip() for ln in playlist_text.splitlines() if ln.strip()]
    for index, line in enumerate(lines):
        if line.upper().startswith("#EXT-X-STREAM-INF:"):
            for follow in lines[index + 1 :]:
                if follow.startswith("#"):
                    continue
                return urljoin(base_url, follow)
            return None
    for line in lines:
        if not line.startswith("#"):
            return urljoin(base_url, line)
    return None


def looks_like_hls(text: str) -> bool:
    upper = text.lstrip().upper()
    return upper.startswith("#EXTM3U") or "#EXTINF:" in upper or "#EXT-X-STREAM-INF:" in upper


def sanitize_text(value: str, *, max_len: int = 240) -> str:
    """Keep probe notes CSV-safe (SSL errors can embed NULs / binary)."""
    if not value:
        return ""
    cleaned = "".join(
        ch if ch in "\t\n\r" or (31 < ord(ch) < 127) or ord(ch) > 159 else " "
        for ch in value
    )
    cleaned = " ".join(cleaned.replace("\x00", " ").split())
    if len(cleaned) > max_len:
        cleaned = cleaned[: max_len - 1].rstrip() + "…"
    return cleaned


def fetch_text(
    url: str,
    *,
    user_agent: str,
    referrer: str,
    timeout: float,
) -> tuple[int, float, str]:
    headers = {
        "User-Agent": user_agent or DEFAULT_USER_AGENT,
        "Accept": "*/*",
    }
    if referrer:
        headers["Referer"] = referrer

    request = urllib.request.Request(url, headers=headers)
    # Some IPTV hosts use odd certs; still verify by default via stdlib context.
    context = ssl.create_default_context()
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        status = getattr(response, "status", 200) or 200
        raw = response.read(512_000)  # cap: playlist + small media headroom
        charset = response.headers.get_content_charset() or "utf-8"
        text = raw.decode(charset, errors="replace")
    latency_ms = (time.perf_counter() - started) * 1000.0
    return int(status), latency_ms, text


def grade(latency_ms: float, *, has_hls: bool, has_resolution: bool, has_media: bool) -> str:
    if not has_hls:
        return "poor"
    if latency_ms <= 2500 and (has_resolution or has_media):
        return "excellent"
    if latency_ms <= 8000:
        return "okay"
    return "okay" if has_media or has_resolution else "poor"


def probe_url(
    url: str,
    *,
    user_agent: str,
    referrer: str,
    timeout: float,
    deep: bool,
) -> ProbeResult:
    if not url:
        return ProbeResult("", "poor", "", "", "empty url")

    try:
        status, latency_ms, text = fetch_text(
            url,
            user_agent=user_agent,
            referrer=referrer,
            timeout=timeout,
        )
    except urllib.error.HTTPError as exc:
        return ProbeResult("", "poor", str(exc.code), "", f"http error: {exc.code}")
    except urllib.error.URLError as exc:
        reason = sanitize_text(str(getattr(exc, "reason", exc)))
        return ProbeResult("", "poor", "", "", f"url error: {reason}")
    except TimeoutError:
        return ProbeResult("", "poor", "", "", "timeout")
    except Exception as exc:  # noqa: BLE001 - probe must never crash the worker
        return ProbeResult("", "poor", "", "", f"error: {sanitize_text(str(exc))}")

    if status >= 400:
        return ProbeResult(
            "",
            "poor",
            str(status),
            f"{latency_ms:.0f}",
            "bad http status",
        )

    if not looks_like_hls(text):
        return ProbeResult(
            "",
            "poor",
            str(status),
            f"{latency_ms:.0f}",
            "response is not HLS",
        )

    height = parse_max_resolution(text)
    has_media = bool(EXTINF_RE.search(text))
    has_variants = bool(STREAM_INF_RE.search(text))
    notes = []

    if deep and has_variants and not has_media:
        child = first_playlist_uri(text, url)
        if child:
            try:
                child_status, child_latency, child_text = fetch_text(
                    child,
                    user_agent=user_agent,
                    referrer=referrer,
                    timeout=timeout,
                )
                latency_ms = max(latency_ms, child_latency)
                if child_status < 400 and looks_like_hls(child_text):
                    height = max(height, parse_max_resolution(child_text))
                    has_media = has_media or bool(EXTINF_RE.search(child_text))
                    notes.append("deep: media playlist ok")
                else:
                    notes.append("deep: media playlist weak")
            except Exception as exc:  # noqa: BLE001
                notes.append(f"deep failed: {sanitize_text(str(exc))}")

    if height:
        notes.append(f"resolution height={height}")
    elif has_media:
        notes.append("media playlist, no RESOLUTION tag")
    elif has_variants:
        notes.append("master playlist, no RESOLUTION tag")

    quality = height_to_label(height)
    stream_quality = grade(
        latency_ms,
        has_hls=True,
        has_resolution=bool(height),
        has_media=has_media or has_variants,
    )

    return ProbeResult(
        video_quality=quality,
        stream_quality=stream_quality,
        http_status=str(status),
        latency_ms=f"{latency_ms:.0f}",
        notes="; ".join(notes) if notes else "ok",
    )


def should_probe(row: dict[str, str], force: bool) -> bool:
    if force:
        return True
    current = (row.get("stream_quality") or "").strip().lower()
    return current in {"", "unknown"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Probe HLS URLs to fill video_quality and stream_quality.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Input CSV (default: {DEFAULT_INPUT})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output CSV (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Only probe the first N eligible rows",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Probe every eligible row (can take a long time)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=12,
        help="Parallel probe workers (default: 12)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=8.0,
        help="Per-request timeout seconds (default: 8)",
    )
    parser.add_argument(
        "--deep",
        action="store_true",
        help="Also fetch a child media playlist when the URL is a master playlist",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-probe rows that already have a stream_quality grade",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    input_path = args.input
    if not input_path.exists() and input_path == DEFAULT_INPUT and FALLBACK_INPUT.exists():
        print(f"{input_path} missing; falling back to {FALLBACK_INPUT}")
        input_path = FALLBACK_INPUT
    if not input_path.exists():
        print(f"Missing {input_path}. Run download/enrich first.")
        return 1

    if not args.all and args.limit is None:
        print("Refusing to probe the full list without --limit or --all.")
        print("Example: uv run python -m builder.probe --limit 50")
        return 2

    with input_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    # Ensure probe output columns exist
    for col in PROBE_COLUMNS:
        if col not in fieldnames:
            fieldnames.append(col)

    eligible_indexes = [i for i, row in enumerate(rows) if should_probe(row, args.force)]
    if args.limit is not None:
        eligible_indexes = eligible_indexes[: max(0, args.limit)]

    print(f"Loaded {len(rows)} rows from {input_path}")
    print(f"Probing {len(eligible_indexes)} row(s) "
          f"(workers={args.workers}, timeout={args.timeout}s, deep={args.deep})")

    def work(index: int) -> tuple[int, ProbeResult]:
        row = rows[index]
        result = probe_url(
            row.get("url", ""),
            user_agent=row.get("http_user_agent", "") or DEFAULT_USER_AGENT,
            referrer=row.get("http_referrer", ""),
            timeout=args.timeout,
            deep=args.deep,
        )
        return index, result

    counts = {"excellent": 0, "okay": 0, "poor": 0}
    completed = 0

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(work, index) for index in eligible_indexes]
        for future in as_completed(futures):
            index, result = future.result()
            row = rows[index]

            if result.video_quality and (
                args.force or not (row.get("video_quality") or "").strip()
            ):
                row["video_quality"] = result.video_quality

            row["stream_quality"] = result.stream_quality
            row["probe_http_status"] = result.http_status
            row["probe_latency_ms"] = result.latency_ms
            row["probe_notes"] = sanitize_text(result.notes)
            counts[result.stream_quality] = counts.get(result.stream_quality, 0) + 1

            completed += 1
            if completed % 25 == 0 or completed == len(eligible_indexes):
                print(
                    f"  progress {completed}/{len(eligible_indexes)} "
                    f"(excellent={counts['excellent']}, "
                    f"okay={counts['okay']}, poor={counts['poor']})"
                )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(
        f"Done. excellent={counts['excellent']}, "
        f"okay={counts['okay']}, poor={counts['poor']}"
    )
    print(f"Wrote {len(rows)} rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
