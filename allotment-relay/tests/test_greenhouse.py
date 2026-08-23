#!/usr/bin/env python3
"""温室可加盖：第 1 座 180 即用，之后更贵并要开垦。"""
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


def test_price_steeper_than_land() -> None:
    from server import config

    assert config.GREENHOUSE_EXPAND_COSTS == [180, 310, 500, 750, 1060]
    assert config.GREENHOUSE_CLEAR_SECONDS[0] == 0
    assert config.GREENHOUSE_CLEAR_SECONDS[1] == 60 * 60
    for i in range(1, 5):
        assert config.greenhouse_expand_cost(i) > config.parcel_expand_cost(i)
        assert config.greenhouse_clear_seconds(i) > config.parcel_clear_seconds(i)


async def test_first_instant_then_clear() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="gh-buy-"))
    db = await _boot(tmp)
    from server import game

    kid, sid = await _enroll(db, "gh@example.com", "棚人")
    async with db.connect() as conn:
        await conn.execute("UPDATE stewards SET tickets=tickets+2000 WHERE id=?", (sid,))
        await conn.commit()

    quote = await game.plot_ops(kid, "买棚")
    assert "180" in quote and "无上限" in quote, quote

    first = await game.plot_ops(kid, "买棚 确认")
    assert "棚1" in first and "180" in first and "马上" in first, first
    async with db.connect() as conn:
        row = await (await conn.execute(
            "SELECT greenhouse_count, greenhouse, tickets FROM stewards WHERE id=?",
            (sid,),
        )).fetchone()
        plot = await (await conn.execute(
            """
            SELECT slot, greenhouse, ready_at FROM parcels
            WHERE steward_id=? AND COALESCE(greenhouse,0)=1 AND slot=1
            """,
            (sid,),
        )).fetchone()
    assert row[0] == 1 and row[1] == 1
    assert plot is not None and plot[1] == 1 and plot[2] == 0

    second = await game.plot_ops(kid, "shed erect")
    assert "棚2" in second and "310" in second, second
    async with db.connect() as conn:
        plot2 = await (await conn.execute(
            "SELECT ready_at FROM parcels WHERE steward_id=? AND greenhouse=1 AND slot=2",
            (sid,),
        )).fetchone()
    assert plot2 is not None and plot2[0] > 0

    blocked = await game.plot_ops(kid, "买棚 确认")
    assert "开垦" in blocked, blocked


async def test_sow_99_alias_and_migrate() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="gh-mig-"))
    db = await _boot(tmp)
    from server import game

    kid, sid = await _enroll(db, "oldgh@example.com", "旧棚")
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET tickets=tickets+400, greenhouse=1 WHERE id=?", (sid,)
        )
        await conn.execute(
            "INSERT INTO parcels (steward_id, slot, orchard, greenhouse, tended) VALUES (?, 99, 0, 1, 0)",
            (sid,),
        )
        await conn.commit()
    await db.init_db()
    async with db.connect() as conn:
        migrated = await (await conn.execute(
            "SELECT slot FROM parcels WHERE steward_id=? AND greenhouse=1",
            (sid,),
        )).fetchone()
        count = (await (await conn.execute(
            "SELECT greenhouse_count FROM stewards WHERE id=?", (sid,)
        )).fetchone())[0]
    assert migrated[0] == 1
    assert count == 1

    async with db.connect() as conn:
        await db.add_item(conn, sid, "seed_kale", 1)
        await conn.commit()
    planted = await game.plot_ops(kid, "sow 99 甘蓝")
    assert "棚1" in planted and "甘蓝" in planted and "⚠" not in planted, planted


def main() -> None:
    test_price_steeper_than_land()
    asyncio.run(test_first_instant_then_clear())
    asyncio.run(test_sow_99_alias_and_migrate())
    print("greenhouse tests ok")


if __name__ == "__main__":
    main()
