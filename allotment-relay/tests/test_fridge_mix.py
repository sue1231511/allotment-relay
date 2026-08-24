#!/usr/bin/env python3
"""自由组合熟菜进冰箱后应能用中文名或 dish_mix_… id 取出。"""
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


async def test_mix_dish_fridge_take_by_cn_name() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="fridge-mix-"))
    db = await _boot(tmp)
    from server import hut, kitchen
    from server.catalog import (
        ITEM_NAMES,
        mix_display_name,
        mix_item_key,
        parse_mix_item,
        register_mix_item,
    )

    sid = await _enroll(db, "mixfridge@example.com", "乱炖人")
    item = mix_item_key("g", 3, "a1b2c3d4", 3)
    register_mix_item(item)
    label = mix_display_name("g", "a1b2c3d4", 3)
    cn_bare = label.replace("★", "")
    # 去掉前导 emoji，只留中文名（玩家常这样抄）
    import re
    cn_only = "".join(re.findall(r"[\u4e00-\u9fff]+", label))

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

    s = await db.get_steward_by_id(sid)
    kid = s["key_id"]

    put = await kitchen.kitchen_ops(kid, f"store {item}")
    assert "冰箱" in put, put

    # 模拟进程重启：ITEM_NAMES 里没有这道自由组合
    ITEM_NAMES.pop(item, None)
    assert item not in ITEM_NAMES

    listed = await kitchen.kitchen_ops(kid, "fridge")
    assert item in listed, listed
    assert cn_only in listed, listed

    async with db.connect() as conn:
        after_store = await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item=?",
            (sid, item),
        )).fetchone()
        in_fridge = await (await conn.execute(
            "SELECT quantity FROM meal_storage WHERE steward_id=?",
            (sid,),
        )).fetchone()
    assert after_store and after_store[0] == 1, after_store
    assert in_fridge and in_fridge[0] == 1, in_fridge

    # 中文名取出（无 emoji、无星）→ 行囊回到 2，冰箱空
    took = await kitchen.kitchen_ops(kid, f"take {cn_only}")
    assert "取出" in took, took

    async with db.connect() as conn:
        bag = await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item=?",
            (sid, item),
        )).fetchone()
        left = await (await conn.execute(
            "SELECT COUNT(*) FROM meal_storage WHERE steward_id=?",
            (sid,),
        )).fetchone()
    assert bag and bag[0] == 2, bag
    assert left and left[0] == 0, left

    # 再存一份，用列表里的 id 经 hut_ops 取出
    ITEM_NAMES.pop(item, None)
    put2 = await hut.hut_ops(kid, f"冰柜 存 {item}")
    assert "冰箱" in put2, put2
    ITEM_NAMES.pop(item, None)
    took2 = await hut.hut_ops(kid, f"冰柜 取 {item}")
    assert "取出" in took2, took2

    async with db.connect() as conn:
        empty = await (await conn.execute(
            "SELECT COUNT(*) FROM meal_storage WHERE steward_id=?",
            (sid,),
        )).fetchone()
        bag2 = await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item=?",
            (sid, item),
        )).fetchone()
    assert empty and empty[0] == 0, empty
    assert bag2 and bag2[0] == 2, bag2

    # 再存一次，用 hut 中文名取（解析不到 id 时走冰箱匹配）
    put3 = await hut.hut_ops(kid, f"冰柜 存 {item}")
    assert "冰箱" in put3, put3
    ITEM_NAMES.pop(item, None)
    took3 = await hut.hut_ops(kid, f"冰柜 取 {cn_only}")
    assert "取出" in took3, took3

    parsed = parse_mix_item(item)
    assert parsed and parsed[0] == "g"
    assert cn_bare
    print("ok fridge mix take", item, cn_only)


async def test_named_dish_still_works() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="fridge-named-"))
    db = await _boot(tmp)
    from server import hut, kitchen

    sid = await _enroll(db, "namedfridge@example.com", "定点人")
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET hut_built=1, hut_level=1 WHERE id=?",
            (sid,),
        )
        await conn.execute(
            """
            INSERT INTO hut_fittings (steward_id, slot, item_key, installed_at)
            VALUES (?, 'soft_1', 'fridge', ?)
            """,
            (sid, db.now()),
        )
        await db.add_item(conn, sid, "dish_salt_crab_s4", 1)
        await conn.commit()
    s = await db.get_steward_by_id(sid)
    kid = s["key_id"]
    await kitchen.kitchen_ops(kid, "store 盐焗沙蟹")
    listed = await kitchen.kitchen_ops(kid, "fridge")
    assert "dish_salt_crab_s4" in listed, listed
    took = await hut.hut_ops(kid, "冰柜 取 盐焗沙蟹")
    assert "取出" in took, took


def main() -> None:
    asyncio.run(test_mix_dish_fridge_take_by_cn_name())
    asyncio.run(test_named_dish_still_works())
    print("all fridge mix tests passed")


if __name__ == "__main__":
    main()
