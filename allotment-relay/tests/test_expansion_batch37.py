"""§59 文档补齐：家维/杂务/料理品质/特殊菜/起名。"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_cooking_star_bonus():
    from server import item_traits as traits

    assert traits.cooking_star_bonus(["flavor", "plain"]) >= 1
    assert traits.cooking_star_bonus(["bugbit", "parasite"]) <= -1


def test_hut_domestic_pay():
    async def run():
        from server import db, hut_domestic as dom

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("h@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "居者", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    await conn.execute(
                        "UPDATE stewards SET hut_built=1, hut_level=3, tickets=50 WHERE id=?",
                        (s["id"],),
                    )
                    view = await dom.assess(conn, s["id"], hut_built=True, hut_level=3, has_fridge=True)
                    assert view["due"] > 0
                    msg = await dom.pay(conn, s["id"])
                    await conn.commit()
                assert "家维" in msg or "交清" in msg

    asyncio.run(run())


def test_hut_chore_resolve():
    async def run():
        from server import db, hut_chores as ch

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("c@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "主妇", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    await ch.ensure_table(conn)
                    await conn.execute(
                        """
                        INSERT INTO steward_hut_chore (steward_id, chore_key, created_at)
                        VALUES (?, 'door_hinge', ?)
                        """,
                        (s["id"], db.now()),
                    )
                    await conn.execute("UPDATE stewards SET tickets=30, energy=20 WHERE id=?", (s["id"],))
                    msg = await ch.resolve(conn, s, "请匠")
                    await conn.commit()
                assert "门" in msg or "匠" in msg

    asyncio.run(run())


def test_barn_rename():
    async def run():
        from server import barn_names as names
        from server import db

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("b@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "牧人", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    await conn.execute(
                        """
                        INSERT INTO barn_animals (steward_id, slot, species, fed, guard)
                        VALUES (?, 1, 'chicken', 0, 0)
                        """,
                        (s["id"],),
                    )
                    msg = await names.rename(conn, s, 1, "豆花")
                    await conn.commit()
                assert "豆花" in msg

    asyncio.run(run())
