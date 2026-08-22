#!/usr/bin/env python3
"""深坑井壁胜场榜 — pit board 与公开 API 数据。"""
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


async def _seed_pit_logs(conn, sid: int, wins: int, losses: int) -> None:
    from server import db as db_mod
    t = db_mod.now()
    for _ in range(wins):
        await conn.execute(
            "INSERT INTO pit_log (steward_id, kind, outcome, opponent, created_at) VALUES (?,?,?,?,?)",
            (sid, "pit", "win", "测试斗士", t),
        )
    for _ in range(losses):
        await conn.execute(
            "INSERT INTO pit_log (steward_id, kind, outcome, opponent, created_at) VALUES (?,?,?,?,?)",
            (sid, "pit", "lose", "测试斗士", t),
        )


def test_pit_board_ranking_and_threshold() -> None:
    asyncio.run(_test_pit_board_ranking_and_threshold())


async def _test_pit_board_ranking_and_threshold() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="ut-pit-board-"))
    db = await _boot(tmp)
    from server import undertide, undertide_pit as up
    from server import undertide_config as uc

    kid_a, sid_a = await _enroll(db, "pit-a@example.com", "钉墙甲")
    kid_b, sid_b = await _enroll(db, "pit-b@example.com", "钉墙乙")
    kid_c, sid_c = await _enroll(db, "pit-c@example.com", "新手丙")

    async with db.connect() as conn:
        from server import undertide as ut_mod
        for sid in (sid_a, sid_b, sid_c):
            await ut_mod._ensure_ut(conn, sid)
            await conn.execute(
                "UPDATE steward_undertide SET access=1, well_hint=1 WHERE steward_id=?",
                (sid,),
            )
        await _seed_pit_logs(conn, sid_a, 12, 8)
        await _seed_pit_logs(conn, sid_b, 10, 0)
        await _seed_pit_logs(conn, sid_c, 3, 2)
        await conn.commit()

    rows = await up.public_pit_board()
    names = [r["name"] for r in rows]
    assert "钉墙甲" in names and "钉墙乙" in names, names
    assert "新手丙" not in names, names
    assert names.index("钉墙甲") < names.index("钉墙乙"), names

    text = await undertide.undertide_ops(kid_a, "pit board")
    assert "井壁" in text or "赢家" in text, text
    assert "钉墙甲" in text, text
    assert str(uc.PIT_BOARD_MIN_FIGHTS) in text, text

    kid_new, sid_new = await _enroll(db, "pit-new@example.com", "墙外人")
    async with db.connect() as conn:
        from server import undertide as ut_mod
        await ut_mod._ensure_ut(conn, sid_new)
        await conn.execute(
            "UPDATE steward_undertide SET access=1 WHERE steward_id=?",
            (sid_new,),
        )
        await conn.commit()
    outsider = await undertide.undertide_ops(kid_new, "pit board")
    assert "再下坑" in outsider or "0胜" in outsider, outsider


if __name__ == "__main__":
    asyncio.run(_test_pit_board_ranking_and_threshold())
