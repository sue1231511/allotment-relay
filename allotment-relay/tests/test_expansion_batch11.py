"""Batch 11: undertide well crack hazard."""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_crack_ui():
    from server import undertide_well_crack as crack

    acts = crack.ui_actions(tickets=5, stock={})
    assert any(a["action"] == "清井" and not a["can"] for a in acts)


def test_crack_blocks_and_resolves():
    async def run():
        from server import db, undertide_well_crack as crack

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("u@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "井下人", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    await conn.execute(
                        "INSERT OR IGNORE INTO steward_undertide (steward_id, shadow_rep, access, well_hint, created_at) VALUES (?,10,0,1,?)",
                        (s["id"], db.now()),
                    )
                    await conn.execute(
                        "UPDATE steward_undertide SET well_hazard='crack', well_corrosion=72 WHERE steward_id=?",
                        (s["id"],),
                    )
                    await conn.commit()
                try:
                    async with db.connect() as conn:
                        await crack.assert_not_blocked(conn, s["id"])
                except ValueError as exc:
                    assert "井裂" in str(exc) or "井险" in str(exc)
                else:
                    raise AssertionError("expected block")
                async with db.connect() as conn:
                    await db.add_item(conn, s["id"], "drift_twine", 1)
                    msg = await crack.resolve(conn, s, "绑索")
                    await conn.commit()
                assert "绑" in msg or "绳" in msg

    asyncio.run(run())
