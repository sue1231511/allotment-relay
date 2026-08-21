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
    assert "sow_all" in blob or "plant" in blob

    bar = mcp._tool_manager.get_tool("bar_ops")
    bar_blob = f"{bar.description}\n{(bar.parameters.get('properties') or {}).get('command', {}).get('description', '')}"
    assert "洗碗" in bar_blob
    assert "荔栀" in bar_blob
    assert "help" in bar_blob
    assert "duo" not in bar.description.lower() or "不要发明" in bar_blob

    ut = mcp._tool_manager.get_tool("undertide_ops")
    ut_blob = f"{ut.description}\n{(ut.parameters.get('properties') or {}).get('command', {}).get('description', '')}"
    assert "猫猫" in ut_blob
    assert "pit medic" not in ut_blob
    assert "medic" in ut_blob

    alliance = mcp._tool_manager.get_tool("alliance_ops")
    al_blob = f"{alliance.description}\n{(alliance.parameters.get('properties') or {}).get('command', {}).get('description', '')}"
    assert "贡献榜" in al_blob

    manual = mcp._tool_manager.get_tool("relay_manual")
    man_blob = manual.description or ""
    assert "禁止发明" in man_blob or "不要发明" in man_blob or "编指令" in man_blob
    assert "help" in man_blob
    assert "enroll" in man_blob
    assert "无参数" in man_blob

    instructions = mcp.instructions or ""
    assert "board" in instructions
    assert "猫猫" in instructions
    assert "relay_manual" in instructions
    assert "禁止发明" in instructions or "不是聊天沙盒" in instructions


def test_relay_manual_covers_systems() -> None:
    from server import game

    text = asyncio.run(game.relay_manual())
    needles = [
        "sow 1 甘蓝",
        "plot_ops status",
        "camera install",
        "incident",
        "repair",
        "shed erect",
        "commons scan",
        "dove",
        "swap ",
        "market ",
        "brew",
        "shop open",
        "lodge",
        "shaonian",
        "gear upgrade",
        "boss attack",
        "barn erect",
        "mascot adopt",
        "lili summon",
        "clinic treat",
        "undertide_ops help",
        "star_ops",
        "应援",
        "不要猜",
        "sow_all",
        "eat_ops",
        "steward_ops board",
        "alliance_ops board",
        "kitchen_ops eat",
        "bar_ops work",
        "甘蓝种×2",
    ]
    missing = [n for n in needles if n not in text]
    assert not missing, f"relay_manual missing: {missing}"
    assert "steward_sheet" not in text
    assert "relay_manual()" not in text
    assert "duo" not in text


def test_readme_workflow_rules() -> None:
    root = Path(__file__).resolve().parents[2]
    readme = (root / "README.md").read_text(encoding="utf-8")
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    for blob in (readme, agents):
        assert "merge origin/main" in blob
        assert "relay_manual" in blob
        assert "mcp_app.py" in blob
    assert "12 个工具" in readme
    assert "steward_ops" in readme and "plot_ops" in readme and "bar_ops" in readme
    assert "空 command" in readme
    assert "禁止" in readme


def test_register_key_copy_ui() -> None:
    root = Path(__file__).resolve().parents[1]
    keys_js = (root / "server/static/keys.js").read_text(encoding="utf-8")
    css = (root / "server/static/style.css").read_text(encoding="utf-8")
    register_html = (root / "server/templates/register.html").read_text(encoding="utf-8")
    recover_html = (root / "server/templates/recover.html").read_text(encoding="utf-8")
    assert "copyText" in keys_js
    assert "secret-copy" in keys_js
    assert "Authorization: Bearer" in keys_js
    assert "break-all" in css
    assert "pre-wrap" in css
    assert "/static/keys.js" in register_html
    assert "/static/keys.js" in recover_html


def test_bar_ops_help() -> None:
    from server import bar

    text = asyncio.run(bar.bar_ops(0, "help"))
    assert "work 岗位" in text
    assert "cheer" in text
    assert "lodge" in text
    assert "duo" not in text or "没有 duo" in text
    assert "set_mood" not in text or "没有" in text


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
    test_relay_manual_covers_systems()
    test_readme_workflow_rules()
    test_register_key_copy_ui()
    test_bar_ops_help()
    asyncio.run(test_scrump_victim_chronicle())
    asyncio.run(test_cheer_targets_isolated())
    asyncio.run(test_kitchen_vend_chinese_and_incident_hint())
    print("consistency tests ok")


if __name__ == "__main__":
    main()
