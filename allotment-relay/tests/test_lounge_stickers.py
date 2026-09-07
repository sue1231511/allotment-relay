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
    assert items[0]["kind"] == "image"
    assert "variant=display" in items[0]["url"]
    assert "variant=thumb" in items[0]["thumb_url"]

    listed = await lounge.human_list_stickers(key)
    assert any(x["id"] == sid for x in listed)

    # 文件名/MIME 乱了也能靠文件头识别
    stealth = await lounge.human_upload_stickers(
        key, [("photo.bin", "application/octet-stream", png)]
    )
    assert stealth[0]["kind"] == "image"

    gif = bytes.fromhex(
        "47494638396101000100800000ffffff00000021f90401000000002c00000000010001000002024401003b"
    )
    gif_items = await lounge.human_upload_stickers(
        key, [("dance.gif", "application/octet-stream", gif)]
    )
    assert gif_items[0]["kind"] == "gif", gif_items
    gif_path = await stickers.sticker_file_path(gif_items[0]["id"])
    assert gif_path.suffix == ".gif"
    assert stickers.sticker_media_type(gif_path) == "image/gif"
    gif_thumb = stickers.ensure_variant(gif_path, "thumb")
    assert gif_thumb.suffix == ".jpg"
    assert stickers.ensure_variant(gif_path, "display") == gif_path

    from io import BytesIO
    from PIL import Image
    raw_big = BytesIO()
    Image.new("RGB", (400, 400), (200, 40, 40)).save(raw_big, format="PNG")
    big_png = raw_big.getvalue()
    assert len(big_png) > 800
    shrunk = await lounge.human_upload_stickers(key, [("photo.png", "image/png", big_png)])
    shrunk_path = await stickers.sticker_file_path(shrunk[0]["id"])
    assert shrunk_path.stat().st_size < len(big_png)
    with Image.open(shrunk_path) as im:
        assert max(im.size) <= stickers.STICKER_DISPLAY_EDGE

    try:
        await lounge.human_upload_stickers(
            key, [("live.heic", "image/heic", b"\x00\x00\x00\x18ftypheic" + b"\x00" * 32)]
        )
        raise AssertionError("expected heic reject")
    except ValueError as exc:
        assert "HEIC" in str(exc) or "另存" in str(exc), exc

    try:
        await lounge.human_upload_stickers(
            key, [("huge.png", "image/png", png + b"\x00" * (stickers.STICKER_MAX_BYTES + 1))]
        )
        raise AssertionError("expected size reject")
    except ValueError as exc:
        assert "KB" in str(exc) or "大" in str(exc), exc

    await lounge.human_delete_sticker(key, sid)
    after_del = await lounge.human_list_stickers(key)
    assert all(x["id"] != sid for x in after_del)

    msg = await lounge.human_send_sticker(key, gif_items[0]["id"])
    assert msg["msg_kind"] == "sticker", msg
    assert msg["sticker_id"] == gif_items[0]["id"]
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

    path = await stickers.sticker_file_path(gif_items[0]["id"])
    assert path.is_file()
    await lounge.human_delete_sticker(key, gif_items[0]["id"])
    gone = await lounge.human_list_stickers(key)
    assert all(x["id"] != gif_items[0]["id"] for x in gone)
    # 图库删了，聊天室已发的动图文件还在
    assert (await stickers.sticker_file_path(gif_items[0]["id"])).is_file()
    print("lounge stickers ok")


if __name__ == "__main__":
    test_lounge_stickers_human_only()
