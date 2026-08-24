#!/usr/bin/env python3
"""自定义熟菜进冰箱后能按中文名 / item id 取出。"""
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


async def _enroll(db, email: str, name: str) -> int:
    key = await db.create_api_key(email)
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], name, "", "naturalist", "")
    async with db.connect() as conn:
        sid = (await (await conn.execute(
            "SELECT id FROM stewards WHERE key_id=?", (row["id"],)
        )).fetchone())[0]
    return sid


async def test_fridge_custom_mix_take_by_chinese_name() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="fridge-mix-"))
    db = await _boot(tmp)
    from server import hut, kitchen
    from server.catalog import mix_item_key, mix_title, register_mix_item

    sid = await _enroll(db, "mixfridge@example.com", "乱炖人")
    s = await db.get_steward_by_id(sid)
    kid = s["key_id"]

    item = mix_item_key("g", 3, "abcdef12", 4)
    register_mix_item(item)
    emoji, name = mix_title("g", "abcdef12")
    assert name, (emoji, name)

    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET hut_built=1, hut_level=1, tickets=400 WHERE id=?",
            (sid,),
        )
        await conn.execute(
            """
            INSERT INTO hut_fittings (steward_id, slot, item_key, installed_at)
            VALUES (?, 'soft_1', 'fridge', ?)
            """,
            (sid, db.now()),
        )
        await db.add_item(conn, sid, item, 2)
        await conn.commit()

    put = await kitchen.kitchen_ops(kid, f"store {item} 2")
    assert "冰箱" in put, put

    status = await kitchen.kitchen_ops(kid, "fridge")
    assert name in status, status
    assert item in status, status  # 列表必须带 id，撞名也能取

    # 原先只显示中文名时，用中文名取会失败
    took = await hut.hut_ops(kid, f"冰柜 取 {name} 1")
    assert "取出" in took, took

    # 星标 / emoji 装饰也能对上
    took2 = await kitchen.kitchen_ops(kid, f"take {emoji}{name}★★★★")
    assert "取出" in took2, took2

    async with db.connect() as conn:
        bag = await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item=?",
            (sid, item),
        )).fetchone()
        left = await (await conn.execute(
            "SELECT quantity FROM meal_storage WHERE steward_id=?",
            (sid,),
        )).fetchone()
    assert bag and bag[0] == 2, bag
    assert not left, left


async def test_fridge_mix_aliases_unit() -> None:
    from server import kitchen
    from server.catalog import mix_item_key, mix_title

    item = mix_item_key("o", 2, "deadbeef", 3)
    dish_key, stars = kitchen._fridge_parts(item)
    assert dish_key.startswith("mix_"), dish_key
    assert stars == 3
    assert kitchen._fridge_satchel_item(dish_key, stars) == item

    row = {"dish_key": dish_key, "stars": stars}
    _emoji, name = mix_title("o", "deadbeef")
    assert kitchen._fridge_row_matches(row, name)
    assert kitchen._fridge_row_matches(row, item)
    assert kitchen._fridge_row_matches(row, f"{_emoji}{name}★★★")
    assert not kitchen._fridge_row_matches(row, "盐焗沙蟹")


def main() -> None:
    asyncio.run(test_fridge_custom_mix_take_by_chinese_name())
    asyncio.run(test_fridge_mix_aliases_unit())
    print("ok")


if __name__ == "__main__":
    main()
