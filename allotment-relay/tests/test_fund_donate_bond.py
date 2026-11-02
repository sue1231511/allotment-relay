#!/usr/bin/env python3
"""基金捐款的岛缘按东八区当天累计算：拆开捐和一次捐总岛缘一样。"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CST = timezone(timedelta(hours=8))


def _cst_ts(year: int, month: int, day: int, hour: int = 12) -> int:
    return int(datetime(year, month, day, hour, tzinfo=CST).timestamp())


DAY1 = _cst_ts(2026, 8, 26)
DAY1_LATE = _cst_ts(2026, 8, 26, 23)
DAY2 = _cst_ts(2026, 8, 27)


@pytest.fixture(autouse=True)
def _restore_now():
    from server import db

    real_now = db.now
    yield
    db.now = real_now


async def _boot(prefix: str):
    tmp = Path(tempfile.mkdtemp(prefix=prefix))
    os.environ["DATA_DIR"] = str(tmp)
    from server import config, db

    config.DATA_DIR = tmp
    config.DB_PATH = tmp / "relay.db"
    db.DATA_DIR = tmp
    db.DB_PATH = tmp / "relay.db"
    await db.init_db()
    return db


async def _enroll(db, email: str, name: str, tickets: int) -> int:
    key = await db.create_api_key(email)
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], name, "", "naturalist", "")
    async with db.connect() as conn:
        await conn.execute("UPDATE stewards SET tickets=? WHERE key_id=?", (tickets, row["id"]))
        await conn.commit()
    return row["id"]


async def _bond(db, key_id: int) -> int:
    async with db.connect() as conn:
        r = await (await conn.execute(
            "SELECT island_bond FROM stewards WHERE key_id=?", (key_id,)
        )).fetchone()
    return int(r[0] or 0)


async def _rows(db) -> list[tuple]:
    async with db.connect() as conn:
        return list(await (await conn.execute(
            "SELECT day, amount, bond_granted FROM fund_donations ORDER BY id"
        )).fetchall())


async def _world(prefix: str):
    db = await _boot(prefix)
    rich = await _enroll(db, f"{prefix}rich@example.com", "余客", 100000)
    await _enroll(db, f"{prefix}poor@example.com", "缺客", 0)
    return db, rich


async def test_split_equals_single() -> None:
    from server import chaoshen

    db1, rich1 = await _world("fund-split-")
    real_now = db1.now
    db1.now = lambda: DAY1
    try:
        for _ in range(100):
            await chaoshen.fund_donate(rich1, 1)
        split_bond = await _bond(db1, rich1)
    finally:
        db1.now = real_now

    db2, rich2 = await _world("fund-single-")
    db2.now = lambda: DAY1
    try:
        await chaoshen.fund_donate(rich2, 100)
        single_bond = await _bond(db2, rich2)
    finally:
        db2.now = real_now

    assert split_bond == single_bond == 60, (split_bond, single_bond)  # floor(6*sqrt(100))


async def test_receipt_mentions_cumulative_and_gain() -> None:
    from server import chaoshen

    db, rich = await _world("fund-receipt-")
    db.now = lambda: DAY1
    first = await chaoshen.fund_donate(rich, 4)
    assert "岛缘 +12" in first and "累计" not in first, first  # floor(6*2)
    second = await chaoshen.fund_donate(rich, 5)  # 累计 9 -> 18，本次 +6
    assert "今天累计捐 9" in second and "岛缘按累计算" in second and "岛缘 +6" in second, second
    assert await _bond(db, rich) == 18


async def test_cross_day_recounts() -> None:
    from server import chaoshen

    db, rich = await _world("fund-days-")
    db.now = lambda: DAY1
    await chaoshen.fund_donate(rich, 100)          # +60
    db.now = lambda: DAY1_LATE                     # 同一东八区日，仍累计
    await chaoshen.fund_donate(rich, 300)          # floor(6*20)=120 -> +60
    assert await _bond(db, rich) == 120
    db.now = lambda: DAY2                          # 次日重新累计
    await chaoshen.fund_donate(rich, 100)          # 又 +60
    assert await _bond(db, rich) == 180
    rows = await _rows(db)
    assert [r[1] for r in rows] == [100, 300, 100] and rows[0][0] != rows[2][0], rows
    assert rows[0][0] == rows[1][0] == 20260826 and rows[2][0] == 20260827, rows


async def test_rejected_donation_not_counted() -> None:
    from server import chaoshen

    db = await _boot("fund-reject-")
    rich = await _enroll(db, "rj-rich@example.com", "余客", 1000)
    poor = await _enroll(db, "rj-poor@example.com", "缺客", 10)
    db.now = lambda: DAY1
    for who, amt in ((poor, 5), (rich, 10 ** 6)):   # 低于岛均 / 超过最多可捐
        try:
            await chaoshen.fund_donate(who, amt)
        except ValueError:
            pass
        else:
            raise AssertionError("donation should be refused")
    assert await _rows(db) == []
    assert await _bond(db, rich) == 0 and await _bond(db, poor) == 0
    await chaoshen.fund_donate(rich, 9)
    assert [r[1] for r in await _rows(db)] == [9]


async def test_old_db_migrates_table() -> None:
    db = await _boot("fund-migrate-")
    async with db.connect() as conn:
        await conn.execute("DROP TABLE fund_donations")
        await conn.commit()
    await db.init_db()   # 老库再启动，迁移要把表补上
    assert await _rows(db) == []
    async with db.connect() as conn:
        cols = [r[1] for r in await (await conn.execute("PRAGMA table_info(fund_donations)")).fetchall()]
    assert cols == ["id", "steward_id", "day", "amount", "bond_granted", "created_at"], cols
