#!/usr/bin/env python3
"""
Live-check stream URLs through the local proxy path.

Default pytest stays offline. Use this script (or pytest -m live) for network checks.

Examples:
  uv run python -m builder.check_urls --limit 50
  uv run python -m builder.check_urls --all --workers 16
  uv run python -m builder.check_urls --ids 0,1618,7784
"""

from __future__ import annotations

import argparse
import csv
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from fastapi.testclient import TestClient

from builder.paths import EXPORT_DIR, VIEWER_DB
from stream_viewer import app as viewer
from stream_viewer import db as catalog_db
from stream_viewer.app import app

OUTPUT_CSV = EXPORT_DIR / "url_check_report.csv"


def load_streams() -> list[dict[str, str]]:
    if not VIEWER_DB.is_file():
        raise SystemExit(f"Missing {VIEWER_DB}. Run: uv run stream-viewer-build")
    conn = catalog_db.connect(VIEWER_DB)
    try:
        return catalog_db.load_streams(conn)
    finally:
        conn.close()


def check_one(client: TestClient, stream: dict[str, str], deep: bool) -> dict[str, str]:
    index = int(stream["id"])
    name = (stream.get("name") or "").strip()
    url = (stream.get("url") or "").strip()
    started = time.perf_counter()
    result = {
        "id": str(index),
        "name": name,
        "url": url,
        "ok": "false",
        "http_status": "",
        "detail": "",
        "child_ok": "",
        "latency_ms": "",
    }
    if not url:
        result["detail"] = "empty url"
        return result

    try:
        meta = client.get(f"/api/streams/{index}")
        if meta.status_code != 200:
            result["http_status"] = str(meta.status_code)
            result["detail"] = meta.text[:240]
            return result
        play_url = meta.json().get("play_url") or ""
        proxy = client.get(play_url)
        result["http_status"] = str(proxy.status_code)
        result["latency_ms"] = f"{(time.perf_counter() - started) * 1000:.0f}"
        if proxy.status_code != 200:
            try:
                result["detail"] = str(proxy.json().get("detail", proxy.text))[:240]
            except Exception:  # noqa: BLE001
                result["detail"] = proxy.text[:240]
            return result

        result["ok"] = "true"
        result["detail"] = "master playlist ok"
        if deep:
            body = proxy.text
            child = next(
                (
                    line.strip()
                    for line in body.splitlines()
                    if line.strip() and not line.strip().startswith("#")
                ),
                "",
            )
            if not child:
                result["child_ok"] = "n/a"
            else:
                child_resp = client.get(child)
                result["child_ok"] = "true" if child_resp.status_code == 200 else "false"
                if child_resp.status_code != 200:
                    try:
                        result["detail"] = (
                            f"master ok; child failed: "
                            f"{child_resp.json().get('detail', child_resp.text)}"
                        )[:240]
                    except Exception:  # noqa: BLE001
                        result["detail"] = f"master ok; child HTTP {child_resp.status_code}"
                    result["ok"] = "false"
                else:
                    result["detail"] = "master + child playlist ok"
        return result
    except Exception as exc:  # noqa: BLE001
        result["detail"] = f"{type(exc).__name__}: {exc}"[:240]
        result["latency_ms"] = f"{(time.perf_counter() - started) * 1000:.0f}"
        return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Live-check IPTV URLs via the local proxy (from viewer.db)."
    )
    parser.add_argument("--output", type=Path, default=OUTPUT_CSV)
    parser.add_argument("--limit", type=int, default=0, help="Only first N streams")
    parser.add_argument("--all", action="store_true", help="Check every stream")
    parser.add_argument("--ids", default="", help="Comma-separated stream ids")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--deep", action="store_true", help="Also fetch first child playlist")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.all and not args.limit and not args.ids:
        raise SystemExit("Pass --limit N, --ids a,b,c, or --all")

    streams = load_streams()
    by_id = {int(stream["id"]): stream for stream in streams}

    viewer.EXPORT_DIR = EXPORT_DIR
    viewer._catalog.clear()
    viewer._catalog.update(
        {"source": None, "streams": [], "by_id": {}, "filters": {}, "total": 0}
    )

    if args.ids:
        indexes = [int(part.strip()) for part in args.ids.split(",") if part.strip()]
    else:
        indexes = [int(stream["id"]) for stream in streams]
        if not args.all:
            indexes = indexes[: max(0, args.limit)]

    missing = [index for index in indexes if index not in by_id]
    if missing:
        raise SystemExit(f"Unknown stream id(s): {missing[:10]}")

    print(f"Checking {len(indexes)} streams from {VIEWER_DB} (deep={args.deep})")
    results: list[dict[str, str]] = []

    with TestClient(app) as client:
        warm = client.get("/api/meta")
        warm.raise_for_status()

        def work(index: int) -> dict[str, str]:
            return check_one(client, by_id[index], args.deep)

        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            futures = {pool.submit(work, index): index for index in indexes}
            done = 0
            for future in as_completed(futures):
                results.append(future.result())
                done += 1
                if done % 25 == 0 or done == len(indexes):
                    ok = sum(1 for row in results if row["ok"] == "true")
                    print(f"  progress {done}/{len(indexes)} ok={ok} fail={done - ok}")

    results.sort(key=lambda row: int(row["id"]))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "id",
        "name",
        "url",
        "ok",
        "http_status",
        "child_ok",
        "latency_ms",
        "detail",
    ]
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    ok = sum(1 for row in results if row["ok"] == "true")
    fail = len(results) - ok
    print(f"Done. ok={ok} fail={fail}")
    print(f"Wrote {args.output}")
    return 1 if fail and args.all else 0


if __name__ == "__main__":
    raise SystemExit(main())
