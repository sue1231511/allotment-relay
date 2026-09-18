"""batch58-60：/eatery→/play 预选、收集簿套餐项、SET_MENUS×9、套餐名厨。"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_set_menu_count_nine():
    from server import eatery_theme as et

    assert len(et.SET_MENUS) >= 9


def test_collection_eatery_combo_dine_unlock():
    async def run():
        from server import db, island_collections as coll

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("g@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "Guest", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                await db.add_chronicle(
                    "eatery",
                    "Guest 在 Host 的馆吃套餐 潮卤海味双拼",
                    s["id"],
                )
                async with db.connect() as conn:
                    await coll.ensure_table(conn)
                    n = await coll.sync_unlocks(conn, s["id"])
                    cur = await conn.execute(
                        "SELECT 1 FROM steward_collection_unlock WHERE steward_id=? AND coll_key=?",
                        (s["id"], "eatery_combo_dine"),
                    )
                    ok = (await cur.fetchone()) is not None
                    await conn.commit()
                assert n >= 1
                assert ok

    asyncio.run(run())


def test_dine_combo_syncs_host_collection():
    async def run():
        from server import db, eatery, island_collections as coll

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
                await eatery.place_human_order(key_g, "Host", "潮卤海味双拼")
                async with db.connect() as conn:
                    await coll.ensure_table(conn)
                    cur = await conn.execute(
                        """
                        SELECT coll_key FROM steward_collection_unlock
                        WHERE steward_id=? AND coll_key IN ('eatery_set_served', 'eatery_combo_dine')
                        """,
                        (host["id"],),
                    )
                    host_keys = {r[0] for r in await cur.fetchall()}
                    cur = await conn.execute(
                        "SELECT coll_key FROM steward_collection_unlock WHERE steward_id=?",
                        (row_g["id"],),
                    )
                    guest_keys = {r[0] for r in await cur.fetchall()}
                    await conn.commit()
                assert "eatery_set_served" in host_keys
                assert "eatery_combo_dine" in guest_keys

    asyncio.run(run())


def test_eatery_set_chef3_achievement():
    async def run():
        from server import db, progress

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("h@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "Chef", "", "naturalist", "")
                host = await db.get_steward_by_key_id(row["id"])
                for i in range(3):
                    await db.add_chronicle(
                        "eatery",
                        f"G{i} 在 Chef 的馆吃套餐 潮卤海味双拼",
                        1000 + i,
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
                assert "eatery_set_chef3" in keys

    asyncio.run(run())
