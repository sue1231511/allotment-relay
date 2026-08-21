#!/usr/bin/env python3
"""旧家具按折旧卖掉。"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_furniture_quote() -> None:
    from server.hut import furniture_sell_quote

    now = 10_000_000
    fresh = furniture_sell_quote(120, now, now=now)
    assert fresh["refund"] == 74, fresh  # 120 * 0.62
    assert fresh["pct"] == 62, fresh

    week = furniture_sell_quote(120, now - 7 * 86400, now=now)
    assert week["refund"] == 30, week  # floor 25%
    assert week["pct"] == 25, week

    mid = furniture_sell_quote(120, 0, now=now)
    assert mid["refund"] == 52, mid  # (0.62+0.25)/2 * 120 = 52.2 → 52
    rug = furniture_sell_quote(32, now, now=now)
    assert rug["refund"] == 20, rug  # 32 * 0.62 = 19.84 → 20


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


async def test_sell_installed() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="furn-sell-"))
    db = await _boot(tmp)
    from server import hut

    sid = await _enroll(db, "furn@example.com", "拆家的")
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET hut_built=1, hut_level=1, tickets=200 WHERE id=?",
            (sid,),
        )
        await conn.execute("UPDATE stewards SET xp=40 WHERE id=?", (sid,))
        await conn.execute(
            """
            INSERT INTO hut_fittings (steward_id, slot, item_key, installed_at)
            VALUES (?, 'soft_1', 'fridge', ?)
            """,
            (sid, db.now()),
        )
        await conn.execute(
            """
            INSERT INTO meal_storage (steward_id, dish_key, stars, quantity, stored_at)
            VALUES (?, 'salt_crab', 4, 1, ?)
            """,
            (sid, db.now()),
        )
        await conn.commit()
    s = await db.get_steward_by_id(sid)
    preview = await hut.furniture_sell_command(s, ["冰箱"])
    assert "确认" in preview and "74 票" in preview, preview
    still = await db.get_steward_by_id(sid)
    assert still["tickets"] == 200

    sold = await hut.furniture_sell_command(s, ["soft_1", "确认"])
    assert "卖掉了" in sold and "74 票" in sold, sold
    after = await db.get_steward_by_id(sid)
    assert after["tickets"] == 274, after["tickets"]
    assert after["xp"] == 40, after["xp"]
    async with db.connect() as conn:
        gone = await (await conn.execute(
            "SELECT 1 FROM hut_fittings WHERE steward_id=?", (sid,)
        )).fetchone()
        assert gone is None
        dish = await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item='dish_salt_crab_s4'",
            (sid,),
        )).fetchone()
        assert dish and dish[0] >= 1, dish


async def test_fridge_blocked_when_shop_open() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="furn-shop-"))
    db = await _boot(tmp)
    from server import hut

    sid = await _enroll(db, "shopfridge@example.com", "开馆人")
    async with db.connect() as conn:
        await conn.execute(
            """
            UPDATE stewards SET hut_built=1, eatery_open=1, tickets=100 WHERE id=?
            """,
            (sid,),
        )
        await conn.execute(
            """
            INSERT INTO hut_fittings (steward_id, slot, item_key, installed_at)
            VALUES (?, 'soft_1', 'fridge', ?)
            """,
            (sid, db.now()),
        )
        await conn.commit()
    s = await db.get_steward_by_id(sid)
    try:
        await hut.furniture_sell_command(s, ["fridge", "确认"])
        raise AssertionError("expected shop block")
    except ValueError as exc:
        assert "小馆" in str(exc)


async def test_bag_mid_rate() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="furn-bag-"))
    db = await _boot(tmp)
    from server import hut

    sid = await _enroll(db, "bagfit@example.com", "袋装件")
    async with db.connect() as conn:
        await conn.execute("UPDATE stewards SET tickets=10 WHERE id=?", (sid,))
        await conn.execute("UPDATE stewards SET xp=5 WHERE id=?", (sid,))
        await db.add_item(conn, sid, "fit_kelp_rug", 1)
        await conn.commit()
    s = await db.get_steward_by_id(sid)
    preview = await hut.furniture_sell_command(s, [])
    assert "行囊" in preview and "浅海藻毯" in preview, preview
    sold = await hut.furniture_sell_command(s, ["kelp_rug", "确认"])
    assert "卖掉了" in sold, sold
    after = await db.get_steward_by_id(sid)
    # 32 * 0.435 = 13.92 → 14
    assert after["tickets"] == 24, after["tickets"]
    assert after["xp"] == 5, after["xp"]


def main() -> None:
    test_furniture_quote()
    asyncio.run(test_sell_installed())
    asyncio.run(test_fridge_blocked_when_shop_open())
    asyncio.run(test_bag_mid_rate())
    print("furniture sell tests ok")


if __name__ == "__main__":
    main()
