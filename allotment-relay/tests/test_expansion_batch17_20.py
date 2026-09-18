"""Batches 17–20: lighthouse gale, hui rush, lili tilt, ting loose."""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_beacon_gust_resolve():
    async def run():
        from server import buxing_beacon_gust as gust
        from server import db

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("u@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "守灯", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    await conn.execute(
                        "INSERT INTO steward_buxing (steward_id, updated_at, beacon_hazard) VALUES (?, ?, ?)",
                        (s["id"], db.now(), "gale"),
                    )
                    await db.add_item(conn, s["id"], "quarry_brick", 1)
                    msg = await gust.resolve(conn, s, "压窗")
                    await conn.commit()
                assert "稳" in msg or "窗" in msg

    asyncio.run(run())


def test_hui_rush_resolve():
    async def run():
        from server import db, hui_clerk_rush as rush

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("u@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "交税", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    await conn.execute(
                        "UPDATE stewards SET hui_hazard='rush', tickets=20 WHERE id=?",
                        (s["id"],),
                    )
                    msg = await rush.resolve(conn, s, "补票")
                    await conn.commit()
                assert "票" in msg

    asyncio.run(run())


def test_lili_tilt_resolve():
    async def run():
        from server import db, lili_cart_tilt as tilt

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("u@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "栗栗", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    await conn.execute(
                        "UPDATE stewards SET lili_hazard='tilt' WHERE id=?",
                        (s["id"],),
                    )
                    await db.add_item(conn, s["id"], "crop_rye", 1)
                    msg = await tilt.resolve(conn, s, "压货")
                    await conn.commit()
                assert "稳" in msg or "麦" in msg or "黑" in msg

    asyncio.run(run())


def test_wall_loose_resolve():
    async def run():
        from server import db, wall_plank_loose as loose

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("u@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "钉牌", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    await conn.execute(
                        "UPDATE stewards SET wall_hazard='loose', tickets=12 WHERE id=?",
                        (s["id"],),
                    )
                    msg = await loose.resolve(conn, s, "加固")
                    await conn.commit()
                assert "稳" in msg or "钉" in msg or "票" in msg

    asyncio.run(run())
