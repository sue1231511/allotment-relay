#!/usr/bin/env python3
"""份地行缺失 / 未知作物时，地籍和上手页不能整页空掉。"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
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


async def _enroll(db, email: str, name: str) -> tuple[str, int]:
    key = await db.create_api_key(email)
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], name, "", "naturalist", "")
    async with db.connect() as conn:
        sid = (await (await conn.execute(
            "SELECT id FROM stewards WHERE key_id=?", (row["id"],)
        )).fetchone())[0]
    return key, sid


def test_missing_veg_rows_heal_on_dashboard() -> None:
    asyncio.run(_test_missing_veg_rows_heal_on_dashboard())


async def _test_missing_veg_rows_heal_on_dashboard() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="allo-heal-"))
    db = await _boot(tmp)
    from server import steward_dashboard

    key, sid = await _enroll(db, "heal@example.com", "缺地人")
    async with db.connect() as conn:
        await conn.execute(
            "DELETE FROM parcels WHERE steward_id=? AND COALESCE(orchard,0)=0 "
            "AND COALESCE(greenhouse,0)=0",
            (sid,),
        )
        await conn.commit()
    before = await db.get_parcels(sid, orchard=0, greenhouse=0)
    assert before == [], before

    data = await steward_dashboard.fetch_dashboard(key)
    veg = [p for p in data["parcels"] if not p.get("orchard") and not p.get("greenhouse")]
    trees = [p for p in data["parcels"] if p.get("orchard") and not p.get("greenhouse")]
    assert len(veg) >= 3, data["parcels"]
    assert all(p["state"] == "fallow" for p in veg), veg
    assert len(trees) >= 3, data["parcels"]


def test_public_allotments_survives_unknown_crop() -> None:
    asyncio.run(_test_public_allotments_survives_unknown_crop())


async def _test_public_allotments_survives_unknown_crop() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="allo-unknown-"))
    db = await _boot(tmp)
    from server import farming

    _key, sid = await _enroll(db, "ghost@example.com", "鬼作物")
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE parcels SET crop='not_a_real_crop', planted_at=?, grow_target=0 "
            "WHERE steward_id=? AND slot=1 AND COALESCE(orchard,0)=0 "
            "AND COALESCE(greenhouse,0)=0",
            (db.now() - 60, sid),
        )
        await conn.commit()

    plot = {
        "crop": "not_a_real_crop",
        "planted_at": db.now() - 60,
        "grow_target": 0,
        "tended": 0,
    }
    assert farming.effective_grow(plot) >= 60
    assert farming.parcel_status(plot)

    rows = await db.public_allotments()
    assert rows, rows
    mine = next(r for r in rows if r["name"] == "鬼作物")
    assert mine["parcel_count"] >= 3, mine
    assert mine["parcels"], mine
    veg = [p for p in mine["parcels"] if not p.get("orchard") and not p.get("greenhouse")]
    assert any(p.get("crop") == "not_a_real_crop" for p in veg), veg


def test_init_db_heals_empty_plot_table() -> None:
    asyncio.run(_test_init_db_heals_empty_plot_table())


async def _test_init_db_heals_empty_plot_table() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="allo-init-"))
    db = await _boot(tmp)
    _key, sid = await _enroll(db, "init@example.com", "空表人")
    async with db.connect() as conn:
        await conn.execute("DELETE FROM parcels WHERE steward_id=?", (sid,))
        await conn.commit()
    assert await db.get_parcels(sid) == []

    await db.init_db()
    rows = await db.get_parcels(sid)
    veg = [p for p in rows if not p.get("orchard") and not p.get("greenhouse")]
    trees = [p for p in rows if p.get("orchard") and not p.get("greenhouse")]
    assert len(veg) >= 3, rows
    assert len(trees) >= 3, rows


def test_play_js_routes_plot_go_home() -> None:
    js = (ROOT / "server" / "static" / "play.js").read_text(encoding="utf-8")
    html = (ROOT / "server" / "templates" / "play.html").read_text(encoding="utf-8")
    assert "function isPlotGo" in js
    assert "goHome('plotsSection')" in js
    assert "play.js?v=plots-heal1" in html
    assert "(d.meters && d.meters.energy)" not in js


def test_public_stats_http_returns_stewards_and_online() -> None:
    asyncio.run(_test_public_stats_http_returns_stewards_and_online())


async def _test_public_stats_http_returns_stewards_and_online() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="allo-stats-"))
    db = await _boot(tmp)
    await _enroll(db, "stats@example.com", "统计人")
    from fastapi.testclient import TestClient
    from server.main import app

    client = TestClient(app)
    missing = client.get("/api/public/weddings")
    assert missing.status_code == 200, missing.text
    res = client.get("/api/public/stats")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["stewards"] >= 1, body
    assert "online" in body, body
    assert isinstance(body.get("online_people"), list), body
    allo = client.get("/api/public/allotments")
    assert allo.status_code == 200, allo.text
    rows = allo.json()
    assert any(r.get("name") == "统计人" for r in rows), rows


if __name__ == "__main__":
    test_missing_veg_rows_heal_on_dashboard()
    test_public_allotments_survives_unknown_crop()
    test_init_db_heals_empty_plot_table()
    test_play_js_routes_plot_go_home()
    test_public_stats_http_returns_stewards_and_online()
    print("ok")
