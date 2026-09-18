"""Batches 13–16: market gust, bar sink, eatery smoke, barn rescue, hull breach."""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_market_gust_resolve():
    async def run():
        from server import db, market_stall_gust as gust

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("u@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "摊主", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    await conn.execute(
                        "UPDATE stewards SET market_hazard='gust' WHERE id=?",
                        (s["id"],),
                    )
                    await db.add_item(conn, s["id"], "quarry_brick", 1)
                    msg = await gust.resolve(conn, s, "压石")
                    await conn.commit()
                assert "压" in msg or "石" in msg

    asyncio.run(run())


def test_bar_flood_resolve():
    async def run():
        from server import db, bar_sink_flood as flood

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("u@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "洗碗", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    await conn.execute(
                        "UPDATE stewards SET bar_hazard='flood', tickets=20 WHERE id=?",
                        (s["id"],),
                    )
                    msg = await flood.resolve(conn, s, "疏通")
                    await conn.commit()
                assert "通" in msg or "票" in msg

    asyncio.run(run())


def test_barn_rescue_lure():
    async def run():
        from server import barn_runaway_rescue as rescue
        from server import db

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("u@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "牧人", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    await conn.execute(
                        "UPDATE stewards SET barn_built=1 WHERE id=?",
                        (s["id"],),
                    )
                    await conn.execute(
                        """
                        INSERT INTO barn_animals (
                            steward_id, slot, species, fed, escaped_at
                        ) VALUES (?,1,'chicken',1,?)
                        """,
                        (s["id"], db.now()),
                    )
                    await db.add_item(conn, s["id"], "crop_rye", 2)
                    msg = await rescue.resolve(conn, s, 1, "诱回")
                    await conn.commit()
                assert "回栏" in msg

    asyncio.run(run())


def test_hull_breach_resolve():
    async def run():
        from server import db, voyage_hull_breach as breach

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("u@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "水手", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                now = db.now()
                async with db.connect() as conn:
                    await conn.execute(
                        """
                        INSERT INTO voyages (steward_id, route, departed_at, returns_at, status, encounter)
                        VALUES (?, 'near', ?, ?, 'hull_breach', ?)
                        """,
                        (s["id"], now, now + 600, json.dumps({"type": "hull_breach"})),
                    )
                    cur = await conn.execute("SELECT id FROM voyages WHERE steward_id=?", (s["id"],))
                    vid = (await cur.fetchone())[0]
                    voyage = {"id": vid, "status": "hull_breach", "encounter": "{}"}
                    await conn.execute("UPDATE stewards SET tickets=50 WHERE id=?", (s["id"],))
                    msg = await breach.resolve(conn, s, voyage, "泵")
                    await conn.commit()
                assert "航" in msg or "泵" in msg

    asyncio.run(run())
