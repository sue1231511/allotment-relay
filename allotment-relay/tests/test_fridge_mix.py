#!/usr/bin/env python3
"""自由组合熟菜进冰箱后能用中文名或 id 取出来。"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_cooked_token_matches_mix_labels() -> None:
    from server.catalog import cooked_token_matches, mix_item_key, mix_title

    item = mix_item_key("g", 3, "00aaaaaa", 3)
    emoji, name = mix_title("g", "00aaaaaa")
    assert name == "即兴好菜", name
    assert cooked_token_matches(item, name)
    assert cooked_token_matches(item, f"{emoji}{name}★★★")
    assert cooked_token_matches(item, item)
    other = mix_item_key("g", 2, "05bbbbbb", 4)
    assert mix_title("g", "05bbbbbb")[1] == name
    assert not cooked_token_matches(item, other)
    assert cooked_token_matches(other, name)


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


async def _ready_fridge(db, sid: int) -> None:
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
        await conn.commit()


async def test_mix_dish_fridge_roundtrip_by_chinese_name() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="fridge-mix-"))
    db = await _boot(tmp)
    from server import hut, kitchen
    from server.catalog import mix_item_key, mix_title

    sid = await _enroll(db, "mixfridge@example.com", "乱炖人")
    await _ready_fridge(db, sid)
    s = await db.get_steward_by_id(sid)
    kid = s["key_id"]

    item = mix_item_key("g", 3, "00aaaaaa", 3)
    name = mix_title("g", "00aaaaaa")[1]
    async with db.connect() as conn:
        await db.add_item(conn, sid, item, 2)
        await conn.commit()

    put = await hut.hut_ops(kid, f"冰柜 存 {item} 2")
    assert "冰箱" in put, put
    listed = await hut.hut_ops(kid, "冰柜")
    assert name in listed, listed
    assert item in listed, listed

    took = await hut.hut_ops(kid, f"冰柜 取 {name} 1")
    assert "取出" in took, took
    async with db.connect() as conn:
        bag = await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item=?",
            (sid, item),
        )).fetchone()
        fridge = await (await conn.execute(
            "SELECT quantity FROM meal_storage WHERE steward_id=?",
            (sid,),
        )).fetchone()
    assert bag and bag[0] == 1, bag
    assert fridge and fridge[0] == 1, fridge

    took2 = await kitchen.kitchen_ops(kid, f"take {name}")
    assert "取出" in took2, took2
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


async def test_mix_dish_store_and_take_without_catalog_registration() -> None:
    """重启后 ITEM_NAMES 没有这道即兴菜，按中文名仍能存取。"""
    tmp = Path(tempfile.mkdtemp(prefix="fridge-mix-restart-"))
    db = await _boot(tmp)
    from server import hut, kitchen
    from server.catalog import ITEM_NAMES, mix_item_key, mix_title

    sid = await _enroll(db, "mixrestart@example.com", "重启人")
    await _ready_fridge(db, sid)
    s = await db.get_steward_by_id(sid)
    kid = s["key_id"]

    item = mix_item_key("o", 2, "11ffffff", 2)
    name = mix_title("o", "11ffffff")[1]
    ITEM_NAMES.pop(item, None)
    async with db.connect() as conn:
        await db.add_item(conn, sid, item, 1)
        await conn.commit()

    put = await kitchen.kitchen_ops(kid, f"store {name}")
    assert "冰箱" in put, put
    listed = await kitchen.kitchen_ops(kid, "fridge")
    assert name in listed and item in listed, listed
    took = await hut.hut_ops(kid, f"冰柜 取 {name}")
    assert "取出" in took, took


async def test_mix_same_title_take_by_id() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="fridge-mix-id-"))
    db = await _boot(tmp)
    from server import hut
    from server.catalog import mix_item_key, mix_title, register_mix_item

    sid = await _enroll(db, "mixtwin@example.com", "撞名人")
    await _ready_fridge(db, sid)
    s = await db.get_steward_by_id(sid)
    kid = s["key_id"]

    first = mix_item_key("g", 3, "00aaaaaa", 3)
    second = mix_item_key("g", 1, "05bbbbbb", 3)
    assert mix_title("g", "00aaaaaa")[1] == mix_title("g", "05bbbbbb")[1]
    register_mix_item(first)
    register_mix_item(second)
    async with db.connect() as conn:
        await db.add_item(conn, sid, first, 1)
        await db.add_item(conn, sid, second, 1)
        await conn.commit()

    await hut.hut_ops(kid, f"冰柜 存 {first}")
    await hut.hut_ops(kid, f"冰柜 存 {second}")
    took = await hut.hut_ops(kid, f"冰柜 取 {second}")
    assert "取出" in took, took
    async with db.connect() as conn:
        bag_first = await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item=?",
            (sid, first),
        )).fetchone()
        bag_second = await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item=?",
            (sid, second),
        )).fetchone()
        stored = [
            r[0]
            for r in await (await conn.execute(
                "SELECT dish_key FROM meal_storage WHERE steward_id=?",
                (sid,),
            )).fetchall()
        ]
    assert not bag_first, bag_first
    assert bag_second and bag_second[0] == 1, bag_second
    assert any("00aaaaaa" in key for key in stored), stored
    assert not any("05bbbbbb" in key for key in stored), stored


def main() -> None:
    test_cooked_token_matches_mix_labels()
    asyncio.run(test_mix_dish_fridge_roundtrip_by_chinese_name())
    asyncio.run(test_mix_dish_store_and_take_without_catalog_registration())
    asyncio.run(test_mix_same_title_take_by_id())
    print("fridge mix tests ok")


if __name__ == "__main__":
    main()
