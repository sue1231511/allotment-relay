#!/usr/bin/env python3
"""橘子树：解析、月令、只进果园、可摇。"""
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


def test_resolve_and_catalog() -> None:
    from server.catalog import CROPS, ITEM_NAMES, ITEM_PRICES, resolve_crop_key, crop_catalog_line
    from server import season

    assert resolve_crop_key("orange") == "orange"
    assert resolve_crop_key("橘子") == "orange"
    assert resolve_crop_key("橙子") == "orange"
    assert resolve_crop_key("柑橘") == "orange"
    assert resolve_crop_key("桔子") == "orange"
    assert resolve_crop_key("橘子种") == "orange"
    assert resolve_crop_key("seed_orange") == "orange"

    meta = CROPS["orange"]
    assert meta["tree"] and meta["shake"]
    assert meta["name"] == "橘子"
    assert ITEM_NAMES["crop_orange"] == "橘子"
    assert ITEM_NAMES["seed_orange"] == "橘子种"
    assert ITEM_PRICES["seed_orange"] == 16
    assert ITEM_PRICES["crop_orange"] == 30

    with season.pinned_month(12):
        line = crop_catalog_line("orange")
        assert "橘子" in line and "果园专种" in line and "可摇" in line
        assert "当月可种" in line
    with season.pinned_month(8):
        line = crop_catalog_line("orange")
        assert "休市" in line


async def test_sow_routes_and_month() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="orange-sow-"))
    db = await _boot(tmp)
    from server import game, season

    kid, sid = await _enroll(db, "orange@example.com", "橘人")
    async with db.connect() as conn:
        await db.add_item(conn, sid, "seed_orange", 3)
        await conn.execute("UPDATE stewards SET tickets=tickets+400, greenhouse=1 WHERE id=?", (sid,))
        await conn.execute(
            "INSERT INTO parcels (steward_id, slot, orchard, greenhouse, tended) VALUES (?, 1, 0, 1, 0)",
            (sid,),
        )
        await conn.execute("UPDATE stewards SET greenhouse_count=1 WHERE id=?", (sid,))
        await conn.commit()

    with season.pinned_month(8):
        blocked = await game.plot_ops(kid, "sow 园1 橘子")
        assert "不在当月" in blocked or "休市" in blocked or "⚠" in blocked, blocked

    with season.pinned_month(12):
        gh = await game.plot_ops(kid, "sow 99 橘子")
        assert "温室不种果树" in gh or "⚠" in gh, gh

        planted = await game.plot_ops(kid, "sow 1 橘子")
        assert "园1" in planted and "橘子" in planted, planted
        async with db.connect() as conn:
            orchard_row = await (await conn.execute(
                "SELECT crop FROM parcels WHERE steward_id=? AND slot=1 AND COALESCE(orchard,0)=1",
                (sid,),
            )).fetchone()
            plot_row = await (await conn.execute(
                "SELECT crop FROM parcels WHERE steward_id=? AND slot=1 AND COALESCE(orchard,0)=0",
                (sid,),
            )).fetchone()
        assert orchard_row[0] == "orange"
        assert plot_row[0] is None


async def test_shake_orange() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="orange-shake-"))
    db = await _boot(tmp)
    from server import game

    kid, sid = await _enroll(db, "orangeshake@example.com", "摇橘")
    async with db.connect() as conn:
        await conn.execute(
            """
            UPDATE parcels SET crop='orange', planted_at=?, tended=1, greenhouse=0,
            grow_target=60, grow_pace=1, harvest_left=0, tree_harvests=0, tree_harvest_max=6
            WHERE steward_id=? AND slot=1 AND COALESCE(orchard,0)=1
            """,
            (db.now() - 10_000, sid),
        )
        await conn.commit()

    shaken = await game.plot_ops(kid, "shake 园1")
    assert "橘子" in shaken and "⚠" not in shaken, shaken
    async with db.connect() as conn:
        qty = (await (await conn.execute(
            "SELECT quantity FROM inventory WHERE steward_id=? AND item='crop_orange'",
            (sid,),
        )).fetchone())
    assert qty is not None and qty[0] >= 1


def main() -> None:
    test_resolve_and_catalog()
    asyncio.run(test_sow_routes_and_month())
    asyncio.run(test_shake_orange())
    print("orange tests ok")


if __name__ == "__main__":
    main()
