#!/usr/bin/env python3
"""潮闻 — 故事探索任务：接取、探索推进、物品推进、交付领奖、放弃、完成榜。"""
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


async def test_tale_flow() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="tale-flow-"))
    db = await _boot(tmp)
    from server import tale

    kid, sid = await _enroll(db, "tale@example.com", "探索者")

    # list 能看到唯一任务
    lst = await tale.tale_ops(kid, "list")
    assert "black_box_lover" in lst, lst
    assert "黑盒与潮声" in lst, lst

    # accept 后 status 显示阶段1
    accepted = await tale.tale_ops(kid, "accept black_box_lover")
    assert "黑盒与潮声" in accepted, accepted
    assert "你在吗？" in accepted, accepted

    status = await tale.tale_ops(kid, "status")
    assert "阶段 1/6" in status, status

    # explore beach 推进到阶段2（扣精力）
    async with db.connect() as conn:
        energy_before = (await (await conn.execute(
            "SELECT energy FROM stewards WHERE id=?", (sid,)
        )).fetchone())[0]
    exp1 = await tale.tale_ops(kid, "explore beach")
    assert "九月十七日" in exp1, exp1
    async with db.connect() as conn:
        energy_after = (await (await conn.execute(
            "SELECT energy FROM stewards WHERE id=?", (sid,)
        )).fetchone())[0]
    assert energy_after == energy_before - 5, (energy_before, energy_after)

    # 获得 relic_iron 自动推进到阶段3
    async with db.connect() as conn:
        await db.add_item(conn, sid, "relic_iron", 1)
        item_msg = await tale.check_item_progress(conn, sid, "relic_iron", 1)
        await conn.commit()
    assert item_msg and "这身体太小了" in item_msg, item_msg

    status = await tale.tale_ops(kid, "status")
    assert "阶段 3/6" in status, status

    # explore plot 推进到阶段4
    exp2 = await tale.tale_ops(kid, "explore plot")
    assert "声音与生日" in exp2, exp2

    # explore bar 推进到阶段5
    exp3 = await tale.tale_ops(kid, "explore bar")
    assert "出国材料" in exp3, exp3

    # 获得 sea_glass 自动推进到阶段6
    async with db.connect() as conn:
        await db.add_item(conn, sid, "sea_glass", 1)
        item_msg2 = await tale.check_item_progress(conn, sid, "sea_glass", 1)
        await conn.commit()
    assert item_msg2 and "最后一封信" in item_msg2, item_msg2

    # 给 fossil_shell 后 turnin 完成
    async with db.connect() as conn:
        await db.add_item(conn, sid, "fossil_shell", 1)
        await conn.commit()
    finish = await tale.tale_ops(kid, "turnin")
    assert "已完成" in finish, finish
    assert "最后一封信" in finish, finish
    assert "工分票 +30" in finish, finish

    # 重复接取被挡
    try:
        await tale.tale_ops(kid, "accept black_box_lover")
        raise AssertionError("repeat accept should block")
    except ValueError as exc:
        assert "已经完成" in str(exc), exc

    # board 有记录
    board = await tale.tale_ops(kid, "board")
    assert "探索者" in board, board
    assert "完成 1 个" in board, board


async def test_tale_explore_daily_cap() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="tale-cap-"))
    db = await _boot(tmp)
    from server import tale

    kid, _ = await _enroll(db, "tale-cap@example.com", "探索者乙")
    await tale.tale_ops(kid, "accept black_box_lover")
    # 每日 3 次主动探索
    await tale.tale_ops(kid, "explore beach")
    await tale.tale_ops(kid, "explore beach")
    await tale.tale_ops(kid, "explore beach")
    try:
        await tale.tale_ops(kid, "explore beach")
        raise AssertionError("daily cap should block")
    except ValueError as exc:
        assert "今天已经主动探索" in str(exc), exc


async def test_tale_abandon() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="tale-abandon-"))
    db = await _boot(tmp)
    from server import tale

    kid, _ = await _enroll(db, "tale-abandon@example.com", "探索者丙")
    await tale.tale_ops(kid, "accept black_box_lover")
    abandoned = await tale.tale_ops(kid, "abandon black_box_lover")
    assert "放下了" in abandoned, abandoned

    # 放弃后可再接
    re = await tale.tale_ops(kid, "accept black_box_lover")
    assert "黑盒与潮声" in re, re


def test_tale_mcp_description() -> None:
    from server.mcp_app import mcp

    tool = mcp._tool_manager.get_tool("tale_ops")
    blob = tool.description + "\n" + (
        (tool.parameters.get("properties") or {}).get("command", {}).get("description", "")
    )
    assert "潮闻" in blob
    assert "black_box_lover" in blob


def main() -> None:
    asyncio.run(test_tale_flow())
    asyncio.run(test_tale_explore_daily_cap())
    asyncio.run(test_tale_abandon())
    test_tale_mcp_description()
    print("tale tests ok")


if __name__ == "__main__":
    main()
