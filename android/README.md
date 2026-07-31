# StreamingViewerTV Android (Chaquopy) build
#
# Prerequisites
# - JDK 17 (recommended) or JDK 21 — JDK 25 is too new for current AGP/Gradle
# - Android SDK (API 35 platform + build-tools); set ANDROID_HOME or sdk.dir
# - Python 3.10 on PATH, or set CHAQUOPY_PYTHON to that interpreter
#
# Quick start
#   make build                 # or build-probed — create iptv_export/viewer.db
#   make android-sync-db       # copy DB into APK assets
#   make bundle-android        # assembleDebug APK
#
# Install on a device/emulator
#   adb install -r android/app/build/outputs/apk/debug/app-debug.apk
#
# The APK starts FastAPI on 127.0.0.1:8787 and loads the existing HTML UI in a WebView.
#
# Pip pins live in android/app/build.gradle.kts (uvicorn without [standard], pydantic v1,
# httpx as the Android HTTP client — stream_viewer falls back from httpx2).

## SDK location

Create `android/local.properties` (gitignored):

```properties
sdk.dir=/path/to/Android/Sdk
```

Android Studio does this automatically when you open the `android/` folder.
`make bundle-android` also writes it from `ANDROID_HOME` / `ANDROID_SDK_ROOT` when missing.

## Python for Chaquopy

Gradle reads `CHAQUOPY_PYTHON` when set; otherwise Chaquopy looks for `python3.10` on `PATH`.

```bash
export JAVA_HOME=/usr/lib/jvm/temurin-17-jdk
export CHAQUOPY_PYTHON="$(command -v python3.10)"   # or uv's cpython 3.10
export ANDROID_HOME="$HOME/Android/Sdk"
make bundle-android
```

## Catalog updates

`viewer.db` is not committed under assets (too large). After rebuilding the catalog:

```bash
make android-sync-db
make bundle-android
```

On first launch the Service copies the asset to `$HOME/iptv_export/viewer.db` (app internal storage). Delete the app data to force a re-copy after updating the asset.

## GitHub Actions (release tags)

Workflow: [`.github/workflows/android.yml`](../.github/workflows/android.yml)

- **Runs on:** pushes of tags matching `v*` (e.g. `v0.3.7`), and manual **workflow_dispatch**
- **Does not run** on every PR/`main` push (catalog + APK build is heavy; see `ci.yml` for tests)
- **Produces:** debug APK `StreamingViewerTV-android-debug.apk`
  - uploaded as a workflow artifact
  - attached to the GitHub Release when the run is a tag push
- Job steps: JDK 17, Python 3.10, Android SDK 35, `make build`, `make bundle-android`

Create a release APK by tagging:

```bash
git tag v0.3.7
git push origin v0.3.7
```

Or run **Actions → Android APK → Run workflow**.

## Project layout

| Path | Role |
|------|------|
| `android/app/src/main/java/...` | Kotlin shell (WebView + foreground Service) |
| `android/app/src/main/python/android_launcher.py` | Sets Android env, calls `run_server` |
| `android/app/src/main/python/stream_viewer/` | Copied from repo by Gradle `syncPythonSources` |
| `android/app/src/main/assets/iptv_export/viewer.db` | Bundled catalog (via `make android-sync-db`) |

Desktop PyInstaller / `make run` are unchanged.
