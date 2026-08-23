#!/usr/bin/env python3
"""生吃：蔬菜拒绝；水果能吃但回得少、连吃会营养不良（熟菜可解）；生鱼安全；肉类感染。"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_meat_aliases_and_flags() -> None:
    from server.catalog import (
        is_fruit_item,
        is_raw_meat,
        is_vegetable_item,
        resolve_item_key,
    )

    assert resolve_item_key("甘蓝") == "crop_kale"
    assert resolve_item_key("鲭鱼") == "fish_mackerel"
    assert resolve_item_key("兔肉") == "meat_rabbit"
    assert resolve_item_key("生猪肉") == "meat_pork"
    assert is_raw_meat("meat_rabbit")
    assert is_raw_meat("meat_pork")
    assert not is_raw_meat("crop_kale")
    assert not is_raw_meat("fish_mackerel")
    assert not is_raw_meat("wild_mint")
    assert not is_raw_meat("dish_garlic_oyster_s3")
    # 水果 = tags 带 fruit/berry；其余作物一律蔬菜
    for fruit in ("crop_mango", "crop_blueberry", "crop_bramble", "crop_coconut",
                  "crop_papaya", "crop_banana", "crop_lime", "crop_orange", "crop_pineapple", "crop_durian"):
        assert is_fruit_item(fruit), fruit
    for veg in ("crop_kale", "crop_ginger", "crop_sweetpotato", "crop_kelp",
                "crop_beet", "crop_rye", "crop_garlic", "crop_chili", "crop_fogpea",
                "crop_lemongrass"):
        assert is_vegetable_item(veg), veg
    assert not is_vegetable_item("crop_mango")
    assert not is_fruit_item("crop_kale")


def test_mcp_tool_copy() -> None:
    from server.mcp_app import mcp

    kitchen = mcp._tool_manager.get_tool("kitchen_ops")
    assert kitchen is not None
    props = kitchen.parameters.get("properties") or {}
    cmd = (props.get("command") or {}).get("description") or ""
    blob = f"{kitchen.description}\n{cmd}"
    assert "eat 芒果" in blob
    assert "eat 鲭鱼" in blob
    assert "不能生吃" in blob
    assert "营养不良" in blob
    assert "兔肉" in blob
    assert "感染" in blob
    assert "下馆子" in blob
    assert "shop dine" in blob


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


def test_vegetable_refused_not_consumed() -> None:
    asyncio.run(_test_vegetable_refused_not_consumed())


async def _test_vegetable_refused_not_consumed() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="raw-veg-"))
    db = await _boot(tmp)
    from server import kitchen

    kid, sid = await _enroll(db, "veggie@example.com", "菜虫")
    async with db.connect() as conn:
        await db.add_item(conn, sid, "crop_kale", 2)
        await conn.commit()

    try:
        await kitchen.kitchen_ops(kid, "eat 甘蓝")
        raise AssertionError("vegetable raw eat should refuse")
    except ValueError as exc:
        assert "不能生吃" in str(exc), exc

    async with db.connect() as conn:
        row = await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item='crop_kale'",
            (sid,),
        )).fetchone()
    assert row and row[0] == 2, row


def test_fruit_low_energy_and_malnutrition() -> None:
    asyncio.run(_test_fruit_low_energy_and_malnutrition())


async def _test_fruit_low_energy_and_malnutrition() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="raw-fruit-"))
    db = await _boot(tmp)
    from server import config, health, kitchen

    kid, sid = await _enroll(db, "fruit@example.com", "果腹")
    async with db.connect() as conn:
        await db.add_item(conn, sid, "crop_mango", 6)
        await db.add_item(conn, sid, "fish_mackerel", 1)
        dish = "dish_garlic_oyster_s3"
        await db.add_item(conn, sid, dish, 2)
        await conn.execute("UPDATE stewards SET energy=20 WHERE id=?", (sid,))
        await conn.commit()

    first = await kitchen.kitchen_ops(kid, "eat 芒果")
    assert "精力 +4" in first, first
    assert "营养不良" in first or "连吃" in first, first

    for _ in range(config.FRUIT_EAT_STREAK_LIMIT - 2):
        await kitchen.kitchen_ops(kid, "eat 芒果")
    hit = await kitchen.kitchen_ops(kid, "eat 芒果")
    assert "营养不良" in hit, hit
    async with db.connect() as conn:
        ailments = await health.list_ailments(conn, sid)
    assert any(a["key"] == "malnutrition" for a in ailments), ailments

    # 生鱼垫肚子：+10 且安全（顺带清水果连击）
    fish_msg = await kitchen.kitchen_ops(kid, "eat 鲭鱼")
    assert "精力 +10" in fish_msg, fish_msg
    assert "安全" in fish_msg, fish_msg

    # 熟菜把营养不良压下去：两档吃两顿，第二顿好利索
    meal1 = await kitchen.kitchen_ops(kid, "eat 蒜蓉生蚝")
    assert "营养不良" in meal1, meal1
    meal2 = await kitchen.kitchen_ops(kid, "eat 蒜蓉生蚝")
    assert "好利索" in meal2, meal2
    async with db.connect() as conn:
        ailments = await health.list_ailments(conn, sid)
    assert not any(a["key"] == "malnutrition" for a in ailments), ailments


def test_meat_infects() -> None:
    asyncio.run(_test_meat_infects())


async def _test_meat_infects() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="raw-meat-"))
    db = await _boot(tmp)
    from server import health, kitchen

    kid, sid = await _enroll(db, "eater@example.com", "食客")
    async with db.connect() as conn:
        await db.add_item(conn, sid, "meat_rabbit", 2)
        await conn.commit()

    health.random.random = lambda: 0.0  # type: ignore[method-assign]
    meat_msg = await kitchen.kitchen_ops(kid, "eat 兔肉")
    assert "精力" in meat_msg, meat_msg
    assert "感染" in meat_msg, meat_msg
    async with db.connect() as conn:
        ailments = await health.list_ailments(conn, sid)
    assert any(a["key"] == "infection" for a in ailments), ailments

    help_msg = await kitchen.kitchen_ops(kid, "help")
    assert "eat 芒果" in help_msg
    assert "只有生肉" in help_msg
    assert "不能生吃" in help_msg
    assert "下馆子" in help_msg
    assert "shop dine 店主名" in help_msg


def main() -> None:
    test_meat_aliases_and_flags()
    test_mcp_tool_copy()
    asyncio.run(_test_vegetable_refused_not_consumed())
    asyncio.run(_test_fruit_low_energy_and_malnutrition())
    asyncio.run(_test_meat_infects())
    print("raw eat / tool copy tests ok")


if __name__ == "__main__":
    main()
