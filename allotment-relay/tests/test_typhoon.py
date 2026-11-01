#!/usr/bin/env python3
"""台风季 — 预报、三选一备灾、防灾工程、登陆惰性结算与幂等。"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
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


def test_typhoon() -> None:
    asyncio.run(_test_typhoon())


def _this_week_monday_noon() -> int:
    """本东八区周周一 12:00。预报只在周四 20:00 登陆前出现，真实时钟落在周五到周日测试就会红，所以钉住时钟。"""
    cst = timezone(timedelta(hours=8))
    now = datetime.fromtimestamp(time.time(), cst)
    monday = (now - timedelta(days=now.weekday())).replace(hour=12, minute=0, second=0, microsecond=0)
    return int(monday.timestamp())


async def _test_typhoon() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="typhoon-"))
    db = await _boot(tmp)
    real_now = db.now
    monday = _this_week_monday_noon()
    db.now = lambda: monday
    try:
        await _typhoon_flow(db)
    finally:
        db.now = real_now


async def _typhoon_flow(db) -> None:
    from server import chaoshen, season, typhoon

    akid, asid = await _enroll(db, "a@example.com", "岛民安")
    season.set_season("春")
    not_now = await chaoshen.chaoshen_ops(akid, "台风")
    assert "不是台风季" in not_now, not_now

    season.set_season("秋")
    async with db.connect() as conn:
        await conn.execute("UPDATE stewards SET energy=50 WHERE id=?", (asid,))
        await conn.commit()

    forecast = await chaoshen.chaoshen_ops(akid, "台风")
    assert "台风预报" in forecast and "备灾" in forecast, forecast

    # 登陆时刻拨到 1 小时后：备灾窗口有效
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE typhoon_events SET landfall_at=?", (db.now() + 3600,)
        )
        await conn.commit()

    # 加固：扣 20 票，重复被拒
    async with db.connect() as conn:
        t0 = (await (await conn.execute(
            "SELECT tickets FROM stewards WHERE id=?", (asid,)
        )).fetchone())[0]
    house = await chaoshen.chaoshen_ops(akid, "台风 备灾 加固")
    assert "加固" in house, house
    async with db.connect() as conn:
        t1 = (await (await conn.execute(
            "SELECT tickets FROM stewards WHERE id=?", (asid,)
        )).fetchone())[0]
    assert t1 == t0 - 20, (t0, t1)
    try:
        await chaoshen.chaoshen_ops(akid, "台风 备灾 闭门")
        raise AssertionError("一季应只能备灾一次")
    except ValueError as exc:
        assert "一次" in str(exc), exc

    # 防灾工程：捐票凑满（目标 = max(20, 人数×8)，1 人 = 20）
    donate = await chaoshen.chaoshen_ops(akid, "台风 捐 票 25")
    assert "凑满" in donate, donate

    # 登陆时刻拨到过去：惰性结算，工程凑满 → 全岛无恙 + 幂等
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE typhoon_events SET landfall_at=?", (db.now() - 60,)
        )
        await conn.commit()
    settled = await chaoshen.chaoshen_ops(akid, "台风")
    assert "全岛无恙" in settled, settled
    again = await chaoshen.chaoshen_ops(akid, "台风")
    assert again != "", again
    async with db.connect() as conn:
        notices = (await (await conn.execute(
            "SELECT COUNT(*) FROM hui_notices WHERE tag='台风纪事'"
        )).fetchone())[0]
        phase = (await (await conn.execute(
            "SELECT phase FROM typhoon_events ORDER BY id LIMIT 1"
        )).fetchone())[0]
    assert phase == "done", phase
    assert notices == 1, ("结算应只发生一次", notices)

    # 未备灾未凑满的第二场：新岛民吃损失
    bkid, bsid = await _enroll(db, "b@example.com", "裸奔民泊")
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE parcels SET crop='kale', ready_at=1, tended=1, harvest_left=3 "
            "WHERE steward_id=? AND orchard=0 AND greenhouse=0", (bsid,)
        )
        await conn.execute(
            "UPDATE typhoon_events SET phase='pending', landfall_at=?, "
            "prep_tickets=0, prep_wood=0",
            (db.now() - 60,),
        )
        await conn.commit()
    raw = await typhoon.typhoon_ops(bkid, "")
    assert "台风过境" in raw, raw
    async with db.connect() as conn:
        rows = await (await conn.execute(
            "SELECT COUNT(*) FROM chronicle WHERE action='typhoon' AND target_id=?",
            (bsid,),
        )).fetchone()
    assert rows[0] >= 1, "裸奔民泊应有一条台风夜纪事"

    season.set_season(None)


if __name__ == "__main__":
    test_typhoon()
    print("ok")
