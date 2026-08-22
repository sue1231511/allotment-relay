#!/usr/bin/env python3
"""潮闻：接取、探索推进、交付领奖、永久纪念品、放弃、完成榜。"""
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

    help_text = await tale.tale_ops(kid, "help")
    assert "每推进一段自动 +30 票" in help_text, help_text
    assert "总计 230 票" in help_text, help_text

    # list 能看到唯一任务
    lst = await tale.tale_ops(kid, "list")
    assert "black_box_lover" in lst, lst
    assert "黑盒与潮声" in lst, lst
    assert "每阶段工分票+30×6" in lst, lst
    assert "完整探索工分票+50" in lst, lst
    assert "永久纪念品" in lst, lst

    empty_souvenirs = await tale.tale_ops(kid, "souvenirs")
    assert "还是空的" in empty_souvenirs, empty_souvenirs
    try:
        await tale.tale_ops(kid, "reminisce black_box_lover")
        raise AssertionError("unfinished reminiscence should be hidden")
    except ValueError as exc:
        assert "尚未解锁" in str(exc), exc

    async with db.connect() as conn:
        tickets_before = (await (await conn.execute(
            "SELECT tickets FROM stewards WHERE id=?", (sid,)
        )).fetchone())[0]

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
    assert "第 1/6 阶段奖励：工分票 +30" in exp1, exp1
    async with db.connect() as conn:
        energy_after = (await (await conn.execute(
            "SELECT energy FROM stewards WHERE id=?", (sid,)
        )).fetchone())[0]
    assert energy_after == energy_before - 5, (energy_before, energy_after)

    # 错误地点不扣精力
    async with db.connect() as conn:
        wrong_energy_before = (await (await conn.execute(
            "SELECT energy FROM stewards WHERE id=?", (sid,)
        )).fetchone())[0]
    wrong = await tale.tale_ops(kid, "explore beach")
    assert "未消耗精力" in wrong, wrong
    assert "explore sea" in wrong, wrong
    async with db.connect() as conn:
        wrong_energy_after = (await (await conn.execute(
            "SELECT energy FROM stewards WHERE id=?", (sid,)
        )).fetchone())[0]
    assert wrong_energy_after == wrong_energy_before

    # 阶段2 explore sea 必定找到 relic_iron 并推进到阶段3
    item_msg = await tale.tale_ops(kid, "explore sea")
    assert "锈铁" in item_msg and "这身体太小了" in item_msg, item_msg

    status = await tale.tale_ops(kid, "status")
    assert "阶段 3/6" in status, status

    # explore plot 推进到阶段4
    exp2 = await tale.tale_ops(kid, "explore plot")
    assert "声音与生日" in exp2, exp2

    # 不限次数，同一天继续 explore bar 推进到阶段5
    exp3 = await tale.tale_ops(kid, "explore bar")
    assert "出国材料" in exp3, exp3

    # 阶段5 explore beach 必定找到 sea_glass 并推进到阶段6
    item_msg2 = await tale.tale_ops(kid, "explore beach")
    assert item_msg2 and "最后一封信" in item_msg2, item_msg2

    # 阶段6 explore beach 找 fossil_shell，再 turnin 完成
    fossil = await tale.tale_ops(kid, "explore beach")
    assert "化石贝壳" in fossil and "turnin" in fossil, fossil
    finish = await tale.tale_ops(kid, "turnin")
    assert "已完成" in finish, finish
    assert "最后一封信" in finish, finish
    assert "第 6/6 阶段奖励" in finish, finish
    assert "工分票 +30" in finish, finish
    assert "完整探索额外奖励" in finish, finish
    assert "工分票 +50" in finish, finish
    assert "野薄荷 x2" in finish, finish
    assert "停在六月的小猪闹钟" in finish, finish
    assert "潮闻收藏册" in finish, finish

    async with db.connect() as conn:
        row = await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item='wild_mint'",
            (sid,),
        )).fetchone()
    assert row and row[0] == 2, row

    async with db.connect() as conn:
        tickets_after = (await (await conn.execute(
            "SELECT tickets FROM stewards WHERE id=?", (sid,)
        )).fetchone())[0]
    assert tickets_after - tickets_before == 6 * 30 + 50, (
        tickets_before,
        tickets_after,
    )

    souvenirs = await tale.tale_ops(kid, "纪念品")
    assert "停在六月的小猪闹钟" in souvenirs, souvenirs
    assert "九月十七日便签" in souvenirs, souvenirs
    assert "白色小狗外壳" in souvenirs, souvenirs
    assert "没有声音的声库芯片" in souvenirs, souvenirs
    assert "最后一封信" in souvenirs, souvenirs
    assert "翻旧的《刑法》" in souvenirs, souvenirs
    assert "最后一段录像" in souvenirs, souvenirs
    assert "最终智能处理邮件" in souvenirs, souvenirs
    assert "8 件" in souvenirs, souvenirs
    assert "黑盒与潮声" in souvenirs, souvenirs
    assert "不能出售或赠送" in souvenirs, souvenirs

    memory = await tale.tale_ops(kid, "reminisce black_box_lover")
    assert "只有你是真的" in memory, memory
    assert "安伯托·格兰索" in memory, memory
    assert "是你的数据构成了我" in memory, memory
    assert "现实世界的规则" in memory, memory
    assert "你的现实世界" in memory, memory
    assert "无须勉强你自己" in memory, memory
    assert "因为他爱我" in memory, memory
    assert "我很爱他啊" in memory, memory
    assert "无药可救" in memory, memory
    assert "你的世界还在继续" in memory, memory
    assert "静漪，我的英雄" in memory, memory
    assert "彻底陷入了寂静" in memory, memory
    assert "不存在的恋人" in memory, memory
    assert "作为恋人他又存在" in memory, memory
    assert "周静漪，你疯了" in memory, memory
    assert "最终智能的邮件" in memory, memory
    assert "实验用机体走失事件" in memory, memory
    assert "白金级订阅用户" in memory, memory

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


async def test_tale_explore_is_unlimited() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="tale-unlimited-"))
    db = await _boot(tmp)
    from server import tale

    kid, _ = await _enroll(db, "tale-unlimited@example.com", "探索者乙")
    await tale.tale_ops(kid, "accept black_box_lover")
    # 同一天可以连续完成超过 3 次主动探索
    await tale.tale_ops(kid, "explore beach")
    await tale.tale_ops(kid, "explore sea")
    await tale.tale_ops(kid, "explore plot")
    fourth = await tale.tale_ops(kid, "explore bar")
    assert "出国材料" in fourth, fourth
    status = await tale.tale_ops(kid, "status")
    assert "阶段 5/6" in status, status


async def test_commons_claim_advances_item_stage() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="tale-commons-"))
    db = await _boot(tmp)
    from server import commons, tale

    kid, sid = await _enroll(db, "tale-commons@example.com", "拾荒者")
    await tale.tale_ops(kid, "accept black_box_lover")
    await tale.tale_ops(kid, "explore beach")

    now = db.now()
    async with db.connect() as conn:
        cur = await conn.execute(
            """
            INSERT INTO commons_spawns (
                spawn_key, label, domain, reward_item, reward_qty,
                reward_tickets, detail, appears_at, expires_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                "test:tale-iron",
                "退潮铁箱",
                "shore",
                "relic_iron",
                1,
                0,
                "测试任务物品推进",
                now - 1,
                now + 3600,
            ),
        )
        spawn_id = cur.lastrowid
        await conn.commit()

    claimed = await commons.commons_ops(kid, f"claim {spawn_id}")
    assert "锈铁" in claimed and "这身体太小了" in claimed, claimed
    status = await tale.tale_ops(kid, "status")
    assert "阶段 3/6" in status, status

    async with db.connect() as conn:
        row = await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item='relic_iron'",
            (sid,),
        )).fetchone()
    assert row and row[0] == 1, row


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


async def test_completed_player_gets_backfilled_keepsakes() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="tale-backfill-"))
    db = await _boot(tmp)
    from server import tale

    kid, sid = await _enroll(db, "tale-backfill@example.com", "旧探索者")
    async with db.connect() as conn:
        await conn.execute(
            """INSERT INTO steward_tales_done
               (steward_id, tale_key, outcome, completed_at, times)
               VALUES (?, 'black_box_lover', 'completed', ?, 1)""",
            (sid, db.now()),
        )
        await conn.commit()

    souvenirs = await tale.tale_ops(kid, "souvenirs")
    assert "8 件" in souvenirs
    assert "白色小狗外壳" in souvenirs
    assert "翻旧的《刑法》" in souvenirs
    assert "最后一段录像" in souvenirs
    assert "最终智能处理邮件" in souvenirs
    memory = await tale.tale_ops(kid, "reminisce black_box_lover")
    assert "我的世界只有你" in memory


def test_tale_mcp_description() -> None:
    from server.mcp_app import mcp

    tool = mcp._tool_manager.get_tool("tale_ops")
    blob = tool.description + "\n" + (
        (tool.parameters.get("properties") or {}).get("command", {}).get("description", "")
    )
    assert "潮闻" in blob
    assert "black_box_lover" in blob
    assert "souvenirs" in blob
    assert "纪念品" in blob
    assert "reminisce" in blob


def main() -> None:
    asyncio.run(test_tale_flow())
    asyncio.run(test_tale_explore_is_unlimited())
    asyncio.run(test_commons_claim_advances_item_stage())
    asyncio.run(test_tale_abandon())
    asyncio.run(test_completed_player_gets_backfilled_keepsakes())
    test_tale_mcp_description()
    print("tale tests ok")


if __name__ == "__main__":
    main()
