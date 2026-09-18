"""§57 玩家连接：借船、托养、菜篮。"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_basket_subscribe_and_claim():
    async def run():
        from server import db, neighbor_links as nl

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                k1 = await db.create_api_key("a@example.com")
                k2 = await db.create_api_key("b@example.com")
                r1 = await db.get_key_row(k1)
                r2 = await db.get_key_row(k2)
                await db.enroll_steward(r1["id"], "卖家", "", "naturalist", "")
                await db.enroll_steward(r2["id"], "买家", "", "naturalist", "")
                s_sell = await db.get_steward_by_key_id(r1["id"])
                s_buy = await db.get_steward_by_key_id(r2["id"])
                async with db.connect() as conn:
                    await nl.ensure_tables(conn)
                    await conn.execute(
                        "UPDATE stewards SET tickets=100 WHERE id IN (?,?)",
                        (s_sell["id"], s_buy["id"]),
                    )
                    a, b = sorted((s_sell["id"], s_buy["id"]))
                    await conn.execute(
                        "INSERT INTO rapport (steward_a, steward_b, score) VALUES (?,?,35)",
                        (a, b),
                    )
                    await nl.basket_open(conn, s_sell)
                    msg = await nl.basket_subscribe(conn, s_buy, "卖家")
                    assert "订阅" in msg
                    item_msg = await nl.basket_claim(conn, s_buy)
                    await conn.commit()
                assert "菜篮" in item_msg

    asyncio.run(run())


def test_boat_loan_effective_key():
    async def run():
        from server import db, neighbor_links as nl

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                k1 = await db.create_api_key("l@example.com")
                k2 = await db.create_api_key("b@example.com")
                r1 = await db.get_key_row(k1)
                r2 = await db.get_key_row(k2)
                await db.enroll_steward(r1["id"], "船主", "", "naturalist", "")
                await db.enroll_steward(r2["id"], "借客", "", "naturalist", "")
                s_l = await db.get_steward_by_key_id(r1["id"])
                s_b = await db.get_steward_by_key_id(r2["id"])
                async with db.connect() as conn:
                    await nl.ensure_tables(conn)
                    await conn.execute(
                        "UPDATE stewards SET boat_key='skiff' WHERE id=?",
                        (s_l["id"],),
                    )
                    s_l = await db.get_steward_by_id(s_l["id"])
                    a, b = sorted((s_l["id"], s_b["id"]))
                    await conn.execute(
                        "INSERT INTO rapport (steward_a, steward_b, score) VALUES (?,?,65)",
                        (a, b),
                    )
                    await nl.boat_loan_give(conn, s_l, "借客")
                    key = await nl.effective_boat_key(conn, s_b)
                    await conn.commit()
                assert key == "skiff"

    asyncio.run(run())
