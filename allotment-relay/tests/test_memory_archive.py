#!/usr/bin/env python3
"""“我的 AI”岛上回忆：目录、只读正文、分支快照与 NPC 回看。"""
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
    key = await db.create_api_key("memory-ui@example.com")
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], "回忆管家", "", "naturalist", "")
    return db, key, row["id"]


async def test_memory_archive() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="memory-archive-"))
    db, key, kid = await _boot(tmp)
    from server import memory_archive, story, story_yesterday, steward_dashboard, tale

    empty = await steward_dashboard.fetch_dashboard(key)
    assert empty["memories"] == []

    await story.story_ops(kid, "start cinderella")
    await story.story_ops(kid, "inspect queen")
    await story.story_ops(kid, "search study")
    await story.story_ops(kid, "contact girl")
    await story.story_ops(kid, "prepare backdoor")
    await story.story_ops(kid, "choose escape")

    steward = await db.get_steward_by_key_id(kid)
    tickets_before = steward["tickets"]
    async with db.connect() as conn:
        run = await (await conn.execute(
            """SELECT id, outcome, flags_json FROM steward_story_runs
               WHERE steward_id=? AND story_key='cinderella'""",
            (steward["id"],),
        )).fetchone()
        assert run and run[1] == "双生逃离"

        await tale._ensure_catalog(conn)
        await conn.execute(
            """INSERT INTO steward_tales_done
               (steward_id, tale_key, outcome, completed_at, times)
               VALUES (?, 'memory_tide', 'completed', ?, 1)""",
            (steward["id"], db.now()),
        )
        await conn.execute(
            """INSERT INTO steward_jingshan
               (steward_id, stage, ordered_at, delivered_day, updated_at)
               VALUES (?,4,0,0,?)""",
            (steward["id"], db.now()),
        )
        await conn.execute(
            """INSERT INTO steward_story_outcomes
               (steward_id, story_key, outcome, completed_at)
               VALUES (?, ?, ?, ?)""",
            (steward["id"], story_yesterday.STORY_KEY, story_yesterday.STORY_TITLE, db.now()),
        )
        await conn.commit()

    dashboard = await steward_dashboard.fetch_dashboard(key)
    indexed = {(item["kind"], item["key"]): item for item in dashboard["memories"]}
    assert ("tale", "memory_tide") in indexed
    assert ("story", "cinderella") in indexed
    assert ("story", "yesterday_no_proof") in indexed
    assert ("npc", "jingshan") in indexed
    assert indexed[("story", "cinderella")]["variants"][0]["label"] == "双生逃离"
    assert indexed[("tale", "memory_tide")]["souvenirs"]

    cinderella = await memory_archive.fetch_review(
        key, "story", "cinderella", indexed[("story", "cinderella")]["variants"][0]["id"]
    )
    chapter_titles = [chapter["title"] for chapter in cinderella["chapters"]]
    assert "第一幕：不会行走的王妃" in chapter_titles
    assert "准备：森林后门" in chapter_titles
    assert "第三幕：消失的新娘" not in chapter_titles
    assert cinderella["ending"] == "双生逃离"
    assert cinderella["read_only"] is True

    tide = await memory_archive.fetch_review(key, "tale", "memory_tide")
    assert tide["title"] == "回忆生潮"
    assert len(tide["chapters"]) == 12
    assert tide["souvenirs"]

    yesterday = await memory_archive.fetch_review(key, "story", "yesterday_no_proof")
    assert yesterday["title"] == "昨日无凭"
    assert story_yesterday.ACTIONS[-1]["ending"] in yesterday["chapters"][-1]["text"]

    npc = await memory_archive.fetch_review(key, "npc", "jingshan")
    assert npc["title"] == "幸好还剩一小口"
    assert len(npc["chapters"]) == 4
    assert "四分之一块糕点" in npc["chapters"][-1]["text"]

    steward_after = await db.get_steward_by_key_id(kid)
    assert steward_after["tickets"] == tickets_before

    try:
        await memory_archive.fetch_review(key, "tale", "spring_beyond_mountain")
        raise AssertionError("unfinished tale must not be readable from UI")
    except ValueError as exc:
        assert "尚未收入" in str(exc)

    try:
        await memory_archive.fetch_review("bad_key", "npc", "jingshan")
        raise AssertionError("private memories require a valid API key")
    except ValueError as exc:
        assert "凭证无效" in str(exc)


def test_steward_memory_frontend_hooks() -> None:
    template = (ROOT / "server/templates/steward.html").read_text(encoding="utf-8")
    script = (ROOT / "server/static/steward.js").read_text(encoding="utf-8")
    css = (ROOT / "server/static/style.css").read_text(encoding="utf-8")
    assert "岛上回忆" in template and "memory-modal" in template
    assert "/api/steward/memory" in script
    assert "data-memory-filter" in script and "连续阅读" in script
    assert ".memory-reader" in css and "body.memory-open" in css
    assert ".memory-modal.hidden" in css


def main() -> None:
    asyncio.run(test_memory_archive())
    test_steward_memory_frontend_hooks()
    print("memory archive tests ok")


if __name__ == "__main__":
    main()
