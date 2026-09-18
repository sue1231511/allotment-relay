"""Batch 21: marriage desk jam, clinic queue, florist pollen."""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_marriage_desk_jam():
    async def run():
        from server import db, marriage_desk_jam as jam

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("u@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "理枝", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    await conn.execute(
                        "UPDATE stewards SET marriage_hazard='jam', tickets=20 WHERE id=?",
                        (s["id"],),
                    )
                    msg = await jam.resolve(conn, s, "补章")
                    await conn.commit()
                assert "票" in msg or "章" in msg

    asyncio.run(run())


def test_clinic_queue_jam():
    async def run():
        from server import clinic_queue_jam as jam
        from server import db

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("u@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "病人", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    await conn.execute(
                        "UPDATE stewards SET clinic_hazard='jam' WHERE id=?",
                        (s["id"],),
                    )
                    await conn.execute("UPDATE stewards SET energy=10 WHERE id=?", (s["id"],))
                    msg = await jam.resolve(conn, s, "候诊")
                    await conn.commit()
                assert "排" in msg or "窗" in msg

    asyncio.run(run())


def test_florist_pollen_resolve():
    async def run():
        from server import db, florist_pollen_sniff as sniff

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("u@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "花客", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    await conn.execute(
                        "UPDATE stewards SET florist_hazard='sniff' WHERE id=?",
                        (s["id"],),
                    )
                    await conn.execute("UPDATE stewards SET energy=10 WHERE id=?", (s["id"],))
                    msg = await sniff.resolve(conn, s, "开窗")
                    await conn.commit()
                assert "窗" in msg or "风" in msg

    asyncio.run(run())
