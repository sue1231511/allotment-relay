"""上手页潮闻 / 人物故事当前一步。不剧透未走幕。"""
from __future__ import annotations

from typing import Any

from . import story, tale
from .tale import DOMAIN_LABELS

PLACE_FOR_DOMAIN: dict[str, str] = {
    "shore": "tide",
    "beach": "tide",
    "sea": "tide",
    "old_wharf": "tide",
    "west_dock": "tide",
    "plot": "plot",
    "bar": "bar",
    "undertide": "undertide",
    "clinic": "clinic",
    "clinic_archive": "clinic",
    "old_clinic": "clinic",
    "west_market": "market",
    "tt": "market",
}


def place_for_domain(domain: str) -> str:
    return PLACE_FOR_DOMAIN.get((domain or "").strip(), "")


def _explore_domain(stage: dict[str, Any]) -> str:
    return str(stage.get("domain") or stage.get("explore_domain") or "")


def _blurb(text: str, limit: int = 48) -> str:
    line = " ".join((text or "").split())
    if len(line) <= limit:
        return line
    return line[: limit - 1] + "…"


def _tale_actions(tale_def: dict[str, Any], stage_idx: int) -> list[dict[str, Any]]:
    stages = tale_def.get("stages") or []
    if stage_idx < 0 or stage_idx >= len(stages):
        return []
    stage = stages[stage_idx]
    kind = stage.get("kind") or ""
    domain = _explore_domain(stage)
    place = place_for_domain(domain)
    where = DOMAIN_LABELS.get(domain, domain)
    title = stage.get("title") or tale_def.get("title") or ""
    hint = stage.get("hint") or ""
    note = f"阶段 {stage_idx + 1}/{len(stages)}：{title}"
    rows: list[dict[str, Any]] = []
    if kind == "explore" or (kind in ("item", "deliver") and domain):
        rows.append({
            "label": f"去{where}看看" if where else "探索这一幕",
            "note": note,
            "hint": hint,
            "tool": "tale_ops",
            "command": f"explore {domain}".strip(),
            "place": place,
        })
    if kind == "deliver":
        rows.append({
            "label": "交付领奖",
            "note": note,
            "hint": hint,
            "tool": "tale_ops",
            "command": "turnin",
            "place": place,
        })
    return rows


def _cinderella_actions(flags: set[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for command in story._available(flags):
        action = story.ACTIONS.get(command)
        if action:
            label = str(action.get("title") or command)
        elif command.startswith("choose "):
            key = command.split(" ", 1)[1]
            outcome = story.OUTCOMES.get(key)
            label = f"决定结局：{outcome[0]}" if outcome else command
        else:
            label = command
        rows.append({
            "label": label,
            "note": "调查或准备，各耗 10 分钟",
            "hint": "",
            "tool": "story_ops",
            "command": command,
            "place": "",
        })
    return rows


def _linear_actions(mod: Any, flags: set[str]) -> list[dict[str, Any]]:
    action = mod.next_action(flags)
    if not action:
        return []
    command = str(action.get("command") or "")
    domain = command.split()[-1] if command.startswith("explore ") else ""
    return [{
        "label": str(action.get("title") or command),
        "note": "按当前这一步走，不跳幕",
        "hint": "",
        "tool": "story_ops",
        "command": command,
        "place": place_for_domain(domain),
    }]


async def snapshot(conn, steward: dict[str, Any]) -> dict[str, Any]:
    available: list[dict[str, Any]] = []
    active: list[dict[str, Any]] = []
    done: list[dict[str, Any]] = []

    catalog = await tale._catalog(conn)
    for item in await tale._available_tales(conn, steward):
        available.append({
            "kind": "tale",
            "key": item["key"],
            "title": item["title"],
            "blurb": _blurb(item.get("intro") or ""),
            "label": f"接取《{item['title']}》",
            "note": "接上以后按当前提示去地点。",
            "tool": "tale_ops",
            "command": f"accept {item['key']}",
            "place": "",
        })
    for row in await tale._active_tales(conn, steward["id"]):
        tale_def = catalog.get(row["tale_key"])
        if not tale_def:
            continue
        steps = _tale_actions(tale_def, int(row["stage_idx"] or 0))
        active.append({
            "kind": "tale",
            "key": row["tale_key"],
            "title": tale_def["title"],
            "blurb": _blurb((steps[0].get("note") if steps else "") or tale_def.get("intro") or ""),
            "actions": steps,
        })
    for key in sorted(await tale._done_keys(conn, steward["id"])):
        tale_def = catalog.get(key) or {}
        done.append({
            "kind": "tale",
            "key": key,
            "title": tale_def.get("title") or key,
        })

    crow = await story._progress(conn, steward["id"], story.STORY_KEY)
    if not crow:
        available.append({
            "kind": "story",
            "key": story.STORY_KEY,
            "title": story.STORY_TITLE,
            "blurb": "调查真相，做好准备，然后决定要救谁。",
            "label": f"开始《{story.STORY_TITLE}》",
            "note": "调查按钮，不是对话窗。",
            "tool": "story_ops",
            "command": f"start {story.STORY_KEY}",
            "place": "",
        })
    elif crow["status"] == "active":
        steps = _cinderella_actions(story._flags(crow))
        active.append({
            "kind": "story",
            "key": story.STORY_KEY,
            "title": story.STORY_TITLE,
            "blurb": f"距离午夜 {crow['minutes_left']} 分钟",
            "actions": steps,
        })
    elif crow["status"] == "completed":
        done.append({
            "kind": "story",
            "key": story.STORY_KEY,
            "title": story.STORY_TITLE,
            "ending": crow["outcome"],
            "replay": {
                "label": f"重玩《{story.STORY_TITLE}》",
                "tool": "story_ops",
                "command": f"start {story.STORY_KEY}",
            },
        })

    for mod in story.LINEAR_STORIES:
        row = await story._progress(conn, steward["id"], mod.STORY_KEY)
        if not row:
            available.append({
                "kind": "story",
                "key": mod.STORY_KEY,
                "title": mod.STORY_TITLE,
                "blurb": _blurb(getattr(mod, "BLURB", "") or getattr(mod, "INTRO", "")),
                "label": f"开始《{mod.STORY_TITLE}》",
                "note": "按当前一步走，不跳幕。",
                "tool": "story_ops",
                "command": f"start {mod.STORY_KEY}",
                "place": "",
            })
        elif row["status"] == "active":
            steps = _linear_actions(mod, story._flags(row))
            active.append({
                "kind": "story",
                "key": mod.STORY_KEY,
                "title": mod.STORY_TITLE,
                "blurb": (steps[0]["label"] if steps else "进行中"),
                "actions": steps,
            })
        elif row["status"] == "completed":
            done.append({
                "kind": "story",
                "key": mod.STORY_KEY,
                "title": mod.STORY_TITLE,
                "ending": row["outcome"] or "",
                "replay": {
                    "label": f"重玩《{mod.STORY_TITLE}》",
                    "tool": "story_ops",
                    "command": f"start {mod.STORY_KEY}",
                },
            })

    return {"available": available, "active": active, "done": done}
