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
    assert "tote_ops gifts" in sent, sent

    sent_log = await game.tote_ops(giver_kid, "赠礼记录")
    assert "赠礼记录" in sent_log, sent_log
    assert "收礼人" in sent_log, sent_log

    gifts = await game.tote_ops(recv_kid, "gifts")
    assert "收礼/打赏记录" in gifts, gifts
    assert "送礼人" in gifts, gifts
    assert "甘蓝" in gifts, gifts
    assert "生日快乐" in gifts, gifts

    # 空 gift / 中文送礼记录 也是查收件箱，避免对方打错指令以为没记录
    via_gift = await game.tote_ops(recv_kid, "gift")
    assert "送礼人" in via_gift and "甘蓝" in via_gift, via_gift
    via_cn = await game.tote_ops(recv_kid, "赠礼")
    assert "送礼人" in via_cn, via_cn
    gifts_cn = await game.tote_ops(recv_kid, "收礼记录")
    assert "收礼/打赏记录" in gifts_cn, gifts_cn

    ticket_gift = await game.tote_ops(giver_kid, "送礼 收礼人 票 5")
    assert "工分票" in ticket_gift, ticket_gift

    gifts2 = await game.tote_ops(recv_kid, "收礼")
    assert "5 工分票" in gifts2 or "工分票" in gifts2, gifts2

    sent_log = await game.tote_ops(giver_kid, "gifts 送出")
    assert "赠礼记录" in sent_log, sent_log
    assert "收礼人" in sent_log, sent_log
    assert "甘蓝" in sent_log, sent_log

    filtered = await game.tote_ops(recv_kid, "gifts 送礼人")
    assert "送礼人" in filtered, filtered
    assert "甘蓝" in filtered, filtered

    # target_id 漏写时，仍应按正文查到
    async with db.connect() as conn:
        await db.add_item(conn, giver_sid, "crop_kale", 1)
        await conn.commit()
    await game.tote_ops(giver_kid, "gift 收礼人 甘蓝 1")
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE chronicle SET target_id=NULL WHERE action IN ('gift', 'gift_inbox') AND target_id=?",
            (recv_sid,),
        )
        await conn.commit()
    recovered = await game.tote_ops(recv_kid, "gifts")
    assert "甘蓝" in recovered, recovered
    assert "送礼人" in recovered, recovered

    async with db.connect() as conn:
        await db.backfill_gift_chronicle_targets(conn)
        await conn.commit()
        row = await (
            await conn.execute(
                "SELECT target_id FROM chronicle WHERE action='gift' AND text LIKE ? ORDER BY id DESC LIMIT 1",
                ("%收礼人%",),
            )
        ).fetchone()
    assert row and int(row[0]) == recv_sid, row

    async with db.connect() as conn:
        await db.add_item(conn, giver_sid, "crop_kale", 1)
        await conn.commit()
    qty_default = await game.tote_ops(giver_kid, "gift 收礼人 甘蓝")
    assert "已送礼给 收礼人" in qty_default, qty_default

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
    assert "送出" in TOTE_HELP, TOTE_HELP
    assert "赠礼记录" in TOTE_HELP, TOTE_HELP
    assert "收礼" in TOTE_HELP or "收件箱" in TOTE_HELP, TOTE_HELP


if __name__ == "__main__":
    asyncio.run(_test_tote_gifts_list())
    print("ok")
