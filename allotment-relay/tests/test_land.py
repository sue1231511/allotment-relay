#!/usr/bin/env python3
"""露天份地无上限：票价/开垦时间按旧表递推，跳过温室 #99。"""
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


def test_expand_formula_matches_old_table() -> None:
    from server import config

    assert config.PARCEL_EXPAND_COSTS == [80, 120, 180, 260, 360]
    assert config.PARCEL_CLEAR_SECONDS == [1800, 2700, 3600, 5400, 7200]
    for i, cost in enumerate([80, 120, 180, 260, 360]):
        assert config.parcel_expand_cost(i) == cost, (i, config.parcel_expand_cost(i))
    for i, sec in enumerate([1800, 2700, 3600, 5400, 7200]):
        assert config.parcel_clear_seconds(i) == sec, (i, config.parcel_clear_seconds(i))
    # 第 9、10 块：差额继续 +120、+140
    assert config.parcel_expand_cost(5) == 480
    assert config.parcel_expand_cost(6) == 620
    assert config.parcel_clear_seconds(5) == 165 * 60
    assert config.parcel_clear_seconds(6) == 210 * 60


def test_next_offer_never_caps() -> None:
    from server import land as land_mod

    fourth = land_mod.next_offer(3)
    assert fourth == {"slot": 4, "cost": 80, "clear_seconds": 1800}
    ninth = land_mod.next_offer(8)
    assert ninth["slot"] == 9
    assert ninth["cost"] == 480
    assert ninth["clear_seconds"] == 165 * 60
    # 温室 #99 留给 shed，露天第 99 块落到 #100
    around_gh = land_mod.next_offer(98)
    assert around_gh["slot"] == 100
    after_gh = land_mod.next_offer(99)
    assert after_gh["slot"] == 101
    assert land_mod.next_outdoor_slot(97) == 98
    assert land_mod.next_outdoor_slot(98) == 100


async def test_buy_beyond_eight() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="land-"))
    db = await _boot(tmp)
    from server import game

    kid, sid = await _enroll(db, "land@example.com", "开荒人")
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET tickets=2000, parcel_count=8 WHERE id=?",
            (sid,),
        )
        for slot in range(4, 9):
            await conn.execute(
                """
                INSERT OR IGNORE INTO parcels (steward_id, slot, crop, planted_at, tended, ready_at)
                VALUES (?, ?, NULL, NULL, 0, 0)
                """,
                (sid, slot),
            )
        await conn.commit()

    quote = await game.plot_ops(kid, "买地")
    assert "无上限" in quote, quote
    assert "480" in quote, quote
    assert "已经买满" not in quote
    assert "最多 8" not in quote

    bought = await game.plot_ops(kid, "买地 确认")
    assert "买下 #9" in bought, bought
    assert "480" in bought, bought
    assert "9 块" in bought, bought
    assert "无上限" in bought, bought

    async with db.connect() as conn:
        row = await (await conn.execute(
            "SELECT parcel_count, tickets FROM stewards WHERE id=?", (sid,)
        )).fetchone()
        plot = await (await conn.execute(
            "SELECT slot, ready_at FROM parcels WHERE steward_id=? AND slot=9 AND COALESCE(orchard,0)=0",
            (sid,),
        )).fetchone()
    assert row[0] == 9
    assert row[1] == 2000 - 480
    assert plot is not None
    assert plot[1] > 0

    again = await game.plot_ops(kid, "买地 确认")
    assert "还在开垦" in again, again


async def test_buy_skips_greenhouse_slot() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="land-gh-"))
    db = await _boot(tmp)
    from server import game

    kid, sid = await _enroll(db, "ghland@example.com", "绕棚人")
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET tickets=200000, parcel_count=98, greenhouse=1 WHERE id=?",
            (sid,),
        )
        await conn.execute(
            "INSERT INTO parcels (steward_id, slot, greenhouse, tended) VALUES (?, 99, 1, 0)",
            (sid,),
        )
        await conn.commit()

    bought = await game.plot_ops(kid, "买地 确认")
    assert "#100" in bought, bought
    async with db.connect() as conn:
        gh = await (await conn.execute(
            "SELECT greenhouse FROM parcels WHERE steward_id=? AND slot=99 AND COALESCE(orchard,0)=0",
            (sid,),
        )).fetchone()
        outdoor = await (await conn.execute(
            "SELECT greenhouse, ready_at FROM parcels WHERE steward_id=? AND slot=100 AND COALESCE(orchard,0)=0",
            (sid,),
        )).fetchone()
        count = (await (await conn.execute(
            "SELECT parcel_count FROM stewards WHERE id=?", (sid,)
        )).fetchone())[0]
    assert gh[0] == 1
    assert outdoor is not None
    assert outdoor[0] == 0
    assert count == 99


def main() -> None:
    test_expand_formula_matches_old_table()
    test_next_offer_never_caps()
    asyncio.run(test_buy_beyond_eight())
    asyncio.run(test_buy_skips_greenhouse_slot())
    print("land tests ok")


if __name__ == "__main__":
    main()
