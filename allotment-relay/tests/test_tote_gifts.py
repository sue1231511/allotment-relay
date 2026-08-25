#!/usr/bin/env python3
"""tote_ops gifts — 查收礼记录。"""
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


def test_tote_gifts_list() -> None:
    asyncio.run(_test_tote_gifts_list())


async def _test_tote_gifts_list() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="tote-gifts-"))
    db = await _boot(tmp)
    from server import game

    giver_kid, giver_sid = await _enroll(db, "giver@example.com", "送礼人")
    recv_kid, recv_sid = await _enroll(db, "recv@example.com", "收礼人")

    empty = await game.tote_ops(recv_kid, "gifts")
    assert "还没有人给你送礼" in empty or "打赏" in empty, empty

    async with db.connect() as conn:
        await db.add_item(conn, giver_sid, "crop_kale", 3)
        await conn.commit()

    sent = await game.tote_ops(giver_kid, "gift 收礼人 甘蓝 1 生日快乐")
    assert "已送礼给 收礼人" in sent, sent

    gifts = await game.tote_ops(recv_kid, "gifts")
    assert "收礼/打赏记录" in gifts, gifts
    assert "送礼人" in gifts, gifts
    assert "甘蓝" in gifts or "羽衣甘蓝" in gifts, gifts
    assert "生日快乐" in gifts, gifts
    # 收件箱不应整段复读「甲 送礼给 乙：」
    assert "送礼给 收礼人" not in gifts, gifts

    ticket_gift = await game.tote_ops(giver_kid, "送礼 收礼人 票 5")
    assert "工分票" in ticket_gift, ticket_gift

    gifts2 = await game.tote_ops(recv_kid, "收礼")
    assert "5 工分票" in gifts2 or "工分票" in gifts2, gifts2

    # 考勤逾期：卖货仍锁，收礼收件箱必须仍能查（集市纪事有、tote gifts 却查不到的坑）
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET last_bar_shift_at=0 WHERE id=?", (recv_sid,)
        )
        await conn.commit()

    overdue_gifts = await game.tote_ops(recv_kid, "gifts")
    assert "收礼/打赏记录" in overdue_gifts, overdue_gifts
    assert "送礼人" in overdue_gifts, overdue_gifts

    try:
        await game.tote_ops(recv_kid, "list")
        raise AssertionError("overdue tote list should stay locked")
    except ValueError as exc:
        assert "上工" in str(exc) or "打卡" in str(exc), exc

    from server.mcp_dispatch import TOTE_HELP
    assert "gifts" in TOTE_HELP, TOTE_HELP
    assert "考勤逾期也能查" in TOTE_HELP, TOTE_HELP


if __name__ == "__main__":
    asyncio.run(_test_tote_gifts_list())
    print("ok")
