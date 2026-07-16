# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec for StreamingViewerTV — shared by Windows, Linux, and macOS builds.

Build with:
    uv run pyinstaller packaging/streaming_viewer_tv.spec

Produces a onedir bundle at dist/StreamingViewerTV/ (an "_internal/" support
folder plus the executable). The release workflow drops a pre-built
iptv_export/viewer.db next to the executable afterward; this spec does not
bundle any catalog data itself.

Windows names the executable StreamingViewerTV.exe; Linux and macOS name it
StreamingViewerTV (no extension) — PyInstaller handles that automatically.
Must be built on the target OS (no cross-compilation).
"""

from pathlib import Path

# SPECPATH is injected by PyInstaller into the spec file's exec() namespace
# (there is no __file__ here), and points at this file's directory.
REPO_ROOT = Path(SPECPATH).resolve().parent
STREAM_VIEWER = REPO_ROOT / "stream_viewer"

# Bundled resources land under _MEIPASS/stream_viewer/{static,templates} at
# runtime, matching stream_viewer.app.resolve_app_paths()'s frozen-mode layout.
datas = [
    (str(STREAM_VIEWER / "static"), "stream_viewer/static"),
    (str(STREAM_VIEWER / "templates"), "stream_viewer/templates"),
]

# uvicorn resolves these lazily at runtime; PyInstaller's static analysis
# misses them unless listed explicitly.
hiddenimports = [
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "uvicorn.logging",
]

a = Analysis(
    [str(STREAM_VIEWER / "launcher.py")],
    pathex=[str(REPO_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="StreamingViewerTV",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="StreamingViewerTV",
)
