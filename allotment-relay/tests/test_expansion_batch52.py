"""batch52-53：余下 trouble flash、套餐堂食捆绑价。"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_combo_dine_price():
    from server import eatery_theme as et

    rows = [{"price": 100}, {"price": 50}]
    assert et.combo_dine_price(rows) == int(round(150 * et.COMBO_DINE_DISCOUNT))


def test_resolve_set_menu():
    from server import eatery_theme as et

    assert et.resolve_set_menu("潮卤海味双拼") is not None
    assert et.resolve_set_menu("sea_brine_combo") is not None


def test_theater_script_flash():
    async def run():
        from server import bad_event_tier_store as ts, db, theater_script_jam as scr

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("t@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "Play", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    await scr.ensure_columns(conn)
                    await conn.execute(
                        "UPDATE stewards SET theater_hazard=? WHERE id=?",
                        (scr.HAZARD_SCRIPT, s["id"]),
                    )
                    await db.add_item(conn, s["id"], "cloth_drift", 1)
                    await conn.commit()
                async with db.connect() as conn:
                    await scr.resolve(conn, dict(s), "抚纸")
                    await conn.commit()
                async with db.connect() as conn:
                    flash = await ts.list_recent_flash(conn, s["id"])
                assert any("稿险" in f["line"] for f in flash)

    asyncio.run(run())
