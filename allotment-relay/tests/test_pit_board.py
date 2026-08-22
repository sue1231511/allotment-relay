#!/usr/bin/env python3
"""undertide_ops pit board — 深坑决斗场玩家榜。"""
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


async def _unlock(db, sid: int) -> None:
    from server import undertide as ut_mod

    async with db.connect() as conn:
        await ut_mod._ensure_ut(conn, sid)
        await conn.execute(
            "UPDATE steward_undertide SET access=1, well_hint=1 WHERE steward_id=?",
            (sid,),
        )
        await conn.commit()


async def _record(db, sid: int, kind: str, outcome: str, opponent: str = "对手") -> None:
    from server import undertide_pit as up

    async with db.connect() as conn:
        await up.pit_record(conn, sid, kind, outcome, opponent)
        await conn.commit()


def test_pit_board() -> None:
    asyncio.run(_test_pit_board())


async def _test_pit_board() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="ut-pit-board-"))
    db = await _boot(tmp)
    from server import undertide
    from server import undertide_pit as up

    kid_a, sid_a = await _enroll(db, "a@example.com", "安")
    kid_b, sid_b = await _enroll(db, "b@example.com", "乙")
    kid_c, sid_c = await _enroll(db, "c@example.com", "丙")
    await _unlock(db, sid_a)
    await _unlock(db, sid_b)
    await _unlock(db, sid_c)

    empty = await undertide.undertide_ops(kid_a, "pit board")
    assert "墙上还是空的" in empty, empty
    assert "steward_ops board" in empty, empty
    assert "你还没下过坑" in empty, empty

    # 安 3胜1负；乙 2胜0负；丙只有巷斗，不上决斗场榜
    for _ in range(3):
        await _record(db, sid_a, "pit", "win", "退役斗士")
    await _record(db, sid_a, "pit", "lose", "独眼船工")
    await _record(db, sid_b, "pit", "win", "退役斗士")
    await _record(db, sid_b, "pit", "win", "收摊的私盐贩")
    await _record(db, sid_c, "muscle", "win", "路人")
    await _record(db, sid_c, "bounty", "win", "仇人")

    board = await undertide.undertide_ops(kid_a, "pit board")
    assert "墙上的位置" in board, board
    an_pos = board.index("安")
    yi_pos = board.index("乙")
    assert an_pos < yi_pos, board
    assert "3胜1负" in board, board
    assert "2胜0负" in board, board
    assert "丙" not in board, board
    assert "#1/" in board, board

    alias = await undertide.undertide_ops(kid_a, "board")
    assert "墙上的位置" in alias, alias
    listed = await undertide.undertide_ops(kid_a, "pit")
    assert "pit board" in listed, listed
    assert "今晚" in listed or "名单" in listed, listed

    pub = await up.public_pit_board()
    names = [r["name"] for r in pub]
    assert names[:2] == ["安", "乙"], pub
    assert "丙" not in names, pub
    assert pub[0]["wins"] == 3, pub


if __name__ == "__main__":
    test_pit_board()
    print("pit board tests ok")
