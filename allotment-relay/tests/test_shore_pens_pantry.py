#!/usr/bin/env python3
"""渔排中文指令 + 港口人手 + 小屋腌晾。"""
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
        await db.add_item(conn, sid, "compost", 8)
        await db.add_item(conn, sid, "crop_kale", 4)
        await db.add_item(conn, sid, "fish_mackerel", 4)
        await conn.commit()
    return row["id"], sid, key


def test_chinese_pen_and_tide_bonus() -> None:
    asyncio.run(_test_chinese_pen_and_tide_bonus())


async def _test_chinese_pen_and_tide_bonus() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="pen-cn-"))
    db = await _boot(tmp)
    from server import commons, config, events, flavor, marine, world
    from server import mcp_dispatch as mux

    async def _quiet(*_a, **_k):
        return None

    events.roll_after_action = _quiet  # type: ignore[assignment]
    commons.roll_discovery = _quiet  # type: ignore[assignment]
    flavor.maybe_suffix = lambda *_a, **_k: ""  # type: ignore[assignment]

    kid, sid, _key = await _enroll(db, "pen-cn@example.com", "排上人")

    erected = await mux.tide_bundle(kid, "搭排")
    assert "渔排就绪" in erected, erected
    stocked = await mux.tide_bundle(kid, "投苗 灰鲱")
    assert "灰鲱" in stocked, stocked
    fed = await mux.tide_bundle(kid, "投饵")
    assert "投饵" in fed or "灰鲱" in fed, fed
    named = await mux.tide_bundle(kid, "名池 薄荷池")
    assert "薄荷池" in named, named
    looked = await mux.tide_bundle(kid, "看排")
    assert "薄荷池" in looked and "灰鲱" in looked, looked

    async with db.connect() as conn:
        await conn.execute(
            "UPDATE fish_pens SET stocked_at=? WHERE steward_id=? AND slot=1",
            (db.now() - 100_000, sid),
        )
        await conn.commit()

    old_tide = world.current_tide
    world.current_tide = lambda: "ebb"  # herring loves ebb
    try:
        harvested = await mux.tide_bundle(kid, "收排")
    finally:
        world.current_tide = old_tide
    assert "收排" in harvested and "灰鲱" in harvested, harvested
    assert "赶退潮多收一条" in harvested, harvested
    assert "x3" in harvested, harvested

    await mux.tide_bundle(kid, "投苗 沙鳗")
    old_rand = marine.random.random
    marine.random.random = lambda: 0.01  # compost
    try:
        patrol = await mux.tide_bundle(kid, "巡排")
    finally:
        marine.random.random = old_rand
    assert "巡了一圈" in patrol, patrol
    assert "堆肥" in patrol, patrol
    again = None
    try:
        again = await mux.tide_bundle(kid, "巡排")
    except ValueError as exc:
        again = str(exc)
    assert "刚巡过" in (again or ""), again


def test_shore_and_hut_human_pens() -> None:
    asyncio.run(_test_shore_and_hut_human_pens())


async def _test_shore_and_hut_human_pens() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="pen-ui-"))
    db = await _boot(tmp)
    from fastapi.testclient import TestClient
    from server.main import app

    kid, sid, key = await _enroll(db, "pen-ui@example.com", "码头人")
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {key}"}

    shore = client.get("/api/v1/shore", headers=headers)
    assert shore.status_code == 200, shore.text
    port = shore.json()["port"]
    assert any(t["key"] == "pen" for t in port["tabs"]), port["tabs"]
    kinds = {row["kind"] for row in (port.get("items") or {}).get("pen") or []}
    assert "搭排" in kinds, kinds

    erected = client.post(
        "/api/v1/shore/act",
        headers={**headers, "Idempotency-Key": "erect-pen"},
        json={"kind": "搭排", "target": ""},
    )
    assert erected.status_code == 200, erected.text
    assert "渔排就绪" in (erected.json()["event"]["narrative"] or ""), erected.json()["event"]
    pen_items = (erected.json()["port"]["items"] or {}).get("pen") or []
    assert any(row["kind"] == "投苗" for row in pen_items), pen_items
    assert any(row["kind"] == "巡排" for row in pen_items), pen_items

    stocked = client.post(
        "/api/v1/shore/act",
        headers={**headers, "Idempotency-Key": "stock-pen"},
        json={"kind": "投苗", "target": "灰鲱 1"},
    )
    assert stocked.status_code == 200, stocked.text
    assert "灰鲱" in (stocked.json()["event"]["narrative"] or ""), stocked.json()["event"]

    fed = client.post(
        "/api/v1/shore/act",
        headers={**headers, "Idempotency-Key": "feed-pen"},
        json={"kind": "投饵", "target": "1"},
    )
    assert fed.status_code == 200, fed.text

    named = client.post(
        "/api/v1/shore/act",
        headers={**headers, "Idempotency-Key": "label-pen"},
        json={"kind": "名池", "target": "1 薄荷池"},
    )
    assert named.status_code == 200, named.text
    assert "薄荷池" in (named.json()["event"]["narrative"] or ""), named.json()["event"]

    looked = client.post(
        "/api/v1/shore/act",
        headers={**headers, "Idempotency-Key": "look-pen"},
        json={"kind": "look", "target": "pen"},
    )
    assert looked.status_code == 200, looked.text
    assert "渔排" in (looked.json()["event"]["narrative"] or ""), looked.json()["event"]

    hut = client.get("/api/v1/hut", headers=headers)
    assert hut.status_code == 200, hut.text
    home = (hut.json()["hut"]["items"] or {}).get("home") or []
    names = [row["name"] for row in home]
    assert any("腌菜坛" in n or n.startswith("腌") for n in names), names
    assert any("晾鱼架" in n or n.startswith("晾") for n in names), names

    bought = client.post(
        "/api/v1/hut/act",
        headers={**headers, "Idempotency-Key": "buy-crock"},
        json={"kind": "buy_install", "target": "pickle_crock"},
    )
    assert bought.status_code == 200, bought.text
    pickled = client.post(
        "/api/v1/hut/act",
        headers={**headers, "Idempotency-Key": "pickle-kale"},
        json={"kind": "pickle", "target": "甘蓝 4"},
    )
    assert pickled.status_code == 200, pickled.text
    assert "腌好" in (pickled.json()["event"]["narrative"] or ""), pickled.json()["event"]

    rack = client.post(
        "/api/v1/hut/act",
        headers={**headers, "Idempotency-Key": "buy-rack"},
        json={"kind": "buy_install", "target": "fish_rack"},
    )
    assert rack.status_code == 200, rack.text
    dried = client.post(
        "/api/v1/hut/act",
        headers={**headers, "Idempotency-Key": "dry-mackerel"},
        json={"kind": "dry", "target": "鲭鱼 4"},
    )
    assert dried.status_code == 200, dried.text
    assert "晾好" in (dried.json()["event"]["narrative"] or ""), dried.json()["event"]

    js = (ROOT / "server/static/island/app.js").read_text(encoding="utf-8")
    assert 'kind === "投苗"' in js
    assert 'kind === "名池"' in js
    assert 'kind === "pickle"' in js
    play = (ROOT / "server/play.py").read_text(encoding="utf-8")
    assert 'command": "搭排"' in play
    assert 'command": "腌"' in play
    help_text = (ROOT / "server/mcp_dispatch.py").read_text(encoding="utf-8")
    assert "巡排" in help_text
    assert "腌 甘蓝 4" in help_text
    manual = (ROOT / "server/templates/partials/island-manual-content.html").read_text(encoding="utf-8")
    assert "渔排栏" in manual
    assert "先买腌菜坛或晾鱼架" in manual


def main() -> None:
    test_chinese_pen_and_tide_bonus()
    test_shore_and_hut_human_pens()
    print("shore pens pantry tests ok")


if __name__ == "__main__":
    main()
