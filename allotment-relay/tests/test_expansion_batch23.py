"""Batch 23: theater curtain jam, script jam."""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_theater_curtain_resolve():
    async def run():
        from server import db, theater_curtain_jam as curtain

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("u@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "演员", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    await conn.execute(
                        "UPDATE stewards SET theater_hazard='curtain', energy=10 WHERE id=?",
                        (s["id"],),
                    )
                    msg = await curtain.resolve(conn, s, "扶幕")
                    await conn.commit()
                assert "幕" in msg

    asyncio.run(run())


def test_theater_script_jam_resolve():
    async def run():
        from server import db, theater_script_jam as script

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("u@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "编剧", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    await conn.execute(
                        "UPDATE stewards SET theater_hazard='script', energy=10 WHERE id=?",
                        (s["id"],),
                    )
                    msg = await script.resolve(conn, s, "压镇")
                    await conn.commit()
                assert "镇" in msg or "槽" in msg

    asyncio.run(run())
