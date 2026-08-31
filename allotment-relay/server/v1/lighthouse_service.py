"""灯塔写操作。喝茶 / 问潮 / 点灯 / 守夜仍走 visit_ops buxing，不另做数值。"""
from __future__ import annotations

from typing import Any

from .. import buxing, db, game
from . import farm_service
from .errors import ApiError, classify, humanize


TITLES = {
    "visit": "上了灯塔",
    "tea": "喝了茶",
    "tide": "问了潮",
    "light": "点了一盏灯",
    "gallery": "灯廊",
    "entrust": "记下了",
    "watch": "守了一夜",
    "remember": "潮汐簿",
    "fulfill": "还了愿",
}

SPEAKERS = {
    "gallery": "灯廊",
    "remember": "潮汐簿",
}


def _command(kind: str, target: str) -> str:
    name = (target or "").strip()
    verb = (kind or "").strip().lower()
    if verb in {"visit", "tea", "tide", "gallery", "watch", "remember"}:
        return verb
    if verb == "light":
        if "|" not in name:
            raise ApiError("BAD_REQUEST", "先写下给谁点的、求什么。")
        return f"light {name}"
    if verb == "entrust":
        if not name:
            raise ApiError("BAD_REQUEST", "先写下一件旧事。")
        return f"entrust {name}"
    if verb == "fulfill":
        if not name.isdigit():
            raise ApiError("BAD_REQUEST", "先点要还愿的那盏灯。")
        return f"fulfill {name}"
    raise ApiError("BAD_REQUEST", "灯塔里没有这一下。")


async def snapshot(api_key: str, key_id: int) -> dict[str, Any]:
    try:
        s = await game.require_steward(key_id, exempt_duty=True)
    except ValueError as exc:
        raise classify(exc) from exc
    async with db.connect() as conn:
        shelf = await buxing.player_view(conn, s)
        await conn.commit()
    snap = await farm_service.snapshot(api_key, s["id"])
    snap["lighthouse"] = shelf
    return snap


async def act(api_key: str, key_id: int, kind: str, target: str = "") -> dict[str, Any]:
    command = _command(kind, target)
    try:
        await game.require_steward(key_id, exempt_duty=True)
    except ValueError as exc:
        raise classify(exc) from exc
    try:
        narrative = await buxing.buxing_ops(key_id, command)
    except ValueError as exc:
        raise classify(exc) from exc
    snap = await snapshot(api_key, key_id)
    snap["event"] = {
        "title": TITLES.get(kind, "灯塔"),
        "narrative": humanize(narrative),
        "kind": "lighthouse",
        "speaker": SPEAKERS.get(kind, "不醒"),
    }
    return snap
