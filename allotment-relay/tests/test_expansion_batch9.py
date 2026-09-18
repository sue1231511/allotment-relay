"""Batch 9: quarry collapse hazard + island quarry act."""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_collapse_ui_actions():
    from server import quarry_collapse

    acts = quarry_collapse.ui_actions(tickets=5, stock={"craft_timber": 0})
    assert any(a["action"] == "撑柱" and not a["can"] for a in acts)
    acts2 = quarry_collapse.ui_actions(tickets=20, stock={"craft_timber": 3})
    assert any(a["action"] == "撑柱" and a["can"] for a in acts2)


def test_collapse_resolve_pull():
    async def run():
        from server import db, quarry_collapse

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("q@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "矿工", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    from server import quarry

                    await quarry.ensure_profile(conn, s["id"])
                    await conn.execute(
                        """
                        UPDATE quarry_claims SET vein='shale', strikes_left=3,
                        hazard='collapse', hazard_json=?
                        WHERE steward_id=? AND slot=1
                        """,
                        (json.dumps({"slot": 1}), s["id"]),
                    )
                    msg = await quarry_collapse.resolve(conn, s, 1, "撤人")
                    await conn.commit()
                    cur = await conn.execute(
                        "SELECT hazard, strikes_left, vein FROM quarry_claims WHERE steward_id=? AND slot=1",
                        (s["id"],),
                    )
                    h, left, vein = await cur.fetchone()
                assert "撤" in msg
                assert not h
                assert left == 0
                assert vein == ""

    asyncio.run(run())


def test_quarry_hew_blocked_when_hazard():
    async def run():
        from server import db, quarry

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("q2@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "矿工二", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    await quarry.ensure_profile(conn, s["id"])
                    await conn.execute(
                        "UPDATE steward_quarry SET pick_tier=1 WHERE steward_id=?",
                        (s["id"],),
                    )
                    await conn.execute(
                        "UPDATE stewards SET last_bar_shift_at=?, last_active_at=?, energy=80 WHERE id=?",
                        (db.now(), db.now(), s["id"]),
                    )
                    await conn.execute(
                        """
                        UPDATE quarry_claims SET vein='shale', strikes_left=2, hazard='collapse'
                        WHERE steward_id=? AND slot=1
                        """,
                        (s["id"],),
                    )
                    await conn.commit()
                try:
                    await quarry.quarry_ops(row["id"], "挖 1")
                except ValueError as exc:
                    assert "塌方" in str(exc)
                else:
                    raise AssertionError("expected ValueError")

    asyncio.run(run())
