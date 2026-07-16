# StreamingViewerTV — Developer Guide

For the user-facing quick start, see [README.md](README.md). This doc covers building,
running, and releasing from source.

Two halves:

| | **Builder** | **Viewer** |
|---|-------------|------------|
| Role | Download / verify / load data | Browse & play streams |
| Package | `builder/` | `stream_viewer/` |
| Command | `uv run stream-viewer-build` | `uv run stream-viewer` |
| Output / input | writes `iptv_export/viewer.db` | reads `iptv_export/viewer.db` |

Default M3U source: `https://iptv-org.github.io/iptv/index.m3u`

## Requirements

- Python 3.10+
- Network access (builder only)
- [uv](https://docs.astral.sh/uv/)

```bash
uv sync
```

## Layout

```
builder/                 # offline data pipeline
  download_streams.py    # M3U → streams.csv
  enrich.py               # API metadata → streams_enriched.csv
  probe.py                # optional HLS health grades
  fetch_epg.py             # iptv-org XMLTV guides
  check_urls.py           # live URL checks via the viewer proxy
  prepare_db.py           # orchestrate + import viewer.db
  paths.py                 # shared iptv_export paths

stream_viewer/           # FastAPI UI (runtime)
  app.py
  db.py                  # SQLite schema + queries (shared with builder)
  epg.py
  static/ templates/

iptv_export/             # generated data (gitignored)
  viewer.db              # required by the viewer
  streams*.csv           # intermediate CSVs
  epg/                   # XMLTV inputs for prepare

packaging/               # PyInstaller desktop bundles
  streaming_viewer_tv.spec
```

## Builder

Downloads essentials (playlist, enrichment, Pluto guides if missing), verifies local files, then builds SQLite:

```bash
uv run stream-viewer-build
# same as: uv run python -m builder.prepare_db

# Include HLS probe (slow for full catalog)
uv run stream-viewer-build --probe --probe-all --probe-deep
```

Or via Make:

```bash
make build              # no probe
make probe              # all streams → streams_probed.csv
make probe LIMIT=50     # quick sample
make build-probed       # download + enrich + probe-all + import
make build-probed LIMIT=100
```

Output: **`iptv_export/viewer.db`** (`streams`, `programmes`, `guide_sources`, `meta`).

### Optional builder steps

```bash
uv run python -m builder.download_streams
uv run python -m builder.enrich
uv run python -m builder.probe --limit 50
uv run python -m builder.fetch_epg --sites tvpassport.com,ontvtonight.com,tvtv.us
uv run python -m builder.check_urls --limit 50 --deep
```

Then: `uv run stream-viewer-build --skip-download`

### Intermediate files (inputs to the DB)

| File | Role |
|------|------|
| `iptv_export/streams.csv` | Raw playlist extract |
| `iptv_export/streams_enriched.csv` | + country/language/topics/quality |
| `iptv_export/streams_probed.csv` | Optional probe grades (preferred if present) |
| `iptv_export/epg/*.xml` | XMLTV guides imported into `programmes` |

## CSV columns

### Base (`streams.csv`)

| Column | Meaning |
|--------|---------|
| `name` | Channel display name |
| `url` | Stream URL |
| `tvg_id` | EPG / guide channel id |
| `tvg_logo` | Channel logo URL |
| `group_title` | Category / genre from the playlist |
| `http_referrer` | Optional Referer some streams require |
| `http_user_agent` | Optional User-Agent some streams require |

### Enriched (`streams_enriched.csv`)

All base columns, plus:

| Column | Meaning | Source |
|--------|---------|--------|
| `country` | ISO country code (e.g. `US`) | iptv-org channels API |
| `country_name` | Country display name | iptv-org countries API |
| `language` | Language code(s), `;`-separated (e.g. `eng`) | iptv-org feeds API |
| `language_name` | Language display name(s) | iptv-org languages API |
| `maturity` | `Family` or `Adult` | derived from `is_nsfw` |
| `is_nsfw` | `true` / `false` | iptv-org channels API |
| `topics` | Topic tags, `;`-separated | API categories (fallback: playlist group) |
| `video_quality` | e.g. `1080p`, `720p`, `SD` | streams API / name parse / probe |
| `stream_quality` | `excellent` / `okay` / `poor` / `unknown` | probe script |
| `popularity` | Placeholder (`unknown`) | fill later from app usage |

### Probe grades (`builder.probe`)

| Grade | Meaning |
|-------|---------|
| `excellent` | Valid HLS, responds quickly, has resolution and/or media tags |
| `okay` | Valid HLS but slow or thin metadata |
| `poor` | Timeout, HTTP error, or not a usable playlist |

The first CSV row is the header; data starts on row 2.

## Viewer

Reads **`iptv_export/viewer.db`** only. Refuses to start if the DB is missing or empty.

```bash
uv run stream-viewer-build --skip-download   # if data files already local
uv run stream-viewer
```

Or: `uv run python -m stream_viewer.app`  
Open [http://127.0.0.1:8787](http://127.0.0.1:8787).

### Features

- Search by name / metadata; infinite-scroll sidebar
- Filters: category, country, language, topic, video quality, stream quality, maturity (when present)
- Filter / source prefs stored in a `svtv_filters` cookie; resizable sidebar splitter
- HLS playback via a local proxy (Referer / User-Agent, short session URLs, M3U8 rewrite after redirects)
- **Theater** expands the player and hides the sidebar (`T`)
- **Fullscreen** uses the browser fullscreen API on the player (`F`)
- Bottom **status bar**: stream/match/listed counts, `tvg_id` coverage, Guide state, playback state, errors, message

### What's on now (EPG)

Guides are imported into `viewer.db` during build. The viewer does **not** download EPG over HTTP at startup.

- **Sidebar:** each row shows `Now: Fetching…`, then `Now: <title>` or `Now: No data`
- **Viewer pane:** programme title sits beside the channel name (`Channel — Programme`)
- **`tvg_id` coverage** means the catalog has an EPG id — not that a title is available yet
- Pluto / iptv-org / custom XMLTV under `iptv_export/epg/` → `programmes` table via `stream-viewer-build`
- APIs: `/api/epg/now`, `/api/epg/status`; `/api/meta` includes `tvg_id_count` and guide status

#### Grab iptv-org EPG for this catalog

One-time tooling setup (Node.js required):

```bash
git clone --depth 1 https://github.com/iptv-org/epg.git .epg_tools
cd .epg_tools && npm install && cd ..
```

Then:

```bash
uv run python -m builder.fetch_epg --report-only
uv run python -m builder.fetch_epg --sites tvpassport.com,ontvtonight.com,tvtv.us
uv run python -m builder.fetch_epg --all-mapped --max-sites 12 --days 2
uv run stream-viewer-build --skip-download
```

## Live URL checks

```bash
uv run python -m builder.check_urls --limit 50 --deep
uv run python -m builder.check_urls --all --workers 16 --deep
```

## Tests

```bash
uv run pytest
uv run pytest -m live    # network; deselected by default
```

EPG / Now-playing UI contracts: `tests/test_epg.py`, `tests/test_now_playing_ui.py`.

Known issues and their regression tests live in [buglist.md](buglist.md) — check there
before filing a duplicate, and add an entry (with a test) for anything new you fix.

## Packaging (desktop bundles)

Releases ship a PyInstaller **onedir** bundle per platform (Windows zip, Linux/macOS
tarball). The shared spec is `packaging/streaming_viewer_tv.spec`. PyInstaller must
run **on the target OS** — there is no cross-compilation.

### Build a bundle locally

```bash
uv sync --group packaging
uv run stream-viewer-build --skip-download   # or a full probed build
uv run pyinstaller --noconfirm packaging/streaming_viewer_tv.spec

# Drop the catalog next to the executable (same layout as CI)
mkdir -p dist/StreamingViewerTV/iptv_export
cp iptv_export/viewer.db dist/StreamingViewerTV/iptv_export/viewer.db
chmod +x dist/StreamingViewerTV/StreamingViewerTV   # Linux / macOS
```

Then run `dist/StreamingViewerTV/StreamingViewerTV` (or `.exe` on Windows). A browser
tab should open at [http://127.0.0.1:8787](http://127.0.0.1:8787).

### Release artifacts

| Platform | CI runner | Archive name |
|----------|-----------|--------------|
| Windows x64 | `windows-latest` | `StreamingViewerTV-<tag>-windows-x64.zip` |
| Linux x86_64 | `ubuntu-latest` | `StreamingViewerTV-<tag>-linux-x86_64.tar.gz` |
| macOS Apple Silicon | `macos-latest` | `StreamingViewerTV-<tag>-macos-arm64.tar.gz` |

The prebuilt macOS release is **arm64 only**. On an Intel Mac, build the bundle
locally with the steps above (same spec). Bundles are unsigned — expect SmartScreen
(Windows) or Gatekeeper (macOS) warnings; see [README.md](README.md) troubleshooting.

## Versioning

The running version is shown in the viewer's status bar. `stream_viewer/_version.py` is the
single source of truth — `pyproject.toml` reads its version from that file, so there's only
one place to edit:

```python
__version__ = "0.1.0"
```

Bump it with each change, per [semver](https://semver.org/):

- **Patch** (`0.1.0` → `0.1.1`) for a `BUG-XXX` fix in [buglist.md](buglist.md)
- **Minor** (`0.1.0` → `0.2.0`) for a `FEAT-XXX` feature in [buglist.md](buglist.md)

Releases are automatic — just bump `_version.py` and merge/push to `main`. No manual tagging
step needed. The [release workflow](.github/workflows/release.yml) runs this pipeline:

1. **`plan`** reads `stream_viewer/_version.py` and checks whether a release for that version
   already exists.
   - Pushed to `main` and the version is unchanged (no new release needed): every other job
     is skipped and the run finishes green — no noise for routine pushes.
   - Pushed to `main` with a bumped version, **or** you manually pushed a `vX.Y.Z` tag: the
     rest of the pipeline runs. A manually-pushed tag is additionally validated — it must
     exactly match `_version.py`, and must not already have a release — failing loudly
     (triggers GitHub's default failure notification) if not.
2. **`test`** runs the full suite (incl. Playwright); a failure stops everything.
3. **`build-catalog`** builds a fresh `viewer.db`, including a full HLS probe of every
   stream (same as `make build-probed`) so releases ship with `stream_quality` grades,
   not just unprobed metadata.
4. **`build-windows`**, **`build-linux`**, and **`build-macos`** package that catalog into
   the three desktop bundles in parallel (see [Packaging](#packaging-desktop-bundles)
   for artifact names and local builds).
5. **`publish-release`** only runs once *all* platform bundles succeed — it creates the
   GitHub Release (and the underlying `vX.Y.Z` tag, which doesn't need to exist
   beforehand) with all three archives attached. If any platform build fails, no
   release is created.

Prefer to tag manually instead (e.g. for a hotfix off a non-`main` ref)? That still works:

```bash
git tag v0.1.0
git push origin v0.1.0
```

Every push/PR to `main` also runs the [CI workflow](.github/workflows/ci.yml) — the same full
test suite, independent of any release — so regressions surface immediately, before `plan`
even has a chance to decide whether to release.
