#!/usr/bin/env python3
"""
Build pipeline entrypoint: download essentials, verify, load viewer.db.

Steps:
  1. Download M3U → streams.csv (unless present / --skip-download)
  2. Enrich → streams_enriched.csv (unless --skip-enrich)
  3. Optional probe → streams_probed.csv (--probe)
  4. Ensure essential Pluto EPG XMLs under iptv_export/epg/
  5. Verify required files exist and look non-empty
  6. Import catalog + programmes into iptv_export/viewer.db

Usage:
  uv run stream-viewer-build
  uv run stream-viewer-build --probe --probe-all
  uv run python -m builder.prepare_db --skip-download
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

from builder import download_streams, enrich, probe
from builder.paths import (
    EPG_CACHE_DIR,
    EPG_DIR,
    EXPORT_DIR,
    ROOT,
    STREAMS_CSV,
    STREAMS_ENRICHED_CSV,
    STREAMS_PROBED_CSV,
    VIEWER_DB,
    choose_streams_csv,
)
from builder.import_catalog import import_epg_dir, import_streams_csv, init_schema
from stream_viewer.db import connect, db_status, programme_count, stream_count

USER_AGENT = "StreamingViewerTV/1.0"

# Essential Pluto guides for prepare (downloaded only if missing).
PLUTO_ESSENTIAL = {
    "pluto_us.xml": "https://i.mjh.nz/PlutoTV/us.xml",
    "pluto_all.xml": "https://i.mjh.nz/PlutoTV/all.xml",
}


def fetch_bytes(url: str, timeout: float = 180.0) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def list_epg_files() -> list[Path]:
    if not EPG_DIR.is_dir():
        return []
    out: list[Path] = []
    for path in sorted(EPG_DIR.iterdir()):
        if not path.is_file() or path.stat().st_size <= 0:
            continue
        name = path.name.lower()
        if name.endswith((".xml", ".xml.gz")) or path.suffix.lower() == ".gz":
            out.append(path)
    return out


def step_download_streams(*, force: bool) -> Path:
    target = STREAMS_CSV
    if target.is_file() and target.stat().st_size > 0 and not force:
        print(f"[skip] streams.csv already present ({target.stat().st_size:,} bytes)")
        return target
    print("[download] IPTV playlist → streams.csv")
    code = download_streams.main()
    if code != 0 or not target.is_file():
        raise SystemExit("Failed to download streams.csv")
    return target


def step_enrich(*, force: bool) -> Path:
    target = STREAMS_ENRICHED_CSV
    source = STREAMS_CSV
    if target.is_file() and target.stat().st_size > 0 and not force:
        print(
            f"[skip] streams_enriched.csv already present "
            f"({target.stat().st_size:,} bytes)"
        )
        return target
    if not source.is_file():
        raise SystemExit("Missing streams.csv; cannot enrich")
    print("[download/enrich] iptv-org API metadata → streams_enriched.csv")
    code = enrich.main()
    if code != 0 or not target.is_file():
        raise SystemExit("Failed to enrich streams")
    return target


def step_probe(
    *,
    force: bool,
    limit: int | None,
    all_streams: bool,
    workers: int,
    deep: bool,
) -> Path:
    target = STREAMS_PROBED_CSV
    if (
        target.is_file()
        and target.stat().st_size > 0
        and not force
        and not all_streams
        and limit is None
    ):
        print(
            f"[skip] streams_probed.csv already present "
            f"({target.stat().st_size:,} bytes)"
        )
        return target

    argv: list[str] = ["--workers", str(max(1, workers))]
    if deep:
        argv.append("--deep")
    if force:
        argv.append("--force")
    if all_streams:
        argv.append("--all")
    elif limit is not None:
        argv.extend(["--limit", str(limit)])
    else:
        # Safe default when --probe is used without scope flags.
        argv.extend(["--limit", "50"])
        print("[probe] no --probe-all/--probe-limit; defaulting to --limit 50")

    print(f"[probe] HLS health → streams_probed.csv ({' '.join(argv)})")
    code = probe.main(argv)
    if code != 0 or not target.is_file():
        raise SystemExit("Failed to probe streams")
    return target


def step_ensure_epg(*, force: bool) -> list[Path]:
    ensure_dir(EPG_DIR)
    for name in PLUTO_ESSENTIAL:
        dest = EPG_DIR / name
        cache = EPG_CACHE_DIR / name
        if dest.is_file() and dest.stat().st_size > 0 and not force:
            print(f"[skip] {dest.relative_to(ROOT)}")
            continue
        if cache.is_file() and cache.stat().st_size > 0 and not force:
            print(f"[copy] {cache.relative_to(ROOT)} → epg/{name}")
            dest.write_bytes(cache.read_bytes())
            continue
        url = PLUTO_ESSENTIAL[name]
        print(f"[download] {url} → epg/{name}")
        dest.write_bytes(fetch_bytes(url))

    files = list_epg_files()
    if not files:
        raise SystemExit(f"No EPG XML files under {EPG_DIR}")
    return files


def verify_essentials() -> dict[str, Path | list[Path]]:
    print("\n=== Verify essential files ===")
    csv_path = choose_streams_csv()
    epg_files = list_epg_files()
    ok = True

    if csv_path:
        print(
            f"  [ok] catalog  {csv_path.relative_to(ROOT)} "
            f"({csv_path.stat().st_size:,} bytes)"
        )
    else:
        print("  [missing] catalog CSV (streams_probed/enriched/streams.csv)")
        ok = False

    if epg_files:
        for path in epg_files:
            print(
                f"  [ok] epg      {path.relative_to(ROOT)} "
                f"({path.stat().st_size:,} bytes)"
            )
    else:
        print(f"  [missing] EPG under {EPG_DIR}/")
        ok = False

    if not ok:
        raise SystemExit("Essential files missing; aborting before SQLite import")

    assert csv_path is not None
    return {"streams_csv": csv_path, "epg_files": epg_files}


def step_import_sqlite(csv_path: Path) -> Path:
    print("\n=== Load viewer.db ===")
    if VIEWER_DB.exists():
        VIEWER_DB.unlink()
    conn = connect(VIEWER_DB)
    try:
        init_schema(conn)
        n_streams = import_streams_csv(conn, csv_path)
        print(f"  imported streams: {n_streams} from {csv_path.name}")
        n_files, n_progs = import_epg_dir(conn, EPG_DIR)
        print(f"  imported programmes: {n_progs} from {n_files} guide file(s)")
        status = db_status(conn)
    finally:
        conn.close()

    if n_streams <= 0:
        raise SystemExit("viewer.db has zero streams")
    if n_progs <= 0:
        print("  [warn] viewer.db has zero programmes (Now-playing will be empty)")

    print(f"  wrote {VIEWER_DB.relative_to(ROOT)} ({VIEWER_DB.stat().st_size:,} bytes)")
    print(
        f"  status: streams={status['streams']} "
        f"programmes={status['programmes']} "
        f"source={status['streams_source']}"
    )
    return VIEWER_DB


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download + verify essentials, then build iptv_export/viewer.db",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Do not fetch playlist / Pluto / API; only verify existing files and import",
    )
    parser.add_argument(
        "--skip-enrich",
        action="store_true",
        help="Skip API enrichment (use streams.csv or existing enriched/probed CSV)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download / re-enrich / re-probe even when local files exist",
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help="Run HLS probe and prefer streams_probed.csv for the DB import",
    )
    parser.add_argument(
        "--probe-all",
        action="store_true",
        help="With --probe, check every stream (slow)",
    )
    parser.add_argument(
        "--probe-limit",
        type=int,
        help="With --probe, only probe the first N eligible streams",
    )
    parser.add_argument(
        "--probe-workers",
        type=int,
        default=16,
        help="Parallel probe workers (default: 16)",
    )
    parser.add_argument(
        "--probe-deep",
        action="store_true",
        help="With --probe, also fetch child media playlists",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ensure_dir(EXPORT_DIR)

    print("=== Build StreamingViewerTV data ===")
    if not args.skip_download:
        step_download_streams(force=args.force)
        if not args.skip_enrich:
            step_enrich(force=args.force)
        step_ensure_epg(force=args.force)
    else:
        print("[skip] download stage (--skip-download)")

    if args.probe:
        if args.probe_all and args.probe_limit is not None:
            raise SystemExit("Use only one of --probe-all or --probe-limit")
        step_probe(
            force=args.force,
            limit=args.probe_limit,
            all_streams=args.probe_all,
            workers=args.probe_workers,
            deep=args.probe_deep,
        )

    verified = verify_essentials()
    csv_path = verified["streams_csv"]
    assert isinstance(csv_path, Path)

    step_import_sqlite(csv_path)

    conn = connect(VIEWER_DB)
    try:
        streams = stream_count(conn)
        programmes = programme_count(conn)
    finally:
        conn.close()

    print("\n=== Ready ===")
    print(f"  {VIEWER_DB}")
    print(f"  streams={streams} programmes={programmes}")
    print(f"  catalog source file: {csv_path.name}")
    print("  Start the UI with: uv run stream-viewer")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        raise SystemExit(130)
