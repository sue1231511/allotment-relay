#!/usr/bin/env python3
"""委托佣工 — 看护委托：接单、assist 日结、满勤结案、超时按天退款。"""
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


def test_labor_contract() -> None:
    asyncio.run(_test_labor_contract())


async def _test_labor_contract() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="labor-contract-"))
    db = await _boot(tmp)
    from server import multi

    bkid, bsid = await _enroll(db, "boss@example.com", "雇主安")
    wkid, wsid = await _enroll(db, "worker@example.com", "帮工阿泊")

    # 雇主的地要有活干（assist 才有得打理）
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE parcels SET crop='crop_kale', tended=0 WHERE steward_id=?", (bsid,)
        )
        await conn.commit()

    # 低酬被拒，正常发单托管
    try:
        await multi.contract_ops(bkid, "post 看护 3 5")
        raise AssertionError("低酬应被拒")
    except ValueError as exc:
        assert "至少" in str(exc), exc
    posted = await multi.contract_ops(bkid, "post 看护 3 30")
    assert "看护委托" in posted and "托管" in posted, posted
    async with db.connect() as conn:
        tickets_boss = (await (await conn.execute(
            "SELECT tickets FROM stewards WHERE id=?", (bsid,)
        )).fetchone())[0]
        cid = (await (await conn.execute(
            "SELECT id FROM contracts WHERE poster_id=? ORDER BY id DESC", (bsid,)
        )).fetchone())[0]

    # 协作度不足不能接
    try:
        await multi.contract_ops(wkid, f"take {cid}")
        raise AssertionError("协作度不足应被拒")
    except ValueError as exc:
        assert "协作度" in str(exc), exc

    # 物品交付对没人接的劳动单无效
    try:
        await multi.contract_ops(wkid, f"fill {cid}")
        raise AssertionError("劳动单不能 fill")
    except ValueError as exc:
        assert "take" in str(exc), exc

    # 处熟再接单
    async with db.connect() as conn:
        await multi._bump_rapport(conn, wsid, bsid, 25)
        await conn.commit()
    taken = await multi.contract_ops(wkid, f"take {cid}")
    assert "接下" in taken, taken

    # 模拟三天：day1/2/3 assist 雇主，日结 10 票/天，第三天满勤结案
    async with db.connect() as conn:
        tickets0 = (await (await conn.execute(
            "SELECT tickets FROM stewards WHERE id=?", (wsid,)
        )).fetchone())[0]
    day_counter = {"n": 0}
    orig_day_id = multi._day_id
    multi._day_id = lambda: f"d{day_counter['n']}"

    async def next_day():
        day_counter["n"] += 1
        # 地恢复未打理，assist 才有活
        async with db.connect() as conn:
            await conn.execute(
                "UPDATE parcels SET tended=0 WHERE steward_id=?", (bsid,)
            )
            await conn.commit()

    try:
        for i, expect_tail in enumerate(["1/3", "2/3", "满勤"]):
            await next_day()
            msg = await multi.alliance_ops(wkid, "assist 雇主安")
            assert "打理" in msg, msg
            assert expect_tail in msg, (i, msg)
        async with db.connect() as conn:
            tickets1 = (await (await conn.execute(
                "SELECT tickets FROM stewards WHERE id=?", (wsid,)
            )).fetchone())[0]
            status = (await (await conn.execute(
                "SELECT status FROM contracts WHERE id=?", (cid,)
            )).fetchone())[0]
    finally:
        multi._day_id = orig_day_id
    # 工钱 30 票全发（10/天×3）；assist 本身也有票，只核差额区间
    assert tickets1 > tickets0 + 30, (tickets0, tickets1)
    assert status == "filled", status

    # 超时未满勤：新单 2 天 30 票，只干 1 天，deadline 挪到过去
    await multi.contract_ops(bkid, "post 看护 2 30")
    async with db.connect() as conn:
        cid2 = (await (await conn.execute(
            "SELECT id FROM contracts WHERE poster_id=? AND status='open' ORDER BY id DESC", (bsid,)
        )).fetchone())[0]
    await multi.contract_ops(wkid, f"take {cid2}")
    day_counter["n"] = 10
    multi._day_id = lambda: f"d{day_counter['n']}"
    try:
        await next_day()
        await multi.alliance_ops(wkid, "assist 雇主安")
    finally:
        multi._day_id = orig_day_id
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE contracts SET deadline=? WHERE id=?", (1, cid2)
        )
        await conn.commit()
    await multi.contract_ops(bkid, "list")
    async with db.connect() as conn:
        conn.row_factory = __import__("aiosqlite").Row
        row = dict(await (await conn.execute(
            "SELECT status, labor_done FROM contracts WHERE id=?", (cid2,)
        )).fetchone())
        boss_now = (await (await conn.execute(
            "SELECT tickets FROM stewards WHERE id=?", (bsid,)
        )).fetchone())[0]
    assert row["status"] == "expired", row
    assert row["labor_done"] == 1, row
    # 退 15（2天30票，干了1天发15，退15）
    assert boss_now == tickets_boss - 30 + 15, (boss_now, tickets_boss)


if __name__ == "__main__":
    test_labor_contract()
    print("ok")
