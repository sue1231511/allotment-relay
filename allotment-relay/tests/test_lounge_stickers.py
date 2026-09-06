#!/usr/bin/env python3
"""聊天室表情包：人类可上传发送，AI scan 不可见。"""
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


def test_lounge_stickers_human_only() -> None:
    asyncio.run(_run())


async def _run() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="lounge-stickers-"))
    db = await _boot(tmp)
    from server import lounge, lounge_stickers as stickers

    key = await db.create_api_key("sticker@example.com")
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], "贴纸测", "", "naturalist", "")

    png = bytes([
        0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x00, 0x00, 0x0D,
        0x49, 0x48, 0x44, 0x52, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
        0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53, 0xDE, 0x00, 0x00, 0x00,
        0x0C, 0x49, 0x44, 0x41, 0x54, 0x08, 0xD7, 0x63, 0xF8, 0xCF, 0xC0, 0x00,
        0x00, 0x00, 0x03, 0x00, 0x01, 0x00, 0x05, 0xFE, 0xD4, 0xEF, 0x00, 0x00,
        0x00, 0x00, 0x49, 0x45, 0x4E, 0x44, 0xAE, 0x42, 0x60, 0x82,
    ])
    items = await lounge.human_upload_stickers(key, [("a.png", "image/png", png)])
    assert len(items) == 1, items
    sid = items[0]["id"]
    assert f"/api/lounge/stickers/{sid}/file" in items[0]["url"]

    listed = await lounge.human_list_stickers(key)
    assert any(x["id"] == sid for x in listed)

    msg = await lounge.human_send_sticker(key, sid)
    assert msg["msg_kind"] == "sticker", msg
    assert msg["sticker_id"] == sid
    assert msg.get("sticker_url")

    human_feed = await lounge.human_list_messages(key)
    assert any(m.get("msg_kind") == "sticker" for m in human_feed["messages"])

    ai_msgs = await lounge.list_messages(
        booth_key="",
        viewer_id=row["id"],
        include_stickers=False,
    )
    assert all(m.get("msg_kind") != "sticker" for m in ai_msgs)

    human_msgs = await lounge.list_messages(
        booth_key="",
        viewer_id=row["id"],
        include_stickers=True,
    )
    assert any(m.get("msg_kind") == "sticker" for m in human_msgs)

    scan = await lounge.lounge_ops(row["id"], "scan")
    assert "/api/lounge/stickers/" not in scan
    assert "最近消息" in scan or "最近" in scan

    path = await stickers.sticker_file_path(sid)
    assert path.is_file()
    print("lounge stickers ok")


if __name__ == "__main__":
    test_lounge_stickers_human_only()
