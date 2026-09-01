"""栗栗流动摊写操作。换货 / 唤摊 / 摸狗仍走 lili_ops，不另做数值。"""
from __future__ import annotations

from typing import Any

from .. import db, game, lili
from . import farm_service
from .errors import ApiError, classify, humanize


TITLES = {
    "trade": "换到了",
    "summon": "献上了",
    "pet": "摸了夜栖",
    "junk": "换到了",
    "look": "流动摊",
}


def _command(kind: str, target: str) -> str:
    verb = (kind or "").strip()
    extra = (target or "").strip()
    if verb == "look":
        return "scan"
    if verb == "trade":
        if not extra:
            raise ApiError("BAD_REQUEST", "先点货架上要换的那一单。")
        return f"trade {extra}"
    if verb == "summon":
        if not extra:
            raise ApiError("BAD_REQUEST", "先点要献的那枚贝壳。")
        return f"summon {extra}"
    if verb == "pet":
        return "pet"
    if verb == "junk":
        return "junk"
    raise ApiError("BAD_REQUEST", "摊上没有这一下。")


async def snapshot(api_key: str, key_id: int) -> dict[str, Any]:
    try:
        s = await game.require_steward(key_id)
    except ValueError as exc:
        raise classify(exc) from exc
    async with db.connect() as conn:
        shelf = await lili.player_view(conn, s)
        await conn.commit()
    snap = await farm_service.snapshot(api_key, s["id"])
    snap["lili"] = shelf
    return snap


async def act(api_key: str, key_id: int, kind: str, target: str = "") -> dict[str, Any]:
    verb = (kind or "").strip()
    command = _command(verb, target)
    try:
        await game.require_steward(key_id)
    except ValueError as exc:
        raise classify(exc) from exc
    try:
        narrative = await lili.lili_ops(key_id, command)
    except ValueError as exc:
        raise classify(exc) from exc
    snap = await snapshot(api_key, key_id)
    snap["event"] = {
        "title": TITLES.get(verb, "栗栗流动摊"),
        "narrative": humanize(narrative),
        "kind": "lili",
        "speaker": "栗栗",
    }
    return snap
