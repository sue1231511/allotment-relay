#!/usr/bin/env python3
"""未命名小鱼：不能网、只能坐钓；小咒；吃/卖随机事件。"""
from __future__ import annotations

import asyncio
import json
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
        await conn.execute(
            "UPDATE stewards SET tickets=400, energy=80 WHERE id=?", (sid,)
        )
        await conn.commit()
    return row["id"], sid


def test_walkblue_cast_only_pool() -> None:
    from server.catalog import (
        SEA_CATCH,
        WALKBLUE_HEX,
        WALKBLUE_ITEM,
        is_cast_only_fish,
        is_walkblue_item,
        resolve_ailment_key,
        resolve_item_key,
        weighted_fish_pick,
    )

    assert SEA_CATCH["walkblue"].get("cast_only") is True
    assert is_cast_only_fish("walkblue")
    assert is_walkblue_item(WALKBLUE_ITEM)
    assert resolve_item_key("未命名小鱼") == WALKBLUE_ITEM
    assert resolve_ailment_key("腿鱼小咒") == WALKBLUE_HEX

    for _ in range(250):
        assert weighted_fish_pick(allow_cast_only=False) != "walkblue"
        assert weighted_fish_pick(
            tide="flood", zones={"deep"}, rarity_cap=6, allow_cast_only=False
        ) != "walkblue"


def test_help_and_manual_copy() -> None:
    from server import game, kitchen
    from server.mcp_app import mcp
    from server.mcp_dispatch import TIDE_HELP, TOTE_HELP, VISIT_HELP

    for blob in (TIDE_HELP, TOTE_HELP, VISIT_HELP):
        assert "未命名小鱼" in blob or "腿鱼小咒" in blob
    assert "不能网" in TIDE_HELP
    assert "vend 未命名小鱼" in TOTE_HELP
    assert "腿鱼小咒" in VISIT_HELP

    help_src = Path(kitchen.__file__).read_text(encoding="utf-8")
    assert "eat 未命名小鱼" in help_src

    manual = asyncio.run(game.relay_manual())
    assert "不能网" in manual
    assert "腿鱼小咒" in manual
    assert "eat 未命名小鱼" in manual
    assert "vend 未命名小鱼" in manual

    tide = mcp._tool_manager.get_tool("tide_ops")
    blob = f"{tide.description}\n{(tide.parameters.get('properties') or {}).get('command', {}).get('description', '')}"
    # schema 极短：赶海/cast 提示即可；未命名小鱼细则在 help/手册
    assert "cast" in blob or "dig" in blob or "net" in blob
    assert "未命名小鱼" in manual and ("不能网" in TIDE_HELP or "只能" in TIDE_HELP)


async def _test_curse_eat_sell() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="walkblue-"))
    db = await _boot(tmp)
    from server import game, health, kitchen, marine
    from server.catalog import WALKBLUE_HEX, WALKBLUE_ITEM

    kid, sid = await _enroll(db, "blue@example.com", "钓客")
    async with db.connect() as conn:
        curse = await marine.on_obtain_walkblue(conn, sid)
        await conn.commit()
    assert "腿鱼小咒" in curse or "小咒" in curse, curse
    async with db.connect() as conn:
        ailments = await health.list_ailments(conn, sid)
    assert any(a["key"] == WALKBLUE_HEX for a in ailments), ailments

    async with db.connect() as conn:
        lift = await marine.apply_walkblue_fate(conn, sid, "curse_lift", kind="eat")
        await conn.commit()
    assert "小咒" in lift or "揭" in lift or "散" in lift, lift
    async with db.connect() as conn:
        ailments = await health.list_ailments(conn, sid)
    assert not any(a["key"] == WALKBLUE_HEX for a in ailments), ailments

    async with db.connect() as conn:
        await db.add_item(conn, sid, WALKBLUE_ITEM, 2)
        await conn.commit()

    async with db.connect() as conn:
        eaten = await marine.apply_walkblue_fate(conn, sid, "whisper", kind="eat")
        await conn.commit()
    assert "雾智" in eaten, eaten

    eat_msg = await kitchen.kitchen_ops(kid, "eat 未命名小鱼")
    assert "精力" in eat_msg, eat_msg
    assert "小咒" in eat_msg or "未命名" in eat_msg, eat_msg

    vend_msg = await game.tote_ops(kid, "vend 未命名小鱼 1")
    assert "票" in vend_msg, vend_msg


async def _test_grab_gives_fish() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="walkblue-grab-"))
    db = await _boot(tmp)
    from server import health, marine
    from server.catalog import WALKBLUE_HEX, WALKBLUE_ITEM

    kid, sid = await _enroll(db, "grab@example.com", "捞客")
    payload = {
        "type": "legged_blue_fish",
        "who": "未命名小鱼",
        "voyage_fish": ["fish_mackerel"],
    }
    async with db.connect() as conn:
        await db.add_item(conn, sid, "fish_mackerel", 1)
        now = db.now()
        await conn.execute(
            """
            INSERT INTO voyages (steward_id, route, departed_at, returns_at, status, encounter)
            VALUES (?,?,?,?, 'fish_encounter', ?)
            """,
            (sid, "near", now, now + 600, json.dumps(payload, ensure_ascii=False)),
        )
        await conn.commit()
    msg = await marine.voyage_ops(kid, "grab")
    assert "未命名小鱼" in msg or "抓住" in msg, msg
    async with db.connect() as conn:
        row = await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item=?",
            (sid, WALKBLUE_ITEM),
        )).fetchone()
        ailments = await health.list_ailments(conn, sid)
    assert row and row[0] >= 1, row
    assert any(a["key"] == WALKBLUE_HEX for a in ailments), ailments


async def _test_net_never_picks_walkblue() -> None:
    from server.shaonian import pick_fish_with_fortune

    for tide in ("ebb", "slack", "flood"):
        for cap in (3, 4, 5, 6):
            for _ in range(40):
                assert pick_fish_with_fortune(tide, cap, None) != "walkblue"
                assert pick_fish_with_fortune(tide, cap, "fish_catch") != "walkblue"


def test_curse_eat_sell() -> None:
    asyncio.run(_test_curse_eat_sell())


def test_grab_gives_fish() -> None:
    asyncio.run(_test_grab_gives_fish())


def test_net_never_picks_walkblue() -> None:
    asyncio.run(_test_net_never_picks_walkblue())


def test_help_copy_sync() -> None:
    test_help_and_manual_copy()


if __name__ == "__main__":
    test_walkblue_cast_only_pool()
    test_help_copy_sync()
    test_net_never_picks_walkblue()
    test_curse_eat_sell()
    test_grab_gives_fish()
    print("walkblue tests ok")
