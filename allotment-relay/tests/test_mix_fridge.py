#!/usr/bin/env python3
"""自由组合熟菜进冰箱后，简称/重启后仍能取出。"""
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
    return sid, row["id"]


async def test_mix_fridge_take_after_restart() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="mix-fridge-"))
    db = await _boot(tmp)
    from server import hut, kitchen
    from server.catalog import ITEM_NAMES, item_label

    sid, kid = await _enroll(db, "mix@example.com", "锅主")
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET hut_built=1, hut_level=2, tickets=400 WHERE id=?",
            (sid,),
        )
        await conn.execute(
            """
            INSERT INTO hut_fittings (steward_id, slot, item_key, installed_at)
            VALUES (?, 'soft_1', 'fridge', ?)
            """,
            (sid, db.now()),
        )
        await db.add_item(conn, sid, "crop_kale", 2)
        await db.add_item(conn, sid, "fish_mackerel", 2)
        await conn.commit()

    await kitchen.kitchen_ops(kid, "cook 甘蓝 鲭鱼")
    async with db.connect() as conn:
        cur = await conn.execute(
            "SELECT item FROM satchel WHERE steward_id=? AND item LIKE 'dish_mix_%'",
            (sid,),
        )
        mix_item = (await cur.fetchone())[0]
    label = item_label(mix_item)
    stored = await kitchen.kitchen_ops(kid, f"store {mix_item}")
    assert "冰箱" in stored, stored

    for key in list(ITEM_NAMES):
        if key.startswith("dish_mix_"):
            del ITEM_NAMES[key]

    core = label.split("★")[0].lstrip("🦐🥘🍲🥗🍳🍛🥣🫕🥫🍽️✨🦞⭐💎")
    took = await hut.hut_ops(kid, f"冰柜 取 {core}")
    assert "取出" in took, took

    await kitchen.kitchen_ops(kid, f"store {mix_item}")
    took2 = await kitchen.kitchen_ops(kid, f"take {core}")
    assert "取出" in took2, took2


def main() -> None:
    asyncio.run(test_mix_fridge_take_after_restart())
    print("ok")


if __name__ == "__main__":
    main()
