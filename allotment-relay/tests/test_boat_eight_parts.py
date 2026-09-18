#!/usr/bin/env python3
"""§59 第二批 #19：船八部件（+鱼舱/冰舱）。"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_eight_parts_and_cargo_ice():
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
                assert len(boat_parts.PARTS) == 12

        parts_full = {k: (100, 100) for k in boat_parts.PARTS}
        assert boat_parts.effective_cargo(4, parts_full) == 4
        low_hold = dict(parts_full)
        low_hold["hold"] = (20, 100)
        assert boat_parts.effective_cargo(4, low_hold) == 2
        assert boat_parts.fish_state_for_ice(low_hold, "fresh") == "fresh"
        low_ice = dict(parts_full)
        low_ice["ice"] = (20, 100)
        assert boat_parts.fish_state_for_ice(low_ice, "fresh") == "bruised"
        low_winch = dict(parts_full)
        low_winch["net_winch"] = (10, 100)
        assert boat_parts.net_winch_empty_delta(low_winch) == 0.07
        neutral = dict(parts_full)
        neutral["bell"] = (70, 100)
        base = boat_parts.fail_bonus(neutral)
        low_bell = dict(neutral)
        low_bell["bell"] = (10, 100)
        assert boat_parts.fail_bonus(low_bell) >= base + 0.03
        high_bell = dict(neutral)
        high_bell["bell"] = (90, 100)
        assert boat_parts.fail_bonus(high_bell) <= base - 0.02
        parts_full = {k: (100, 100) for k in boat_parts.PARTS}
        assert boat_parts.parley_bonus(parts_full) == 0.08
        low_comp = dict(parts_full)
        low_comp["compass"] = (10, 100)
        assert boat_parts.parley_bonus(low_comp) < 0

    asyncio.run(run())


def test_light_bad_flags():
    async def run():
        from server import db, light_bad_events as lb

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("u2@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "农人", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    await lb.set_flag(conn, s["id"], "line_tangle")
                    assert await lb.has_flag(conn, s["id"], "line_tangle")
                    bonus = await lb.cast_empty_bonus(conn, s["id"])
                    assert bonus == 0.12
                    assert not await lb.has_flag(conn, s["id"], "line_tangle")
                    await lb.set_flag(conn, s["id"], "net_weed")
                    assert await lb.net_empty_bonus(conn, s["id"]) == 0.10
                    await lb.set_flag(conn, s["id"], "humid_soft")
                    assert await lb.sleep_energy_penalty(conn, s["id"]) == 3
                    assert not await lb.has_flag(conn, s["id"], "humid_soft")
                    await conn.commit()

    asyncio.run(run())
