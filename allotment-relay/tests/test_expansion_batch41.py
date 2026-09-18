"""batch41：泡饮、船改装、共耕。"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_home_drink_brew():
    async def run():
        from server import db, home_drinks as hd

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("d@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "泡手", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    await db.add_item(conn, s["id"], "crop_fogpea", 1)
                    await db.add_item(conn, s["id"], "wild_mint", 1)
                    await conn.execute("UPDATE stewards SET energy=30 WHERE id=?", (s["id"],))
                    msg = await hd.brew(conn, s, "mist_pea_tea")
                    await conn.commit()
                assert "雾豆" in msg

    asyncio.run(run())


def test_boat_mod_install():
    async def run():
        from server import boat_mods as bm, db

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("s@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "船工", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    await conn.execute(
                        "UPDATE stewards SET boat_key='skiff', tickets=100 WHERE id=?",
                        (s["id"],),
                    )
                    await db.add_item(conn, s["id"], "craft_copper_nails", 2)
                    s = await db.get_steward_by_id(s["id"])
                    msg = await bm.install(conn, s, "copper_bell")
                    await conn.commit()
                assert "铜雾钟" in msg

    asyncio.run(run())


def test_cofarm_subscribe():
    async def run():
        from server import db, multi, neighbor_cofarm as cf

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                k1 = await db.create_api_key("a@example.com")
                k2 = await db.create_api_key("b@example.com")
                r1 = await db.get_key_row(k1)
                r2 = await db.get_key_row(k2)
                await db.enroll_steward(r1["id"], "Alpha", "", "naturalist", "")
                await db.enroll_steward(r2["id"], "Beta", "", "naturalist", "")
                sa = await db.get_steward_by_key_id(r1["id"])
                sb = await db.get_steward_by_key_id(r2["id"])
                async with db.connect() as conn:
                    a, b = sorted((sa["id"], sb["id"]))
                    for _ in range(16):
                        await multi._bump_rapport(conn, sa["id"], sb["id"], 3)
                    msg = await cf.subscribe(conn, sa, "Beta")
                    await conn.commit()
                assert "共耕" in msg

    asyncio.run(run())
