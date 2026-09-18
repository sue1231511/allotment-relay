"""batch40：坏事件扩面、潮下炼制、收集持久化、名册协作按钮数据。"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_undertide_refine_brine():
    async def run():
        from server import db, undertide_refine as ref

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("r@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "炼师", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    await db.add_item(conn, s["id"], "ut_pit_silt", 2)
                    await db.add_item(conn, s["id"], "quarry_salt", 1)
                    await conn.execute("UPDATE stewards SET energy=50 WHERE id=?", (s["id"],))
                    msg = await ref.refine(conn, s, "brine_crystal")
                    await conn.commit()
                assert "焖晶" in msg or "盐泥晶" in msg

    asyncio.run(run())


def test_collection_persists_after_item_gone():
    async def run():
        from server import db, island_collections as coll

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("x@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "Keeper", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    await db.add_item(conn, s["id"], "fish_herring", 1)
                    await coll.sync_unlocks(conn, s["id"])
                    await db.take_item(conn, s["id"], "fish_herring", 1)
                    text = await coll.sheet(conn, s["id"])
                    await conn.commit()
                assert "herring" in text or "鲱" in text
                assert "✓" in text

    asyncio.run(run())


def test_neighbor_roster_rapport():
    async def run():
        from server import db, multi

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                k1 = await db.create_api_key("a@example.com")
                k2 = await db.create_api_key("b@example.com")
                r1 = await db.get_key_row(k1)
                r2 = await db.get_key_row(k2)
                await db.enroll_steward(r1["id"], "Alpha", "", "naturalist", "")
                await db.enroll_steward(r2["id"], "Beta", "", "naturalist", "")
                sa = await db.get_steward_by_key_id(r1["id"])
                sb = await db.get_steward_by_key_id(r2["id"])
                async with db.connect() as conn:
                    for _ in range(14):
                        await multi._bump_rapport(conn, sa["id"], sb["id"], 3)
                    await conn.commit()
                roster = await multi.neighbor_roster(sa, online_only=False)
                peer = next(p for p in roster["people"] if p["name"] == "Beta")
                assert peer["rapport"] == 42

    asyncio.run(run())
