#!/usr/bin/env python3
"""小橘小剧场：单人流程、头粉双倍好感、工资延后结算。"""
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


async def test_theater_flow() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="theater-"))
    db = await _boot(tmp)
    from server import star, theater

    kid, sid = await _enroll(db, "stage@example.com", "剧场甲")
    try:
        await theater.theater_ops(kid, "看板")
        raise AssertionError("theater should require an active stage show")
    except ValueError as exc:
        assert "剧场不开工" in str(exc), exc

    await star.owner_set_tonight("stage", "great", "", "潮声不会谢幕", "", "")
    await star.star_ops(kid, "粉丝团")
    board = await theater.theater_ops(kid, "看板")
    assert "头粉：好感×2" in board, board

    old_choice, old_random = theater.random.choice, theater.random.random
    theater.random.choice = lambda values: values[0]
    theater.random.random = lambda: 0.2
    try:
        audition = await theater.theater_ops(kid, "试镜")
        assert "报幕员" in audition and "头粉" in audition, audition
        rehearse = await theater.theater_ops(kid, "对戏")
        assert "好感 +4" in rehearse and "头粉双倍" in rehearse, rehearse
        perform = await theater.theater_ops(kid, "演出")
        assert "满堂彩" in perform and "待领 65票" in perform and "好感+10" in perform, perform
    finally:
        theater.random.choice, theater.random.random = old_choice, old_random

    async with db.connect() as conn:
        before_claim = (await (await conn.execute(
            "SELECT tickets FROM stewards WHERE id=?", (sid,)
        )).fetchone())[0]
        affinity = (await (await conn.execute(
            "SELECT score FROM star_theater_affinity WHERE steward_id=?", (sid,)
        )).fetchone())[0]
    assert affinity == 14, affinity
    claim = await theater.theater_ops(kid, "领薪")
    assert "+65票" in claim and "档信+2" in claim and "雾智+3" in claim, claim
    async with db.connect() as conn:
        after_claim = (await (await conn.execute(
            "SELECT tickets FROM stewards WHERE id=?", (sid,)
        )).fetchone())[0]
    assert after_claim == before_claim + 65, (before_claim, after_claim)

    relation = await theater.theater_ops(kid, "关系")
    assert "14/100" in relation and "头粉" in relation, relation


SCRIPT_BODY = (
    "第一幕：南巷口还在放戏。旧收音机里有人叫了一声，碗筷却是空的。"
    "院门旁那杯茶已经凉了，谁也没有再添。"
)


async def test_theater_scripts() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="theater-script-"))
    db = await _boot(tmp)
    from server import config, theater

    kid, sid = await _enroll(db, "script@example.com", "编剧甲")
    guild = await theater.theater_ops(kid, "编剧社")
    assert "常开" in guild and "500" in guild and "750" in guild, guild
    assert "还没投过" in guild, guild

    try:
        await theater.theater_ops(kid, "看板")
        raise AssertionError("board still requires a stage show")
    except ValueError as exc:
        assert "剧场不开工" in str(exc), exc

    posted = await theater.theater_ops(
        kid, f"投稿 潮闻 岸上旧收音机 | {SCRIPT_BODY}"
    )
    assert "#1" in posted and "岸上旧收音机" in posted and "潮闻" in posted, posted

    desk = await theater.theater_ops(kid, "稿件")
    assert "#1 《岸上旧收音机》（投潮闻）待审" in desk, desk

    pending = await theater.owner_pending_scripts()
    assert len(pending) == 1 and pending[0]["title"] == "岸上旧收音机", pending
    assert pending[0]["pitch"] == "tale" and pending[0]["body"] == SCRIPT_BODY

    async with db.connect() as conn:
        tickets_before = (await (await conn.execute(
            "SELECT tickets FROM stewards WHERE id=?", (sid,)
        )).fetchone())[0]
    decided = await theater.owner_decide_script(1, "tale")
    assert "潮闻" in decided["msg"] and decided["payout"] == config.THEATER_SCRIPT_TALE_PAY, decided
    async with db.connect() as conn:
        tickets_after = (await (await conn.execute(
            "SELECT tickets FROM stewards WHERE id=?", (sid,)
        )).fetchone())[0]
    assert tickets_after == tickets_before + 750, (tickets_before, tickets_after)

    try:
        await theater.owner_decide_script(1, "story")
        raise AssertionError("already decided script should block")
    except ValueError as exc:
        assert "处理过" in str(exc), exc

    story = await theater.theater_ops(kid, f"投稿 故事 灰了的裙摆 | {SCRIPT_BODY}")
    assert "故事" in story, story
    paid = await theater.owner_decide_script(2, "story")
    assert paid["payout"] == 500, paid
    async with db.connect() as conn:
        tickets_story = (await (await conn.execute(
            "SELECT tickets FROM stewards WHERE id=?", (sid,)
        )).fetchone())[0]
    assert tickets_story == tickets_after + 500, (tickets_after, tickets_story)

    rejected = await theater.theater_ops(kid, f"投稿 空的旧皮箱 | {SCRIPT_BODY}")
    assert "#3" in rejected, rejected
    bounce = await theater.owner_decide_script(3, "reject", "还缺一场能站住的结尾")
    assert bounce["payout"] == 0 and "退稿" in bounce["msg"], bounce
    async with db.connect() as conn:
        tickets_same = (await (await conn.execute(
            "SELECT tickets FROM stewards WHERE id=?", (sid,)
        )).fetchone())[0]
    assert tickets_same == tickets_story, (tickets_story, tickets_same)

    for i in range(3):
        await theater.theater_ops(kid, f"投稿 待审{i} | {SCRIPT_BODY}")
    try:
        await theater.theater_ops(kid, f"投稿 第四篇 | {SCRIPT_BODY}")
        raise AssertionError("pending cap should block")
    except ValueError as exc:
        assert "待审已经 3" in str(exc), exc
    pulled = await theater.theater_ops(kid, "撤回 4")
    assert "已撤回 #4" in pulled, pulled
    again = await theater.theater_ops(kid, f"投稿 第四篇改投 | {SCRIPT_BODY}")
    assert "第四篇改投" in again, again

    try:
        await theater.theater_ops(kid, "投稿 太短 | 还不够")
        raise AssertionError("short body should block")
    except ValueError as exc:
        assert "太短" in str(exc), exc


def test_theater_mcp_description() -> None:
    from server.mcp_app import mcp
    tool = mcp._tool_manager.get_tool("theater_ops")
    blob = f"{tool.description}\n{(tool.parameters.get('properties') or {}).get('command', {}).get('description', '')}"
    for word in ("试镜", "对戏", "演出", "领薪", "投稿"):
        assert word in blob, word
    # 细则在手册
    import asyncio
    from server import game
    man = asyncio.run(game.relay_manual())
    assert "头粉" in man and "编剧社" in man


def main() -> None:
    asyncio.run(test_theater_flow())
    asyncio.run(test_theater_scripts())
    test_theater_mcp_description()
    print("theater tests ok")


if __name__ == "__main__":
    main()
