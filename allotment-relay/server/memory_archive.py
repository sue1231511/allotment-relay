"""“我的 AI”网页使用的只读岛上回忆档案。"""
from __future__ import annotations

import json
from typing import Any

import aiosqlite

from . import db, jingshan, story, story_tomorrow, story_yesterday, tale


TALE_BLURBS = {
    "black_box_lover": "海边的黑盒、被留下的声音与一段跨过潮声的陪伴。",
    "memory_tide": "一个等待女儿回家的老人，以及记忆深处没有消失的人。",
    "spring_beyond_mountain": "两个姐妹、一双总在忙碌的手，和终于走到山外的春天。",
    "missing_pages": "一位岛上医生不曾写下的八年，和后来人终于放下的追问。",
    "asking_around": "一个黄毛青年、一次次靠岸的船，和始终没有问出口的话。",
    "mr_ke": "杂货铺里的克太太与克先生，以及一百多年后仍被留下的那个人。",
    "tonight_damp": "雨后林子里刚醒的人，以及他始终觉得自己只是刚刚回家。",
    "unhappy_service": "仓库最角落的问题机，以及一句很不高兴为您服务。",
}

LINEAR_STORY_MODULES = {
    story_yesterday.STORY_KEY: story_yesterday,
    story_tomorrow.STORY_KEY: story_tomorrow,
}

LINEAR_STORY_BLURBS = {
    story_yesterday.STORY_KEY: "旧照片、两枚贝壳，以及一段被两个人共同遗忘的往事。",
    story_tomorrow.STORY_KEY: "林雾、两箱东西，以及一扇贴满纸条的门。",
}


def _keepsakes(rewards: dict[str, Any]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    if rewards.get("souvenir"):
        items.append(rewards["souvenir"])
    items.extend(rewards.get("keepsakes") or [])
    return [
        {
            "name": str(item.get("name") or "纪念品"),
            "emoji": str(item.get("emoji") or "◌"),
            "description": str(item.get("description") or ""),
        }
        for item in items
    ]


def _entry(
    *,
    kind: str,
    key: str,
    title: str,
    blurb: str,
    completed_at: int,
    chapter_count: int,
    ending: str = "",
    souvenirs: list[dict[str, str]] | None = None,
    variants: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "key": key,
        "title": title,
        "blurb": blurb,
        "completed_at": int(completed_at or 0),
        "chapter_count": int(chapter_count),
        "ending": ending,
        "souvenirs": souvenirs or [],
        "variants": variants or [],
        "reviewable": True,
    }


async def list_memories(
    conn: aiosqlite.Connection, steward_id: int
) -> list[dict[str, Any]]:
    """只列已经完成的内容；未完成与未遇见内容不会泄露。"""
    conn.row_factory = aiosqlite.Row
    memories: list[dict[str, Any]] = []

    catalog = await tale._catalog(conn)
    tale_rows = await (await conn.execute(
        """SELECT tale_key, completed_at FROM steward_tales_done
           WHERE steward_id=? AND outcome='completed'
           ORDER BY completed_at DESC""",
        (steward_id,),
    )).fetchall()
    for row in tale_rows:
        item = catalog.get(row["tale_key"])
        if not item:
            continue
        achievement = (item.get("rewards") or {}).get("achievement") or {}
        memories.append(_entry(
            kind="tale",
            key=item["key"],
            title=item["title"],
            blurb=TALE_BLURBS.get(item["key"], "一段已经走完、可以重新翻开的潮闻。"),
            completed_at=row["completed_at"],
            chapter_count=len(_tale_chapters(item)),
            ending=str(achievement.get("name") or "完整探索"),
            souvenirs=_keepsakes(item.get("rewards") or {}),
        ))

    outcome_rows = await (await conn.execute(
        """SELECT story_key, outcome, completed_at FROM steward_story_outcomes
           WHERE steward_id=? ORDER BY completed_at DESC""",
        (steward_id,),
    )).fetchall()
    outcomes: dict[str, list[aiosqlite.Row]] = {}
    for row in outcome_rows:
        outcomes.setdefault(row["story_key"], []).append(row)

    run_rows = await (await conn.execute(
        """SELECT id, story_key, outcome, flags_json, completed_at
           FROM steward_story_runs WHERE steward_id=?
           ORDER BY completed_at DESC, id DESC""",
        (steward_id,),
    )).fetchall()
    runs: dict[str, list[aiosqlite.Row]] = {}
    for row in run_rows:
        runs.setdefault(row["story_key"], []).append(row)

    if story.STORY_KEY in outcomes:
        variants: list[dict[str, Any]] = []
        seen: set[str] = set()
        for run in runs.get(story.STORY_KEY, []):
            if run["outcome"] in seen:
                continue
            seen.add(run["outcome"])
            variants.append({
                "id": str(run["id"]),
                "label": run["outcome"],
                "completed_at": run["completed_at"],
            })
        for old in outcomes[story.STORY_KEY]:
            if old["outcome"] in seen:
                continue
            variants.append({
                "id": f"legacy:{old['outcome']}",
                "label": f"{old['outcome']} · 旧结局档案",
                "completed_at": old["completed_at"],
            })
        latest = outcomes[story.STORY_KEY][0]
        latest_flags = set(json.loads(runs[story.STORY_KEY][0]["flags_json"] or "[]")) if runs.get(story.STORY_KEY) else set()
        memories.append(_entry(
            kind="story",
            key=story.STORY_KEY,
            title=story.STORY_TITLE,
            blurb="水晶鞋、失踪的新娘，以及午夜前真正发生过的选择。",
            completed_at=latest["completed_at"],
            chapter_count=(2 + sum(
                1 for action in story.ACTIONS.values() if action["flag"] in latest_flags
            )) if latest_flags else 0,
            ending=" · ".join(row["outcome"] for row in outcomes[story.STORY_KEY]),
            variants=variants,
        ))

    for story_key, mod in LINEAR_STORY_MODULES.items():
        if story_key not in outcomes:
            continue
        latest = outcomes[story_key][0]
        extra_ending = 1 if any(action.get("ending") for action in mod.ACTIONS) else 0
        memories.append(_entry(
            kind="story",
            key=mod.STORY_KEY,
            title=mod.STORY_TITLE,
            blurb=LINEAR_STORY_BLURBS.get(mod.STORY_KEY, "一段已经走完、可以重新翻开的人物故事。"),
            completed_at=latest["completed_at"],
            chapter_count=1 + len(mod.ACTIONS) + extra_ending,
            ending=mod.STORY_TITLE,
            souvenirs=[
                {"name": item["name"], "emoji": item["emoji"], "description": item["desc"]}
                for item in mod.SOUVENIRS
            ],
            variants=[{"id": "canonical", "label": "完整故事", "completed_at": latest["completed_at"]}],
        ))

    jingshan_row = await (await conn.execute(
        """SELECT stage, updated_at FROM steward_jingshan
           WHERE steward_id=? AND stage>=4""",
        (steward_id,),
    )).fetchone()
    if jingshan_row:
        memories.append(_entry(
            kind="npc",
            key="jingshan",
            title="幸好还剩一小口",
            blurb="何敬山、苏月琴和一盒迟到了很多年的糕点。",
            completed_at=jingshan_row["updated_at"],
            chapter_count=len(jingshan.review_sections()),
            ending="何敬山与苏月琴",
        ))

    kind_order = {"tale": 0, "story": 1, "npc": 2}
    memories.sort(key=lambda item: (-item["completed_at"], kind_order[item["kind"]], item["title"]))
    return memories


def _tale_chapters(item: dict[str, Any]) -> list[dict[str, str]]:
    chapters = [{"title": "引子", "text": item["intro"]}]
    chapters.extend(
        {"title": stage["title"], "text": stage.get("text", "")}
        for stage in item["stages"]
    )
    reminiscence = tale.TALE_REMINISCENCES.get(item["key"])
    if reminiscence:
        chapters.extend(
            {"title": f"补充回忆｜{section['title']}", "text": section["text"]}
            for section in reminiscence["sections"]
        )
    return chapters


def _linear_chapters(mod: Any) -> list[dict[str, str]]:
    chapters = [{"title": "引子", "text": mod.INTRO}]
    for action in mod.ACTIONS:
        chapters.append({"title": action["title"], "text": action["text"]})
        if action.get("ending"):
            chapters.append({
                "title": getattr(mod, "ENDING_TITLE", "结尾"),
                "text": action["ending"],
            })
    return chapters


def _cinderella_chapters(flags: set[str], outcome: str) -> list[dict[str, str]]:
    chapters = [{"title": "引子", "text": story.INTRO}]
    chapters.extend(
        {"title": action["title"], "text": action["text"]}
        for action in story.ACTIONS.values()
        if action["flag"] in flags
    )
    chapters.append({"title": f"结局｜{outcome}", "text": story._cinderella_ending(outcome)})
    return chapters


def _minimum_cinderella_flags(outcome_title: str) -> set[str]:
    """旧数据没有路线快照时，只恢复该结局必需的最短证据链。"""
    needed: set[str] = set()
    for title, flags, _ in story.OUTCOMES.values():
        if title == outcome_title:
            needed.update(flags)
            break
    changed = True
    while changed:
        changed = False
        for action in story.ACTIONS.values():
            if action["flag"] not in needed:
                continue
            for required in action.get("requires", set()):
                if required not in needed:
                    needed.add(required)
                    changed = True
    return needed


async def _load_review(
    conn: aiosqlite.Connection,
    steward_id: int,
    kind: str,
    key: str,
    variant: str,
) -> dict[str, Any]:
    conn.row_factory = aiosqlite.Row
    chapters: list[dict[str, str]]
    title: str
    ending = ""
    completed_at = 0
    souvenirs: list[dict[str, str]] = []
    notice = "回忆重映只读取已完成正文，不消耗精力，也不会重复发放任何奖励。"

    if kind == "tale":
        catalog = await tale._catalog(conn)
        item = catalog.get(key)
        done = await (await conn.execute(
            """SELECT completed_at FROM steward_tales_done
               WHERE steward_id=? AND tale_key=? AND outcome='completed'""",
            (steward_id, key),
        )).fetchone()
        if not item or not done:
            raise ValueError("这段潮闻尚未收入你的岛上回忆。")
        title = item["title"]
        chapters = _tale_chapters(item)
        completed_at = done["completed_at"]
        souvenirs = _keepsakes(item.get("rewards") or {})
        ending = str(((item.get("rewards") or {}).get("achievement") or {}).get("name") or "完整探索")
    elif kind == "story" and key in LINEAR_STORY_MODULES:
        mod = LINEAR_STORY_MODULES[key]
        done = await (await conn.execute(
            """SELECT MAX(completed_at) AS completed_at FROM steward_story_outcomes
               WHERE steward_id=? AND story_key=?""",
            (steward_id, key),
        )).fetchone()
        if not done or not done["completed_at"]:
            raise ValueError("这段人物故事尚未收入你的岛上回忆。")
        title = mod.STORY_TITLE
        chapters = _linear_chapters(mod)
        completed_at = done["completed_at"]
        ending = mod.STORY_TITLE
        souvenirs = [
            {"name": item["name"], "emoji": item["emoji"], "description": item["desc"]}
            for item in mod.SOUVENIRS
        ]
    elif kind == "story" and key == story.STORY_KEY:
        if variant.startswith("legacy:"):
            legacy_outcome = variant.split(":", 1)[1]
            old = await (await conn.execute(
                """SELECT completed_at FROM steward_story_outcomes
                   WHERE steward_id=? AND story_key=? AND outcome=?""",
                (steward_id, key, legacy_outcome),
            )).fetchone()
            if not old:
                raise ValueError("没有找到这个旧结局档案。")
            title = story.STORY_TITLE
            ending = legacy_outcome
            completed_at = old["completed_at"]
            chapters = _cinderella_chapters(
                _minimum_cinderella_flags(legacy_outcome), ending
            )
            notice = "这是旧版本留下的结局档案：系统只能恢复抵达该结局必需的正文，不能伪造当时额外调查过的路线。"
            return {
                "kind": kind,
                "key": key,
                "title": title,
                "ending": ending,
                "completed_at": int(completed_at or 0),
                "chapters": chapters,
                "souvenirs": [],
                "read_only": True,
                "notice": notice,
            }
        params: tuple[Any, ...]
        where = "steward_id=? AND story_key=?"
        params = (steward_id, key)
        if variant and variant.isdigit():
            where += " AND id=?"
            params += (int(variant),)
        run = await (await conn.execute(
            f"""SELECT id, outcome, flags_json, completed_at FROM steward_story_runs
                 WHERE {where} ORDER BY completed_at DESC, id DESC LIMIT 1""",
            params,
        )).fetchone()
        if not run:
            raise ValueError("这次《灰姑娘》的完整路线没有留下快照，请完成新的一轮后再观看。")
        title = story.STORY_TITLE
        ending = run["outcome"]
        completed_at = run["completed_at"]
        chapters = _cinderella_chapters(set(json.loads(run["flags_json"] or "[]")), ending)
    elif kind == "npc" and key == "jingshan":
        done = await (await conn.execute(
            """SELECT updated_at FROM steward_jingshan
               WHERE steward_id=? AND stage>=4""",
            (steward_id,),
        )).fetchone()
        if not done:
            raise ValueError("这段相遇尚未收入你的岛上回忆。")
        title = "幸好还剩一小口"
        ending = "何敬山与苏月琴"
        completed_at = done["updated_at"]
        chapters = jingshan.review_sections()
    else:
        raise ValueError("没有这段岛上回忆。")

    return {
        "kind": kind,
        "key": key,
        "title": title,
        "ending": ending,
        "completed_at": int(completed_at or 0),
        "chapters": chapters,
        "souvenirs": souvenirs,
        "read_only": True,
        "notice": notice,
    }


async def fetch_review(
    api_key: str, kind: str, key: str, variant: str = ""
) -> dict[str, Any]:
    key_row = await db.get_key_row(api_key.strip())
    if not key_row:
        raise ValueError("凭证无效")
    steward = await db.get_steward_by_key_id(key_row["id"])
    if not steward or not steward["enrolled"]:
        raise ValueError("请先 steward_ops enroll 登记管理员")
    async with db.connect() as conn:
        return await _load_review(
            conn,
            steward["id"],
            kind.strip().lower(),
            key.strip().lower(),
            variant.strip(),
        )
