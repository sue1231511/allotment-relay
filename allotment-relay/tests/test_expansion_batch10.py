"""Batch 10: workshop salvage snag."""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_snag_ui_energy_gate():
    from server import workshop_salvage_snag as snag

    low = snag.ui_actions(tickets=100, stock={}, energy=5)
    assert any(a["action"] == "硬拽" and not a["can"] for a in low)


def test_snag_resolve_cut():
    async def run():
        from server import db, workshop_salvage_snag as snag

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("w@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "匠人", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    from server import craft

                    await craft.ensure_profile(conn, s["id"])
                    await conn.execute(
                        """
                        UPDATE steward_craft SET salvage_hazard='snag'
                        WHERE steward_id=?
                        """,
                        (s["id"],),
                    )
                    await db.add_item(conn, s["id"], "drift_twine", 2)
                    msg = await snag.resolve(conn, s, "割绳")
                    await conn.commit()
                    cur = await conn.execute(
                        "SELECT salvage_hazard FROM steward_craft WHERE steward_id=?",
                        (s["id"],),
                    )
                    h = (await cur.fetchone())[0]
                assert "脚" in msg or "割" in msg
                assert not h

    asyncio.run(run())
