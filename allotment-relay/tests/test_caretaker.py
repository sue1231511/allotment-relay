#!/usr/bin/env python3
"""荒宅代管 — 判定、押金、收获归代管人、原主回归自动结束。"""
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
    return row["id"], sid


def test_caretaker() -> None:
    asyncio.run(_test_caretaker())


async def _test_caretaker() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="caretaker-"))
    db = await _boot(tmp)
    from server import caretaker, multi

    okid, osid = await _enroll(db, "owner@example.com", "离岛人")
    ckid, csid = await _enroll(db, "keeper@example.com", "看家人")

    # 原主还在岛上：不算荒宅、不能代管
    roster = await multi.alliance_ops(ckid, "荒宅")
    assert "没有荒宅" in roster or "离岛人" not in roster, roster
    try:
        await multi.alliance_ops(ckid, "代管 离岛人")
        raise AssertionError("在岛岛民不能被代管")
    except ValueError as exc:
        assert "还在岛上" in str(exc), exc

    # 原主离岛 30 天，地里种上熟甘蓝
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET last_active_at=?, created_at=? WHERE id=?",
            (db.now() - 30 * 86400, db.now() - 40 * 86400, osid),
        )
        await conn.execute(
            "UPDATE parcels SET crop='kale', ready_at=1, tended=1, harvest_left=3 "
            "WHERE steward_id=? AND orchard=0 AND greenhouse=0",
            (osid,),
        )
        await conn.commit()
    roster = await multi.alliance_ops(ckid, "荒宅")
    assert "离岛人" in roster and "30 天" in roster, roster

    # 协作度不足
    try:
        await multi.alliance_ops(ckid, "代管 离岛人")
        raise AssertionError("协作度不足应被拒")
    except ValueError as exc:
        assert "协作度" in str(exc), exc

    async with db.connect() as conn:
        await multi._bump_rapport(conn, csid, osid, 35)
        await conn.commit()
    started = await multi.alliance_ops(ckid, "代管 离岛人")
    assert "代管开始" in started and "潮汐基金" in started, started

    # 收获：熟菜进代管人行囊，地清空
    harvest = await multi.alliance_ops(ckid, "代管收")
    assert "收了" in harvest and "进了你的行囊" in harvest, harvest
    async with db.connect() as conn:
        bag = (await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item='crop_kale'",
            (csid,),
        )).fetchone())
        plots = (await (await conn.execute(
            "SELECT COUNT(*) FROM parcels WHERE steward_id=? AND crop IS NOT NULL "
            "AND orchard=0 AND greenhouse=0", (osid,)
        )).fetchone())[0]
    assert bag and int(bag[0]) >= 1, bag
    assert plots == 0, plots

    # 同日再收被拒
    try:
        await multi.alliance_ops(ckid, "代管收")
        raise AssertionError("同日重复收应被拒")
    except ValueError as exc:
        assert "今天收过了" in str(exc), exc

    # 原主回来：代管自动结束并给原主留纪事
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET last_active_at=? WHERE id=?", (db.now(), osid)
        )
        await conn.commit()
    ended = await multi.alliance_ops(ckid, "代管收")
    assert "代管已结束" in ended and "原主回来了" in ended, ended
    async with db.connect() as conn:
        n = (await (await conn.execute(
            "SELECT COUNT(*) FROM chronicle WHERE action='caretake' AND target_id=?",
            (osid,),
        )).fetchone())[0]
        active = (await (await conn.execute(
            "SELECT COUNT(*) FROM home_caretakes WHERE active=1"
        )).fetchone())[0]
        fund = (await (await conn.execute(
            "SELECT tickets FROM tide_fund WHERE id=1"
        )).fetchone())
    assert n >= 1, "原主没收到代管纪事"
    assert active == 0, active
    assert fund and int(fund[0]) >= 30, fund


if __name__ == "__main__":
    test_caretaker()
    print("ok")
