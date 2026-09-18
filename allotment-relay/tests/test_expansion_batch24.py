"""Batch 24: musong fog, jingshan crate, star mic."""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_musong_fog_resolve():
    async def run():
        from server import db, musong_sendoff_fog as fog

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("u@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "旅人", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    await conn.execute(
                        "UPDATE stewards SET musong_hazard='fog', energy=10 WHERE id=?",
                        (s["id"],),
                    )
                    msg = await fog.resolve(conn, s, "候潮")
                    await conn.commit()
                assert "潮" in msg or "册" in msg

    asyncio.run(run())


def test_jingshan_crate_resolve():
    async def run():
        from server import db, jingshan_crate_loose as crate

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("u@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "送货", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    await conn.execute(
                        "UPDATE stewards SET jingshan_hazard='crate' WHERE id=?",
                        (s["id"],),
                    )
                    await conn.execute("UPDATE stewards SET tickets=20 WHERE id=?", (s["id"],))
                    msg = await crate.resolve(conn, s, "捆扎")
                    await conn.commit()
                assert "箱" in msg or "绳" in msg or "票" in msg

    asyncio.run(run())


def test_star_mic_resolve():
    async def run():
        from server import db, star_mic_feedback as mic

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("u@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "粉丝", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    await conn.execute(
                        "UPDATE stewards SET star_hazard='mic', energy=12 WHERE id=?",
                        (s["id"],),
                    )
                    msg = await mic.resolve(conn, s, "润麦")
                    await conn.commit()
                assert "麦" in msg

    asyncio.run(run())
