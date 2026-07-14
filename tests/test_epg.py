"""EPG now-playing lookup tests (viewer.db only; no runtime XML parse)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from builder.import_catalog import import_epg_dir, init_schema, parse_xmltv_time
from stream_viewer import app as viewer
from stream_viewer import db as catalog_db
from stream_viewer.app import app
from stream_viewer.epg import extract_pluto_id
from tests.db_fixtures import build_viewer_db, write_stub_epg_xml


def _xmltv_doc(channel_id: str, title: str, start: datetime, stop: datetime) -> str:
    def fmt(value: datetime) -> str:
        return value.strftime("%Y%m%d%H%M%S") + " +0000"

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<tv>
  <channel id="{channel_id}">
    <display-name>Demo</display-name>
  </channel>
  <programme start="{fmt(start)}" stop="{fmt(stop)}" channel="{channel_id}">
    <title>{title}</title>
  </programme>
</tv>
"""


@pytest.fixture
def epg_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    export = tmp_path / "iptv_export"
    export.mkdir()
    csv_path = export / "streams.csv"
    csv_path.write_text(
        "name,url,tvg_id,tvg_logo,group_title,country,country_name,language_name,topics,video_quality,stream_quality\n"
        "00s Replay,https://jmp2.uk/plu-62ba60f059624e000781c436.m3u8,00sReplay.us@SD,"
        "https://images.pluto.tv/channels/62ba60f059624e000781c436/colorLogoPNG.png,"
        "Movies,US,United States,English,movies,720p,excellent\n"
        "Demo News,https://example.com/news.m3u8,news.us,"
        ","
        "News,US,United States,English,news,720p,okay\n",
        encoding="utf-8",
    )
    epg_dir = export / "epg"
    epg_dir.mkdir()
    write_stub_epg_xml(epg_dir / "local.xml", "00sReplay.us@SD", "Local Movie Night")
    build_viewer_db(export, csv_path)

    monkeypatch.setattr(viewer, "ROOT", tmp_path)
    monkeypatch.setattr(viewer, "EXPORT_DIR", export)
    viewer._catalog.clear()
    viewer._catalog.update(
        {"source": None, "streams": [], "by_id": {}, "filters": {}, "total": 0}
    )

    with TestClient(app) as client:
        yield client


def test_parse_xmltv_time():
    value = parse_xmltv_time("20260713120000 +0000")
    assert value is not None
    assert value.hour == 12
    assert value.tzinfo is not None

    offset = parse_xmltv_time("20260713080000 -0400")
    assert offset is not None
    assert offset.hour == 12  # 08:00 EDT → 12:00 UTC


def test_extract_pluto_id():
    assert (
        extract_pluto_id(
            {
                "url": "https://jmp2.uk/plu-62ba60f059624e000781c436.m3u8",
                "tvg_logo": "",
            }
        )
        == "62ba60f059624e000781c436"
    )


def test_local_xmltv_now_playing(epg_client: TestClient):
    response = epg_client.get("/api/epg/now", params={"stream_ids": "0"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["items"]["0"]["title"] == "Local Movie Night"

    detail = epg_client.get("/api/streams/0")
    assert detail.status_code == 200
    assert detail.json()["now_playing"]["title"] == "Local Movie Night"


def test_import_indexes_pluto_keys(tmp_path: Path):
    epg_dir = tmp_path / "epg"
    epg_dir.mkdir()
    now = datetime.now(timezone.utc)
    xml = _xmltv_doc(
        "62ba60f059624e000781c436",
        "Driven",
        now - timedelta(minutes=30),
        now + timedelta(minutes=90),
    )
    (epg_dir / "pluto_us.xml").write_text(xml, encoding="utf-8")
    db_path = tmp_path / "viewer.db"
    conn = catalog_db.connect(db_path)
    try:
        init_schema(conn)
        files, progs = import_epg_dir(conn, epg_dir)
        assert files == 1
        assert progs >= 1
        found = catalog_db.now_playing_for_keys(
            conn, ["pluto:62ba60f059624e000781c436"]
        )
    finally:
        conn.close()
    assert found is not None
    assert found["title"] == "Driven"


def test_import_keeps_prior_pluto_countries(tmp_path: Path):
    """BUG-002 successor: multi-region Pluto programmes must coexist in viewer.db."""
    epg_dir = tmp_path / "epg"
    epg_dir.mkdir()
    now = datetime.now(timezone.utc)
    us = _xmltv_doc(
        "aaaaaaaaaaaaaaaaaaaaaaaa",
        "US Show",
        now - timedelta(minutes=10),
        now + timedelta(minutes=50),
    )
    de = _xmltv_doc(
        "bbbbbbbbbbbbbbbbbbbbbbbb",
        "DE Show",
        now - timedelta(minutes=10),
        now + timedelta(minutes=50),
    )
    (epg_dir / "pluto_us.xml").write_text(us, encoding="utf-8")
    (epg_dir / "pluto_de.xml").write_text(de, encoding="utf-8")

    db_path = tmp_path / "viewer.db"
    conn = catalog_db.connect(db_path)
    try:
        init_schema(conn)
        import_epg_dir(conn, epg_dir)
        us_now = catalog_db.now_playing_for_keys(
            conn, ["pluto:aaaaaaaaaaaaaaaaaaaaaaaa"]
        )
        de_now = catalog_db.now_playing_for_keys(
            conn, ["pluto:bbbbbbbbbbbbbbbbbbbbbbbb"]
        )
    finally:
        conn.close()

    assert us_now is not None and us_now["title"] == "US Show"
    assert de_now is not None and de_now["title"] == "DE Show"


def test_startup_requires_viewer_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    export = tmp_path / "iptv_export"
    export.mkdir()
    monkeypatch.setattr(viewer, "ROOT", tmp_path)
    monkeypatch.setattr(viewer, "EXPORT_DIR", export)
    with pytest.raises(RuntimeError, match="Missing .*viewer\\.db"):
        viewer.require_viewer_db()


def test_viewer_has_no_csv_or_xml_parsers():
    """BUG-009: stream_viewer must not parse CSV/XMLTV at runtime."""
    root = Path(__file__).resolve().parents[1]
    app_src = (root / "stream_viewer" / "app.py").read_text(encoding="utf-8")
    epg_src = (root / "stream_viewer" / "epg.py").read_text(encoding="utf-8")
    db_src = (root / "stream_viewer" / "db.py").read_text(encoding="utf-8")
    assert "import csv" not in app_src
    assert "csv.DictReader" not in app_src
    assert "ElementTree" not in epg_src
    assert "ElementTree" not in db_src
    assert "import csv" not in db_src
    assert "class EpgStore" not in epg_src
