"""Batch 12: workshop anvil quench hazard."""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_quench_ui():
    from server import workshop_anvil_quench as quench

    acts = quench.ui_actions(tickets=3, stock={}, energy_now=20)
    assert any(a["action"] == "泼水" and not a["can"] for a in acts)


def test_quench_blocks_take_and_resolves():
    async def run():
        from server import db, workshop_anvil_quench as quench

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("u@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "匠人", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                now = db.now()
                async with db.connect() as conn:
                    await conn.execute(
                        """
                        INSERT INTO steward_craft (
                            steward_id, job_key, job_ready_at, job_qty, pan_count,
                            last_salvage_at, salvages_total, crafts_total, net_patch_until,
                            anvil_hazard
                        ) VALUES (?, 'copper_nails', ?, 3, 1, 0, 0, 0, 0, 'quench')
                        """,
                        (s["id"], now - 10),
                    )
                    await conn.commit()
                try:
                    async with db.connect() as conn:
                        await quench.assert_not_blocked(conn, s["id"])
                except ValueError as exc:
                    assert "烫" in str(exc) or "淬火" in str(exc)
                else:
                    raise AssertionError("expected block")
                async with db.connect() as conn:
                    await db.add_item(conn, s["id"], "quarry_salt", 1)
                    msg = await quench.resolve(conn, s, "泼水")
                    await conn.commit()
                assert "烟" in msg or "取" in msg

    asyncio.run(run())
