"""batch42：维修总览、黑旗档位、六类船、共耕×周目标、收集簿扩项。"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_repair_digest_empty():
    async def run():
        from server import db, repair_digest as rep

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("r@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "修手", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    msg = await rep.digest(conn, s["id"])
                assert "暂无" in msg or "待办" in msg

    asyncio.run(run())


def test_repair_digest_boat_damaged():
    async def run():
        from server import db, repair_digest as rep

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("d@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "船损", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    await conn.execute(
                        "UPDATE stewards SET boat_damaged=1, boat_key='skiff' WHERE id=?",
                        (s["id"],),
                    )
                    msg = await rep.digest(conn, s["id"])
                assert "船体损坏" in msg

    asyncio.run(run())


def test_six_boats_config():
    from server.config import BOATS

    assert len(BOATS) == 6
    assert "watch_hoy" in BOATS and "longliner" in BOATS


def test_hail_repair_hint():
    from server import bad_event_tiers as tiers

    hint = tiers.repair_hint("hail", tier=tiers.TIER_HEAVY)
    assert "steward_ops 维修" in hint or "tide_ops" in hint


def test_collections_sync_no_sql_error():
    async def run():
        from server import db, island_collections as coll

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("c@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "藏家", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    n = await coll.sync_unlocks(conn, s["id"])
                    text = await coll.sheet(conn, s["id"])
                    await conn.commit()
                assert n >= 0
                assert f"/{len(coll.ENTRIES)}" in text

    asyncio.run(run())


def test_cofarm_league_extra_when_assist_goal():
    async def run():
        from server import db, multi, neighbor_cofarm as cf

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
                    for _ in range(16):
                        await multi._bump_rapport(conn, sa["id"], sb["id"], 3)
                    await cf.subscribe(conn, sa, "Beta")
                    row = await multi._ensure_league_week(conn)
                    await conn.execute(
                        "UPDATE league_week SET goal_key='assist', progress=0, completed=0 WHERE week_id=?",
                        (row["week_id"],),
                    )
                    bonus = await cf.league_extra_after_assist(conn, sa["id"], sb["id"])
                    await conn.commit()
                assert bonus and "assist" in bonus

    asyncio.run(run())
