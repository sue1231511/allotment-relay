#!/usr/bin/env python3
"""人物故事探索：灰姑娘、时钟、前置证据与五种结局。"""
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
    key = await db.create_api_key("story@example.com")
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], "调查者", "", "naturalist", "")
    return db, row["id"]


async def test_escape_and_replay() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="story-escape-"))
    _, kid = await _boot(tmp)
    from server import story

    assert "灰姑娘" in await story.story_ops(kid, "list")
    intro = await story.story_ops(kid, "start cinderella")
    assert "距离午夜只剩 60 分钟" in intro
    status = await story.story_ops(kid, "status")
    assert "inspect queen" in status and "enter cellar" not in status

    queen = await story.story_ops(kid, "inspect queen")
    assert "空荡的裙摆" in queen and "50 分钟" in queen
    study = await story.story_ops(kid, "search study")
    assert "足部尺寸名单" in study
    girl = await story.story_ops(kid, "contact girl")
    assert "赛琳娜" in girl
    backdoor = await story.story_ops(kid, "prepare backdoor")
    assert "逃生通道" in backdoor
    ending = await story.story_ops(kid, "choose escape")
    assert "结局：双生逃离" in ending
    assert "双生逃离" in await story.story_ops(kid, "archive")

    replay = await story.story_ops(kid, "start cinderella")
    assert "60 分钟" in replay


async def test_truth_and_other_endings() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="story-truth-"))
    _, kid = await _boot(tmp)
    from server import story

    await story.story_ops(kid, "start cinderella")
    await story.story_ops(kid, "search portraits")
    cellar = await story.story_ops(kid, "enter cellar")
    assert "她的双脚早已被王子割下" in cellar
    await story.story_ops(kid, "prepare trap")
    hunt = await story.story_ops(kid, "choose hunt")
    assert "结局：血色密室" in hunt

    await story.story_ops(kid, "start cinderella")
    await story.story_ops(kid, "search study")
    await story.story_ops(kid, "search portraits")
    await story.story_ops(kid, "enter cellar")
    await story.story_ops(kid, "prepare broadcast")
    judgment = await story.story_ops(kid, "choose judgment")
    assert "结局：公开罪恶" in judgment
    archive = await story.story_ops(kid, "archive")
    assert "血色密室" in archive and "公开罪恶" in archive

    await story.story_ops(kid, "start cinderella")
    await story.story_ops(kid, "search study")
    await story.story_ops(kid, "contact girl")
    rescue = await story.story_ops(kid, "choose rescue")
    assert "结局：循环不息" in rescue


async def test_timeout_and_guards() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="story-timeout-"))
    _, kid = await _boot(tmp)
    from server import story

    await story.story_ops(kid, "start cinderella")
    try:
        await story.story_ops(kid, "enter cellar")
        raise AssertionError("cellar should require portraits")
    except ValueError as exc:
        assert "线索不足" in str(exc)

    # 五次有效调查后剩 10 分钟，仍可完成最后一次准备并在零点选择 HE。
    await story.story_ops(kid, "inspect queen")
    await story.story_ops(kid, "search study")
    await story.story_ops(kid, "search portraits")
    await story.story_ops(kid, "enter cellar")
    await story.story_ops(kid, "contact girl")
    last_prepare = await story.story_ops(kid, "prepare backdoor")
    assert "距离午夜：0 分钟" in last_prepare
    ending = await story.story_ops(kid, "choose escape")
    assert "结局：双生逃离" in ending

    # 归零后若不选择已解锁结局、还继续调查，才会错过午夜。
    await story.story_ops(kid, "start cinderella")
    await story.story_ops(kid, "inspect queen")
    await story.story_ops(kid, "search study")
    await story.story_ops(kid, "search portraits")
    await story.story_ops(kid, "enter cellar")
    await story.story_ops(kid, "contact girl")
    await story.story_ops(kid, "prepare trap")
    timeout = await story.story_ops(kid, "prepare backdoor")
    assert "结局：绝望降临" in timeout


def test_story_mcp_description() -> None:
    from server.mcp_app import mcp
    tool = mcp._tool_manager.get_tool("story_ops")
    blob = tool.description + "\n" + (
        (tool.parameters.get("properties") or {}).get("command", {}).get("description", "")
    )
    assert "灰姑娘" in blob
    assert "start cinderella" in blob
    assert "choose escape" in blob
    assert "空 command=list" in blob


def main() -> None:
    asyncio.run(test_escape_and_replay())
    asyncio.run(test_truth_and_other_endings())
    asyncio.run(test_timeout_and_guards())
    test_story_mcp_description()
    print("ok")


if __name__ == "__main__":
    main()
