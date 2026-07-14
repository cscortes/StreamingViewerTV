"""Live network checks — skipped by default.

Run a sample:
  uv run pytest -m live -q

Or check many/all URLs with the dedicated script:
  uv run python -m builder.check_urls --limit 50 --deep
  uv run python -m builder.check_urls --all --workers 16 --deep
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from stream_viewer import app as viewer
from stream_viewer.app import app

VIEWER_DB = Path("iptv_export/viewer.db")


@pytest.fixture
def live_client(monkeypatch: pytest.MonkeyPatch):
    if not VIEWER_DB.is_file():
        pytest.skip("No iptv_export/viewer.db — run: make build")
    export = VIEWER_DB.parent
    monkeypatch.setattr(viewer, "EXPORT_DIR", export)
    viewer._catalog.clear()
    viewer._catalog.update(
        {"source": None, "streams": [], "by_id": {}, "filters": {}, "total": 0}
    )
    with TestClient(app) as client:
        yield client


@pytest.mark.live
def test_sample_streams_through_proxy(live_client: TestClient):
    """Hit a small sample of real URLs through the proxy (network required)."""
    client = live_client
    listed = client.get("/api/streams", params={"limit": 1}).json()
    total = listed["total"]
    if total <= 0:
        pytest.skip("viewer.db has no streams")

    sample_ids = sorted({0, 1, 2, 10, 50, 100, min(500, total - 1)})
    failures: list[str] = []
    successes = 0

    for stream_id in sample_ids:
        detail = client.get(f"/api/streams/{stream_id}")
        if detail.status_code != 200:
            failures.append(f"id={stream_id} detail HTTP {detail.status_code}")
            continue
        play_url = detail.json().get("play_url")
        if not play_url:
            failures.append(f"id={stream_id} missing play_url")
            continue
        proxied = client.get(play_url)
        if proxied.status_code != 200:
            failures.append(
                f"id={stream_id} proxy HTTP {proxied.status_code}: "
                f"{proxied.text[:120]}"
            )
            continue
        successes += 1

    assert successes >= 1, f"no working streams; failures={failures}"
