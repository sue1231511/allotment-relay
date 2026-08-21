#!/usr/bin/env python3
"""岸畔小馆可按折旧卖掉；打烊不退开张费。"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_sell_quote() -> None:
    from server import config
    from server.eatery import eatery_sell_quote

    now = 10_000_000
    fresh = eatery_sell_quote(now, now=now)
    assert fresh["refund"] == 50, fresh
    assert fresh["pct"] == 62, fresh
    assert fresh["cost"] == config.EATERY_OPEN_COST

    week = eatery_sell_quote(now - 7 * 86400, now=now)
    assert week["refund"] == 20, week
    assert week["pct"] == 25, week
    assert week["rate"] == config.EATERY_SELL_RATE_FLOOR

    older = eatery_sell_quote(now - 30 * 86400, now=now)
    assert older["refund"] == 20, older

    unknown = eatery_sell_quote(0, now=now)
    assert unknown["refund"] == 35, unknown
    assert "中档" in unknown["note"]


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
    return row["id"], sid


async def _open_shop(db, sid: int, tickets: int = 200) -> dict:
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET hut_built=1, tickets=? WHERE id=?",
            (tickets, sid),
        )
        await conn.execute("UPDATE stewards SET xp=40 WHERE id=?", (sid,))
        await conn.execute(
            """
            INSERT INTO hut_fittings (steward_id, slot, item_key, installed_at)
            VALUES (?, 'soft_1', 'fridge', ?)
            """,
            (sid, db.now()),
        )
        await db.add_item(conn, sid, "dish_salt_crab_s4", 1)
        await conn.commit()
    s = await db.get_steward_by_id(sid)
    from server import eatery

    msg = await eatery.eatery_command(s, "open 潮线小馆")
    assert "开张" in msg, msg
    return await db.get_steward_by_id(sid)


async def test_sell_flow() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="shop-sell-"))
    db = await _boot(tmp)
    from server import eatery

    _kid, sid = await _enroll(db, "shop-sell@example.com", "馆主")
    s = await _open_shop(db, sid)
    assert s["eatery_open"] == 1
    assert s["eatery_opened_at"] > 0
    tickets_open = s["tickets"]
    xp_open = s["xp"]
    assert tickets_open == 120, tickets_open  # 200 - 80

    stocked = await eatery.eatery_command(s, "stock dish_salt_crab_s4")
    assert "上架" in stocked, stocked

    preview = await eatery.eatery_command(s, "卖掉")
    assert "确认" in preview, preview
    assert "50 票" in preview or "折旧回收 50" in preview, preview
    still = await db.get_steward_by_id(sid)
    assert still["eatery_open"] == 1
    assert still["tickets"] == tickets_open

    sold = await eatery.eatery_command(s, "卖掉 确认")
    assert "卖掉了" in sold, sold
    assert "50 票" in sold, sold
    after = await db.get_steward_by_id(sid)
    assert after["eatery_open"] == 0
    assert after["eatery_opened_at"] == 0
    assert after["eatery_label"] == ""
    assert after["tickets"] == tickets_open + 50, after["tickets"]
    assert after["xp"] == xp_open, after["xp"]

    async with db.connect() as conn:
        fridge = await (await conn.execute(
            "SELECT item_key FROM hut_fittings WHERE steward_id=? AND item_key='fridge'",
            (sid,),
        )).fetchone()
        assert fridge, "fridge should stay"
        dish = await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item='dish_salt_crab_s4'",
            (sid,),
        )).fetchone()
        assert dish and dish[0] >= 1, dish
        menu_n = (await (await conn.execute(
            "SELECT COUNT(*) FROM eatery_menu WHERE steward_id=?", (sid,)
        )).fetchone())[0]
        assert menu_n == 0

    try:
        await eatery.eatery_command(after, "卖掉 确认")
        raise AssertionError("expected sell to fail after shop is gone")
    except ValueError as exc:
        assert "没有在开的馆" in str(exc)


async def test_close_does_not_refund() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="shop-close-"))
    db = await _boot(tmp)
    from server import eatery

    _kid, sid = await _enroll(db, "shop-close@example.com", "打烊人")
    s = await _open_shop(db, sid)
    tickets_open = s["tickets"]
    msg = await eatery.eatery_command(s, "close")
    assert "打烊" in msg and "不退" in msg and "卖掉" in msg, msg
    closed = await db.get_steward_by_id(sid)
    assert closed["eatery_open"] == 0
    assert closed["tickets"] == tickets_open
    try:
        await eatery.eatery_command(closed, "卖掉")
        raise AssertionError("close should forfeit sell")
    except ValueError as exc:
        assert "打烊过" in str(exc) or "没有在开的馆" in str(exc)


def main() -> None:
    test_sell_quote()
    asyncio.run(test_sell_flow())
    asyncio.run(test_close_does_not_refund())
    print("shop sell tests ok")


if __name__ == "__main__":
    main()
