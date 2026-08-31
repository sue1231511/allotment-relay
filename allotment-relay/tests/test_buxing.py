#!/usr/bin/env python3
"""守灯人·不醒：灯塔日常与文字灯廊。"""
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
    config.DATA_DIR = tmp; config.DB_PATH = tmp / "relay.db"
    db.DATA_DIR = tmp; db.DB_PATH = tmp / "relay.db"
    await db.init_db()
    key = await db.create_api_key("buxing@example.com")
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], "点灯人", "", "naturalist", "")
    return db, row["id"]


async def test_buxing_flow() -> None:
    db, kid = await _boot(Path(tempfile.mkdtemp(prefix="buxing-")))
    from server import mcp_dispatch

    listing = await mcp_dispatch.visit_bundle(kid, "list")
    assert "守灯人·不醒" in listing and "buxing help" in listing
    visited = await mcp_dispatch.visit_bundle(kid, "buxing visit")
    assert "茶不要钱" in visited and "灯芯" in visited
    tea = await mcp_dispatch.visit_bundle(kid, "buxing tea")
    assert "精力 +" in tea
    assert "今天喝过了" in await mcp_dispatch.visit_bundle(kid, "buxing tea")
    for _ in range(5):
        assert "免费" in await mcp_dispatch.visit_bundle(kid, "buxing tide")
    assert "灯油钱 −3 票" in await mcp_dispatch.visit_bundle(kid, "buxing tide")
    light = await mcp_dispatch.visit_bundle(kid, "buxing light 给妈妈 | 求平安")
    assert "第 1 盏" in light and "精力 +" in light
    gallery = await mcp_dispatch.visit_bundle(kid, "buxing gallery")
    assert "给妈妈点的，求平安" in gallery
    assert "成了就好" in await mcp_dispatch.visit_bundle(kid, "buxing fulfill 1")
    assert "成了。" in await mcp_dispatch.visit_bundle(kid, "buxing gallery")
    assert "灯芯 +5" in await mcp_dispatch.visit_bundle(kid, "buxing entrust 一把旧钥匙")
    assert "灯油钱 −60 票" in await mcp_dispatch.visit_bundle(kid, "buxing watch")
    remembered = await mcp_dispatch.visit_bundle(kid, "buxing remember")
    assert "一把旧钥匙" in remembered and "给妈妈" in remembered
    from server import buxing, game
    s = await game.require_steward(kid, exempt_duty=True)
    async with db.connect() as conn:
        view = await buxing.player_view(conn, s)
        await conn.commit()
    assert view["speaker"] == "不醒"
    assert {row["id"] for row in view["choices"]} >= {"tea", "tide", "light", "gallery", "watch"}
    assert any(row["id"] == 1 for row in view["lights"])


def test_buxing_mcp_description() -> None:
    from server.mcp_app import mcp
    from server.mcp_dispatch import VISIT_HELP
    import asyncio
    from server import game

    tool = mcp._tool_manager.get_tool("visit_ops")
    blob = tool.description + "\n" + ((tool.parameters.get("properties") or {}).get("command", {}).get("description", ""))
    assert "潮生会" in blob
    man = asyncio.run(game.relay_manual())
    assert "守灯人·不醒" in man or "不醒" in man
    assert "buxing" in man or "buxing" in VISIT_HELP
    assert "问潮前 5 次免费" in VISIT_HELP
    assert "灯廊" in VISIT_HELP
    from server.buxing import BUXING_HELP
    assert "立绘对话" in VISIT_HELP
    assert "立绘对话" in BUXING_HELP


def main() -> None:
    asyncio.run(test_buxing_flow()); test_buxing_mcp_description(); print("buxing tests ok")


if __name__ == "__main__": main()
