#!/usr/bin/env python3
"""Received gifts must not list gift + gift_inbox as two rows."""
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


async def _enroll(db, email: str, name: str) -> tuple[str, int, int]:
    key = await db.create_api_key(email)
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], name, "", "naturalist", "")
    async with db.connect() as conn:
        sid = (await (await conn.execute(
            "SELECT id FROM stewards WHERE key_id=?", (row["id"],)
        )).fetchone())[0]
    return key, row["id"], sid


def test_received_gifts_dedupe() -> None:
    asyncio.run(_test_received_gifts_dedupe())


async def _test_received_gifts_dedupe() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="gift-dedupe-"))
    db = await _boot(tmp)
    from server import game
    from server.steward_dashboard import fetch_dashboard

    giver_key, giver_kid, giver_sid = await _enroll(db, "g@example.com", "hui-kk")
    recv_key, recv_kid, recv_sid = await _enroll(db, "r@example.com", "收礼人")

    async with db.connect() as conn:
        await db.add_item(conn, giver_sid, "crop_kale", 2)
        await conn.commit()

    await game.tote_ops(giver_kid, "gift 收礼人 甘蓝 1 潮信贝测试")
    rows = await db.list_received_gifts(recv_sid, 20)
    assert len(rows) == 1, rows
    assert "甘蓝" in (rows[0].get("summary") or rows[0].get("text") or "")

    text = await game.tote_ops(recv_kid, "gifts")
    assert text.count("甘蓝") == 1, text
    assert text.count("潮信贝测试") == 1, text

    dash = await fetch_dashboard(recv_key)
    gifts = dash.get("gifts") or []
    assert len(gifts) == 1, gifts


if __name__ == "__main__":
    test_received_gifts_dedupe()
