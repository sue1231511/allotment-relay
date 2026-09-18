"""Boat part wear and fail bonus (八部件)."""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_six_parts_initialized():
    async def run():
        from server import boat_parts, db

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("u@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "船长", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    parts = await boat_parts.get_all(conn, s["id"])
                    await conn.commit()
                assert set(parts.keys()) == set(boat_parts.PARTS)
                assert all(parts[k] == (100, 100) for k in boat_parts.PARTS)

    asyncio.run(run())


def test_fail_bonus_six_parts():
    from server import boat_parts

    parts = {k: (100, 100) for k in boat_parts.PARTS}
    parts["anchor"] = (20, 100)
    parts["bilge"] = (20, 100)
    extra = boat_parts.fail_bonus(parts)
    assert extra >= 0.08
