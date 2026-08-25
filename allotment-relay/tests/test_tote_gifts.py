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
    spaced_kid, spaced_sid = await _enroll(db, "space@example.com", "岸边 的人")

    empty = await game.tote_ops(recv_kid, "gifts")
    assert "还没有人给你送礼" in empty or "打赏" in empty, empty

    async with db.connect() as conn:
        await db.add_item(conn, giver_sid, "crop_kale", 8)
        await conn.commit()

    sent = await game.tote_ops(giver_kid, "gift 收礼人 甘蓝 1 生日快乐")
    assert "已送礼给 收礼人" in sent, sent
    assert "tote_ops gifts" in sent or "收礼" in sent, sent

    gifts = await game.tote_ops(recv_kid, "gifts")
    assert "收礼/打赏记录" in gifts, gifts
    assert "送礼人" in gifts, gifts
    assert "甘蓝" in gifts, gifts
    assert "生日快乐" in gifts, gifts

    alias = await game.tote_ops(recv_kid, "赠礼")
    assert "送礼人" in alias and "甘蓝" in alias, alias
    recv_zh = await game.tote_ops(recv_kid, "收礼")
    assert "甘蓝" in recv_zh, recv_zh

    ticket_gift = await game.tote_ops(giver_kid, "送礼 收礼人 票 5")
    assert "工分票" in ticket_gift, ticket_gift
    gifts2 = await game.tote_ops(recv_kid, "收礼")
    assert "5 工分票" in gifts2 or "工分票" in gifts2, gifts2

    sent_log = await game.tote_ops(giver_kid, "gifts 送出")
    assert "送出的礼" in sent_log, sent_log
    assert "收礼人" in sent_log, sent_log
    assert "甘蓝" in sent_log, sent_log

    filtered = await game.tote_ops(recv_kid, "gifts 送礼人")
    assert "送礼人" in filtered, filtered
    assert "甘蓝" in filtered, filtered

    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET lounge_human_name=? WHERE id=?",
            ("小花", recv_sid),
        )
        await conn.commit()
    nick_gift = await game.tote_ops(giver_kid, "gift 小花·收礼人 甘蓝 1")
    assert "已送礼给 收礼人" in nick_gift, nick_gift
    nick_only = await game.tote_ops(giver_kid, "gift 小花 甘蓝 1")
    assert "已送礼给 收礼人" in nick_only, nick_only

    space_gift = await game.tote_ops(giver_kid, "gift 岸边 的人 甘蓝 1 给带空格的人")
    assert "已送礼给 岸边 的人" in space_gift, space_gift
    spaced_seen = await game.tote_ops(spaced_kid, "赠礼")
    assert "给带空格的人" in spaced_seen, spaced_seen
    assert "送礼人" in spaced_seen, spaced_seen

    async with db.connect() as conn:
        await conn.execute(
            "INSERT INTO chronicle (action, actor_id, target_id, text, created_at) "
            "VALUES ('gift', ?, NULL, ?, ?)",
            (giver_sid, "送礼人 送礼给 收礼人：甘蓝（crop_kale）x1 — 旧账无 target", db.now()),
        )
        await conn.commit()
    legacy = await game.tote_ops(recv_kid, "gifts")
    assert "旧账无 target" in legacy, legacy

    sheet = await game.steward_sheet(recv_kid)
    assert "甘蓝" in sheet, sheet
    assert "tote_ops gifts" in sheet or "赠礼" in sheet, sheet

    from server.mcp_dispatch import TOTE_HELP
    assert "gifts" in TOTE_HELP, TOTE_HELP
    assert "赠礼" in TOTE_HELP, TOTE_HELP
    assert "gifts 送出" in TOTE_HELP, TOTE_HELP
    assert "送礼" in TOTE_HELP, TOTE_HELP


if __name__ == "__main__":
    asyncio.run(_test_tote_gifts_list())
    print("ok")
