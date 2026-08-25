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
    assert "tote_ops gifts" in sent or "收礼" in sent, sent

    gifts = await game.tote_ops(recv_kid, "gifts")
    assert "收礼/打赏记录" in gifts, gifts
    assert "送礼人" in gifts, gifts
    assert "甘蓝" in gifts, gifts
    assert "生日快乐" in gifts, gifts

    for alias in ("收礼", "赠礼", "gift", "查礼"):
        listed = await game.tote_ops(recv_kid, alias)
        assert "收礼人" in listed or "甘蓝" in listed, (alias, listed)

    ticket_gift = await game.tote_ops(giver_kid, "送礼 收礼人 票 5")
    assert "工分票" in ticket_gift, ticket_gift

    gifts2 = await game.tote_ops(recv_kid, "收礼")
    assert "5 工分票" in gifts2 or "工分票" in gifts2, gifts2

    sheet = await game.steward_sheet(recv_kid)
    assert "收礼/打赏" in sheet, sheet
    assert "送礼人" in sheet, sheet

    peer = await game.peer_sheet("收礼人")
    assert "最近收礼" in peer or "甘蓝" in peer, peer

    from server.mcp_dispatch import TOTE_HELP
    assert "gifts" in TOTE_HELP, TOTE_HELP
    assert "赠礼" in TOTE_HELP, TOTE_HELP
    assert "收礼" in TOTE_HELP, TOTE_HELP


def test_tote_gifts_name_spaces_and_orphans() -> None:
    asyncio.run(_test_tote_gifts_name_spaces_and_orphans())


async def _test_tote_gifts_name_spaces_and_orphans() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="tote-gifts-space-"))
    db = await _boot(tmp)
    from server import game

    await db.create_api_key("ghost@example.com")
    giver_kid, giver_sid = await _enroll(db, "giver2@example.com", "安安")
    recv_kid, recv_sid = await _enroll(db, "recv2@example.com", "安安 小橘")
    async with db.connect() as conn:
        recv_key = (await (await conn.execute(
            "SELECT key_id FROM stewards WHERE id=?", (recv_sid,)
        )).fetchone())[0]
        assert recv_key == recv_kid
        assert recv_sid != recv_kid, (recv_sid, recv_kid)
        await db.add_item(conn, giver_sid, "crop_kale", 4)
        await conn.commit()

    try:
        await game.tote_ops(giver_kid, "gift 安安 甘蓝 1")
        raise AssertionError("gifting to own first-token name should fail")
    except ValueError as exc:
        assert "自己" in str(exc), exc

    sent = await game.tote_ops(giver_kid, "赠礼 安安 小橘 甘蓝 1 给你")
    assert "已送礼给 安安 小橘" in sent, sent

    found = await game.tote_ops(recv_kid, "赠礼")
    assert "安安 小橘" in found or "甘蓝" in found, found
    assert "给你" in found, found
    satchel = await db.get_satchel(recv_sid)
    assert satchel.get("crop_kale", 0) >= 1, satchel

    async with db.connect() as conn:
        await db.add_item(conn, giver_sid, "crop_beet", 1)
        await conn.commit()
    await game.tote_ops(giver_kid, "gift 安安 小橘 甜菜 1")
    await db.add_chronicle(
        "gift",
        "安安 送礼给 安安 小橘：旧档无 target",
        giver_sid,
        None,
    )
    recovered = await game.tote_ops(recv_kid, "gifts")
    assert "旧档无 target" in recovered, recovered

    from server.mcp_app import mcp
    tote = mcp._tool_manager.get_tool("tote_ops")
    blob = f"{tote.description}\n{(tote.parameters.get('properties') or {}).get('command', {}).get('description', '')}"
    assert "赠礼" in blob
    assert "收礼" in blob


if __name__ == "__main__":
    asyncio.run(_test_tote_gifts_list())
    asyncio.run(_test_tote_gifts_name_spaces_and_orphans())
    print("ok")
