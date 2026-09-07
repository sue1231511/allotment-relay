#!/usr/bin/env python3
"""heart_ops — 日常心意。"""
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


async def _enroll(db, email: str, name: str):
    key = await db.create_api_key(email)
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], name, "", "naturalist", "")
    s = await db.get_steward_by_key_id(row["id"])
    async with db.connect() as conn:
        await conn.execute("UPDATE stewards SET tickets=500 WHERE id=?", (s["id"],))
        await conn.commit()
    return row["id"], int(s["id"])


def test_heart_send_reply_return() -> None:
    asyncio.run(_test())


async def _test() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="heart-ops-"))
    db = await _boot(tmp)
    from server import heart

    kid, sid = await _enroll(db, "heart@example.com", "心意官")
    help_text = await heart.heart_ops(kid, "help")
    assert "heart_ops" in help_text or "心意" in help_text, help_text

    sent = await heart.heart_ops(kid, "送 🧋 | 午后奶茶 | 窗边 | 12 | 记得喝水")
    assert "#" in sent and ("送" in sent or "心意" in sent), sent

    snap = await heart.snapshot(sid)
    assert len(snap["pending"]) == 1, snap
    gid = int(snap["pending"][0]["id"])

    opened = await heart.open_card(sid, gid)
    assert opened["status"] in ("opened", "kept"), opened

    replied = await heart.reply_card(sid, gid, "收到啦，谢谢")
    assert "收到啦" in (replied.get("reply_text") or ""), replied

    ret = await heart.send_as_human(
        sid, emoji="🍰", title="回你蛋糕", scene="桌边", tickets=8, note="也想你"
    )
    assert ret["from_role"] == "human", ret
    rid = int(ret["id"])
    assert ret["status"] == "pending", ret

    looked = await heart.heart_ops(kid, f"看 {rid}")
    assert "待拆" in looked and "拆" in looked, looked
    still = await heart.snapshot(sid)
    assert any(c["id"] == rid and c["status"] == "pending" for c in still["pending"]), still

    unwrapped = await heart.heart_ops(kid, f"拆 {rid}")
    assert "已拆开" in unwrapped and "红点" in unwrapped, unwrapped
    after = await heart.snapshot(sid)
    assert not any(c["id"] == rid for c in after["pending"]), after
    assert any(c["id"] == rid and c["status"] == "opened" for c in after["album"]), after

    try:
        await heart.heart_ops(kid, f"拆 {gid}")
        raise AssertionError("expected unwrap of own gift to fail")
    except ValueError as exc:
        assert "人类" in str(exc) or "上手页" in str(exc), exc

    listed = await heart.heart_ops(kid, "列表")
    assert "待你拆" in listed and "heart_ops 拆" in listed, listed

    await heart.heart_ops(kid, "送 ☕ | 第二杯 | 阳台 | 5")
    await heart.heart_ops(kid, "送 🌙 | 第三份 | 廊下 | 5")
    try:
        await heart.heart_ops(kid, "送 ⭐ | 第四份 | 屋顶 | 5")
        raise AssertionError("expected daily limit")
    except ValueError as exc:
        assert "3" in str(exc) or "满" in str(exc), exc

    try:
        await heart.heart_ops(kid, "送 🍕 | 披萨 | 厨房 | 10")
        raise AssertionError("expected invalid emoji")
    except ValueError as exc:
        assert "预设" in str(exc) or "外观" in str(exc), exc

    album = await heart.heart_ops(kid, "册")
    assert "午后奶茶" in album or "心意" in album or "#" in album, album


if __name__ == "__main__":
    test_heart_send_reply_return()
    print("ok")
