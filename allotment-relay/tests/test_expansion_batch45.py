"""batch45：份地/赶海 debuff 灾档、全典称呼、新灶谱与炼制。"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_debuff_tier_resolves_on_take_flag():
    async def run():
        from server import bad_event_tier_store as ts, db, light_bad_events as lb

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("d@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "Debuff", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    from server import bad_event_tiers as tiers_mod

                    await lb.set_debuff(
                        conn,
                        s["id"],
                        "shovel_dull",
                        tiers_mod.TIER_LIGHT,
                        "铲钝",
                    )
                    assert len(await ts.list_open(conn, s["id"])) == 1
                    assert await lb.take_flag(conn, s["id"], "shovel_dull")
                    assert len(await ts.list_open(conn, s["id"])) == 0
                    await conn.commit()

    asyncio.run(run())


def test_collection_legend_achievement():
    async def run():
        from server import db, island_collections as coll, progress

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("l@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "Legend", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    await coll.ensure_table(conn)
                    now = db.now()
                    for entry in coll.ENTRIES:
                        await conn.execute(
                            """
                            INSERT OR IGNORE INTO steward_collection_unlock
                            (steward_id, coll_key, unlocked_at) VALUES (?,?,?)
                            """,
                            (s["id"], entry[0], now),
                        )
                    await progress.scan_achievements(conn, s)
                    cur = await conn.execute(
                        "SELECT ach_key FROM steward_achievements WHERE steward_id=?",
                        (s["id"],),
                    )
                    keys = {r[0] for r in await cur.fetchall()}
                    await conn.commit()
                assert "collection_legend" in keys

    asyncio.run(run())


def test_tide_black_salt_recipe():
    from server.undertide_refine import RECIPES

    assert "tide_black_salt" in RECIPES
