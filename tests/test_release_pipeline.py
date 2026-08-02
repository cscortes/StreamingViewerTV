"""FEAT-005: unified desktop + Android release pipeline contracts."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE_YML = ROOT / ".github" / "workflows" / "release.yml"
ANDROID_YML = ROOT / ".github" / "workflows" / "android.yml"
GRADLE = ROOT / "android" / "app" / "build.gradle.kts"


def test_no_standalone_android_workflow():
    assert not ANDROID_YML.exists()


def test_release_workflow_builds_android_from_shared_viewer_db():
    text = RELEASE_YML.read_text(encoding="utf-8")
    android_job = text.split("build-android:")[1].split("publish-release:")[0]
    assert "name: viewer-db" in android_job
    assert "make bundle-android" in android_job
    assert "stream-viewer-build" not in android_job
    assert "StreamingViewerTV-${{ needs.plan.outputs.tag }}-android-debug.apk" in android_job


def test_publish_release_needs_all_platforms_and_attaches_apk():
    text = RELEASE_YML.read_text(encoding="utf-8")
    publish = text.split("publish-release:")[1]
    assert "build-windows" in publish
    assert "build-linux" in publish
    assert "build-macos" in publish
    assert "build-android" in publish
    assert "android-debug.apk" in publish
    assert "gh release create" in publish


def test_android_gradle_versions_from_version_py():
    gradle = GRADLE.read_text(encoding="utf-8")
    assert "../stream_viewer/_version.py" in gradle
    assert "__version__" in gradle
    assert "versionName" in gradle
    assert "versionCode" in gradle
