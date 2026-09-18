"""batch50-51：trouble flash 扩展、小馆套餐建议、扩菜。"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_set_menu_complete():
    from server import eatery_theme as et

    items = ["dish_tide_ginger_crab_s3", "dish_brine_clam_pot_s3"]
    lines = et.set_menu_lines(items)
    assert any("潮卤海味双拼" in ln and "已齐" in ln for ln in lines)


def test_recipe_count_still_130_plus():
    from server.catalog import HEARTH_RECIPES, KITCHEN_DISHES

    assert len(KITCHEN_DISHES) + len(HEARTH_RECIPES) >= 130
    assert "blue_moss_soup" in KITCHEN_DISHES


def test_hut_chore_flash():
    async def run():
        from server import bad_event_tier_store as ts, db, hut_chores as hc

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("h@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "Home", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    await hc.ensure_table(conn)
                    await conn.execute(
                        """
                        INSERT INTO steward_hut_chore (steward_id, chore_key, created_at)
                        VALUES (?, ?, ?)
                        """,
                        (s["id"], "door_hinge", db.now()),
                    )
                    await conn.commit()
                async with db.connect() as conn:
                    await hc.resolve(conn, dict(s), "请匠")
                    await conn.commit()
                async with db.connect() as conn:
                    flash = await ts.list_recent_flash(conn, s["id"])
                assert any("杂务" in f["line"] for f in flash)

    asyncio.run(run())


def test_anvil_quench_flash():
    async def run():
        from server import bad_event_tier_store as ts, db, workshop_anvil_quench as aq

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("a@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "Smith", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    await aq.ensure_columns(conn)
                    await conn.execute(
                        """
                        INSERT INTO steward_craft (steward_id, anvil_hazard, anvil_hazard_json)
                        VALUES (?, ?, ?)
                        ON CONFLICT(steward_id) DO UPDATE SET
                        anvil_hazard=excluded.anvil_hazard,
                        anvil_hazard_json=excluded.anvil_hazard_json
                        """,
                        (s["id"], aq.HAZARD_QUENCH, "{}"),
                    )
                    await db.add_item(conn, s["id"], "quarry_salt", 1)
                    await conn.commit()
                async with db.connect() as conn:
                    await aq.resolve(conn, dict(s), "泼水")
                    await conn.commit()
                async with db.connect() as conn:
                    flash = await ts.list_recent_flash(conn, s["id"])
                assert any("淬火" in f["line"] or "砧险" in f["line"] for f in flash)

    asyncio.run(run())
