#!/usr/bin/env python3
"""反馈：羊毛毯收/卖卡住砧；手机地图畜栏喂过的狗不显示。"""
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


async def _enroll(db, email: str, name: str) -> tuple[int, int]:
    key = await db.create_api_key(email)
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], name, "", "naturalist", "")
    async with db.connect() as conn:
        sid = (await (await conn.execute(
            "SELECT id FROM stewards WHERE key_id=?", (row["id"],)
        )).fetchone())[0]
        await conn.execute(
            "UPDATE stewards SET last_bar_shift_at=?, energy=80, tickets=800, "
            "hut_built=1, hut_level=2, barn_built=1 WHERE id=?",
            (db.now(), sid),
        )
        await conn.commit()
    return row["id"], sid


async def _qty(db, sid: int, item: str) -> int:
    bag = await db.get_satchel(sid)
    return int(bag.get(item) or 0)


async def test_wool_rug_can_stack_and_vend() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="rug-stack-"))
    db = await _boot(tmp)
    kid, sid = await _enroll(db, "rug@example.com", "毯人")
    from server import craft, game, hut
    from server.catalog import resolve_item_key
    from server.v1 import views

    assert resolve_item_key("羊毛毯") == "fit_wool_rug"
    assert resolve_item_key("🧶羊毛毯") == "fit_wool_rug"

    async with db.connect() as conn:
        await db.add_item(conn, sid, "fit_wool_rug", 1)
        await db.add_item(conn, sid, "fit_wool_rug", 1)
        await conn.commit()
    assert await _qty(db, sid, "fit_wool_rug") == 2

    row = views._stock_row({
        "item": "fit_wool_rug",
        "name": "🧶羊毛毯",
        "qty": 2,
        "stack_cap": 1,
    })
    assert row["can_vend"] is True
    assert int(row["vend_price"] or 0) > 1, row

    s = await db.get_steward_by_id(sid)
    before = int(s["tickets"])
    sold = await game.tote_ops(kid, "vend 羊毛毯 1")
    assert "卖掉了" in sold or "羊毛毯" in sold, sold
    after = await db.get_steward_by_id(sid)
    assert int(after["tickets"]) > before, (before, after["tickets"], sold)
    assert await _qty(db, sid, "fit_wool_rug") == 1

    async with db.connect() as conn:
        await craft.ensure_profile(conn, sid)
        await conn.execute(
            "UPDATE steward_craft SET job_key=?, job_ready_at=0, job_qty=1 WHERE steward_id=?",
            ("wool_rug", sid),
        )
        await conn.commit()
    taken = await craft.craft_ops(kid, "取")
    assert "羊毛毯" in taken, taken
    assert await _qty(db, sid, "fit_wool_rug") == 2

    val = hut._fitting_value("wool_rug")
    assert val["cost"] >= 71, val
    quote = hut.furniture_sell_quote(val["cost"], 0)
    assert quote["refund"] > 1, quote


async def test_fed_guard_dog_visible_on_island_barn() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="barn-dog-"))
    db = await _boot(tmp)
    _kid, sid = await _enroll(db, "dog@example.com", "看门")
    from server import hut

    now = db.now()
    async with db.connect() as conn:
        for slot in range(1, 7):
            await conn.execute(
                "INSERT OR IGNORE INTO barn_animals (steward_id, slot, species, fed) "
                "VALUES (?,?,NULL,0)",
                (sid, slot),
            )
        await conn.execute(
            """
            UPDATE barn_animals
            SET species='dog', stocked_at=?, fed=1, guard=1, born_at=?
            WHERE steward_id=? AND slot=5
            """,
            (now - 13 * 3600, now - 13 * 3600, sid),
        )
        await conn.commit()
    s = await db.get_steward_by_id(sid)
    async with db.connect() as conn:
        view = await hut.player_view(conn, s)
        await conn.commit()
    rows = (view.get("items") or {}).get("barn") or []
    names = [str(r.get("name") or "") for r in rows]
    assert any("#5" in n and "狗" in n for n in names), names
    dog = next(r for r in rows if "#5" in str(r.get("name") or "") and "狗" in str(r.get("name") or ""))
    assert "守夜" in (dog.get("note") or ""), dog
    assert "占着" in (dog.get("note") or ""), dog
    buys = [r for r in rows if r.get("kind") == "barn_buy"]
    assert buys, rows
    assert all("#5" not in str(r.get("note") or "") for r in buys), buys


async def test_hut_home_can_install_and_sell_bag_rug() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="rug-home-"))
    db = await _boot(tmp)
    kid, sid = await _enroll(db, "home-rug@example.com", "装毯")
    from server import hut
    from server.v1 import hut_service

    async with db.connect() as conn:
        await db.add_item(conn, sid, "fit_wool_rug", 1)
        await conn.commit()
    s = await db.get_steward_by_id(sid)
    async with db.connect() as conn:
        view = await hut.player_view(conn, s)
        await conn.commit()
    home = (view.get("items") or {}).get("home") or []
    kinds = {(r.get("kind"), r.get("target")) for r in home}
    assert ("install", "wool_rug") in kinds, home
    assert any(r.get("kind") == "sell_fit" and "wool_rug" in str(r.get("target") or "") for r in home), home

    installed = await hut_service._install(kid, "wool_rug")
    assert "羊毛毯" in installed or "装" in installed, installed
    async with db.connect() as conn:
        slot = await (await conn.execute(
            "SELECT slot, item_key FROM hut_fittings WHERE steward_id=?",
            (sid,),
        )).fetchone()
    assert slot and "wool" in str(slot[1]), slot

    async with db.connect() as conn:
        await db.add_item(conn, sid, "fit_wool_rug", 1)
        await conn.commit()
    s = await db.get_steward_by_id(sid)
    async with db.connect() as conn:
        view = await hut.player_view(conn, s)
        await conn.commit()
    home = (view.get("items") or {}).get("home") or []
    kinds = {(r.get("kind"), r.get("target")) for r in home}
    assert ("install", "wool_rug") in kinds, home
    again = await hut_service._install(kid, "wool_rug")
    assert "羊毛毯" in again or "装" in again, again
    async with db.connect() as conn:
        rows = await (await conn.execute(
            "SELECT slot FROM hut_fittings WHERE steward_id=? AND item_key LIKE '%wool%'",
            (sid,),
        )).fetchall()
    assert len(rows) == 2, rows


def main() -> None:
    asyncio.run(test_wool_rug_can_stack_and_vend())
    asyncio.run(test_fed_guard_dog_visible_on_island_barn())
    asyncio.run(test_hut_home_can_install_and_sell_bag_rug())
    print("feedback rug/barn tests ok")


if __name__ == "__main__":
    main()
