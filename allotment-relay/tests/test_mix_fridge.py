#!/usr/bin/env python3
"""自由组合熟菜进冰箱：中文名可存可取，清单带 dish_mix_… id。"""
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


async def test_mix_dish_fridge_cn_roundtrip() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="mix-fridge-"))
    db = await _boot(tmp)
    from server import hut, kitchen
    from server.catalog import (
        ITEM_NAMES,
        ITEM_PRICES,
        mix_display_name,
        mix_item_key,
        parse_mix_item,
        register_mix_item,
    )

    # 固定一道自由组合菜（不走 cook，避免随机星级）
    item = mix_item_key("o", 2, "a1b2c3d4", 3)
    register_mix_item(item)
    parsed = parse_mix_item(item)
    assert parsed
    grade, _tier, sig, stars = parsed
    label = mix_display_name(grade, sig, stars)
    # 显示名形如 🍲份地乱炖★★★ — 玩家常只抄中文
    from server.kitchen import _dish_token_variants

    variants = _dish_token_variants(label)
    bare_cn = min((v for v in variants if v and not v.startswith("dish_")), key=len)
    assert bare_cn and "★" not in bare_cn, (label, variants, bare_cn)

    sid = await _enroll(db, "mixfridge@example.com", "即兴厨")
    s = await db.get_steward_by_id(sid)
    kid = s["key_id"]
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

    # 模拟进程重启：ITEM_NAMES / ITEM_PRICES 里没有这道 mix
    ITEM_NAMES.pop(item, None)
    ITEM_PRICES.pop(item, None)

    # 按中文名存进冰箱（hut 原先会 unknown_item）
    put = await hut.hut_ops(kid, f"冰柜 存 {bare_cn} 1")
    assert "入冰箱" in put, put
    assert item in put or "冰箱" in put, put

    listed = await kitchen.kitchen_ops(kid, "fridge")
    assert bare_cn in listed, listed
    assert item in listed, listed  # 清单必须带 id，否则取不出

    # 再清一次注册表，确保取菜不依赖内存别名
    ITEM_NAMES.pop(item, None)
    ITEM_PRICES.pop(item, None)

    took = await hut.hut_ops(kid, f"冰柜 取 {bare_cn}")
    assert "取出" in took, took
    assert item in took, took

    async with db.connect() as conn:
        bag = await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item=?",
            (sid, item),
        )).fetchone()
        stored = await (await conn.execute(
            "SELECT quantity FROM meal_storage WHERE steward_id=?",
            (sid,),
        )).fetchone()
    assert bag and bag[0] == 2, bag  # 存了 1 份又取回，行囊仍 2
    assert not stored or stored[0] == 0

    # kitchen_ops 路径：再存再用完整显示名取
    ITEM_NAMES.pop(item, None)
    ITEM_PRICES.pop(item, None)
    await kitchen.kitchen_ops(kid, f"store {bare_cn}")
    ITEM_NAMES.pop(item, None)
    ITEM_PRICES.pop(item, None)
    took2 = await kitchen.kitchen_ops(kid, f"take {label}")
    assert "取出" in took2, took2


async def test_mix_fridge_by_item_id() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="mix-fridge-id-"))
    db = await _boot(tmp)
    from server import hut
    from server.catalog import mix_item_key, register_mix_item

    item = mix_item_key("g", 3, "deadbeef", 4)
    register_mix_item(item)
    sid = await _enroll(db, "mixid@example.com", "编号厨")
    s = await db.get_steward_by_id(sid)
    kid = s["key_id"]
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
        await db.add_item(conn, sid, item, 1)
        await conn.commit()

    put = await hut.hut_ops(kid, f"冰柜 存 {item}")
    assert "入冰箱" in put, put
    took = await hut.hut_ops(kid, f"冰柜 取 {item}")
    assert "取出" in took, took


async def main() -> None:
    await test_mix_dish_fridge_cn_roundtrip()
    await test_mix_fridge_by_item_id()
    print("ok")


if __name__ == "__main__":
    asyncio.run(main())
