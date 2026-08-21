#!/usr/bin/env python3
"""生吃：作物/鱼安全；只有肉类会感染。MCP 工具说明带例子。"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_meat_aliases_and_flags() -> None:
    from server.catalog import is_raw_meat, resolve_item_key

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


def test_mcp_tool_copy() -> None:
    from server.mcp_app import mcp

    kitchen = mcp._tool_manager.get_tool("kitchen_ops")
    assert kitchen is not None
    props = kitchen.parameters.get("properties") or {}
    cmd = (props.get("command") or {}).get("description") or ""
    blob = f"{kitchen.description}\n{cmd}"
    assert "eat 甘蓝" in blob
    assert "兔肉" in blob
    assert "感染" in blob
    assert "安全" in blob


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


async def test_eat_crop_safe_meat_infects() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="raw-eat-"))
    db = await _boot(tmp)
    from server import health, kitchen

    kid, sid = await _enroll(db, "eater@example.com", "食客")
    async with db.connect() as conn:
        await db.add_item(conn, sid, "crop_kale", 2)
        await db.add_item(conn, sid, "fish_mackerel", 1)
        await db.add_item(conn, sid, "meat_rabbit", 2)
        await conn.commit()

    crop_msg = await kitchen.kitchen_ops(kid, "eat 甘蓝")
    assert "精力" in crop_msg, crop_msg
    assert "安全" in crop_msg, crop_msg
    async with db.connect() as conn:
        ailments = await health.list_ailments(conn, sid)
    assert ailments == [], ailments

    fish_msg = await kitchen.kitchen_ops(kid, "eat 鲭鱼")
    assert "精力" in fish_msg, fish_msg
    assert "安全" in fish_msg, fish_msg
    async with db.connect() as conn:
        ailments = await health.list_ailments(conn, sid)
    assert ailments == [], ailments

    health.random.random = lambda: 0.0  # type: ignore[method-assign]
    meat_msg = await kitchen.kitchen_ops(kid, "eat 兔肉")
    assert "精力" in meat_msg, meat_msg
    assert "感染" in meat_msg, meat_msg
    async with db.connect() as conn:
        ailments = await health.list_ailments(conn, sid)
    assert any(a["key"] == "infection" for a in ailments), ailments

    help_msg = await kitchen.kitchen_ops(kid, "help")
    assert "eat 甘蓝" in help_msg
    assert "只有生肉" in help_msg


def main() -> None:
    test_meat_aliases_and_flags()
    test_mcp_tool_copy()
    asyncio.run(test_eat_crop_safe_meat_infects())
    print("raw eat / tool copy tests ok")


if __name__ == "__main__":
    main()
