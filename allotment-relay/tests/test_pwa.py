#!/usr/bin/env python3
"""第4期 PWA：加到主屏幕、离线说明书、极简通知。"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT))


async def _boot(tmp: Path):
    os.environ["DATA_DIR"] = str(tmp)
    from server import config, db

    config.DATA_DIR = tmp
    config.DB_PATH = tmp / "relay.db"
    db.DATA_DIR = tmp
    db.DB_PATH = tmp / "relay.db"
    await db.init_db()
    return db


def _client():
    from fastapi.testclient import TestClient
    from server.main import app

    return TestClient(app)


def test_pwa() -> None:
    asyncio.run(_test_pwa_routes())
    test_pwa_files()


async def _test_pwa_routes() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="pwa-"))
    await _boot(tmp)
    client = _client()

    manifest = client.get("/manifest.webmanifest")
    assert manifest.status_code == 200, manifest.text
    assert "application/manifest+json" in (manifest.headers.get("content-type") or "")
    body = manifest.json()
    assert body["start_url"] == "/play", body
    assert body["display"] == "standalone", body
    assert body["theme_color"] == "#2c4a4e", body
    assert body["scope"] == "/", body
    assert any(i.get("src") == "/static/pwa/icon.svg" for i in body["icons"]), body["icons"]

    sw = client.get("/sw.js")
    assert sw.status_code == 200, sw.text
    assert sw.headers.get("service-worker-allowed") == "/", sw.headers
    text = sw.text
    assert 'CACHE = "tidal-manual-v1"' in text
    assert '"/offline"' in text and '"/manual"' in text
    assert "path.startsWith(\"/api/\")" in text
    assert "path.startsWith(\"/mcp\")" in text

    offline = client.get("/offline")
    assert offline.status_code == 200, offline.text
    assert "现在没网" in offline.text
    assert 'href="/manual"' in offline.text
    assert "说明书还在" in offline.text

    play = client.get("/play")
    assert play.status_code == 200, play.text
    assert 'rel="manifest"' in play.text
    assert "/static/pwa.js?v=pwa1" in play.text
    assert 'id="tidal-install"' in play.text
    assert "加到主屏幕" in play.text

    island = client.get("/island")
    assert island.status_code == 200, island.text
    assert 'rel="manifest"' in island.text
    assert "/static/pwa.js?v=pwa1" in island.text

    manual = client.get("/manual")
    assert manual.status_code == 200, manual.text
    assert 'rel="manifest"' in manual.text
    assert "04 · HOME SCREEN" in manual.text
    assert "加到主屏幕" in manual.text
    assert "一天最多一条" in manual.text
    assert "不会为岸维每天震" in manual.text

    home = client.get("/")
    assert home.status_code == 200, home.text
    assert 'rel="manifest"' in home.text


def test_pwa_files() -> None:
    pwa_js = (ROOT / "server/static/pwa.js").read_text(encoding="utf-8")
    play_js = (ROOT / "server/static/play.js").read_text(encoding="utf-8")
    sw = (ROOT / "server/static/pwa/sw.js").read_text(encoding="utf-8")
    play_html = (ROOT / "server/templates/play.html").read_text(encoding="utf-8")
    main_py = (ROOT / "server/main.py").read_text(encoding="utf-8")
    game_py = (ROOT / "server/game.py").read_text(encoding="utf-8")
    mcp_app = (ROOT / "server/mcp_app.py").read_text(encoding="utf-8")
    help_txt = (ROOT / "server/mcp_dispatch.py").read_text(encoding="utf-8")
    human = (REPO / "docs/HUMAN_MOBILE.md").read_text(encoding="utf-8")
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    island_md = (REPO / "docs/island-manual.md").read_text(encoding="utf-8")

    assert "tidal-nudge-day" in pwa_js
    assert "tax_arrears" in pwa_js
    assert "upkeep_arrears" not in pwa_js
    assert "邻居" not in pwa_js
    assert "nudgeFromDash" in pwa_js
    assert "nudgeFromDash" in play_js
    assert 'id="tidal-install"' in play_html
    assert 'id="tidal-notify"' in play_html
    assert "Service-Worker-Allowed" in main_py
    assert '@app.get("/offline"' in main_py
    assert '@app.get("/sw.js"' in main_py
    assert "不要把加到主屏幕当成新工具" in game_py
    assert "人类 /play 可加到主屏幕" in mcp_app
    assert "不要把加到主屏幕当成新工具" in help_txt
    assert "第 4 期 · 像安装过 · 已上线" in human
    assert "不为岸维每天震" in human
    assert "加到主屏幕" in readme
    assert "加到主屏幕" in island_md
    assert '"/api/"' not in sw.split("PRECACHE")[1].split("];")[0]
    assert "networkFirst" in sw


if __name__ == "__main__":
    test_pwa()
