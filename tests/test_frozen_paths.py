"""Path resolution must work both in normal dev runs and inside a PyInstaller-frozen build."""

from __future__ import annotations

from pathlib import Path

from stream_viewer.app import resolve_app_paths


def test_dev_mode_resolves_relative_to_source_file():
    module_file = "/home/user/StreamingViewerTV/stream_viewer/app.py"
    export_dir, static_dir, templates_dir = resolve_app_paths(
        frozen=False,
        executable="/usr/bin/python3",
        module_file=module_file,
        meipass=None,
    )
    assert export_dir == Path("/home/user/StreamingViewerTV/iptv_export")
    assert static_dir == Path("/home/user/StreamingViewerTV/stream_viewer/static")
    assert templates_dir == Path("/home/user/StreamingViewerTV/stream_viewer/templates")


def test_frozen_mode_puts_data_next_to_executable():
    """viewer.db must live beside the .exe so it persists across app updates/reinstalls."""
    export_dir, _static_dir, _templates_dir = resolve_app_paths(
        frozen=True,
        executable="/home/alice/Downloads/StreamingViewerTV/StreamingViewerTV.exe",
        module_file="ignored/when/frozen/app.py",
        meipass="/tmp/_MEI12345",
    )
    assert export_dir == Path("/home/alice/Downloads/StreamingViewerTV/iptv_export")


def test_frozen_mode_resolves_bundled_resources_under_meipass():
    """static/templates are bundled data files extracted under PyInstaller's _MEIPASS."""
    _export_dir, static_dir, templates_dir = resolve_app_paths(
        frozen=True,
        executable="/opt/StreamingViewerTV/StreamingViewerTV",
        module_file="ignored/when/frozen/app.py",
        meipass="/tmp/_MEI67890",
    )
    assert static_dir == Path("/tmp/_MEI67890/stream_viewer/static")
    assert templates_dir == Path("/tmp/_MEI67890/stream_viewer/templates")


def test_frozen_mode_without_meipass_falls_back_to_executable_dir():
    """Onedir builds may not set _MEIPASS; resources should still resolve next to the exe."""
    _export_dir, static_dir, _templates_dir = resolve_app_paths(
        frozen=True,
        executable="/opt/StreamingViewerTV/StreamingViewerTV",
        module_file="ignored/when/frozen/app.py",
        meipass=None,
    )
    assert static_dir == Path("/opt/StreamingViewerTV/stream_viewer/static")
