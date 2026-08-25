#!/usr/bin/env python3
"""tote_ops gifts / 送礼记录 — 双方都能查到赠礼。"""
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


async def _enroll(db, email: str, name: str) -> tuple[int, str, int]:
    key = await db.create_api_key(email)
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], name, "", "naturalist", "")
    async with db.connect() as conn:
        sid = (await (await conn.execute(
            "SELECT id FROM stewards WHERE key_id=?", (row["id"],)
        )).fetchone())[0]
    return row["id"], key, sid


def test_tote_gifts_list() -> None:
    asyncio.run(_test_tote_gifts_list())


async def _test_tote_gifts_list() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="tote-gifts-"))
    db = await _boot(tmp)
    from server import game
    from server import steward_dashboard

    giver_kid, _giver_key, giver_sid = await _enroll(db, "giver@example.com", "送礼人")
    recv_kid, recv_key, recv_sid = await _enroll(db, "recv@example.com", "收礼人")

    empty = await game.tote_ops(recv_kid, "gifts")
    assert "还没有人给你送礼" in empty or "打赏" in empty, empty

    async with db.connect() as conn:
        await db.add_item(conn, giver_sid, "crop_kale", 3)
        await conn.commit()

    sent = await game.tote_ops(giver_kid, "gift 收礼人 甘蓝 1 生日快乐")
    assert "已送礼给 收礼人" in sent, sent
    assert "gifts" in sent or "收礼" in sent, sent

    gifts = await game.tote_ops(recv_kid, "gifts")
    assert "收礼/打赏记录" in gifts, gifts
    assert "送礼人" in gifts, gifts
    assert "甘蓝" in gifts, gifts
    assert "生日快乐" in gifts, gifts
    # 收件箱展示细节，不整句重复「送礼给」
    assert "送礼给 收礼人" not in gifts, gifts

    alias = await game.tote_ops(recv_kid, "赠礼")
    assert "送礼人" in alias and "甘蓝" in alias, alias

    sent_log = await game.tote_ops(giver_kid, "送礼记录")
    assert "送礼记录" in sent_log, sent_log
    assert "收礼人" in sent_log, sent_log
    assert "甘蓝" in sent_log, sent_log

    sent_alias = await game.tote_ops(giver_kid, "sent")
    assert "收礼人" in sent_alias, sent_alias

    ticket_gift = await game.tote_ops(giver_kid, "送礼 收礼人 票 5")
    assert "工分票" in ticket_gift, ticket_gift

    gifts2 = await game.tote_ops(recv_kid, "收礼")
    assert "5 工分票" in gifts2 or "工分票" in gifts2, gifts2

    # 旧纪事缺 target_id 时，正文兜底仍能被收礼人查到
    async with db.connect() as conn:
        await db.add_item(conn, giver_sid, "crop_beet", 1)
        await conn.commit()
    await game.tote_ops(giver_kid, "gift 收礼人 甜菜 1 旧档")
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE chronicle SET target_id=NULL "
            "WHERE action='gift' AND text LIKE '%旧档%' AND actor_id=?",
            (giver_sid,),
        )
        await conn.commit()
    orphan = await game.tote_ops(recv_kid, "gifts")
    assert "旧档" in orphan or "甜菜" in orphan, orphan

    # 考勤逾期仍可查收礼（只读）
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET last_bar_shift_at=0 WHERE id=?",
            (recv_sid,),
        )
        await conn.commit()
    overdue_ok = await game.tote_ops(recv_kid, "gifts")
    assert "送礼人" in overdue_ok, overdue_ok

    from server.mcp_dispatch import TOTE_HELP
    assert "gifts" in TOTE_HELP, TOTE_HELP
    assert "送礼记录" in TOTE_HELP, TOTE_HELP
    assert "赠礼" in TOTE_HELP, TOTE_HELP

    view = await steward_dashboard.fetch_dashboard(recv_key)
    assert view["gifts"], view
    assert any(g["who"] == "送礼人" for g in view["gifts"]), view
    assert all("送礼给" not in g["text"] for g in view["gifts"]), view


if __name__ == "__main__":
    asyncio.run(_test_tote_gifts_list())
    print("ok")
