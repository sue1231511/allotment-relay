#!/usr/bin/env python3
"""第六批：牲畜性格、惊逃寻回、厨电耐久。"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_temper_roll_and_yield():
    from server import barn_temper

    t = barn_temper.roll_for_species("chicken")
    assert t in barn_temper.TEMPERS
    animal = {"temper": "greedy"}
    assert barn_temper.adjust_yield(animal, 10) >= 11


async def _test_escape_recover():
    from server import barn, barn_escape, config, db

    with tempfile.TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        os.environ["DATA_DIR"] = str(tmp_p)
        config.DATA_DIR = tmp_p
        config.DB_PATH = tmp_p / "relay.db"
        db.DATA_DIR = tmp_p
        db.DB_PATH = tmp_p / "relay.db"
        await db.init_db()
        key = await db.create_api_key("b6@test.local")
        row = await db.get_key_row(key)
        await db.enroll_steward(row["id"], "B6", "", "naturalist", "")
        async with db.connect() as conn:
            sid = (await (await conn.execute(
                "SELECT id FROM stewards WHERE key_id=?", (row["id"],)
            )).fetchone())[0]
            await conn.execute("UPDATE stewards SET tickets=200, energy=100, barn_built=1 WHERE id=?", (sid,))
            await conn.execute(
                "INSERT INTO barn_animals (steward_id, slot, species, fed, temper, escaped_at) "
                "VALUES (?,1,'chicken',1,'skittish',?)",
                (sid, db.now()),
            )
            await conn.commit()
            s = await db.get_steward_by_id(sid)
            msg = await barn_escape.recover(conn, s, 1)
            await conn.commit()
            assert "找回来" in msg


def test_escape_recover():
    asyncio.run(_test_escape_recover())


async def _test_appliance_repair():
    from server import config, db, hut_appliances

    with tempfile.TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        os.environ["DATA_DIR"] = str(tmp_p)
        config.DATA_DIR = tmp_p
        config.DB_PATH = tmp_p / "relay.db"
        db.DATA_DIR = tmp_p
        db.DB_PATH = tmp_p / "relay.db"
        await db.init_db()
        key = await db.create_api_key("b6b@test.local")
        row = await db.get_key_row(key)
        await db.enroll_steward(row["id"], "B6b", "", "naturalist", "")
        async with db.connect() as conn:
            sid = (await (await conn.execute(
                "SELECT id FROM stewards WHERE key_id=?", (row["id"],)
            )).fetchone())[0]
            await conn.execute(
                "UPDATE stewards SET tickets=200, hut_built=1, hut_level=2 WHERE id=?",
                (sid,),
            )
            await hut_appliances.ensure_table(conn)
            await conn.execute(
                "INSERT INTO steward_hut_appliance (steward_id, appliance_key, durability, max_dur) "
                "VALUES (?, 'stove', 10, 100)",
                (sid,),
            )
            await conn.commit()
            msg = await hut_appliances.repair(conn, sid, "stove")
            await conn.commit()
            assert "灶台修好了" in msg


def test_appliance_repair():
    asyncio.run(_test_appliance_repair())
