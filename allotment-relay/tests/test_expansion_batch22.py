"""Batch 22: vet stall fumes, shaonian omen gust, atelier thread snag."""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_vet_stall_fumes_resolve():
    async def run():
        from server import db, vet_stall_fumes as fumes

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
                        "UPDATE stewards SET vet_hazard='fumes', energy=10 WHERE id=?",
                        (s["id"],),
                    )
                    msg = await fumes.resolve(conn, s, "通风")
                    await conn.commit()
                assert "风" in msg or "窗" in msg

    asyncio.run(run())


def test_shaonian_omen_gust_resolve():
    async def run():
        from server import db, shaonian_omen_gust as gust

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("u@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "卜客", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    await conn.execute(
                        "UPDATE stewards SET shaonian_hazard='gust', energy=10 WHERE id=?",
                        (s["id"],),
                    )
                    msg = await gust.resolve(conn, s, "问潮")
                    await conn.commit()
                assert "潮" in msg or "卦" in msg

    asyncio.run(run())


def test_cloth_thread_snag_resolve():
    async def run():
        from server import cloth_thread_snag as snag
        from server import db

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("u@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "裁缝", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    await conn.execute(
                        "UPDATE stewards SET atelier_hazard='snag', energy=12 WHERE id=?",
                        (s["id"],),
                    )
                    msg = await snag.resolve(conn, s, "润梭")
                    await conn.commit()
                assert "梭" in msg or "油" in msg

    asyncio.run(run())
