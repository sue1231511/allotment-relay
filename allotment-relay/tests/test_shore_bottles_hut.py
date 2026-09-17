#!/usr/bin/env python3
"""海边漂流瓶 + 小屋泡澡/读书接到人手。"""
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


async def _enroll(db, email: str, name: str, *, tickets: int = 800) -> tuple[int, int]:
    key = await db.create_api_key(email)
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], name, "", "naturalist", "")
    async with db.connect() as conn:
        sid = (await (await conn.execute(
            "SELECT id FROM stewards WHERE key_id=?", (row["id"],)
        )).fetchone())[0]
        await conn.execute(
            "UPDATE stewards SET last_bar_shift_at=?, energy=80, tickets=?, "
            "hut_built=1, hut_level=2 WHERE id=?",
            (db.now(), tickets, sid),
        )
        await conn.commit()
    return row["id"], sid


def test_tide_and_alliance_chinese_bottles() -> None:
    asyncio.run(_test_tide_and_alliance_chinese_bottles())


async def _test_tide_and_alliance_chinese_bottles() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="bottle-ops-"))
    db = await _boot(tmp)
    from server import mcp_dispatch as mux

    kid_a, _ = await _enroll(db, "bottle-a@example.com", "投瓶人")
    kid_b, _ = await _enroll(db, "bottle-b@example.com", "捞瓶人")

    scan = await mux.tide_bundle(kid_a, "漂流瓶")
    assert "待捞" in scan, scan
    left = await mux.tide_bundle(kid_a, "投瓶 今晚浪很大")
    assert "瓶已入海" in left and "今晚浪很大" in left, left
    via_alliance = await mux.alliance_bundle(kid_a, "bottle scan")
    assert "待捞" in via_alliance, via_alliance

    fished = await mux.tide_bundle(kid_b, "捞瓶")
    assert "捞到" in fished or "缘分" in fished or "水草" in fished or "寂寞" in fished or "暂无" in fished, fished
    # Force a hit: plant another bottle and fish with chance patched.
    from server import bottles, config

    old_chance = config.BOTTLE_FISH_CHANCE
    config.BOTTLE_FISH_CHANCE = 1.0
    try:
        await mux.tide_bundle(kid_a, "投瓶 第二句留给你")
        got = await bottles.bottle_ops(kid_b, "捞瓶")
        assert "捞到" in got and "第二句留给你" in got, got
        bid = int(got.split("#", 1)[1].split("：", 1)[0])
        replied = await mux.tide_bundle(kid_b, f"回瓶 {bid} 海里见")
        assert "已回瓶" in replied, replied
        read = await mux.tide_bundle(kid_b, f"看瓶 {bid}")
        assert "第二句留给你" in read and "海里见" in read, read
    finally:
        config.BOTTLE_FISH_CHANCE = old_chance


def test_shore_and_hut_human_taps() -> None:
    asyncio.run(_test_shore_and_hut_human_taps())


async def _test_shore_and_hut_human_taps() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="bottle-ui-"))
    db = await _boot(tmp)
    from fastapi.testclient import TestClient
    from server.main import app
    from server.v1 import hut_service, shore_service

    key = await db.create_api_key("shore-hut@example.com")
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], "岸上人", "", "naturalist", "")
    async with db.connect() as conn:
        sid = (await (await conn.execute(
            "SELECT id FROM stewards WHERE key_id=?", (row["id"],)
        )).fetchone())[0]
        await conn.execute(
            "UPDATE stewards SET last_bar_shift_at=?, energy=80, tickets=800, "
            "hut_built=1, hut_level=2 WHERE id=?",
            (db.now(), sid),
        )
        await conn.commit()

    client = TestClient(app)
    headers = {"Authorization": f"Bearer {key}"}
    shore = client.get("/api/v1/shore", headers=headers)
    assert shore.status_code == 200, shore.text
    pier = shore.json()["shore"]
    assert any(t["key"] == "bottle" for t in pier["tabs"]), pier["tabs"]
    bottle_items = (pier.get("items") or {}).get("bottle") or []
    kinds = {row["kind"] for row in bottle_items}
    assert "捞瓶" in kinds and "投瓶" in kinds, bottle_items

    left = client.post(
        "/api/v1/shore/act",
        headers={**headers, "Idempotency-Key": "leave-bottle"},
        json={"kind": "投瓶", "target": "潮线留一句"},
    )
    assert left.status_code == 200, left.text
    assert "瓶已入海" in (left.json()["event"]["narrative"] or ""), left.json()["event"]

    looked = client.post(
        "/api/v1/shore/act",
        headers={**headers, "Idempotency-Key": "look-bottle"},
        json={"kind": "look", "target": "bottle"},
    )
    assert looked.status_code == 200, looked.text
    assert "待捞" in (looked.json()["event"]["narrative"] or ""), looked.json()["event"]

    fished = client.post(
        "/api/v1/shore/act",
        headers={**headers, "Idempotency-Key": "fish-bottle"},
        json={"kind": "捞瓶", "target": ""},
    )
    assert fished.status_code == 200, fished.text

    hut = client.get("/api/v1/hut", headers=headers)
    assert hut.status_code == 200, hut.text
    home = (hut.json()["hut"]["items"] or {}).get("home") or []
    names = [row["name"] for row in home]
    assert any("浴桶" in n or n == "泡澡" for n in names), names
    assert any("书架" in n or n == "读书" for n in names), names

    miss_bath = client.post(
        "/api/v1/hut/act",
        headers={**headers, "Idempotency-Key": "bath-miss"},
        json={"kind": "bath", "target": ""},
    )
    assert miss_bath.status_code >= 400, miss_bath.text

    bought_tub = client.post(
        "/api/v1/hut/act",
        headers={**headers, "Idempotency-Key": "buy-tub"},
        json={"kind": "buy_install", "target": "bath_tub"},
    )
    assert bought_tub.status_code == 200, bought_tub.text
    soaked = client.post(
        "/api/v1/hut/act",
        headers={**headers, "Idempotency-Key": "bath-ok"},
        json={"kind": "bath", "target": ""},
    )
    assert soaked.status_code == 200, soaked.text
    assert "雾智" in (soaked.json()["event"]["narrative"] or ""), soaked.json()["event"]

    bought_shelf = client.post(
        "/api/v1/hut/act",
        headers={**headers, "Idempotency-Key": "buy-shelf"},
        json={"kind": "buy_install", "target": "bookshelf"},
    )
    assert bought_shelf.status_code == 200, bought_shelf.text
    read = client.post(
        "/api/v1/hut/act",
        headers={**headers, "Idempotency-Key": "read-ok"},
        json={"kind": "read", "target": ""},
    )
    assert read.status_code == 200, read.text
    assert "雾智" in (read.json()["event"]["narrative"] or ""), read.json()["event"]

    # Direct service commands stay on existing tools.
    snap = await shore_service.act(key, row["id"], "投瓶", "再投一句")
    assert "瓶已入海" in snap["event"]["narrative"] or "上限" in snap["event"]["narrative"]
    view = await hut_service.snapshot(key, row["id"])
    home2 = (view["hut"]["items"] or {}).get("home") or []
    assert any(r.get("kind") == "bath" for r in home2), home2
    assert any(r.get("kind") == "read" for r in home2), home2


def test_docs_name_the_new_verbs() -> None:
    app = (ROOT / "server/static/island/app.js").read_text(encoding="utf-8")
    assert 'kind === "投瓶"' in app
    assert 'kind === "回瓶"' in app
    manual = (ROOT / "server/templates/partials/island-manual-content.html").read_text(encoding="utf-8")
    assert "漂流瓶栏能看" in manual
    assert "装了浴桶能泡澡" in manual
    play = (ROOT / "server/play.py").read_text(encoding="utf-8")
    assert "捞瓶" in play and "泡澡" in play
    mcp = (ROOT / "server/mcp_app.py").read_text(encoding="utf-8")
    assert "捞瓶" in mcp and "泡澡" in mcp
    from server.mcp_dispatch import VISIT_HELP, TIDE_HELP, HUT_HELP
    assert "腿鱼小咒" in VISIT_HELP
    assert "捞瓶" in TIDE_HELP and "泡澡" in HUT_HELP


def main() -> None:
    test_tide_and_alliance_chinese_bottles()
    test_shore_and_hut_human_taps()
    test_docs_name_the_new_verbs()
    print("shore bottles / hut cozy tests ok")


if __name__ == "__main__":
    main()
