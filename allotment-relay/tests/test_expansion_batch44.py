"""batch44：灾档持久化、收集称呼、港口改装 UI、卤浸钉炼制。"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_tier_store_open_resolve():
    async def run():
        from server import bad_event_tier_store as ts, db

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("t@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "档手", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    await ts.open_event(
                        conn, s["id"], "quarry", "heavy", "坑1塌方", ref_key="1",
                    )
                    rows = await ts.list_open(conn, s["id"])
                    assert len(rows) == 1
                    await ts.resolve(conn, s["id"], "quarry", ref_key="1")
                    assert len(await ts.list_open(conn, s["id"])) == 0
                    await conn.commit()

    asyncio.run(run())


def test_collection_achievement_scan():
    async def run():
        from server import db, island_collections as coll, progress

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("c@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "藏家", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    await coll.ensure_table(conn)
                    now = db.now()
                    for i in range(25):
                        await conn.execute(
                            """
                            INSERT OR IGNORE INTO steward_collection_unlock
                            (steward_id, coll_key, unlocked_at) VALUES (?,?,?)
                            """,
                            (s["id"], f"k{i}", now),
                        )
                    gained = await progress.scan_achievements(conn, s)
                    await conn.commit()
                assert gained >= 1

    asyncio.run(run())


def test_refine_brine_nails_recipe():
    from server.undertide_refine import RECIPES

    assert "brine_nails" in RECIPES
