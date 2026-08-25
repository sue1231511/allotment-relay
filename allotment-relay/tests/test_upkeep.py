#!/usr/bin/env python3
"""岸维：按产业每天收维修费，东八区换班后划入潮汐基金。"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CST = timezone(timedelta(hours=8))


def _cst_ts(year: int, month: int, day: int, hour: int = 12) -> int:
    return int(datetime(year, month, day, hour, tzinfo=CST).timestamp())


# 2026-08-25 是周二。次日 08-26 会再开一张日单。
ENROLL_TUE = _cst_ts(2026, 8, 25)
NEXT_DAY = _cst_ts(2026, 8, 26)
DAY_AFTER = _cst_ts(2026, 8, 27)


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


async def _set(db, sid: int, **fields) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)
    async with db.connect() as conn:
        await conn.execute(
            f"UPDATE stewards SET {cols} WHERE id=?",
            (*fields.values(), sid),
        )
        await conn.commit()


async def _row(db, sid: int) -> tuple[int, int]:
    async with db.connect() as conn:
        r = await (await conn.execute(
            "SELECT tickets, COALESCE(upkeep_arrears, 0) FROM stewards WHERE id=?",
            (sid,),
        )).fetchone()
    return int(r[0]), int(r[1])


def test_due_from_holdings() -> None:
    from server import config, upkeep

    assert upkeep.PLOT_EXTRA == 2
    assert upkeep.ORCHARD_EXTRA == 2
    assert upkeep.GREENHOUSE == 2
    assert upkeep.BARN_BASE == 2
    assert upkeep.BARN_STOCKED == 2
    assert upkeep.PEN == 2
    assert upkeep.SALT_EXTRA == 2
    assert upkeep.QUARRY_EXTRA == 2
    assert upkeep.HUT_BY_LEVEL[2] == 2
    assert upkeep.BOAT_FEE["skiff"] == 2

    due, items = upkeep.due_from_holdings({
        "plots": config.START_PARCELS,
        "orchards": config.START_ORCHARDS,
        "greenhouses": 0,
        "barn": False,
        "barn_stocked": 0,
        "eatery": False,
        "hut_built": False,
        "hut_level": 0,
        "pens": 0,
        "pans": 0,
        "pits": 0,
        "boat_key": "",
    })
    assert due == 0, (due, items)

    due, items = upkeep.due_from_holdings({
        "plots": config.START_PARCELS + 2,
        "orchards": config.START_ORCHARDS + 1,
        "greenhouses": 1,
        "barn": True,
        "barn_stocked": 3,
        "eatery": True,
        "hut_built": True,
        "hut_level": 2,
        "pens": 1,
        "pans": 2,
        "pits": 3,
        "boat_key": "skiff",
    })
    # 2*2 plots + 1*2 orchard + 2 gh + 2 barn + 3*2 stocked + 2 shop
    # + 2 hut2 + 2 pen + 2 salt extra + 2*2 pits + 2 boat
    assert due == 4 + 2 + 2 + 2 + 6 + 2 + 2 + 2 + 2 + 4 + 2, (due, items)
    keys = {it["key"] for it in items}
    assert "plot" in keys and "eatery" in keys and "greenhouse" in keys


async def test_first_day_exempt() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="upkeep-new-"))
    db = await _boot(tmp)
    from server import mcp_dispatch

    real_now = db.now
    db.now = lambda: ENROLL_TUE
    try:
        kid, sid = await _enroll(db, "new@example.com", "新客")
        await _set(db, sid, parcel_count=8, eatery_open=1, tickets=400)
        text = await mcp_dispatch.visit_bundle(kid, "潮生会 维")
        assert "免征到明天" in text or "新号" in text, text
        tickets, arrears = await _row(db, sid)
        assert tickets == 400, tickets
        assert arrears == 0, arrears
    finally:
        db.now = real_now


async def test_daily_levy_and_lock() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="upkeep-levy-"))
    db = await _boot(tmp)
    from server import mcp_dispatch, game

    real_now = db.now
    db.now = lambda: ENROLL_TUE
    kid, sid = await _enroll(db, "farm@example.com", "园主")
    await _set(
        db, sid,
        tickets=500,
        parcel_count=5,
        greenhouse_count=1,
        greenhouse=1,
        eatery_open=1,
        barn_built=1,
        last_bar_shift_at=ENROLL_TUE,
    )
    db.now = lambda: NEXT_DAY
    try:
        async with db.connect() as conn:
            await conn.execute(
                "DELETE FROM world_flags WHERE flag_key LIKE 'shore_upkeep:%'"
            )
            await conn.commit()
        text = await mcp_dispatch.visit_bundle(kid, "潮生会 维")
        assert "岸维" in text, text
        tickets, arrears = await _row(db, sid)
        # extra 2 plots=4, gh=2, barn=2, shop=2 → 10. auto-collect (500-200=300 cap)
        assert arrears == 0, (arrears, tickets, text)
        assert tickets == 500 - 10, (tickets, text)
        assert "10" in text or "已划" in text or "已结清" in text, text

        # same calendar day: no second bill
        again = await mcp_dispatch.visit_bundle(kid, "潮生会 维")
        tickets2, arrears2 = await _row(db, sid)
        assert tickets2 == tickets, (tickets2, again)
        assert arrears2 == 0, arrears2

        db.now = lambda: DAY_AFTER
        third = await mcp_dispatch.visit_bundle(kid, "潮生会 维")
        tickets3, arrears3 = await _row(db, sid)
        assert arrears3 == 0, (arrears3, tickets3, third)
        assert tickets3 == tickets - 10, (tickets3, third)

        await _set(db, sid, tickets=180, upkeep_arrears=12, last_bar_shift_at=DAY_AFTER)
        locked = await game.plot_ops(kid, "买地 确认")
        assert "欠岸维" in locked or "维 交" in locked, locked
    finally:
        db.now = real_now


async def test_pay_and_shop_pause() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="upkeep-pay-"))
    db = await _boot(tmp)
    from server import eatery, mcp_dispatch, upkeep

    real_now = db.now
    db.now = lambda: ENROLL_TUE
    try:
        host_kid, host_sid = await _enroll(db, "host@example.com", "馆主")
        guest_kid, guest_sid = await _enroll(db, "guest@example.com", "食客")
        await _set(
            db, host_sid,
            tickets=200,
            eatery_open=1,
            eatery_label="盐汤",
            upkeep_arrears=12,
            last_bar_shift_at=ENROLL_TUE,
        )
        await _set(db, guest_sid, tickets=80, last_bar_shift_at=ENROLL_TUE)
        host = await db.get_steward_by_id(host_sid)
        assert upkeep.shop_paused(host)
        try:
            await eatery._dine(await db.get_steward_by_id(guest_sid), "馆主", None)
            raise AssertionError("paused shop should not serve")
        except ValueError as exc:
            assert "暂停堂食" in str(exc) or "岸维" in str(exc), str(exc)

        paid = await mcp_dispatch.visit_bundle(host_kid, "潮生会 维 交")
        assert "划" in paid or "结清" in paid, paid
        tickets, arrears = await _row(db, host_sid)
        assert arrears == 0, arrears
        assert tickets == 188, tickets
        host = await db.get_steward_by_id(host_sid)
        assert not upkeep.shop_paused(host)
    finally:
        db.now = real_now


async def test_help_not_mascot() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="upkeep-help-"))
    db = await _boot(tmp)
    from server import mcp_dispatch

    real_now = db.now
    db.now = lambda: ENROLL_TUE
    try:
        kid, _sid = await _enroll(db, "help@example.com", "问事人")
        text = await mcp_dispatch.visit_bundle(kid, "潮生会 维")
        assert "mascot upkeep" in text, text
        assert "plot_ops repair" in text, text
        assert "没有 upkeep_ops" in text, text
        desk = await mcp_dispatch.visit_bundle(kid, "潮生会")
        assert "维" in desk, desk
    finally:
        db.now = real_now


def main() -> None:
    test_due_from_holdings()
    asyncio.run(test_first_day_exempt())
    asyncio.run(test_daily_levy_and_lock())
    asyncio.run(test_pay_and_shop_pause())
    asyncio.run(test_help_not_mascot())
    print("ok")


if __name__ == "__main__":
    main()
