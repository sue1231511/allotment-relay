"""batch47-48：小馆主题、灶腌卤炼制、灶险 flash、扩菜、岛灶栏特殊标。"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_eatery_theme_sea_line():
    from server import eatery_theme as et

    items = ["dish_tide_ginger_crab_s3", "dish_braised_fish_s3", "dish_brine_kelp_pot_s3"]
    line = et.menu_theme_line(items)
    assert "海味" in line


def test_pickling_brine_recipe():
    from server.undertide_refine import RECIPES

    assert "pickling_brine" in RECIPES
    assert RECIPES["pickling_brine"]["out"][0] == "proc_pickling_brine"


def test_recipe_count_130_plus():
    from server.catalog import HEARTH_RECIPES, KITCHEN_DISHES

    assert len(KITCHEN_DISHES) + len(HEARTH_RECIPES) >= 130
    assert "fogpea_tofu" in KITCHEN_DISHES


def test_eatery_smoke_flash():
    async def run():
        from server import bad_event_tier_store as ts, db, eatery_smoke_panic as smoke

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("s@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "Smoke", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    await smoke.ensure_columns(conn)
                    await conn.execute(
                        "UPDATE stewards SET eatery_hazard=? WHERE id=?",
                        (smoke.HAZARD_SMOKE, s["id"]),
                    )
                    steward = dict(s)
                    await smoke.resolve(conn, steward, "开窗")
                    await conn.commit()
                async with db.connect() as conn:
                    flash = await ts.list_recent_flash(conn, s["id"])
                assert any("糊烟" in f["line"] for f in flash)

    asyncio.run(run())


def test_market_gust_flash():
    async def run():
        from server import bad_event_tier_store as ts, db, market_stall_gust as gust

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("m@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "Stall", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    await gust.ensure_columns(conn)
                    await conn.execute(
                        "UPDATE stewards SET market_hazard=? WHERE id=?",
                        (gust.HAZARD_GUST, s["id"]),
                    )
                    await gust.resolve(conn, dict(s), "压石")
                    await conn.commit()
                async with db.connect() as conn:
                    flash = await ts.list_recent_flash(conn, s["id"])
                assert any("掀摊" in f["line"] for f in flash)

    asyncio.run(run())
