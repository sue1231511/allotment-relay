#!/usr/bin/env python3
"""果园：只种树、无上限、份地拒果树。"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def _boot(tmp: Path):
    os.environ["DATA_DIR"] = str(tmp)
    from server import config, db

    config.DATA_DIR = tmp
    config.DB_PATH = tmp / "relay.db"
    db.DATA_DIR = tmp
    db.DB_PATH = tmp / "relay.db"
    await db.init_db()
    return db


async def _enroll(db, email: str, name: str) -> tuple[int, int]:
    key = await db.create_api_key(email)
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], name, "", "naturalist", "")
    async with db.connect() as conn:
        sid = (await (await conn.execute(
            "SELECT id FROM stewards WHERE key_id=?", (row["id"],)
        )).fetchone())[0]
    return row["id"], sid


def test_slot_labels() -> None:
    from server import land as land_mod

    assert land_mod.parse_slot_ref("园3") == (3, 1)
    assert land_mod.parse_slot_ref("1", orchard_ctx=True) == (1, 1)
    assert land_mod.parse_slot_ref("1") == (1, 0)
    assert land_mod.slot_label(4, 1) == "园4"
    assert land_mod.slot_label({"slot": 2, "orchard": 1}) == "园2"
    fourth = land_mod.next_offer(3, orchard=True)
    assert fourth == {"slot": 4, "cost": 80, "clear_seconds": 1800}
    ninth = land_mod.next_offer(8, orchard=True)
    assert ninth["slot"] == 9
    assert ninth["cost"] == 480


async def test_enroll_has_orchard_slots() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="orch-enroll-"))
    db = await _boot(tmp)
    kid, sid = await _enroll(db, "orch@example.com", "果园人")
    async with db.connect() as conn:
        count = (await (await conn.execute(
            "SELECT orchard_count FROM stewards WHERE id=?", (sid,)
        )).fetchone())[0]
        trees = (await (await conn.execute(
            "SELECT COUNT(*) FROM parcels WHERE steward_id=? AND COALESCE(orchard,0)=1",
            (sid,),
        )).fetchone())[0]
        plots = (await (await conn.execute(
            "SELECT COUNT(*) FROM parcels WHERE steward_id=? AND COALESCE(orchard,0)=0",
            (sid,),
        )).fetchone())[0]
    assert count == 3
    assert trees == 3
    assert plots == 3
    from server import game
    status = await game.plot_ops(kid, "果园")
    assert "无上限" in status and "树位" in status, status


async def test_sow_routes_trees_to_orchard() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="orch-sow-"))
    db = await _boot(tmp)
    from server import game

    kid, sid = await _enroll(db, "sowtree@example.com", "种树人")
    async with db.connect() as conn:
        await db.add_item(conn, sid, "seed_mango", 2)
        await db.add_item(conn, sid, "seed_kale", 1)
        await conn.commit()

    veg_on_orchard = await game.plot_ops(kid, "果园 sow 1 甘蓝")
    assert "只种果树" in veg_on_orchard or "⚠" in veg_on_orchard, veg_on_orchard

    from server import season
    with season.pinned_month(6):
        planted = await game.plot_ops(kid, "sow 1 芒果")
    assert "园1" in planted and "芒果" in planted, planted
    async with db.connect() as conn:
        orchard_row = await (await conn.execute(
            "SELECT crop FROM parcels WHERE steward_id=? AND slot=1 AND COALESCE(orchard,0)=1",
            (sid,),
        )).fetchone()
        plot_row = await (await conn.execute(
            "SELECT crop FROM parcels WHERE steward_id=? AND slot=1 AND COALESCE(orchard,0)=0",
            (sid,),
        )).fetchone()
    assert orchard_row[0] == "mango"
    assert plot_row[0] is None

    kale = await game.plot_ops(kid, "sow 1 甘蓝")
    assert "#1" in kale and "甘蓝" in kale, kale


async def test_buy_orchard_beyond_eight() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="orch-buy-"))
    db = await _boot(tmp)
    from server import game

    kid, sid = await _enroll(db, "buyorch@example.com", "扩园人")
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET tickets=2000, orchard_count=8 WHERE id=?",
            (sid,),
        )
        for slot in range(4, 9):
            await conn.execute(
                """
                INSERT OR IGNORE INTO parcels
                (steward_id, slot, orchard, crop, planted_at, tended, ready_at)
                VALUES (?, ?, 1, NULL, NULL, 0, 0)
                """,
                (sid, slot),
            )
        await conn.commit()

    quote = await game.plot_ops(kid, "买园")
    assert "480" in quote and "无上限" in quote, quote
    bought = await game.plot_ops(kid, "买园 确认")
    assert "园9" in bought and "480" in bought, bought
    async with db.connect() as conn:
        row = await (await conn.execute(
            "SELECT orchard_count, tickets FROM stewards WHERE id=?", (sid,)
        )).fetchone()
        plot = await (await conn.execute(
            "SELECT ready_at FROM parcels WHERE steward_id=? AND slot=9 AND orchard=1",
            (sid,),
        )).fetchone()
    assert row[0] == 9
    assert row[1] == 2000 - 480
    assert plot is not None and plot[0] > 0


def main() -> None:
    test_slot_labels()
    asyncio.run(test_enroll_has_orchard_slots())
    asyncio.run(test_sow_routes_trees_to_orchard())
    asyncio.run(test_buy_orchard_beyond_eight())
    print("orchard tests ok")


if __name__ == "__main__":
    main()
