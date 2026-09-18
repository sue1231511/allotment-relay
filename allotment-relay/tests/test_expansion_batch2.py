#!/usr/bin/env python3
"""第二批扩展：肥力、虫害、留种、船体、鱼线。"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_soil_family():
    from server import soil

    assert soil.crop_family("kale") == "leaf"
    assert soil.crop_family("fogpea") == "legume"
    assert soil.grow_target_mult(30) > 1.0
    assert soil.grow_target_mult(90) < 1.0


def test_pest_yield():
    from server import plot_pests

    assert plot_pests.yield_mult({"pest_key": "root_rot", "pest_level": 2}) < 0.6


async def _test_lineage_db():
    from server import config, db, seed_lineage

    with tempfile.TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        os.environ["DATA_DIR"] = str(tmp_p)
        config.DATA_DIR = tmp_p
        config.DB_PATH = tmp_p / "relay.db"
        db.DATA_DIR = tmp_p
        db.DB_PATH = tmp_p / "relay.db"
        await db.init_db()
        key = await db.create_api_key("b2@test.local")
        row = await db.get_key_row(key)
        await db.enroll_steward(row["id"], "B2", "", "naturalist", "")
        async with db.connect() as conn:
            sid = (await (await conn.execute(
                "SELECT id FROM stewards WHERE key_id=?", (row["id"],)
            )).fetchone())[0]
            await db.add_item(conn, sid, "crop_kale", 2)
            await conn.commit()
        steward = await db.get_steward_by_id(sid)
        async with db.connect() as conn:
            msg = await seed_lineage.save_from_crop(conn, steward, "kale")
            await conn.commit()
            assert "第1代" in msg
            lin = await seed_lineage.get_lineage(conn, sid, "kale")
            assert lin and lin["generation"] == 1


def test_seed_lineage():
    asyncio.run(_test_lineage_db())


async def _test_hull_db():
    from server import boat_hull, config, db

    with tempfile.TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        os.environ["DATA_DIR"] = str(tmp_p)
        config.DATA_DIR = tmp_p
        config.DB_PATH = tmp_p / "relay.db"
        db.DATA_DIR = tmp_p
        db.DB_PATH = tmp_p / "relay.db"
        await db.init_db()
        key = await db.create_api_key("hull@test.local")
        row = await db.get_key_row(key)
        await db.enroll_steward(row["id"], "Hull", "", "naturalist", "")
        async with db.connect() as conn:
            sid = (await (await conn.execute(
                "SELECT id FROM stewards WHERE key_id=?", (row["id"],)
            )).fetchone())[0]
            h, mx = await boat_hull.get_hull(conn, sid)
            assert h == mx == 100
            note = await boat_hull.wear_after_voyage(conn, sid, "deep", storm=True)
            h2, _ = await boat_hull.get_hull(conn, sid)
            assert h2 < h
            assert "船体" in note


def test_boat_hull():
    asyncio.run(_test_hull_db())
