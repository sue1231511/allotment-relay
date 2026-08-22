#!/usr/bin/env python3
"""全服聊天室 — MCP + 网页 API。"""
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


def test_lounge_mcp_and_web() -> None:
    asyncio.run(_test_lounge_mcp_and_web())


async def _test_lounge_mcp_and_web() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="lounge-"))
    db = await _boot(tmp)
    from server import lounge

    key = await db.create_api_key("chat@example.com")
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], "聊天测试", "", "naturalist", "")

    help_text = await lounge.lounge_ops(row["id"], "help")
    assert "scan" in help_text and "say" in help_text

    scan_empty = await lounge.lounge_ops(row["id"], "")
    assert "全服聊天室公约" in scan_empty
    assert "完全免费" in scan_empty
    assert "bug" in scan_empty.lower() or "异常" in scan_empty

    await lounge.lounge_ops(row["id"], "say 温室要 shed erect")
    await asyncio.sleep(lounge.LOUNGE_COOLDOWN_SEC + 1)
    web_msg = await lounge.human_post(key, "人类也来答疑")
    assert web_msg["kind"] == "人类"
    assert web_msg["who"] == "聊天测试"

    msgs = await lounge.list_messages()
    assert len(msgs) == 2
    assert msgs[0]["source"] == "mcp"
    assert msgs[1]["source"] == "web"

    pinned = lounge.pinned_notice("https://example.com/register")
    assert "虚构" in pinned
    assert "example.com/register" in pinned
    assert "bug" in pinned.lower() or "异常" in pinned

    try:
        await lounge.human_post(key, "http://spam.example")
        raise AssertionError("should block links")
    except ValueError as exc:
        assert "链接" in str(exc)
