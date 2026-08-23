#!/usr/bin/env python3
"""人物故事探索：灰姑娘分支与《昨日无凭》顺序调查、奖励、纪念品。"""
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
    db, kid = await _boot(tmp)
    from server import story

    assert "灰姑娘" in await story.story_ops(kid, "list")
    intro = await story.story_ops(kid, "start cinderella")
    assert "距离午夜只剩 60 分钟" in intro
    try:
        await story.story_ops(kid, "review cinderella")
        raise AssertionError("unfinished story review should not reveal later text")
    except ValueError as exc:
        assert "尚未解锁" in str(exc) and "避免剧透" in str(exc)
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
    assert "工分票 +60、档信 +5、雾智 +5" in ending
    steward = await db.get_steward_by_key_id(kid)
    assert steward["tickets"] == 180
    assert "双生逃离" in await story.story_ops(kid, "archive")
    review_list = await story.story_ops(kid, "review")
    assert "review cinderella" in review_list
    review = await story.story_ops(kid, "review cinderella")
    assert "人物故事全篇回顾 · 《灰姑娘》" in review
    assert "仅重读已经解锁的完整正文" in review
    assert "第一幕：不会行走的王妃" in review
    assert "第二幕：重新开启的舞会" in review
    assert "第五幕：下一位辛德瑞拉" in review
    assert "准备：森林后门" in review
    assert "结局｜双生逃离" in review and "—— 全篇完 ——" in review
    assert "第三幕：消失的新娘" not in review
    steward_after_review = await db.get_steward_by_key_id(kid)
    assert steward_after_review["tickets"] == 180

    replay = await story.story_ops(kid, "start cinderella")
    assert "60 分钟" in replay

    await story.story_ops(kid, "inspect queen")
    await story.story_ops(kid, "search study")
    await story.story_ops(kid, "contact girl")
    await story.story_ops(kid, "prepare backdoor")
    replay_ending = await story.story_ops(kid, "choose escape")
    assert "首次故事结局奖励" not in replay_ending
    steward = await db.get_steward_by_key_id(kid)
    assert steward["tickets"] == 180


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


async def test_yesterday_story_rewards_and_souvenirs() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="story-yesterday-"))
    db, kid = await _boot(tmp)
    from server import story, story_yesterday

    listing = await story.story_ops(kid, "list")
    assert "昨日无凭" in listing and "yesterday_no_proof" in listing
    intro = await story.story_ops(kid, "start yesterday_no_proof")
    assert "explore old_wharf" in intro
    try:
        await story.story_ops(kid, "review yesterday_no_proof")
        raise AssertionError("unfinished linear story review should not reveal later text")
    except ValueError as exc:
        assert "尚未解锁" in str(exc) and "避免剧透" in str(exc)
    status = await story.story_ops(kid, "status")
    assert "调查 0/12" in status and "explore old_wharf" in status

    try:
        await story.story_ops(kid, "explore west_house")
        raise AssertionError("yesterday story should be sequential")
    except ValueError as exc:
        assert "下一步" in str(exc) and "explore old_wharf" in str(exc)

    for action in story_yesterday.ACTIONS[:-1]:
        scene = await story.story_ops(kid, action["command"])
        assert action["title"] in scene
        assert "本幕探索奖励：工分票 +30" in scene
    ending = await story.story_ops(kid, story_yesterday.ACTIONS[-1]["command"])
    assert "探索完成：《昨日无凭》" in ending
    assert "第十二、十三幕探索奖励：工分票 +60" in ending
    assert "工分票 +120" in ending
    assert "旧事见证人" in ending
    assert "褪色的合照" in ending and "未洗出的底片" in ending

    steward = await db.get_steward_by_key_id(kid)
    assert steward["tickets"] == 630
    review_list = await story.story_ops(kid, "review")
    assert "review yesterday_no_proof" in review_list
    review = await story.story_ops(kid, "review yesterday_no_proof")
    assert "人物故事全篇回顾 · 《昨日无凭》" in review
    assert story_yesterday.INTRO in review
    for action in story_yesterday.ACTIONS:
        assert action["title"] in review
        assert action["text"] in review
    assert story_yesterday.ACTIONS[-1]["ending"] in review
    assert "—— 全篇完 ——" in review
    steward_after_review = await db.get_steward_by_key_id(kid)
    assert steward_after_review["tickets"] == 630
    async with db.connect() as conn:
        title = await (await conn.execute(
            "SELECT 1 FROM steward_achievements WHERE steward_id=? AND ach_key='old_story_witness'",
            (steward["id"],),
        )).fetchone()
        assert title
        stages = await (await conn.execute(
            """SELECT COUNT(*) FROM steward_story_stage_rewards
               WHERE steward_id=? AND story_key='yesterday_no_proof'""",
            (steward["id"],),
        )).fetchone()
        assert stages[0] == 13

    souvenirs = await story.story_ops(kid, "souvenirs")
    assert "4 件" in souvenirs
    for item in story_yesterday.SOUVENIRS:
        assert item["name"] in souvenirs
    assert "不能出售或赠送" in souvenirs

    await story.story_ops(kid, "start yesterday_no_proof")
    for action in story_yesterday.ACTIONS:
        replay = await story.story_ops(kid, action["command"])
    assert "首次人物故事奖励" not in replay
    assert "探索奖励" not in replay
    steward = await db.get_steward_by_key_id(kid)
    assert steward["tickets"] == 630


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
    assert "60票" in blob
    assert "昨日无凭" in blob
    assert "start yesterday_no_proof" in blob
    assert "souvenirs" in blob
    assert "review [故事key]" in blob
    assert "完整人物故事" in blob
    assert "不重复发" in blob


def main() -> None:
    asyncio.run(test_escape_and_replay())
    asyncio.run(test_truth_and_other_endings())
    asyncio.run(test_timeout_and_guards())
    asyncio.run(test_yesterday_story_rewards_and_souvenirs())
    test_story_mcp_description()
    print("ok")


if __name__ == "__main__":
    main()
