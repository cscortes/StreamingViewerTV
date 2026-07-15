# Bug list

| ID | Date reported | Description | Status | Fixed |
|----|---------------|-------------|--------|-------|
| BUG-001 | 2026-07-13 | After selecting a stream, the “Pick a stream” overlay stays visible on top of the player. | Fixed | 2026-07-13 |
| BUG-002 | 2026-07-13 | “Now: …” EPG titles vanish after browsing Pluto channels from more than one country. | Fixed | 2026-07-13 |
| BUG-003 | 2026-07-13 | Now-playing line is blank instead of always showing Fetching / title / No data. | Fixed | 2026-07-13 |
| BUG-004 | 2026-07-13 | Programme title missing beside stream name in the viewer pane. | Fixed | 2026-07-13 |
| BUG-005 | 2026-07-13 | Stale cookie `source=streams_probed.csv` yields 404 on stream detail after switching to viewer.db. | Fixed | 2026-07-13 |
| BUG-006 | 2026-07-13 | Redundant match count next to Reset duplicates the status bar. | Fixed | 2026-07-13 |
| BUG-007 | 2026-07-13 | Header Source picker and Reload button are unnecessary with viewer.db. | Fixed | 2026-07-13 |
| BUG-008 | 2026-07-13 | Brand subtitle showed catalog source/stream count; count belongs only in the status bar. | Fixed | 2026-07-13 |
| BUG-009 | 2026-07-13 | Viewer still inventoried/parsed CSV and XMLTV; runtime must use viewer.db only. | Fixed | 2026-07-13 |
| BUG-010 | 2026-07-13 | Category / filter dropdowns hard to find or squeezed in the filter bar. | Fixed | 2026-07-13 |
| BUG-011 | 2026-07-13 | Category filter not visible; catalog must have categories with stream items. | Fixed | 2026-07-13 |
| BUG-012 | 2026-07-13 | Category filters still missing in UI because they were JS-only into an empty form. | Fixed | 2026-07-13 |
| FEAT-001 | 2026-07-13 | Show “what’s on now” (EPG title) in the sidebar and player when available. | Done | 2026-07-13 |
| BUG-013 | 2026-07-14 | `stream-viewer-build` crashes with `NameError` right after writing `viewer.db`, so the build reports failure despite succeeding. | Fixed | 2026-07-14 |
| FEAT-002 | 2026-07-14 | Windows/Linux desktop packaging (PyInstaller) with automated GitHub Releases; visible semantic version in the status bar. | Done | 2026-07-14 |

## Details

### BUG-001 — “Pick a stream” banner stays after selection

- **Reported:** 2026-07-13
- **Status:** Fixed
- **Fixed:** 2026-07-13
- **Cause:** `.player-empty { display: grid }` overrode the HTML `hidden` attribute.
- **Fix:** `.player-empty[hidden] { display: none !important; }`

### BUG-002 — Multi-country Pluto EPG wipes prior “Now:” titles

- **Reported:** 2026-07-13
- **Status:** Fixed
- **Fixed:** 2026-07-13
- **Symptom:** Status bar can show Guide **Loaded**, but most sidebar/player `Now: …` lines are missing. Hitting channels from a second Pluto region (e.g. DE after US) makes earlier region titles disappear.
- **Cause:** `EpgStore.ensure_pluto_guide()` deleted **all** `pluto:*` programme keys before indexing the newly loaded country, so only the last region remained in memory.
- **Fix:** Track programme keys per guide source and drop/reindex only that source when refreshing; keep other countries’ programmes.

#### AI instructions (regression workflow)

When working this bug (or a regression of it), do **not** “fix by inspection” alone. Follow this order:

1. **Reproduce with a failing test first**
   - Add a unit test under `tests/test_epg.py` (or extend an existing one) that:
     - Builds two tiny XMLTV fixtures for different Pluto channel UUIDs (e.g. US + DE), each with a current programme title.
     - Writes them as `pluto_us.xml` / `pluto_de.xml` under a temp `epg_cache` dir used by `EpgStore`.
     - Calls `ensure_pluto_guide("us")` then `ensure_pluto_guide("de")`.
     - Asserts **both** `now_for_keys(["pluto:<us-uuid>"])` and `now_for_keys(["pluto:<de-uuid>"])` still return their titles after the second load.
   - Run that test against the **broken** behavior (or temporarily reintroduce the wipe) and confirm it **fails** for the right reason (US title gone after DE load). Do not proceed until the failure is observed.

2. **Implement the fix**
   - Change `stream_viewer/epg.py` so loading one Pluto region does not clear other regions’ indexed programmes (per-source key tracking).

3. **Verify the same test now passes**
   - Re-run the exact test from step 1; it must pass.
   - Also run `uv run pytest tests/test_epg.py` and keep related EPG tests green.
   - Optional smoke: with the app running, load a US Pluto channel (confirm `Now:`), then a DE/IT Pluto channel, then return to the US channel — US `Now:` must still appear.

4. **Do not mark fixed** until step 3’s regression test is green.

Canonical regression test: `tests/test_epg.py::test_pluto_guides_keep_prior_countries`.

### BUG-003 — Always show Now: Fetching… / title / No data

- **Reported:** 2026-07-13
- **Status:** Fixed
- **Fixed:** 2026-07-13
- **Symptom:** Sidebar/player often show no programme line at all. User expects a visible status: `Now: Fetching…` while loading, `Now: <title>` when known, otherwise `Now: No data`.
- **Cause:** `.stream-now` stayed `hidden` unless EPG returned a title; empty/null results cleared the line. Also, Pluto channels tagged with unknown country codes (e.g. `SE`) never consulted the combined guide.
- **Fix:** Always render the Now line in one of the three states (sidebar + player). For Pluto, map unknown countries to `all` and fall back to the combined guide when the region guide has no hit.

#### AI instructions (regression workflow)

1. **Reproduce with failing checks first**
   - Add/extend `tests/test_epg.py` for backend gaps (e.g. unknown country → `pluto_all` guide) and confirm the new test **fails** on the broken code.
   - Add `tests/test_now_playing_ui.py` (or equivalent) that reads `stream_viewer/static/app.js` and asserts the UI contract strings/helpers exist and that new rows are not created with `hidden` Now lines. Confirm this fails if the placeholder UX is removed.
   - Optionally hard-fail a temporary change that hides empty Now lines, to prove the UI test catches the regression.

2. **Implement the fix**
   - `app.js`: `setStreamNowLine` / `formatNowDetails` — never blank; pending → Fetching…; miss → No data; hit → title.
   - `epg.py`: unknown Pluto country uses / falls back to `all`.

3. **Verify the same tests pass**
   - `uv run pytest tests/test_epg.py tests/test_now_playing_ui.py`
   - Manual: hard-refresh viewer — every listed row shows `Now: Fetching…` then either a title or `Now: No data`; viewer `#nowProgramme` follows Fetching… / title / No data beside the stream name.

4. **Do not mark fixed** until step 3 is green.

Canonical tests: `tests/test_epg.py::test_unknown_country_uses_all_guide`, `tests/test_now_playing_ui.py`.

### BUG-004 — Programme title beside stream name in viewer pane

- **Reported:** 2026-07-13
- **Status:** Fixed
- **Fixed:** 2026-07-13
- **Symptom:** When EPG finds a programme, it appears in the sidebar but not clearly next to the stream name in the bottom viewer pane.
- **Cause:** Player header only set `#nowTitle` (channel name); programme lived only in `#nowDetails` meta text (easy to miss) or was absent from the title row.
- **Fix:** Add `#nowProgramme` in `.now-title-row` beside `#nowTitle`, updated via `setViewerProgramme()` whenever EPG resolves (Fetching… / title / No data).

#### AI instructions (regression workflow)

1. **Reproduce with a failing test first**
   - Extend `tests/test_now_playing_ui.py` to assert:
     - `index.html` contains `id="nowProgramme"` in the same title row as `id="nowTitle"`.
     - `app.js` defines `setViewerProgramme` and calls it from `playStream` / `refreshNowPlaying` when a title is found.
   - Confirm the test **fails** if `#nowProgramme` or `setViewerProgramme` is removed.

2. **Implement the fix**
   - Wire programme text into the viewer title row alongside the stream name.

3. **Verify the same test passes**
   - `uv run pytest tests/test_now_playing_ui.py`
   - Manual: select a Pluto channel with a known `Now:` sidebar title — viewer pane must show `Channel — Programme` in the bottom header.

4. **Do not mark fixed** until step 3 is green.

Canonical test: `tests/test_now_playing_ui.py::test_viewer_pane_shows_programme_beside_stream_name`.

### BUG-005 — Stale catalog source cookie 404s after viewer.db

- **Reported:** 2026-07-13
- **Status:** Fixed
- **Fixed:** 2026-07-13
- **Symptom:** UI requests like `GET /api/streams/0?source=streams_probed.csv` return **404** after moving the runtime catalog to `viewer.db`. Browser cookie `svtv_filters` still remembered the old CSV source; that file is often missing (gitignored / `make clean` / build without probe).
- **Cause:** `resolve_source()` hard-failed on unknown sources instead of falling back to `viewer.db`. The UI also listed intermediate CSVs as selectable sources.
- **Fix:**
  - `available_sources()` exposes only `viewer.db` for the running app.
  - `resolve_source()` ignores missing/stale source names and falls back to `viewer.db`.
  - `ensure_catalog()` compares against the **resolved** source name so stale cookies do not thrash reloads.
  - `app.js` `loadMeta` rewrites prefs when the server returns a different source than requested.

#### AI instructions (regression workflow)

1. **Reproduce with a failing test first**
   - Under `tests/test_known_issues.py`, with a temp export that has `viewer.db` but **no** `streams_probed.csv`:
     - `GET /api/streams/0?source=streams_probed.csv` must **not** 404.
     - `GET /api/meta?source=streams_probed.csv` must report `source: viewer.db`.
     - `available_sources()` must list only `viewer.db`.
   - Confirm the old hard-404 behavior fails that test.

2. **Implement the fix** (see bullets above in `stream_viewer/app.py` + `static/app.js`).

3. **Verify**
   - `uv run pytest tests/test_known_issues.py -k stale_source`
   - Manual: hard-refresh with an old `svtv_filters` cookie containing `streams_probed.csv` — stream clicks must work; source label shows `viewer.db`.

4. **Do not mark fixed** until the regression test is green.

Canonical test: `tests/test_known_issues.py::TestStaleCatalogSource::test_stale_csv_source_falls_back_to_viewer_db`.

### BUG-006 — Redundant match count beside Reset

- **Reported:** 2026-07-13
- **Status:** Fixed
- **Fixed:** 2026-07-13
- **Symptom:** Filter bar shows “N matches” next to Reset while the status bar already shows match/listed counts.
- **Cause:** Legacy `#resultCount` in the filter meta row duplicated status-bar messaging.
- **Fix:** Remove `#resultCount` from the template/CSS/JS; keep match totals only in the status bar.

#### AI instructions (regression workflow)

1. Assert `index.html` has `resetFiltersBtn` but **no** `id="resultCount"`.
2. Assert `app.js` does not reference `resultCount`.
3. Confirm status bar still updates match text via `state.statusMessage`.

Canonical test: `tests/test_now_playing_ui.py::test_no_duplicate_match_count_beside_reset`.

### BUG-007 — Remove header Source picker and Reload

- **Reported:** 2026-07-13
- **Status:** Fixed
- **Fixed:** 2026-07-13
- **Symptom:** Upper-right Source dropdown and Reload button clutter the main screen; runtime catalog is always `viewer.db`.
- **Cause:** Leftover multi-CSV UI from before the SQLite catalog.
- **Fix:** Remove `#sourceSelect` / `#reloadBtn` from the header; brand subtitle shows stream count only. Catalog source still appears in the status bar.

#### AI instructions (regression workflow)

1. Assert `index.html` has no `sourceSelect` or `reloadBtn`.
2. Assert `app.js` has no `sourceSelect` / `reloadBtn` listeners.
3. Brand subtitle still updates via `#sourceLabel` with a stream count.

Canonical test: `tests/test_now_playing_ui.py::test_no_header_source_picker_or_reload`.

### BUG-008 — Brand subtitle must not show source or stream count

- **Reported:** 2026-07-13
- **Status:** Fixed
- **Fixed:** 2026-07-13
- **Symptom:** Under “StreamingViewerTV”, the UI showed catalog source (`streams_probed.csv` / `viewer.db`) and/or stream count; that duplicates status-bar info and is unnecessary branding noise.
- **Cause:** `#sourceLabel` / `.brand-sub` under the brand name.
- **Fix:** Remove the brand subtitle. Status bar shows **Streams** (catalog total) plus Matches / Listed.

#### AI instructions (regression workflow)

1. Assert `index.html` has brand text but no `#sourceLabel` / `.brand-sub`.
2. Assert status bar has Streams via `#statusCatalog`.
3. Assert `app.js` does not set `sourceLabel` text.

Canonical test: `tests/test_now_playing_ui.py::test_brand_has_no_source_or_stream_subtitle`.

### BUG-009 — Viewer must not verify or parse CSV/XMLTV

- **Reported:** 2026-07-13
- **Status:** Fixed
- **Fixed:** 2026-07-13
- **Symptom:** Startup inventoried `streams*.csv` and `epg/*.xml`; `load_catalog` could still parse CSV; `stream_viewer.epg` / `db` still contained XMLTV/CSV import paths.
- **Cause:** Leftover catalog pipelines after switching runtime to `viewer.db`.
- **Fix:** Prepare-stage import lives in `builder/import_catalog.py`. Viewer read-only SQLite + EPG key helpers only. Startup checks `viewer.db` alone.

#### AI instructions (regression workflow)

1. Assert `stream_viewer/app.py` has no `import csv` / `DictReader`.
2. Assert `stream_viewer/db.py` and `epg.py` have no `ElementTree` / CSV import.
3. Assert CSV/XML import APIs live under `builder/`.
4. Stale `?source=streams_probed.csv` still serves `viewer.db` (BUG-005).

Canonical test: `tests/test_epg.py::test_viewer_has_no_csv_or_xml_parsers`.

### BUG-010 — Category filters must stay visible and usable

- **Reported:** 2026-07-13
- **Status:** Fixed
- **Fixed:** 2026-07-13
- **Symptom:** Category (and other) filter dropdowns appeared missing after chrome cleanup.
- **Cause:** Filter bar was a single flex row; with search + Reset, the `#filterForm` selects could be squeezed/`min-width: 0` collapsed. API still returned `group_title` as Category.
- **Fix:** Give filters a dedicated full-width grid row, restore select chevrons, cap huge exact-match option lists, split multi-value `group_title`.

#### AI instructions (regression workflow)

1. Assert `GET /api/meta` includes `filters.group_title` labeled Category with expected options.
2. Assert `GET /api/streams?group_title=News` narrows the list.
3. Assert `.filters` uses the filter-bar grid area (not squeezed beside search only).

Canonical test: `tests/test_known_issues.py::TestCategoryFilters::test_meta_includes_category_filter`.

### BUG-011 — Category must come from catalog topics and be verified in tests

- **Reported:** 2026-07-13
- **Status:** Fixed
- **Fixed:** 2026-07-13
- **Symptom:** Category still not visible / usable; no regression covering whether `viewer.db` actually has category values with streams.
- **Cause:** “Category” was bound to noisy M3U `group_title` (Undefined/General). Filter-bar rise-in animation could leave opacity issues. No catalog assertion on Category population.
- **Fix:** Label **Category** from `topics` (news/movies/…). Startup + tests require ≥2 categories with ≥1 stream each. Disable opacity animation on the filter bar.

#### AI instructions (regression workflow)

1. Assert fixture DB: `/api/meta` → `filters.topics` labeled Category with counts ≥ 1.
2. Assert `assert_catalog_has_categories` fails when topics are empty/undefined-only.
3. If `iptv_export/viewer.db` exists, assert it has ≥2 populated categories.

Canonical tests: `tests/test_catalog_categories.py`.

### BUG-012 — Category filters must be server-rendered in the page HTML

- **Reported:** 2026-07-13
- **Status:** Fixed
- **Fixed:** 2026-07-13
- **Symptom:** `/api/meta` returned Category options and startup logged categories, but the page still showed only Search + Reset.
- **Cause:** `#filterForm` was empty in HTML; filters depended entirely on client `renderFilters()`.
- **Fix:** Jinja renders filter `<select>`s (including Category/`topics`) into `index.html` from the catalog. Cache-bust static assets (`?v=3`).

#### AI instructions (regression workflow)

1. Assert `GET /` HTML contains `id="filter-topics"`, label Category, and option values like `news`/`movies`.
2. Keep `/api/meta` Category assertions from BUG-011.

Canonical test: `tests/test_known_issues.py::TestCategoryFilters::test_index_html_server_renders_category_filter`.

Playwright (must catch UI regressions): `tests/test_ui_filters_playwright.py::test_category_and_core_filters_are_visible` (runs via `make test`).

### FEAT-001 — “What’s on now” in sidebar + player

- **Reported:** 2026-07-13
- **Status:** Done
- **Fixed:** 2026-07-13
- **Notes:**
  - Sidebar: always `Now: Fetching…` / `Now: <title>` / `Now: No data` (BUG-003).
  - Viewer pane: programme beside channel name via `#nowProgramme` (BUG-004).
  - Guides are imported into `viewer.db` at build time; multi-region Pluto programmes coexist in SQLite (BUG-002 regression covered by import tests).
  - Optional local XMLTV in `iptv_export/epg/` keyed by `tvg_id` (imported at build).
  - Status bar shows `tvg_id` coverage and Guide Idle/Loaded.
  - Docs: README “What’s on now (EPG)” + this file.

### BUG-013 — `stream-viewer-build` crashes after writing `viewer.db`

- **Reported:** 2026-07-14
- **Status:** Fixed
- **Fixed:** 2026-07-14
- **Symptom:** `uv run stream-viewer-build` (and `make build`) printed `wrote iptv_export/viewer.db (...)` — the DB was written correctly — then crashed with `NameError: name 'stream_count' is not defined` while printing the final `=== Ready ===` summary. The command exits non-zero despite the build having actually succeeded, which would fail any automation (CI release workflow, scripts) that checks the exit code.
- **Cause:** `builder/prepare_db.py` calls `stream_count(conn)` / `programme_count(conn)` in `main()`, but only `connect` and `db_status` were imported from `stream_viewer.db`.
- **Fix:** Import `programme_count` and `stream_count` alongside `connect`/`db_status` in `builder/prepare_db.py`.

#### AI instructions (regression workflow)

1. **Reproduce with a failing test first**
   - `tests/test_prepare_db.py` monkeypatches `builder.paths` / `builder.prepare_db` module-level path constants (`EXPORT_DIR`, `VIEWER_DB`, `EPG_DIR`, etc., plus `STREAM_CSV_CANDIDATES`) to a `tmp_path`, seeds a minimal `streams.csv` + `epg/*.xml`, then calls `prepare_db.main(["--skip-download"])` — fully offline, no network.
   - Temporarily drop the import (`from stream_viewer.db import connect, db_status` only) and confirm both tests in that file fail with the exact original `NameError`. Do not proceed until that failure is observed.

2. **Implement the fix**
   - Restore the full import line in `builder/prepare_db.py`.

3. **Verify the same tests now pass**
   - `uv run pytest tests/test_prepare_db.py`
   - Manual: `uv run stream-viewer-build --skip-download` (with local CSV/EPG already present) must print `=== Ready ===` and exit 0.

4. **Do not mark fixed** until step 3’s regression test is green.

Canonical tests: `tests/test_prepare_db.py::test_prepare_db_main_completes_without_crashing`, `tests/test_prepare_db.py::test_prepare_db_module_imports_count_helpers`.

### FEAT-002 — Windows/Linux packaging, GitHub Releases, visible version

- **Reported:** 2026-07-14
- **Status:** Done
- **Fixed:** 2026-07-14
- **Notes:**
  - `stream_viewer/_version.py` is the single source of truth for the app version (starts at `0.1.0`); `pyproject.toml` reads it dynamically. Shown in the status bar and in `FastAPI(version=...)`.
  - `stream_viewer/app.py:resolve_app_paths()` makes path resolution frozen-build-aware: `viewer.db` lives next to the executable (persists across updates); bundled `static`/`templates` resolve under PyInstaller’s `_MEIPASS`.
  - `main()` launches uvicorn with the app object directly (not an import string) and auto-opens the default browser (`STREAM_VIEWER_NO_BROWSER=1` to opt out).
  - `packaging/streaming_viewer_tv.spec` + `stream_viewer/launcher.py` build a onedir bundle for both Windows and Linux (verified locally end-to-end: built the Linux bundle, ran it with a real `viewer.db`, confirmed it served the UI and status bar showed the version).
  - `.github/workflows/release.yml`: on a `vX.Y.Z` tag push, verifies the tag matches `_version.py`, builds the catalog once, packages Windows (`.zip`) and Linux (`.tar.gz`) builds, and attaches both to the GitHub Release.
  - Bump policy (semver): patch digit per `BUG-XXX` fix, minor digit per `FEAT-XXX` feature — documented in README “Versioning”.

#### AI instructions (regression workflow)

1. Assert `stream_viewer/app.py` exposes `resolve_app_paths()` and that dev-mode / frozen-mode resolution differ as expected — `tests/test_frozen_paths.py`.
2. Assert the rendered `index.html` shows the current `stream_viewer._version.__version__` in the status bar — `tests/test_known_issues.py::test_index_html_shows_current_version_in_status_bar`.
3. If packaging changes, rebuild locally (`uv run pyinstaller packaging/streaming_viewer_tv.spec`) and smoke-test the resulting binary with a real `viewer.db` dropped next to it before trusting CI.

Canonical tests: `tests/test_frozen_paths.py`, `tests/test_known_issues.py::test_index_html_shows_current_version_in_status_bar`.
