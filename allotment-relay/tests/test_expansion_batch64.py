#!/usr/bin/env python3
"""batch64：§五 坏事带来机会 — 鸟啄种、切线旧钩、搏鱼切线。"""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def test_bird_peck_luck_grants_seed():
    async def run():
        import os
        import sys

        sys.path.insert(0, str(ROOT))
        os.environ["DATA_DIR"] = str(Path(tempfile.mkdtemp()))
        tmp = Path(os.environ["DATA_DIR"])
        from server import config, db

        config.DATA_DIR = tmp
        config.DB_PATH = tmp / "relay.db"
        db.DATA_DIR = tmp
        db.DB_PATH = tmp / "relay.db"
        await db.init_db()
        from server import event_opportunity as opp_mod
        from server import light_bad_events as light_mod

        key = await db.create_api_key("bird@example.com")
        row = await db.get_key_row(key)
        await db.enroll_steward(row["id"], "Peck", "", "naturalist", "")
        s = await db.get_steward_by_key_id(row["id"])
        async with db.connect() as conn:
            await conn.execute(
                """
                UPDATE parcels SET crop='kale', harvest_left=3, tended=1, grow_target=60
                WHERE steward_id=? AND slot=1 AND orchard=0 AND greenhouse=0
                """,
                (s["id"],),
            )
            await conn.commit()
        rolls = iter([0.05, 0.01, 0.01, 0.01])
        with patch("server.light_bad_events.random.random", lambda: next(rolls)), patch(
            "server.event_opportunity.random.random", lambda: 0.01,
        ):
            async with db.connect() as conn:
                cur = await conn.execute(
                    "SELECT id, crop, harvest_left FROM parcels WHERE steward_id=?", (s["id"],),
                )
                plot = dict(zip(("id", "crop", "harvest_left"), (await cur.fetchone())))
                plot["harvest_left"] = int(plot["harvest_left"])
                msg = await light_mod.roll_tend_glitch(conn, s["id"], plot)
                await conn.commit()
        assert msg and "斑鸠" in msg
        assert "羽衣甘蓝种" in msg or "种" in msg
        stock = await db.get_satchel(s["id"])
        assert stock.get("seed_kale", 0) >= 1, stock

    asyncio.run(run())


def test_unsnag_cut_hook_refind_then_cast():
    async def run():
        import os
        import sys

        sys.path.insert(0, str(ROOT))
        os.environ["DATA_DIR"] = str(Path(tempfile.mkdtemp()))
        tmp = Path(os.environ["DATA_DIR"])
        from server import config, db

        config.DATA_DIR = tmp
        config.DB_PATH = tmp / "relay.db"
        db.DATA_DIR = tmp
        db.DB_PATH = tmp / "relay.db"
        await db.init_db()
        from server import event_opportunity as opp_mod
        from server import fishing_parts as parts_mod

        key = await db.create_api_key("fish@example.com")
        row = await db.get_key_row(key)
        await db.enroll_steward(row["id"], "Line", "", "naturalist", "")
        s = await db.get_steward_by_key_id(row["id"])
        async with db.connect() as conn:
            await parts_mod.ensure_table(conn)
            await conn.execute(
                """
                INSERT INTO steward_fish_parts (steward_id, part_key, durability, max_dur, snagged)
                VALUES (?, 'hook', 10, 70, 1)
                """,
                (s["id"],),
            )
            await conn.commit()
        with patch("server.event_opportunity.random.random", lambda: 0.01):
            async with db.connect() as conn:
                msg = await parts_mod.clear_snag(conn, s["id"], "切线")
                await conn.commit()
        assert "旧钩" in msg
        async with db.connect() as conn:
            got = await opp_mod.maybe_consume_hook_refind(conn, s["id"])
            await conn.commit()
        assert got and "旧钩" in got
        async with db.connect() as conn:
            cur = await conn.execute(
                "SELECT durability FROM steward_fish_parts WHERE steward_id=? AND part_key='hook'",
                (s["id"],),
            )
            dur = int((await cur.fetchone())[0])
        assert dur >= 22

    asyncio.run(run())


def test_fight_cut_sea_glass_branch():
    async def run():
        import os
        import sys

        sys.path.insert(0, str(ROOT))
        os.environ["DATA_DIR"] = str(Path(tempfile.mkdtemp()))
        tmp = Path(os.environ["DATA_DIR"])
        from server import config, db

        config.DATA_DIR = tmp
        config.DB_PATH = tmp / "relay.db"
        db.DATA_DIR = tmp
        db.DB_PATH = tmp / "relay.db"
        await db.init_db()
        from server import big_fish_fight as fight_mod

        key = await db.create_api_key("big@example.com")
        row = await db.get_key_row(key)
        await db.enroll_steward(row["id"], "Fight", "", "naturalist", "")
        s = await db.get_steward_by_key_id(row["id"])
        from server import fishing_parts as parts_mod

        async with db.connect() as conn:
            await fight_mod.ensure_table(conn)
            await parts_mod.ensure_table(conn)
            await conn.execute(
                """
                INSERT INTO steward_fish_fight (steward_id, species, weight_kg, state, payload_json, created_at)
                VALUES (?, 'tuna', 12.0, 'fresh', ?, 1)
                """,
                (s["id"], json.dumps({"rod_tier": 2})),
            )
            await conn.commit()
        rolls = iter([0.01, 0.99])
        with patch("server.event_opportunity.random.random", lambda: next(rolls)):
            async with db.connect() as conn:
                msg = await fight_mod.resolve(conn, dict(s), "切线")
                await conn.commit()
        assert "海玻璃" in msg
        stock = await db.get_satchel(s["id"])
        assert stock.get("sea_glass", 0) >= 2, stock

    asyncio.run(run())
