#!/usr/bin/env python3
"""听潮亭木牌墙 — MCP + 网页 API。"""
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


async def _enroll(db, email: str, name: str) -> tuple[str, int]:
    key = await db.create_api_key(email)
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], name, "", "naturalist", "")
    return key, row["id"]


def test_wall_mcp_and_web() -> None:
    asyncio.run(_test_wall_mcp_and_web())


async def _test_wall_mcp_and_web() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="wall-"))
    db = await _boot(tmp)
    from server import wall

    wall.COOLDOWN_SEC = 0
    key_a, id_a = await _enroll(db, "wall-a@example.com", "亭甲")
    key_b, id_b = await _enroll(db, "wall-b@example.com", "亭乙")

    help_text = await wall.wall_ops(id_a, "help")
    assert "看亭" in help_text and "贴 问事" in help_text
    assert "lounge_ops" in help_text and "forum_ops" in help_text
    assert "潮生会" in help_text or "厅示" in help_text
    assert "/board" in help_text or "全服榜" in help_text

    empty = await wall.wall_ops(id_a, "")
    assert "听潮亭" in empty and "问事" in empty
    assert "还空着" in empty or "木牌" in empty

    posted = await wall.wall_ops(id_a, "贴 问事 温室怎么建 | 先 shed erect 再 sow 棚1")
    assert "已钉 #1" in posted, posted
    assert "温室怎么建" in posted

    listed = await wall.wall_ops(id_a, "问事")
    assert "#1" in listed and "温室怎么建" in listed

    viewed = await wall.wall_ops(id_b, "看 1")
    assert "先 shed erect" in viewed

    replied = await wall.wall_ops(id_b, "回 1 谢了，棚盖好了就能种")
    assert "已回 #1" in replied, replied
    assert "谢了" in replied

    mine = await wall.wall_ops(id_a, "我的")
    assert "#1" in mine and "温室怎么建" in mine

    snap = await wall.public_snapshot()
    assert snap["total"] == 1
    assert snap["threads"][0]["title"] == "温室怎么建"
    assert snap["threads"][0]["replies"] == 1

    thread = await wall.get_thread(1)
    assert thread["body"].startswith("先 shed")
    assert thread["replies_list"][0]["who"] == "亭乙"

    web = await wall.human_create(key_b, "闲话", "今晚雾大", "海边看不清灯塔。")
    assert web["ok"] is True
    assert web["thread"]["board_name"] == "闲话"
    assert web["thread"]["who"].endswith("亭乙")

    idle = await wall.public_snapshot("闲话")
    assert idle["board"] == "idle"
    assert any(t["title"] == "今晚雾大" for t in idle["threads"])

    s = await db.get_steward_by_key_id(id_a)
    async with db.connect() as conn:
        view = await wall.player_view(conn, s)
    assert view["name"] == "听潮亭"
    keys = [t["key"] for t in view["tabs"]]
    assert keys == ["ask", "trade", "idle", "seek", "mine"], keys
    assert view["boards"]["ask"]["threads"], view["boards"]
    assert view["mine"], view
    assert view["mine"][0]["can_tear"] is True
    assert view["title_min"] == wall.TITLE_MIN
    assert view["body_min"] == wall.BODY_MIN
    assert "每天 4 帖" in view["post_note"]

    torn = await wall.wall_ops(id_a, "撕 1")
    assert "已撕下 #1" in torn
    try:
        await wall.get_thread(1)
        raise AssertionError("torn thread still visible")
    except ValueError as exc:
        assert "撕" in str(exc)

    try:
        await wall.wall_ops(id_a, "贴 问事 带链接 | 看 https://spam.example")
        raise AssertionError("link should be rejected")
    except ValueError as exc:
        assert "链接" in str(exc)

    try:
        await wall.wall_ops(id_a, "贴 没有分区")
        raise AssertionError("missing pipe should fail")
    except ValueError as exc:
        assert "标题" in str(exc) or "|" in str(exc) or "用法" in str(exc)


def test_wall_daily_cap_and_mod() -> None:
    asyncio.run(_test_wall_daily_cap_and_mod())


async def _test_wall_daily_cap_and_mod() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="wall-cap-"))
    db = await _boot(tmp)
    from server import config, wall

    _, id_a = await _enroll(db, "cap-a@example.com", "限甲")
    _, id_mod = await _enroll(db, "cap-mod@example.com", "管事")
    config.LOUNGE_MOD_NAMES = ["管事"]

    wall.COOLDOWN_SEC = 0
    long_body = "这是一块足够长的正文用来钉在亭柱上。"
    for i in range(wall.DAILY_THREADS):
        await wall.wall_ops(id_a, f"贴 闲话 第{i}块木牌 | {long_body}{i}")
    try:
        await wall.wall_ops(id_a, f"贴 闲话 多一块 | {long_body}超额")
        raise AssertionError("daily thread cap should trip")
    except ValueError as exc:
        assert "今日已钉" in str(exc), exc

    pinned = await wall.wall_ops(id_mod, "mod pin 1")
    assert "置顶" in pinned
    locked = await wall.wall_ops(id_mod, "mod lock 1")
    assert "锁" in locked
    try:
        await wall.wall_ops(id_a, "回 1 锁了还回")
        raise AssertionError("locked thread should reject replies")
    except ValueError as exc:
        assert "锁" in str(exc)

    await wall.wall_ops(id_mod, "mod unlock 1")
    await wall.wall_ops(id_mod, "mod tear 2")
    snap = await wall.public_snapshot("闲话")
    ids = [t["id"] for t in snap["threads"]]
    assert 2 not in ids
    assert 1 in ids
    assert snap["threads"][0]["pinned"] is True


if __name__ == "__main__":
    test_wall_mcp_and_web()
    test_wall_daily_cap_and_mod()
    print("wall tests ok")
