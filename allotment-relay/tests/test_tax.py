#!/usr/bin/env python3
"""岸税：口袋现票超额累进，周一换班自动划入潮汐基金。"""
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


# 2026-08-25 是周二（W35）。下周一 08-31 是 W36。
ENROLL_TUE = _cst_ts(2026, 8, 25)
NEXT_MON = _cst_ts(2026, 8, 31)


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


async def _set_tickets(db, sid: int, tickets: int) -> None:
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET tickets=? WHERE id=?",
            (tickets, sid),
        )
        await conn.commit()


async def _row(db, sid: int) -> tuple[int, int]:
    async with db.connect() as conn:
        r = await (await conn.execute(
            "SELECT tickets, COALESCE(tax_arrears, 0) FROM stewards WHERE id=?",
            (sid,),
        )).fetchone()
    return int(r[0]), int(r[1])


async def _fund(db) -> int:
    async with db.connect() as conn:
        r = await (await conn.execute(
            "SELECT tickets FROM tide_fund WHERE id=1"
        )).fetchone()
    return int(r[0] if r else 0)


def test_tax_due_brackets() -> None:
    from server import tax

    assert tax.TAX_FREE == 800
    assert tax.tax_due(0) == 0
    assert tax.tax_due(800) == 0
    assert tax.tax_due(1500) == 28  # (1500-800)*4%
    assert tax.tax_due(4000) == 188  # 68 + 120
    assert tax.tax_due(10000) == 908  # 68 + 280 + 560
    assert tax.tax_due(40000) == 7208
    assert tax.tax_due(100000) == 24808
    assert tax.band_name(120) == "免征"
    assert tax.band_name(1500) == "温水"
    assert tax.band_name(4000) == "殷实"
    assert tax.band_name(10000) == "阔手"
    assert tax.band_name(20000) == "豪客"
    assert tax.band_name(40000) == "潮主"
    assert tax.band_name(100000) == "潮宗"

    # 岛上实况：岛均约 4000，第二十名刚到岛均，榜首 20 万。
    assert tax.gap_surcharge(4000, 4000) == 0
    assert tax.gap_surcharge(20000, 4000) == 0
    assert tax.gap_surcharge(40000, 4000) == 1600  # (40000-20000)*8%
    assert tax.gap_surcharge(200000, 4000) == 25600
    assert tax.tax_due(4000, 4000) == 188
    assert tax.tax_due(200000, 4000) == 60808 + 25600
    assert tax.tax_due(200000) == 60808  # 不传岛均不加潮差


async def test_first_week_exempt() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="tax-new-"))
    db = await _boot(tmp)
    from server import mcp_dispatch, tax

    real_now = db.now
    db.now = lambda: ENROLL_TUE
    try:
        kid, sid = await _enroll(db, "new@example.com", "新客")
        await _set_tickets(db, sid, 5000)
        text = await mcp_dispatch.visit_bundle(kid, "潮生会 税")
        assert "免征到下周" in text or "新号" in text, text
        tickets, arrears = await _row(db, sid)
        assert tickets == 5000, tickets
        assert arrears == 0, arrears
        assert tax.tax_due(5000) == 268  # 殷实档未改
    finally:
        db.now = real_now


async def test_weekly_levy_and_fund() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="tax-levy-"))
    db = await _boot(tmp)
    from server import mcp_dispatch, tax

    real_now = db.now
    db.now = lambda: ENROLL_TUE
    kid, sid = await _enroll(db, "rich@example.com", "阔客")
    await _set_tickets(db, sid, 4000)
    db.now = lambda: NEXT_MON
    try:
        async with db.connect() as conn:
            await conn.execute(
                "DELETE FROM world_flags WHERE flag_key LIKE 'shore_tax:%'"
            )
            await conn.commit()
        text = await mcp_dispatch.visit_bundle(kid, "潮生会 税")
        due = tax.tax_due(4000)
        assert due == 188
        assert "殷实" in text, text
        tickets, arrears = await _row(db, sid)
        assert arrears == 0, arrears
        assert tickets == 4000 - due, (tickets, due)
        assert await _fund(db) == due
        assert "已划" in text or "结清" in text, text
        sheet = await mcp_dispatch.steward_ops(kid, "sheet")
        assert "岸税" in sheet, sheet
        assert "殷实" in sheet, sheet
    finally:
        db.now = real_now


async def test_pay_arrears_unlocks_land() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="tax-debt-"))
    db = await _boot(tmp)
    from server import game, mcp_dispatch

    real_now = db.now
    db.now = lambda: ENROLL_TUE
    kid, sid = await _enroll(db, "owe@example.com", "欠客")
    db.now = lambda: NEXT_MON
    try:
        await _set_tickets(db, sid, 4000)
        async with db.connect() as conn:
            await conn.execute(
                "DELETE FROM world_flags WHERE flag_key LIKE 'shore_tax:%'"
            )
            await conn.commit()
        await mcp_dispatch.visit_bundle(kid, "潮生会 税")
        async with db.connect() as conn:
            await conn.execute(
                "UPDATE stewards SET tickets=180, tax_arrears=120, last_bar_shift_at=? WHERE id=?",
                (NEXT_MON, sid),
            )
            await conn.commit()

        locked = await game.plot_ops(kid, "买地 确认")
        assert "欠岸税" in locked or "税 交" in locked, locked

        try:
            await mcp_dispatch.visit_bundle(kid, "潮生会 基金 捐 8")
        except ValueError as exc:
            assert "岸税" in str(exc), str(exc)
        else:
            raise AssertionError("fund donate should refuse while in arrears")

        paid = await mcp_dispatch.visit_bundle(kid, "潮生会 税 交")
        assert "120" in paid or "划" in paid, paid
        tickets, arrears = await _row(db, sid)
        assert arrears == 0, arrears
        assert tickets == 60, tickets

        quote = await game.plot_ops(kid, "买地")
        assert "确认" in quote, quote
    finally:
        db.now = real_now


async def test_partial_pay_and_help() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="tax-part-"))
    db = await _boot(tmp)
    from server import mcp_dispatch

    real_now = db.now
    db.now = lambda: ENROLL_TUE
    kid, sid = await _enroll(db, "part@example.com", "分客")
    db.now = lambda: NEXT_MON
    try:
        help_text = await mcp_dispatch.visit_bundle(kid, "潮生会 help")
        assert "税 交" in help_text, help_text
        assert "没有 tax_ops" in help_text, help_text
        assert "800" in help_text, help_text

        async with db.connect() as conn:
            await conn.execute(
                "UPDATE stewards SET tickets=180, tax_arrears=80 WHERE id=?",
                (sid,),
            )
            await conn.commit()
        part = await mcp_dispatch.visit_bundle(kid, "潮生会 税 交 30")
        assert "30" in part, part
        tickets, arrears = await _row(db, sid)
        assert tickets == 150, tickets
        assert arrears == 50, arrears
    finally:
        db.now = real_now


async def test_gap_levy_on_whale() -> None:
    """岛均被少数人拉高时，榜首要交潮差，刚到岛均的人不用。"""
    tmp = Path(tempfile.mkdtemp(prefix="tax-gap-"))
    db = await _boot(tmp)
    from server import tax

    real_now = db.now
    db.now = lambda: ENROLL_TUE
    whale_kid, whale_sid = await _enroll(db, "whale@example.com", "鲸客")
    mid_kid, mid_sid = await _enroll(db, "mid@example.com", "中客")
    poor = []
    for i in range(18):
        kid, sid = await _enroll(db, f"p{i}@example.com", f"贫{i}")
        poor.append((kid, sid))
    await _set_tickets(db, whale_sid, 200000)
    await _set_tickets(db, mid_sid, 4000)
    for _kid, sid in poor:
        await _set_tickets(db, sid, 2000)
    # 200000 + 4000 + 18*2000 = 240000 / 20 = 12000
    db.now = lambda: NEXT_MON
    try:
        async with db.connect() as conn:
            await conn.execute(
                "DELETE FROM world_flags WHERE flag_key LIKE 'shore_tax:%'"
            )
            result = await tax.ensure_shore_tax(conn, ts=NEXT_MON)
            await conn.commit()
        avg = 12000
        whale_due = tax.tax_due(200000, avg)
        mid_due = tax.tax_due(4000, avg)
        assert tax.gap_surcharge(4000, avg) == 0
        assert tax.gap_surcharge(200000, avg) > 0
        assert result and result["assessed"] >= whale_due + mid_due, result
        whale_left, whale_arrears = await _row(db, whale_sid)
        mid_left, mid_arrears = await _row(db, mid_sid)
        assert whale_arrears == 0
        assert mid_arrears == 0
        assert whale_left == 200000 - whale_due, (whale_left, whale_due)
        assert mid_left == 4000 - mid_due, (mid_left, mid_due)
        assert whale_due > tax.bracket_due(200000)
    finally:
        db.now = real_now


async def test_no_tax_ops() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="tax-noops-"))
    db = await _boot(tmp)
    kid, _sid = await _enroll(db, "ops@example.com", "误客")
    from server import mcp_dispatch

    desk = await mcp_dispatch.visit_bundle(kid, "潮生会")
    assert "岸税" in desk or "税" in desk, desk
    try:
        await mcp_dispatch.visit_bundle(kid, "潮生会 逃税")
    except ValueError as exc:
        assert "未知" in str(exc) or "税" in str(exc), str(exc)
    else:
        raise AssertionError("逃税 should not exist")


def test_tax() -> None:
    test_tax_due_brackets()
    asyncio.run(test_first_week_exempt())
    asyncio.run(test_weekly_levy_and_fund())
    asyncio.run(test_pay_arrears_unlocks_land())
    asyncio.run(test_partial_pay_and_help())
    asyncio.run(test_gap_levy_on_whale())
    asyncio.run(test_no_tax_ops())


if __name__ == "__main__":
    test_tax()
    print("ok")
