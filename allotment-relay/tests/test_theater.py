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


def test_theater_mcp_description() -> None:
    from server.mcp_app import mcp
    tool = mcp._tool_manager.get_tool("theater_ops")
    blob = f"{tool.description}\n{(tool.parameters.get('properties') or {}).get('command', {}).get('description', '')}"
    for word in ("试镜", "对戏", "演出", "领薪", "头粉", "不替代"):
        assert word in blob, word


def main() -> None:
    asyncio.run(test_theater_flow())
    test_theater_mcp_description()
    print("theater tests ok")


if __name__ == "__main__":
    main()
