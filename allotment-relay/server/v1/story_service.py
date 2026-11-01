"""潮闻与人物故事的移动端适配层。

列表和「当前一步」来自 ``story_progress.snapshot``（和上手页同一份），动作只翻成已有的
``tale_ops`` / ``story_ops``。不新增剧情、奖励或数值。写操作先对着当前列表验一遍：
只有列表里真的出现的接取 / 开始 / 下一步才放行，不允许前端自己编指令。
"""
from __future__ import annotations

import logging
import re
from typing import Any

from .. import db, game, memory_archive, story, story_progress, tale
from . import farm_service
from .errors import ApiError, classify, humanize

log = logging.getLogger(__name__)

_KEY = re.compile(r"^[a-z0-9_]{1,48}$")
_TOOLS = {"tale_ops": tale.tale_ops, "story_ops": story.story_ops}
TITLES = {"accept": "接取潮闻", "start": "开始故事", "step": "故事这一步"}


def _key(value: str, label: str) -> str:
    text = (value or "").strip().lower()
    if not _KEY.match(text):
        raise ApiError("BAD_REQUEST", f"{label}不对。")
    return text


async def _view(key_id: int) -> dict[str, Any]:
    try:
        steward = await game.require_steward(key_id, exempt_duty=True)
    except ValueError as exc:
        raise classify(exc) from exc
    try:
        async with db.connect() as conn:
            view = await story_progress.snapshot(conn, steward)
            await conn.commit()
    except ValueError as exc:
        raise classify(exc) from exc
    for row in view["done"]:
        row["reviewable"] = True
    # 阶段提示是写给模型的（带 scan/dig、tale_ops explore 之类），人类按钮不显示
    for row in view["active"]:
        for step in row.get("actions") or []:
            step["hint"] = ""
    return view


async def snapshot(api_key: str, key_id: int) -> dict[str, Any]:
    view = await _view(key_id)
    snap = await farm_service.snapshot(api_key, key_id)
    snap["story"] = view
    return snap


def _allowed(view: dict[str, Any], kind: str, target: str) -> tuple[str, str]:
    """把前端点的东西对到当前列表里，返回 (tool, command)；对不上就拒绝。"""
    if kind == "accept":
        key = _key(target, "潮闻")
        for row in view["available"]:
            if row["kind"] == "tale" and row["key"] == key:
                return "tale_ops", f"accept {key}"
        raise ApiError("BAD_REQUEST", "这篇潮闻现在接不了。", status=409)
    if kind == "start":
        key = _key(target, "故事")
        for row in view["available"]:
            if row["kind"] == "story" and row["key"] == key:
                return "story_ops", f"start {key}"
        for row in view["done"]:
            replay = row.get("replay") or {}
            if row["kind"] == "story" and row["key"] == key and replay.get("command") == f"start {key}":
                return "story_ops", f"start {key}"
        raise ApiError("BAD_REQUEST", "这篇故事现在开始不了。", status=409)
    if kind == "step":
        tool, sep, command = (target or "").partition("|")
        tool, command = tool.strip(), command.strip()
        if not sep or tool not in _TOOLS or not command:
            raise ApiError("BAD_REQUEST", "先点故事列表里的这一步。")
        for row in view["active"]:
            for step in row.get("actions") or []:
                if step.get("tool") == tool and step.get("command") == command:
                    return tool, command
        raise ApiError("BAD_REQUEST", "这一步现在不是当前一步。", status=409)
    raise ApiError("BAD_REQUEST", "这里没有这一下。")


async def act(api_key: str, key_id: int, kind: str, target: str = "") -> dict[str, Any]:
    kind = (kind or "").strip()
    if kind == "review":
        return await review(api_key, key_id, target)
    view = await _view(key_id)
    tool, command = _allowed(view, kind, (target or "").strip())
    try:
        narrative = await _TOOLS[tool](key_id, command)
    except ValueError as exc:
        raise classify(exc) from exc
    snap = await snapshot(api_key, key_id)
    snap["event"] = {"title": TITLES.get(kind, "潮闻"), "narrative": humanize(narrative), "kind": "story"}
    return snap


async def review(api_key: str, key_id: int, target: str) -> dict[str, Any]:
    """回看已走完的潮闻 / 故事（只读，不发奖、不耗精力）。target = 类型|key[|变体]。"""
    bits = [b.strip() for b in (target or "").split("|")]
    if len(bits) < 2 or bits[0] not in ("tale", "story"):
        raise ApiError("BAD_REQUEST", "先点要回看的那一篇。")
    key = _key(bits[1], "故事")
    variant = bits[2] if len(bits) > 2 else ""
    try:
        data = await memory_archive.fetch_review(api_key, bits[0], key, variant)
    except ValueError as exc:
        raise classify(exc) from exc
    snap = await snapshot(api_key, key_id)
    snap["review"] = data
    return snap
