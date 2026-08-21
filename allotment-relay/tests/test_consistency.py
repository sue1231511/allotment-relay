#!/usr/bin/env python3
"""叙事 / 工具说明 / 逻辑对齐：纪事、cheer 分流、中文岗位、MCP 文案。"""
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


def test_bar_job_aliases() -> None:
    from server.bar_catalog import resolve_bar_job, resolve_bar_period

    assert resolve_bar_job("洗碗") == "dishwasher"
    assert resolve_bar_job("洗碗工") == "dishwasher"
    assert resolve_bar_job("dishwasher") == "dishwasher"
    assert resolve_bar_job("牛郎") == "host"
    assert resolve_bar_job("调酒师") == "bartender"
    assert resolve_bar_job("杂工") == "runner"
    assert resolve_bar_job("迎宾") == "greeter"
    assert resolve_bar_job("服务生") == "server"
    assert resolve_bar_job("没有这个岗") is None
    assert resolve_bar_period("白班") == "day"
    assert resolve_bar_period("dusk") == "day"
    assert resolve_bar_period("夜班") == "night"
    assert resolve_bar_period("night") == "night"


def test_mcp_descriptions() -> None:
    from server.mcp_app import mcp

    plot = mcp._tool_manager.get_tool("plot_ops")
    blob = f"{plot.description}\n{(plot.parameters.get('properties') or {}).get('command', {}).get('description', '')}"
    assert "空 command 看各地块" not in blob
    assert "status" in blob
    assert "30%" in blob

    bar = mcp._tool_manager.get_tool("bar_ops")
    bar_blob = f"{bar.description}\n{(bar.parameters.get('properties') or {}).get('command', {}).get('description', '')}"
    assert "洗碗" in bar_blob
    assert "荔栀" in bar_blob

    steward = mcp._tool_manager.get_tool("steward_ops")
    st_blob = f"{steward.description}\n{(steward.parameters.get('properties') or {}).get('command', {}).get('description', '')}"
    assert "成就" in st_blob

    ut = mcp._tool_manager.get_tool("undertide_ops")
    ut_blob = f"{ut.description}\n{(ut.parameters.get('properties') or {}).get('command', {}).get('description', '')}"
    assert "猫猫" in ut_blob
    assert "pit medic" not in ut_blob
    assert "medic" in ut_blob

    alliance = mcp._tool_manager.get_tool("alliance_ops")
    al_blob = f"{alliance.description}\n{(alliance.parameters.get('properties') or {}).get('command', {}).get('description', '')}"
    assert "贡献榜" in al_blob

    instructions = mcp.instructions or ""
    assert "board" in instructions
    assert "猫猫" in instructions


async def test_scrump_victim_chronicle() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="consist-scrump-"))
    db = await _boot(tmp)
    from server import events

    _, vic_sid = await _enroll(db, "vic@example.com", "邻乙")
    steward = await db.get_steward_by_id(vic_sid)
    async with db.connect() as conn:
        await conn.execute(
            """
            UPDATE parcels SET crop='kale', planted_at=?, tended=1, greenhouse=0,
            grow_target=120 WHERE steward_id=? AND slot=1
            """,
            (db.now() - 10_000, vic_sid),
        )
        result = await events._scrump_victim(conn, steward)
        await conn.commit()
        assert result is not None, "ripe plot should be nibbleable"
        row = await (await conn.execute(
            "SELECT text FROM chronicle WHERE action='scrump' AND target_id=?",
            (vic_sid,),
        )).fetchone()
        assert row, "chronicle missing"
        assert "邻乙" in row[0] and "羽衣甘蓝" in row[0], row[0]


async def test_cheer_targets_isolated() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="consist-cheer-"))
    db = await _boot(tmp)
    from server import bar, undertide

    kid, sid = await _enroll(db, "cheer@example.com", "哄客")
    async with db.connect() as conn:
        ut = await undertide._ensure_ut(conn, sid)
        await conn.execute(
            "UPDATE steward_undertide SET access=1, well_hint=1 WHERE steward_id=?",
            (sid,),
        )
        await conn.commit()

    lizhi = await bar.bar_ops(kid, "cheer 今晚酒香")
    assert "荔栀" in lizhi or "提议" in lizhi, lizhi

    cat = await undertide.undertide_ops(kid, "cheer 账本漂亮")
    assert "说太多" not in cat, cat
    assert "猫猫" in cat or "提议" in cat or "贫嘴" in cat, cat

    again_lizhi = None
    try:
        await bar.bar_ops(kid, "cheer 再哄一次")
        raise AssertionError("lizhi daily cheer should block")
    except ValueError as exc:
        again_lizhi = str(exc)
    assert "说过一次" in again_lizhi, again_lizhi

    try:
        await undertide.undertide_ops(kid, "cheer 再哄猫")
        raise AssertionError("cat daily cheer should block")
    except ValueError as exc:
        assert "说过一次" in str(exc), exc


async def test_kitchen_vend_chinese_and_incident_hint() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="consist-vend-"))
    db = await _boot(tmp)
    from server import catalog, events, kitchen

    kid, sid = await _enroll(db, "cook@example.com", "厨子")
    dish = catalog.dish_item("garlic_oyster", 3)
    async with db.connect() as conn:
        await db.add_item(conn, sid, dish, 1)
        await conn.commit()
    msg = await kitchen.kitchen_ops(kid, "vend 蒜蓉生蚝")
    assert "票" in msg, msg
    async with db.connect() as conn:
        left = await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item=?",
            (sid, dish),
        )).fetchone()
        assert not left or left[0] == 0, left

    hint = await events.incident_ops(kid, "status")
    assert "incident_ops" not in hint, hint
    assert "plot_ops" in hint or "无未处理" in hint or "风平浪静" in hint, hint


def main() -> None:
    test_bar_job_aliases()
    test_mcp_descriptions()
    asyncio.run(test_scrump_victim_chronicle())
    asyncio.run(test_cheer_targets_isolated())
    asyncio.run(test_kitchen_vend_chinese_and_incident_hint())
    print("consistency tests ok")


if __name__ == "__main__":
    main()
