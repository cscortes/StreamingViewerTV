#!/usr/bin/env python3
"""Build iptv-org channel lists from our CSV and grab XMLTV into iptv_export/epg/.

Uses the local checkout at .epg_tools/ (iptv-org/epg). Guides are keyed by the
same xmltv_id / tvg_id values as the playlist, so the viewer can show Now: titles
beyond Pluto.

Examples:
  # Map catalog → which sites cover us, then grab a few US-friendly sites
  uv run python -m builder.fetch_epg --sites tvpassport.com,ontvtonight.com,tvtv.us

  # Grab every site that maps to at least one catalog channel (slow)
  uv run python -m builder.fetch_epg --all-mapped --max-sites 15
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path
from urllib.request import Request, urlopen

from builder.paths import EPG_CHANNELS_DIR, EPG_DIR, EXPORT_DIR, ROOT

EPG_TOOLS = ROOT / ".epg_tools"
CHANNELS_DIR = EPG_CHANNELS_DIR
EXPORT = EXPORT_DIR
GUIDES_API = "https://iptv-org.github.io/api/guides.json"
DEFAULT_SOURCES = (
    "streams_probed.csv",
    "streams_enriched.csv",
    "streams.csv",
)

# Prefer these when a channel appears on multiple sites.
SITE_PRIORITY = (
    "tvpassport.com",
    "ontvtonight.com",
    "tvtv.us",
    "tvguide.com",
    "freeview.co.uk",
    "chaines-tv.orange.fr",
    "gatotv.com",
    "mi.tv",
    "meuguia.tv",
    "airtelxstream.in",
    "dishtv.in",
    "tataplay.com",
    "horizon.tv",
    "distro.tv",
    "m.tv.sms.cz",
    "canalplus.com",
    "tv.mail.ru",
    "sat.tv",
    "epg.iptvx.one",
    "i.mjh.nz",
)


def resolve_csv(explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit)
        if not path.is_file():
            raise SystemExit(f"CSV not found: {path}")
        return path
    for name in DEFAULT_SOURCES:
        path = EXPORT / name
        if path.is_file():
            return path
    raise SystemExit(f"No CSV found under {EXPORT}")


def load_tvg_ids(csv_path: Path) -> list[str]:
    ids: list[str] = []
    with csv_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            tvg = (row.get("tvg_id") or "").strip()
            if tvg:
                ids.append(tvg)
    return ids


def fetch_guides() -> list[dict]:
    print(f"Downloading {GUIDES_API} …")
    req = Request(GUIDES_API, headers={"User-Agent": "StreamingViewerTV/1.0"})
    with urlopen(req, timeout=120) as response:  # noqa: S310 — fixed HTTPS URL
        return json.loads(response.read().decode("utf-8"))


def index_guides(guides: list[dict]) -> tuple[dict[str, list[dict]], dict[str, list[dict]]]:
    by_full: dict[str, list[dict]] = defaultdict(list)
    by_channel: dict[str, list[dict]] = defaultdict(list)
    for guide in guides:
        channel = guide.get("channel")
        if not channel:
            continue
        feed = guide.get("feed")
        by_channel[channel].append(guide)
        if feed:
            by_full[f"{channel}@{feed}"].append(guide)
    return by_full, by_channel


def pick_guide(candidates: list[dict]) -> dict | None:
    if not candidates:
        return None
    priority = {site: index for index, site in enumerate(SITE_PRIORITY)}

    def sort_key(guide: dict) -> tuple[int, str]:
        site = guide.get("site") or ""
        return (priority.get(site, len(SITE_PRIORITY)), site)

    return sorted(candidates, key=sort_key)[0]


def map_catalog(
    tvg_ids: list[str],
    by_full: dict[str, list[dict]],
    by_channel: dict[str, list[dict]],
) -> tuple[dict[str, list[dict]], int]:
    """Return site -> channel dicts for channels.xml, plus matched stream count."""
    site_channels: dict[str, dict[str, dict]] = defaultdict(dict)
    matched = 0
    for tvg in tvg_ids:
        base = tvg.split("@", 1)[0]
        candidates = by_full.get(tvg) or by_channel.get(base) or []
        guide = pick_guide(candidates)
        if not guide:
            continue
        matched += 1
        site = (guide.get("site") or "").strip()
        site_id = (guide.get("site_id") or "").strip()
        if not site or not site_id:
            continue
        # Keep playlist tvg_id so the viewer matches without alias translation.
        xmltv_id = tvg
        lang = (guide.get("lang") or "en").strip() or "en"
        name = (guide.get("site_name") or xmltv_id).strip() or xmltv_id
        # Deduplicate by xmltv_id within a site.
        site_channels[site][xmltv_id] = {
            "site": site,
            "site_id": site_id,
            "xmltv_id": xmltv_id,
            "lang": lang,
            "name": name,
        }
    return site_channels, matched


def write_channels_xml(path: Path, channels: list[dict]) -> None:
    root = ET.Element("channels")
    for item in sorted(channels, key=lambda row: row["xmltv_id"].lower()):
        node = ET.SubElement(root, "channel")
        node.set("site", item["site"])
        node.set("lang", item["lang"])
        node.set("xmltv_id", item["xmltv_id"])
        node.set("site_id", item["site_id"])
        node.text = item["name"]
    path.parent.mkdir(parents=True, exist_ok=True)
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)


def ensure_epg_tools() -> Path:
    if not EPG_TOOLS.is_dir():
        raise SystemExit(
            f"Missing {EPG_TOOLS}. Clone it with:\n"
            f"  git clone --depth 1 https://github.com/iptv-org/epg.git .epg_tools\n"
            f"  cd .epg_tools && npm install"
        )
    if not (EPG_TOOLS / "node_modules").is_dir():
        print("Installing iptv-org/epg dependencies …")
        subprocess.run(["npm", "install"], cwd=EPG_TOOLS, check=True)
    return EPG_TOOLS


def grab_channels(
    channels_xml: Path,
    output_xml: Path,
    *,
    days: int,
    max_connections: int,
) -> None:
    ensure_epg_tools()
    output_xml.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "npm",
        "run",
        "grab",
        "--",
        f"--channels={channels_xml.resolve()}",
        f"--output={output_xml.resolve()}",
        f"--days={days}",
        f"--maxConnections={max_connections}",
    ]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, cwd=EPG_TOOLS, check=True)


def count_programmes(path: Path) -> tuple[int, int]:
    text = path.read_text(encoding="utf-8", errors="replace")
    channels = len(re.findall(r"<channel\s", text))
    programmes = len(re.findall(r"<programme\s", text))
    return channels, programmes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", help="Catalog CSV (default: probed/enriched/streams)")
    parser.add_argument(
        "--sites",
        help="Comma-separated sites to grab (default: top mapped sites)",
    )
    parser.add_argument(
        "--all-mapped",
        action="store_true",
        help="Include every site that maps to at least one catalog channel",
    )
    parser.add_argument("--max-sites", type=int, default=8, help="Cap sites when auto-selecting")
    parser.add_argument("--days", type=int, default=1, help="Programme days to download")
    parser.add_argument("--max-connections", type=int, default=3)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only write channels.xml mapping reports; do not grab",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Print coverage stats and exit",
    )
    args = parser.parse_args()

    csv_path = resolve_csv(args.csv)
    tvg_ids = load_tvg_ids(csv_path)
    print(f"Catalog {csv_path.name}: {len(tvg_ids)} rows with tvg_id")

    guides = fetch_guides()
    by_full, by_channel = index_guides(guides)
    site_channels, matched = map_catalog(tvg_ids, by_full, by_channel)
    print(
        f"Mapped {matched}/{len(tvg_ids)} tvg_id rows "
        f"({100 * matched / max(len(tvg_ids), 1):.1f}%) across {len(site_channels)} sites"
    )

    ranked = sorted(site_channels.items(), key=lambda item: len(item[1]), reverse=True)
    for site, channels in ranked[:20]:
        print(f"  {site}: {len(channels)} channels")

    if args.report_only:
        return 0

    if args.sites:
        wanted = {part.strip() for part in args.sites.split(",") if part.strip()}
    elif args.all_mapped:
        wanted = {site for site, _ in ranked[: max(1, args.max_sites)]}
    else:
        # Default pilot: priority sites that actually appear in the mapping.
        wanted = []
        for site in SITE_PRIORITY:
            if site in site_channels:
                wanted.append(site)
            if len(wanted) >= args.max_sites:
                break
        wanted = set(wanted)
        if not wanted:
            wanted = {site for site, _ in ranked[: args.max_sites]}

    CHANNELS_DIR.mkdir(parents=True, exist_ok=True)
    EPG_DIR.mkdir(parents=True, exist_ok=True)

    selected_total = 0
    for site in sorted(wanted):
        channels = list(site_channels.get(site, {}).values())
        if not channels:
            print(f"Skip {site}: no mapped channels")
            continue
        selected_total += len(channels)
        safe = re.sub(r"[^\w.-]+", "_", site)
        channels_xml = CHANNELS_DIR / f"{safe}.channels.xml"
        write_channels_xml(channels_xml, channels)
        print(f"Wrote {channels_xml} ({len(channels)} channels)")
        if args.dry_run:
            continue
        output_xml = EPG_DIR / f"iptvorg_{safe}.xml"
        try:
            grab_channels(
                channels_xml,
                output_xml,
                days=args.days,
                max_connections=args.max_connections,
            )
        except subprocess.CalledProcessError as exc:
            print(f"Grab failed for {site}: {exc}", file=sys.stderr)
            continue
        if output_xml.is_file():
            ch_count, prog_count = count_programmes(output_xml)
            print(f"  -> {output_xml.name}: {ch_count} channels, {prog_count} programmes")

    print(f"Selected {selected_total} channel mappings across {len(wanted)} site(s)")
    if not args.dry_run:
        print(f"Guides are in {EPG_DIR} — restart stream-viewer to load them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
