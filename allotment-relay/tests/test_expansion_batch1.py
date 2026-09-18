#!/usr/bin/env python3
"""第一批扩展：内容表、品质、鲜度、鱼重。"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_expansion_catalog_static():
    from server import catalog

    assert "spinach" in catalog.CROPS
    assert "apple" in catalog.CROPS
    assert catalog.ITEM_PRICES.get("seed_tomato") == 11
    assert "clownfish" in catalog.SEA_CATCH
    assert catalog.ITEM_PRICES.get("proc_flour") == 14
    assert "turkey" in catalog.LIVESTOCK
    assert len(catalog.HEARTH_RECIPES) >= 40


def test_quality_rolls():
    from server import item_traits

    q = item_traits.roll_crop_quality({"watered": 1, "tended": 1})
    assert q in item_traits.CROP_QUALITY_KEYS
    w = item_traits.roll_fish_weight_kg("tuna")
    assert w >= 3.0
    st = item_traits.roll_fish_state("mackerel")
    assert st in item_traits.FISH_STATE_KEYS


async def _test_traits_db():
    from server import config, db, item_traits

    with tempfile.TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        os.environ["DATA_DIR"] = str(tmp_p)
        config.DATA_DIR = tmp_p
        config.DB_PATH = tmp_p / "relay.db"
        db.DATA_DIR = tmp_p
        db.DB_PATH = tmp_p / "relay.db"
        await db.init_db()
        key = await db.create_api_key("exp@test.local")
        row = await db.get_key_row(key)
        await db.enroll_steward(row["id"], "Exp", "", "naturalist", "")
        async with db.connect() as conn:
            sid = (await (await conn.execute(
                "SELECT id FROM stewards WHERE key_id=?", (row["id"],)
            )).fetchone())[0]
            await item_traits.grant_satchel(
                conn, sid, "fish_mackerel", 1, quality="fresh", weight_kg=1.2,
            )
            await conn.commit()
            note = await item_traits.summary_for_item(conn, sid, "fish_mackerel")
            assert "1.2kg" in note or "极鲜" in note


def test_grant_traits():
    asyncio.run(_test_traits_db())
