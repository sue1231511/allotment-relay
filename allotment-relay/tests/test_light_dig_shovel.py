#!/usr/bin/env python3
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_shovel_dull_flag():
    async def run():
        from server import db, light_bad_events as lb

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("dig@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "赶海", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    await lb.set_flag(conn, s["id"], "shovel_dull")
                    assert await lb.dig_energy_penalty(conn, s["id"]) == 2
                    assert await lb.dig_energy_penalty(conn, s["id"]) == 0
                    await conn.commit()

    asyncio.run(run())
