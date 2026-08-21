#!/usr/bin/env python3
"""浇水/施肥缩短成熟时间。"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_grow_cut_math() -> None:
    from server import config
    from server.farming import apply_grow_cut, grow_cut_seconds

    assert grow_cut_seconds(120, 0.18) == 0
    assert grow_cut_seconds(1000, 0.18) == 180
    plot = {"grow_target": 3600}
    new, saved = apply_grow_cut(plot, config.WATER_CUT_RATE)
    assert saved == int(3600 * 0.18)
    assert new == 3600 - saved
    fert = apply_grow_cut(plot, config.FERTILIZE_COMPOST_CUT)
    assert fert[1] == int(3600 * 0.12)


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


async def test_water_and_fertilize() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="water-"))
    db = await _boot(tmp)
    from server import farming, game

    kid, sid = await _enroll(db, "water@example.com", "浇水人")
    planted = db.now() - 60
    async with db.connect() as conn:
        await conn.execute(
            """
            UPDATE parcels SET crop='kale', planted_at=?, tended=0, greenhouse=0,
            grow_target=3600, harvest_left=0, fertilized=0, watered=0
            WHERE steward_id=? AND slot=1
            """,
            (planted, sid),
        )
        await db.add_item(conn, sid, "compost", 2)
        await conn.commit()

    water = await game.plot_ops(kid, "浇水 1")
    assert "浇了水" in water and "提前" in water, water
    again = await game.plot_ops(kid, "浇水 1")
    assert "已经浇过" in again, again

    async with db.connect() as conn:
        row = await (await conn.execute(
            "SELECT watered, grow_target FROM parcels WHERE steward_id=? AND slot=1",
            (sid,),
        )).fetchone()
        compost_before = (await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item='compost'",
            (sid,),
        )).fetchone())[0]
    assert row[0] == 1
    assert row[1] < 3600
    after_water = row[1]

    fert = await game.plot_ops(kid, "施肥 1")
    assert "已施堆肥" in fert and "提前" in fert, fert
    async with db.connect() as conn:
        row = await (await conn.execute(
            "SELECT fertilized, grow_target, watered FROM parcels WHERE steward_id=? AND slot=1",
            (sid,),
        )).fetchone()
        compost_after = (await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item='compost'",
            (sid,),
        )).fetchone())[0]
    assert row[0] == 1
    assert row[1] < after_water
    assert row[2] == 1
    assert compost_after == compost_before - 1

    twice = await game.plot_ops(kid, "施肥 1 堆肥")
    assert "已经施过" in twice, twice

    plot = {
        "crop": "kale", "tended": 0, "planted_at": planted,
        "grow_target": row[1], "fertilized": 1, "watered": 1, "greenhouse": 0,
    }
    extra = farming.parcel_extra(plot)
    assert "水" in extra and "肥" in extra, extra


def main() -> None:
    test_grow_cut_math()
    asyncio.run(test_water_and_fertilize())
    print("water/fertilize tests ok")


if __name__ == "__main__":
    main()
