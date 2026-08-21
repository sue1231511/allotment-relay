#!/usr/bin/env python3
"""小屋潮柜；偷菜按比例掐，不能一把掏空。"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_scrump_take_qty() -> None:
    from server.farming import harvest_pool, remaining_harvest, scrump_take_qty

    assert scrump_take_qty(0) == 0
    assert scrump_take_qty(1) == 0
    assert scrump_take_qty(2) == 1
    assert scrump_take_qty(3) == 1
    assert scrump_take_qty(4) == 1
    assert scrump_take_qty(5) == 1
    assert scrump_take_qty(6) == 1
    assert scrump_take_qty(7) == 2
    assert scrump_take_qty(10) == 3

    untended = {"crop": "kale", "tended": 0, "harvest_left": 0}
    tended = {"crop": "kale", "tended": 1, "harvest_left": 0}
    assert harvest_pool(untended) == 5
    assert harvest_pool(tended) == 6
    assert harvest_pool({"crop": "durian", "tended": 0}) == 2
    assert remaining_harvest({**tended, "harvest_left": 2}) == 2
    nibble = remaining_harvest(tended)
    taken = scrump_take_qty(nibble)
    assert taken == 1
    assert taken < nibble
    assert taken <= int(nibble * 0.30) or taken == 1

    from server.catalog import crop_catalog_line

    kale_line = crop_catalog_line("kale")
    assert "短茬" in kale_line and "5把" in kale_line and "约1时" in kale_line
    durian_line = crop_catalog_line("durian")
    assert "稀有" in durian_line and "2把" in durian_line and "约5时" in durian_line


async def _boot(tmp: Path):
    os.environ["DATA_DIR"] = str(tmp)
    from server import config, db

    config.DATA_DIR = tmp
    config.DB_PATH = tmp / "relay.db"
    db.DATA_DIR = tmp
    db.DB_PATH = tmp / "relay.db"
    await db.init_db()
    return db


async def _enroll(db, email: str, name: str) -> int:
    key = await db.create_api_key(email)
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], name, "", "naturalist", "")
    async with db.connect() as conn:
        sid = (await (await conn.execute(
            "SELECT id FROM stewards WHERE key_id=?", (row["id"],)
        )).fetchone())[0]
    return sid


async def test_cabinet_and_scrump() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="cabinet-"))
    db = await _boot(tmp)
    from server import events, hut, npc

    sid = await _enroll(db, "cab@example.com", "柜主")
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET hut_built=1, hut_level=1, tickets=400 WHERE id=?",
            (sid,),
        )
        await conn.execute(
            """
            INSERT INTO hut_fittings (steward_id, slot, item_key, installed_at)
            VALUES (?, 'soft_1', 'cabinet', ?)
            """,
            (sid, db.now()),
        )
        await db.add_item(conn, sid, "crop_kale", 5)
        await db.add_item(conn, sid, "dish_salt_crab_s4", 1)
        await conn.commit()
    s = await db.get_steward_by_id(sid)

    listed = await hut.cabinet_command(s, [])
    assert "空" in listed, listed
    put = await hut.cabinet_command(s, ["存", "甘蓝", "3"])
    assert "入柜" in put, put
    async with db.connect() as conn:
        bag = (await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item='crop_kale'",
            (sid,),
        )).fetchone())[0]
        cab = (await (await conn.execute(
            "SELECT quantity FROM hut_cabinet WHERE steward_id=? AND item='crop_kale'",
            (sid,),
        )).fetchone())[0]
    assert bag == 2, bag
    assert cab == 3, cab

    try:
        await hut.cabinet_command(s, ["存", "dish_salt_crab_s4"])
        raise AssertionError("dishes should go to fridge")
    except ValueError as exc:
        assert "冰箱" in str(exc)

    stolen = None
    async with db.connect() as conn:
        stolen = await npc._steal_item(conn, sid)
        await conn.commit()
    async with db.connect() as conn:
        cab = (await (await conn.execute(
            "SELECT quantity FROM hut_cabinet WHERE steward_id=? AND item='crop_kale'",
            (sid,),
        )).fetchone())[0]
    assert cab == 3, f"cabinet should survive pickpocket ({stolen=!r})"

    took = await hut.cabinet_command(s, ["取", "甘蓝", "1"])
    assert "取出" in took, took

    vic = await _enroll(db, "farm@example.com", "田主")
    async with db.connect() as conn:
        await conn.execute(
            """
            UPDATE parcels SET crop='kale', planted_at=?, tended=1, greenhouse=0,
            grow_target=120, harvest_left=0 WHERE steward_id=? AND slot=1
            """,
            (db.now() - 10_000, vic),
        )
        await conn.execute(
            "UPDATE stewards SET last_active_at=? WHERE id=?",
            (db.now() - 4000, vic),
        )
        await conn.commit()
    thief = await db.get_steward_by_id(sid)
    events.random.random = lambda: 0.99  # type: ignore[method-assign]
    msg = await events.manual_scrump(thief, "田主", 1)
    assert "还剩" in msg, msg
    async with db.connect() as conn:
        plot = await (await conn.execute(
            "SELECT crop, harvest_left FROM parcels WHERE steward_id=? AND slot=1",
            (vic,),
        )).fetchone()
    assert plot[0] == "kale"
    assert plot[1] == 5, plot  # 打理甘蓝 6 把，掐走 30%→1


async def test_cannot_take_last() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="scrump-last-"))
    db = await _boot(tmp)
    from server import events

    thief_sid = await _enroll(db, "last-thief@example.com", "末手")
    vic = await _enroll(db, "last-farm@example.com", "留一把")
    async with db.connect() as conn:
        await conn.execute(
            """
            UPDATE parcels SET crop='kale', planted_at=?, tended=1, greenhouse=0,
            grow_target=120, harvest_left=1 WHERE steward_id=? AND slot=1
            """,
            (db.now() - 10_000, vic),
        )
        await conn.execute(
            "UPDATE stewards SET last_active_at=? WHERE id=?",
            (db.now() - 4000, vic),
        )
        await conn.commit()
    thief = await db.get_steward_by_id(thief_sid)
    events.random.random = lambda: 0.99  # type: ignore[method-assign]
    try:
        await events.manual_scrump(thief, "留一把", 1)
        raise AssertionError("should not empty the last handful")
    except ValueError as exc:
        assert "摘空" in str(exc)
    async with db.connect() as conn:
        plot = await (await conn.execute(
            "SELECT crop, harvest_left FROM parcels WHERE steward_id=? AND slot=1",
            (vic,),
        )).fetchone()
    assert plot[0] == "kale"
    assert plot[1] == 1


async def test_cabinet_dump_on_remove() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="cab-dump-"))
    db = await _boot(tmp)
    from server import hut

    sid = await _enroll(db, "dump@example.com", "拆柜人")
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET hut_built=1, hut_level=1 WHERE id=?", (sid,),
        )
        await conn.execute(
            """
            INSERT INTO hut_fittings (steward_id, slot, item_key, installed_at)
            VALUES (?, 'soft_1', 'cabinet', ?)
            """,
            (sid, db.now()),
        )
        await db.add_item(conn, sid, "shell_catseye", 2)
        await conn.commit()
    s = await db.get_steward_by_id(sid)
    await hut.cabinet_command(s, ["存", "shell_catseye", "2"])
    async with db.connect() as conn:
        dumped = await hut.dump_cabinet(conn, sid)
        await conn.commit()
    assert dumped == 2
    async with db.connect() as conn:
        bag = (await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item='shell_catseye'",
            (sid,),
        )).fetchone())
        empty = await (await conn.execute(
            "SELECT COUNT(*) FROM hut_cabinet WHERE steward_id=?", (sid,)
        )).fetchone()
    assert bag and bag[0] >= 2, bag
    assert empty[0] == 0


def main() -> None:
    test_scrump_take_qty()
    asyncio.run(test_cabinet_and_scrump())
    asyncio.run(test_cannot_take_last())
    asyncio.run(test_cabinet_dump_on_remove())
    print("cabinet/scrump tests ok")


if __name__ == "__main__":
    main()
