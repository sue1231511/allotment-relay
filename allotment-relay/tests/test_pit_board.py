#!/usr/bin/env python3
"""undertide_ops pit board — 深坑井壁活人榜。"""
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


async def _open_pit(db, sid: int) -> None:
    from server import undertide as ut_mod

    async with db.connect() as conn:
        await ut_mod._ensure_ut(conn, sid)
        await conn.execute(
            "UPDATE steward_undertide SET access=1, well_hint=1 WHERE steward_id=?",
            (sid,),
        )
        await conn.execute("UPDATE stewards SET tickets=500, health=100, energy=100 WHERE id=?", (sid,))
        await conn.commit()


def test_pit_board_empty_and_ranked() -> None:
    asyncio.run(_test_pit_board_empty_and_ranked())


async def _test_pit_board_empty_and_ranked() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="ut-pit-board-"))
    db = await _boot(tmp)
    from server import undertide
    from server import undertide_pit as pit

    kid_a, sid_a = await _enroll(db, "pit-a@example.com", "深坑甲")
    kid_b, sid_b = await _enroll(db, "pit-b@example.com", "深坑乙")
    await _open_pit(db, sid_a)
    await _open_pit(db, sid_b)

    empty = await undertide.undertide_ops(kid_a, "pit board")
    assert "还没有活人的名字" in empty or "井壁" in empty, empty
    assert "你：还没下过深坑" in empty, empty

    async with db.connect() as conn:
        # 甲：2 胜 1 负（深坑）
        await pit.pit_record(conn, sid_a, "pit", "win", "铁牙")
        await pit.pit_record(conn, sid_a, "pit", "win", "瘦鬼")
        await pit.pit_record(conn, sid_a, "pit", "lose", "老磨")
        # 乙：1 胜（深坑）+ 肌肉胜不进榜
        await pit.pit_record(conn, sid_b, "pit", "win", "铁牙")
        await pit.pit_record(conn, sid_b, "muscle", "win", "街角的人")
        await conn.commit()

    board = await undertide.undertide_ops(kid_a, "pit 榜")
    assert "深坑甲" in board and "深坑乙" in board, board
    assert board.index("深坑甲") < board.index("深坑乙"), board
    assert "2胜1负" in board, board
    assert "井壁 #1" in board, board

    # muscle 胜不该把乙抬过甲
    wall = await undertide.undertide_ops(kid_b, "pit 井壁")
    assert "井壁 #2" in wall, wall

    rows = None
    async with db.connect() as conn:
        rows = await pit.pit_board_rows(conn)
    assert len(rows) == 2
    assert rows[0]["name"] == "深坑甲" and rows[0]["wins"] == 2
    assert rows[1]["name"] == "深坑乙" and rows[1]["wins"] == 1


if __name__ == "__main__":
    asyncio.run(_test_pit_board_empty_and_ranked())
