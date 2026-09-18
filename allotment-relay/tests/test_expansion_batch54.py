"""batch54-55：/island 套餐堂食 UI、SET_MENUS 扩量、套餐客成就。"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_set_menu_count():
    from server import eatery_theme as et

    assert len(et.SET_MENUS) >= 5


def test_player_view_exposes_combo_dish():
    async def run():
        from server import db, eatery

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key_h = await db.create_api_key("h@example.com")
                row_h = await db.get_key_row(key_h)
                await db.enroll_steward(row_h["id"], "Host", "", "naturalist", "")
                host = await db.get_steward_by_key_id(row_h["id"])
                key_g = await db.create_api_key("g@example.com")
                row_g = await db.get_key_row(key_g)
                await db.enroll_steward(row_g["id"], "Guest", "", "naturalist", "")
                guest = await db.get_steward_by_key_id(row_g["id"])
                async with db.connect() as conn:
                    await conn.execute(
                        "UPDATE stewards SET eatery_open=1, eatery_label='测试馆', hut_built=1, tickets=500 WHERE id=?",
                        (host["id"],),
                    )
                    await conn.execute(
                        """
                        INSERT INTO eatery_menu (steward_id, item, price, listed_at)
                        VALUES (?, ?, ?, ?), (?, ?, ?, ?)
                        """,
                        (
                            host["id"],
                            "dish_tide_ginger_crab_s3",
                            80,
                            db.now(),
                            host["id"],
                            "dish_brine_clam_pot_s3",
                            90,
                            db.now(),
                        ),
                    )
                    await conn.execute(
                        "UPDATE stewards SET tickets=500 WHERE id=?",
                        (guest["id"],),
                    )
                    guest = await db.get_steward_by_id(guest["id"])
                    view = await eatery.player_view(conn, guest)
                    await conn.commit()
                combos = [d for d in view["dishes"] if d.get("is_combo")]
                assert combos
                assert combos[0].get("can_dine")
                assert combos[0].get("combo_name") == "潮卤海味双拼"

    asyncio.run(run())


def test_eatery_combo_achievement():
    async def run():
        from server import db, progress

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("c@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "Combo", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                await db.add_chronicle(
                    "eatery",
                    "Combo 在 Host 的馆吃套餐 潮卤海味双拼",
                    s["id"],
                )
                async with db.connect() as conn:
                    await progress.scan_achievements(conn, s)
                    cur = await conn.execute(
                        "SELECT ach_key FROM steward_achievements WHERE steward_id=?",
                        (s["id"],),
                    )
                    keys = {r[0] for r in await cur.fetchall()}
                    await conn.commit()
                assert "eatery_combo" in keys

    asyncio.run(run())
