"""岸工坊写操作。打钉 / 灌盐 / 打捞仍走 craft_ops，不另做数值。"""
from __future__ import annotations

from typing import Any

from .. import craft, db, game
from . import farm_service
from .errors import ApiError, classify, humanize


KINDS = {
    "craft": "打",
    "take": "取",
    "fill": "灌",
    "harvest": "收盐",
    "open_pan": "开池 确认",
    "salvage": "打捞",
    "donate": "捐",
    "patch": "补网",
}

TITLES = {
    "craft": "开打了",
    "take": "取到了",
    "fill": "灌进盐田",
    "harvest": "收了盐",
    "open_pan": "开了新池",
    "salvage": "打捞",
    "donate": "陈列上了",
    "patch": "补上网",
}


def _command(kind: str, target: str) -> str:
    verb = KINDS.get(kind)
    if not verb:
        raise ApiError("BAD_REQUEST", "工坊里没有这一下。")
    name = (target or "").strip()
    if kind == "craft":
        if not name:
            raise ApiError("BAD_REQUEST", "先点砧上要打的东西。")
        return f"打 {name}"
    if kind == "donate":
        if not name:
            raise ApiError("BAD_REQUEST", "先点要捐的那一套。")
        return f"捐 {name}"
    if kind == "fill" and name:
        return f"灌 {name}"
    if kind == "harvest" and name:
        return f"收盐 {name}"
    return verb


async def snapshot(api_key: str, key_id: int) -> dict[str, Any]:
    try:
        s = await game.require_steward(key_id)
    except ValueError as exc:
        raise classify(exc) from exc
    async with db.connect() as conn:
        shelf = await craft.player_view(conn, s)
        await conn.commit()
    snap = await farm_service.snapshot(api_key, s["id"])
    snap["workshop"] = shelf
    return snap


async def act(api_key: str, key_id: int, kind: str, target: str = "") -> dict[str, Any]:
    command = _command((kind or "").strip(), target)
    try:
        await game.require_steward(key_id)
    except ValueError as exc:
        raise classify(exc) from exc
    try:
        narrative = await craft.craft_ops(key_id, command)
    except ValueError as exc:
        raise classify(exc) from exc
    snap = await snapshot(api_key, key_id)
    snap["event"] = {
        "title": TITLES.get(kind, "岸工坊"),
        "narrative": humanize(narrative),
        "kind": "workshop",
    }
    return snap
