"""batch56-57：/eatery 与 /play 套餐展示、齐柜主成就、SET_MENUS 扩量。"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_set_menu_count_seven():
    from server import eatery_theme as et

    assert len(et.SET_MENUS) >= 7


def test_public_snapshot_includes_combos():
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
                async with db.connect() as conn:
                    await conn.execute(
                        "UPDATE stewards SET eatery_open=1, eatery_label='测试馆', hut_built=1 WHERE id=?",
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
                    await conn.commit()
                snap = await eatery.public_eatery_snapshot()
                shop = next(s for s in snap["shops"] if s["name"] == "Host")
                assert shop["combos"]
                assert shop["combos"][0]["name"] == "潮卤海味双拼"
                assert shop["combos"][0]["price"] == int(round((80 + 90) * 0.88))

    asyncio.run(run())


def test_human_order_combo_by_name():
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
                async with db.connect() as conn:
                    await conn.execute(
                        "UPDATE stewards SET eatery_open=1, hut_built=1, tickets=500 WHERE id=?",
                        (host["id"],),
                    )
                    await conn.execute(
                        "UPDATE stewards SET tickets=500 WHERE id=?",
                        (row_g["id"],),
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
                    await conn.commit()
                host_before = await db.get_steward_by_id(host["id"])
                combo_price = int(round((80 + 90) * 0.88))
                out = await eatery.place_human_order(key_g, "Host", "潮卤海味双拼")
                assert "套餐" in out["message"]
                assert out["tickets_left"] == 500 - combo_price
                host_after = await db.get_steward_by_id(host["id"])
                assert host_after["tickets"] == host_before["tickets"] + combo_price

    asyncio.run(run())


def test_eatery_set_chef_achievement():
    async def run():
        from server import db, progress

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key_h = await db.create_api_key("h@example.com")
                row_h = await db.get_key_row(key_h)
                await db.enroll_steward(row_h["id"], "Host", "", "naturalist", "")
                host = await db.get_steward_by_key_id(row_h["id"])
                await db.add_chronicle(
                    "eatery",
                    "Guest 在 Host 的馆吃套餐 潮卤海味双拼",
                    999,
                    host["id"],
                )
                async with db.connect() as conn:
                    await progress.scan_achievements(conn, host)
                    cur = await conn.execute(
                        "SELECT ach_key FROM steward_achievements WHERE steward_id=?",
                        (host["id"],),
                    )
                    keys = {r[0] for r in await cur.fetchall()}
                    await conn.commit()
                assert "eatery_set_chef" in keys

    asyncio.run(run())
