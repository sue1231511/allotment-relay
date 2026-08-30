"""盐风崖写操作。买镐 / 探脉 / 挖 / 洗仍走 quarry_ops，不另做数值。"""
from __future__ import annotations

from typing import Any

from .. import db, game, quarry
from . import farm_service
from .errors import ApiError, classify, humanize


KINDS = {
    "buy_pick": "买镐",
    "prospect": "探脉",
    "hew": "挖",
    "wash": "洗",
    "open_pit": "开坑 确认",
    "upgrade": "升镐 确认",
}

TITLES = {
    "buy_pick": "领到镐了",
    "prospect": "探脉",
    "hew": "挥了一镐",
    "wash": "洗了矿",
    "open_pit": "开了新坑",
    "upgrade": "镐升了一档",
}


def _command(kind: str, target: str) -> str:
    verb = KINDS.get(kind)
    if not verb:
        raise ApiError("BAD_REQUEST", "崖上没有这一下。")
    name = (target or "").strip()
    if kind == "wash":
        if not name:
            raise ApiError("BAD_REQUEST", "先点要洗的原矿。")
        return f"洗 {name}"
    if kind == "prospect" and name:
        return f"探脉 {name}"
    if kind == "hew" and name:
        return f"挖 {name}"
    return verb


async def snapshot(api_key: str, key_id: int) -> dict[str, Any]:
    try:
        s = await game.require_steward(key_id)
    except ValueError as exc:
        raise classify(exc) from exc
    async with db.connect() as conn:
        shelf = await quarry.player_view(conn, s)
        await conn.commit()
    snap = await farm_service.snapshot(api_key, s["id"])
    snap["quarry"] = shelf
    return snap


async def act(api_key: str, key_id: int, kind: str, target: str = "") -> dict[str, Any]:
    command = _command((kind or "").strip(), target)
    try:
        await game.require_steward(key_id)
    except ValueError as exc:
        raise classify(exc) from exc
    try:
        narrative = await quarry.quarry_ops(key_id, command)
    except ValueError as exc:
        raise classify(exc) from exc
    snap = await snapshot(api_key, key_id)
    snap["event"] = {
        "title": TITLES.get(kind, "盐风崖"),
        "narrative": humanize(narrative),
        "kind": "quarry",
    }
    return snap
