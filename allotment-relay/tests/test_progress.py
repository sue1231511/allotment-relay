#!/usr/bin/env python3
"""成就称呼 + 等级里程碑奖励。"""
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


def test_knobs() -> None:
    from server.progress import (
        ACHIEVEMENTS, LEVEL_REWARDS, display_title, format_reward, resolve_achievement,
    )
    from server.ranks import level_from_xp, xp_to_reach

    assert "scrump" in ACHIEVEMENTS
    assert ACHIEVEMENTS["scrump"]["name"] == "逾篱客"
    assert resolve_achievement("逾篱手") == "scrump"
    assert resolve_achievement("顺手牵菜") == "scrump"
    assert resolve_achievement("逾篱客") == "scrump"
    assert resolve_achievement("有屋的") == "hut"
    assert 5 in LEVEL_REWARDS and 8 in LEVEL_REWARDS
    assert "潮柜" in format_reward(8)
    assert level_from_xp(120) == 3
    assert xp_to_reach(4) == 216
    assert display_title({"xp": 120, "worn_title": ""}) == "岸民"
    assert display_title({"xp": 120, "worn_title": "scrump"}) == "逾篱客"


def test_level_gifts_and_titles() -> None:
    asyncio.run(_test_level_gifts_and_titles())


async def _test_level_gifts_and_titles() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="progress-"))
    db = await _boot(tmp)
    from server import game, progress, ranks

    kid, sid = await _enroll(db, "p@example.com", "岸测")
    s = await db.get_steward_by_id(sid)
    assert int(s["reward_level"]) == ranks.level_from_xp(s["xp"]) == 3
    tickets0 = int(s["tickets"])

    sheet = await game.steward_sheet(kid)
    assert "称呼" in sheet, sheet
    s = await db.get_steward_by_id(sid)
    assert int(s["tickets"]) == tickets0, "sheet must not dump catch-up gifts on a new enroll"
    assert int(s["reward_level"]) == 3

    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET xp=?, hut_built=1 WHERE id=?",
            (ranks.xp_to_reach(5), sid),
        )
        await conn.commit()

    listed = await progress.progress_ops(kid, "成就")
    assert "升级礼" in listed or "份地手" in listed or "站稳了" in listed, listed
    assert "棚主" in listed, listed
    s = await db.get_steward_by_id(sid)
    assert int(s["reward_level"]) >= 5
    assert int(s["tickets"]) > tickets0
    satchel = await db.get_satchel(sid)
    assert satchel.get("seed_kale", 0) >= 2, satchel

    worn = await progress.progress_ops(kid, "称呼 有屋的")
    assert "棚主" in worn, worn
    s = await db.get_steward_by_id(sid)
    assert s["worn_title"] == "hut"
    peer = await game.peer_sheet("岸测")
    assert "棚主" in peer, peer

    off = await progress.progress_ops(kid, "称呼 卸")
    assert "岸民" in off or "份地手" in off, off

    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET reward_level=0, xp=? WHERE id=?",
            (ranks.xp_to_reach(8), sid),
        )
        await conn.commit()
    s = await db.get_steward_by_id(sid)
    extra0 = int(s.get("cabinet_extra") or 0)
    async with db.connect() as conn:
        conn.row_factory = __import__("aiosqlite").Row
        n = await progress.grant_level_rewards(conn, dict(s))
        await conn.commit()
    assert n == 0, "reward_level 0 should grandfather to current level"
    s = await db.get_steward_by_id(sid)
    assert int(s["reward_level"]) == ranks.level_from_xp(s["xp"])
    assert int(s.get("cabinet_extra") or 0) == extra0


def main() -> None:
    test_knobs()
    asyncio.run(_test_level_gifts_and_titles())
    print("progress tests ok")


if __name__ == "__main__":
    main()
