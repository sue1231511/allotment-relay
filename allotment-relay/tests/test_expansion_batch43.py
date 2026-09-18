"""batch43：借船临期提醒。"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_loan_reminder_within_24h():
    async def run():
        from server import db, neighbor_links as nl

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                k1 = await db.create_api_key("l@example.com")
                k2 = await db.create_api_key("b@example.com")
                r1 = await db.get_key_row(k1)
                r2 = await db.get_key_row(k2)
                await db.enroll_steward(r1["id"], "船主", "", "naturalist", "")
                await db.enroll_steward(r2["id"], "借家", "", "naturalist", "")
                sl = await db.get_steward_by_key_id(r1["id"])
                sb = await db.get_steward_by_key_id(r2["id"])
                async with db.connect() as conn:
                    await conn.execute(
                        "UPDATE stewards SET boat_key='skiff' WHERE id=?",
                        (sl["id"],),
                    )
                    until = db.now() + 3600
                    await nl.ensure_tables(conn)
                    await conn.execute(
                        """
                        INSERT INTO neighbor_boat_loan
                        (borrower_id, lender_id, boat_key, until_ts, created_at)
                        VALUES (?,?,?,?,?)
                        """,
                        (sb["id"], sl["id"], "skiff", until, db.now()),
                    )
                    notes = await nl.loan_reminder_notices(conn, sb["id"], ping=False)
                    await conn.commit()
                assert any("借船提醒" in n for n in notes)

    asyncio.run(run())
