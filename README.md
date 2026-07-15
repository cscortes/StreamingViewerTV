# StreamingViewerTV

Two halves:

| | **Builder** | **Viewer** |
|---|-------------|------------|
| Role | Download / verify / load data | Browse & play streams |
| Package | `builder/` | `stream_viewer/` |
| Command | `uv run stream-viewer-build` | `uv run stream-viewer` |
| Output / input | writes `iptv_export/viewer.db` | reads `iptv_export/viewer.db` |

Default M3U source: `https://iptv-org.github.io/iptv/index.m3u`

## Windows / Linux — no Python required

Don't want to install Python/`uv`? Grab a packaged build from the
[Releases page](../../releases) — it ships with a pre-built catalog, so it
works immediately, even offline.

**Windows:**

1. Download `StreamingViewerTV-<version>-windows-x64.zip` and unzip it anywhere.
2. Double-click `StreamingViewerTV.exe` inside the extracted folder. A browser tab opens automatically at the viewer.
3. Windows SmartScreen may warn about an unrecognized publisher — the app isn't code-signed. Click **More info** → **Run anyway** to continue.

**Linux:**

1. Download `StreamingViewerTV-<version>-linux-x86_64.tar.gz` and extract it: `tar xzf StreamingViewerTV-*.tar.gz`.
2. Run it: `./StreamingViewerTV/StreamingViewerTV` (double-click may also work, depending on your file manager's launcher settings; if extraction stripped the executable bit, run `chmod +x StreamingViewerTV/StreamingViewerTV` first).
3. A browser tab opens automatically at the viewer.

The bundled catalog is a snapshot as of that release's build date. Grab a newer release for fresher data — there's no in-app "refresh" button (yet).

These builds are produced automatically by [.github/workflows/release.yml](.github/workflows/release.yml) whenever a `vX.Y.Z` tag is pushed; see [Versioning](#versioning) below.

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
  enrich.py              # API metadata → streams_enriched.csv
  probe.py               # optional HLS health grades
  fetch_epg.py           # iptv-org XMLTV guides
  check_urls.py          # live URL checks via the viewer proxy
  prepare_db.py          # orchestrate + import viewer.db
  paths.py               # shared iptv_export paths

stream_viewer/           # FastAPI UI (runtime)
  app.py
  db.py                  # SQLite schema + queries (shared with builder)
  epg.py
  static/ templates/

iptv_export/             # generated data (gitignored)
  viewer.db              # required by the viewer
  streams*.csv           # intermediate CSVs
  epg/                   # XMLTV inputs for prepare
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

### What’s on now (EPG)

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

To publish a release, push a matching tag:

```bash
git tag v0.1.0
git push origin v0.1.0
```

The [release workflow](.github/workflows/release.yml) then runs this pipeline:

1. **`test`** and **`check-version`** run in parallel: the full test suite (incl. Playwright)
   must pass, and the tag must equal `_version.py`'s value with no existing release for that
   tag already — either failing stops everything immediately (and marks the run red, which
   triggers GitHub's default failure notification to whoever pushed the tag).
2. **`build-catalog`** builds a fresh `viewer.db`.
3. **`build-windows`** and **`build-linux`** package that catalog into the two desktop bundles, in parallel.
4. **`publish-release`** only runs once *both* bundles succeed — it creates the GitHub Release
   for that tag with both archives attached. If either platform build fails, no release is created.

Every push/PR to `main` also runs the [CI workflow](.github/workflows/ci.yml) — the same full
test suite, independent of any release — so regressions surface long before you get to tagging.
