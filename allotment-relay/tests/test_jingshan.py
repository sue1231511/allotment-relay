#!/usr/bin/env python3
"""何敬山：初识、商船糕点委托、送货与后续探索记录。"""
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
    key = await db.create_api_key("jingshan@example.com")
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], "送货人", "", "naturalist", "")
    return db, row["id"]


async def test_jingshan_flow() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="jingshan-"))
    db, kid = await _boot(tmp)
    from server import mcp_dispatch, npc

    listing = await mcp_dispatch.visit_bundle(kid, "list")
    assert "何敬山" in listing and "jingshan visit / order / deliver" in listing, listing

    # 中文固定 NPC 入口也进入同一条有状态的小事件。
    first = await npc.npc_ops(kid, "visit 何敬山")
    assert "第一次见到何敬山" in first, first
    assert "人物记录：何敬山" in first, first
    assert "jingshan order" in first, first
    for hidden in ("苏月琴", "前三十年", "后三十年", "吃不了"):
        assert hidden not in first, first

    status = await mcp_dispatch.visit_bundle(kid, "jingshan status")
    assert "jingshan order" in status, status

    ordered = await mcp_dispatch.visit_bundle(kid, "jingshan order")
    assert "价格不低的糕点" in ordered, ordered
    assert "何敬山自己付" in ordered, ordered
    assert "jingshan deliver" in ordered, ordered
    assert "前三十年" not in ordered, ordered

    async with db.connect() as conn:
        before = (await (await conn.execute(
            "SELECT satiety FROM stewards WHERE key_id=?", (kid,)
        )).fetchone())[0]

    delivered = await mcp_dispatch.visit_bundle(kid, "jingshan deliver")
    for text in (
        "给我老伴买的",
        "年轻时候她喜欢这个",
        "那时候买不起",
        "她现在吃不了",
        "前三十年是没钱买",
        "后三十年是有钱了，人吃不了了",
        "什么都有时候",
        "别浪费了，好东西",
        "饱食 +2",
    ):
        assert text in delivered, delivered

    async with db.connect() as conn:
        after = (await (await conn.execute(
            "SELECT satiety FROM stewards WHERE key_id=?", (kid,)
        )).fetchone())[0]
    assert after == before + 2, (before, after)

    try:
        await mcp_dispatch.visit_bundle(kid, "jingshan revisit")
        raise AssertionError("same-day follow-up should wait")
    except ValueError as exc:
        assert "换一个游戏日" in str(exc), exc

    # 模拟时间已过去，再触发院中四分之一块糕点的后续。
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE steward_jingshan SET delivered_day=?",
            (db.day_id() - 1,),
        )
        await conn.commit()

    later = await mcp_dispatch.visit_bundle(kid, "jingshan revisit")
    for text in (
        "苏月琴坐在院子里",
        "四分之一块糕点",
        "少吃又不是不吃",
        "把自己的茶推给她",
        "年轻的时候，他们总觉得以后还有很多机会",
        "幸好，还剩下一小口",
    ):
        assert text in later, later

    remembered = await mcp_dispatch.visit_bundle(kid, "jingshan remember")
    assert "探索记录：幸好还剩一小口" in remembered, remembered
    assert "后来真的有了以后" in remembered, remembered

    async with db.connect() as conn:
        state = await (await conn.execute(
            "SELECT stage FROM steward_jingshan"
        )).fetchone()
        chronicle_count = (await (await conn.execute(
            "SELECT COUNT(*) FROM chronicle WHERE action='jingshan'"
        )).fetchone())[0]
    assert state and state[0] == 4, state
    assert chronicle_count == 4, chronicle_count


def test_jingshan_mcp_description() -> None:
    from server.mcp_app import mcp
    from server import game

    tool = mcp._tool_manager.get_tool("visit_ops")
    blob = tool.description + "\n" + (
        (tool.parameters.get("properties") or {}).get("command", {}).get("description", "")
    )
    for text in ("何敬山", "jingshan visit", "order", "deliver", "revisit"):
        assert text in blob, blob
    # 苏月琴说明在手册，不塞进 MCP schema
    import asyncio
    manual = asyncio.run(game.relay_manual())
    assert "苏月琴不是单独 NPC" in manual


def main() -> None:
    asyncio.run(test_jingshan_flow())
    test_jingshan_mcp_description()
    print("jingshan tests ok")


if __name__ == "__main__":
    main()
