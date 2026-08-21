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
    assert "30 格" in listed, listed
    assert "冰柜 存" in listed, listed
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


async def test_icebox_alias_routes_dishes() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="icebox-"))
    db = await _boot(tmp)
    from server import hut, kitchen

    assert hut._resolve_fitting_key("冰柜") == "fridge"
    assert hut._resolve_fitting_key("冰箱") == "fridge"
    assert hut._resolve_fitting_key("潮柜") == "cabinet"
    assert hut._resolve_fitting_key("柜子") == "cabinet"

    sid = await _enroll(db, "ice@example.com", "冰柜人")
    s = await db.get_steward_by_id(sid)
    kid = s["key_id"]
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
        await db.add_item(conn, sid, "crop_kale", 4)
        await db.add_item(conn, sid, "dish_salt_crab_s4", 2)
        await conn.commit()

    put = await hut.hut_ops(kid, "冰柜 存 甘蓝 2")
    assert "入柜" in put, put
    listed = await hut.hut_ops(kid, "冰柜")
    assert "甘蓝" in listed and "潮柜" in listed, listed
    assert "冰箱" in listed, listed

    try:
        await hut.hut_ops(kid, "冰柜 存 盐焗沙蟹")
        raise AssertionError("cooked food needs a fridge installed")
    except ValueError as exc:
        assert "冰箱" in str(exc) and "buy fridge" in str(exc), exc

    async with db.connect() as conn:
        await conn.execute(
            """
            INSERT INTO hut_fittings (steward_id, slot, item_key, installed_at)
            VALUES (?, 'soft_2', 'fridge', ?)
            """,
            (sid, db.now()),
        )
        await conn.commit()
    s = await db.get_steward_by_id(sid)
    dish_put = await hut.hut_ops(kid, "冰柜 存 盐焗沙蟹")
    assert "冰箱" in dish_put, dish_put
    async with db.connect() as conn:
        bag = await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item='dish_salt_crab_s4'",
            (sid,),
        )).fetchone()
        stored = await (await conn.execute(
            "SELECT dish_key, stars, quantity FROM meal_storage WHERE steward_id=?",
            (sid,),
        )).fetchone()
    assert not bag or bag[0] == 1, bag
    assert stored and stored[0] == "salt_crab" and stored[1] == 4 and stored[2] == 1, stored

    cn_put = await kitchen.kitchen_ops(kid, "store 盐焗沙蟹")
    assert "冰箱" in cn_put, cn_put
    took = await hut.hut_ops(kid, "冰柜 取 盐焗沙蟹 2")
    assert "取出" in took, took
    status = await hut.hut_ops(kid, "status")
    assert "冰柜 存" in status, status


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


def test_event_and_cabinet_knobs() -> None:
    from server import config
    from server.hut import cabinet_capacity

    assert config.EVENT_ROLL_CHANCE == 0.08
    assert config.EVENT_GOOD_SHARE == 0.30
    assert config.AILMENT_BAD_EVENT_CHANCE == 0.13
    assert config.CABINET_SLOTS == 30
    assert config.CABINET_SLOT_COST == 12
    assert config.CABINET_SLOTS_MAX == 60
    assert cabinet_capacity(0) == 30
    assert cabinet_capacity(5) == 35
    assert cabinet_capacity(999) == 60


async def test_cabinet_expand() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="cab-exp-"))
    db = await _boot(tmp)
    from server import config, hut

    old = (config.CABINET_SLOTS, config.CABINET_SLOTS_MAX, config.CABINET_SLOT_COST)
    config.CABINET_SLOTS = 2
    config.CABINET_SLOTS_MAX = 4
    config.CABINET_SLOT_COST = 10
    try:
        sid = await _enroll(db, "exp@example.com", "扩柜人")
        async with db.connect() as conn:
            await conn.execute(
                "UPDATE stewards SET hut_built=1, hut_level=1, tickets=50 WHERE id=?",
                (sid,),
            )
            await conn.execute(
                """
                INSERT INTO hut_fittings (steward_id, slot, item_key, installed_at)
                VALUES (?, 'soft_1', 'cabinet', ?)
                """,
                (sid, db.now()),
            )
            await db.add_item(conn, sid, "crop_kale", 1)
            await db.add_item(conn, sid, "crop_fogpea", 1)
            await db.add_item(conn, sid, "shell_catseye", 1)
            await conn.commit()
        s = await db.get_steward_by_id(sid)
        listed = await hut.cabinet_command(s, [])
        assert "2 格" in listed, listed

        await hut.cabinet_command(s, ["存", "甘蓝", "1"])
        await hut.cabinet_command(s, ["存", "雾豌豆", "1"])
        try:
            await hut.cabinet_command(s, ["存", "shell_catseye", "1"])
            raise AssertionError("should be full at 2 slots")
        except ValueError as exc:
            assert "满" in str(exc)

        msg = await hut.cabinet_command(s, ["扩"])
        assert "加了 1 格" in msg, msg
        async with db.connect() as conn:
            tickets, extra = await (await conn.execute(
                "SELECT tickets, cabinet_extra FROM stewards WHERE id=?", (sid,),
            )).fetchone()
        assert tickets == 40, tickets
        assert extra == 1, extra

        put3 = await hut.cabinet_command(s, ["存", "shell_catseye", "1"])
        assert "入柜" in put3, put3

        msg2 = await hut.cabinet_command(s, ["扩", "5"])
        assert "加了 1 格" in msg2, msg2
        async with db.connect() as conn:
            tickets, extra = await (await conn.execute(
                "SELECT tickets, cabinet_extra FROM stewards WHERE id=?", (sid,),
            )).fetchone()
        assert tickets == 30, tickets
        assert extra == 2, extra

        try:
            await hut.cabinet_command(s, ["扩"])
            raise AssertionError("should refuse at max")
        except ValueError as exc:
            assert "顶" in str(exc) or "扩到顶" in str(exc)
    finally:
        config.CABINET_SLOTS, config.CABINET_SLOTS_MAX, config.CABINET_SLOT_COST = old


def main() -> None:
    test_scrump_take_qty()
    test_event_and_cabinet_knobs()
    asyncio.run(test_cabinet_and_scrump())
    asyncio.run(test_cannot_take_last())
    asyncio.run(test_cabinet_dump_on_remove())
    asyncio.run(test_icebox_alias_routes_dishes())
    asyncio.run(test_cabinet_expand())
    print("cabinet/scrump tests ok")


if __name__ == "__main__":
    main()
