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

    sent_log = await game.tote_ops(giver_kid, "赠礼记录")
    assert "赠礼记录" in sent_log, sent_log
    assert "收礼人" in sent_log, sent_log

    gifts = await game.tote_ops(recv_kid, "gifts")
    assert "收礼/打赏记录" in gifts, gifts
    assert "送礼人" in gifts, gifts
    assert "甘蓝" in gifts, gifts
    assert "生日快乐" in gifts, gifts

    gifts_cn = await game.tote_ops(recv_kid, "收礼记录")
    assert "收礼/打赏记录" in gifts_cn, gifts_cn

    ticket_gift = await game.tote_ops(giver_kid, "送礼 收礼人 票 5")
    assert "工分票" in ticket_gift, ticket_gift

    gifts2 = await game.tote_ops(recv_kid, "收礼")
    assert "5 工分票" in gifts2 or "工分票" in gifts2, gifts2

    from server.mcp_dispatch import steward_ops
    steward_gifts = await steward_ops(recv_kid, "收礼")
    assert "收礼/打赏记录" in steward_gifts, steward_gifts

    async with db.connect() as conn:
        cur = await conn.execute(
            "SELECT COUNT(*) FROM chronicle WHERE action='gift_inbox' AND target_id=?",
            (recv_sid,),
        )
        inbox = (await cur.fetchone())[0]
    assert inbox >= 2, inbox

    from server.mcp_dispatch import TOTE_HELP
    assert "gifts" in TOTE_HELP, TOTE_HELP
    assert "赠礼记录" in TOTE_HELP, TOTE_HELP
    assert "对方行囊" in TOTE_HELP or "还能收" in TOTE_HELP, TOTE_HELP


def test_gift_rejects_when_peer_stack_full() -> None:
    asyncio.run(_test_gift_rejects_when_peer_stack_full())


async def _test_gift_rejects_when_peer_stack_full() -> None:
    """对方同种货到顶时：拒收并写明是对方满了；送礼方数量不变。"""
    tmp = Path(tempfile.mkdtemp(prefix="tote-gift-full-"))
    db = await _boot(tmp)
    from server import game
    from server.catalog import peer_satchel_full_message

    giver_kid, giver_sid = await _enroll(db, "full-giver@example.com", "雾豆送礼")
    _recv_kid, recv_sid = await _enroll(db, "full-recv@example.com", "雾豆收礼")

    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET satchel_stack_extra=5 WHERE id IN (?,?)",
            (giver_sid, recv_sid),
        )
        await db.add_item(conn, giver_sid, "crop_fogpea", 64)
        await db.add_item(conn, recv_sid, "crop_fogpea", 64)
        await conn.commit()

    try:
        await game.tote_ops(giver_kid, "gift 雾豆收礼 雾豌豆 20")
        raise AssertionError("gift must fail when peer stack is full")
    except ValueError as exc:
        msg = str(exc)
        assert "对方" in msg and "雾豆收礼" in msg, msg
        assert "满了" in msg or "还能再收" in msg, msg
        assert "不是你自己的计数坏了" in msg or "货还在你行囊里" in msg, msg
        # 旧文案会让模型以为是自己的包满了
        assert not msg.startswith("行囊里 雾豌豆"), msg

    sample = peer_satchel_full_message("雾豆收礼", "crop_fogpea", 60, 10, 64)
    assert "还能再收 4" in sample, sample
    assert "改送 ≤4" in sample, sample

    bag = await db.get_satchel(giver_sid)
    assert bag.get("crop_fogpea") == 64, bag
    peer_bag = await db.get_satchel(recv_sid)
    assert peer_bag.get("crop_fogpea") == 64, peer_bag

    # 对方腾出一点空位后，按空位送得进
    async with db.connect() as conn:
        assert await db.take_item(conn, recv_sid, "crop_fogpea", 4)
        await conn.commit()
    ok = await game.tote_ops(giver_kid, "gift 雾豆收礼 雾豌豆 4")
    assert "已送礼给 雾豆收礼" in ok, ok
    bag2 = await db.get_satchel(giver_sid)
    assert bag2.get("crop_fogpea") == 60, bag2


if __name__ == "__main__":
    asyncio.run(_test_tote_gifts_list())
    asyncio.run(_test_gift_rejects_when_peer_stack_full())
    print("ok")
