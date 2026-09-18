"""batch46：EXTRA 定点菜、125+ 菜谱 KPI、鸟啄灾档 flash、卤边潮锅特殊。"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_recipe_catalog_100_plus():
    from server.catalog import HEARTH_RECIPES, KITCHEN_DISHES

    total = len(KITCHEN_DISHES) + len(HEARTH_RECIPES)
    assert total >= 125
    assert "tide_ginger_crab" in KITCHEN_DISHES
    assert "brine_clam_pot" in KITCHEN_DISHES


def test_bird_peck_flash_in_tierlog():
    async def run():
        from server import bad_event_tier_store as ts, db, light_bad_events as lb
        from server import bad_event_tiers as tiers_mod

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("b@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "Bird", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    await tiers_mod.record_flash(
                        conn,
                        s["id"],
                        "plot",
                        tiers_mod.TIER_MID,
                        "斑鸠啄了一口",
                        ref_key="flash:bird_peck",
                    )
                    await conn.commit()
                async with db.connect() as conn:
                    report = await ts.format_report(conn, s["id"])
                    flash = await ts.list_recent_flash(conn, s["id"])
                assert "近日瞬时" in report
                assert len(flash) >= 1
                assert "斑鸠" in flash[0]["line"]

    asyncio.run(run())


def test_brine_clam_special_key():
    from server import kitchen_special as ks

    assert "brine_clam_pot" in ks.SPECIAL_DISH_KEYS
    assert ks.SPECIAL_ON_EAT["brine_clam_pot"] == "brine_clam"
