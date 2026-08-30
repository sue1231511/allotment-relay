"""小馆写操作。堂食 / 上架 / 开馆仍走 kitchen_ops shop，不另做数值。"""
from __future__ import annotations

from typing import Any

from .. import db, eatery, game, kitchen
from . import farm_service
from .errors import ApiError, classify, humanize


TITLES = {
    "dine": "吃完了",
    "stock": "上了菜单",
    "unstock": "撤下来了",
    "open": "开张了",
    "sell": "卖掉了",
}


def _command(kind: str, target: str) -> str:
    name = (target or "").strip()
    if kind == "dine":
        shop, _, item = name.partition("|")
        shop = shop.strip()
        item = item.strip()
        if not shop:
            raise ApiError("BAD_REQUEST", "先点要去的那家馆。")
        if item:
            return f"shop dine {shop} {item}"
        return f"shop dine {shop}"
    if kind == "stock":
        if not name:
            raise ApiError("BAD_REQUEST", "先点要上架的那道菜。")
        return f"shop stock {name}"
    if kind == "unstock":
        if not name:
            raise ApiError("BAD_REQUEST", "先点要撤下的那道菜。")
        return f"shop unstock {name}"
    if kind == "open":
        label = name or ""
        return f"shop open {label}".rstrip()
    if kind == "sell":
        if name in ("确认", "ok", "yes", "confirm", "卖"):
            return "shop 卖掉 确认"
        return "shop 卖掉"
    raise ApiError("BAD_REQUEST", "小馆里没有这一下。")


async def snapshot(api_key: str, key_id: int) -> dict[str, Any]:
    try:
        s = await game.require_steward(key_id, exempt_duty=True)
    except ValueError as exc:
        raise classify(exc) from exc
    async with db.connect() as conn:
        shelf = await eatery.player_view(conn, s)
        await conn.commit()
    snap = await farm_service.snapshot(api_key, s["id"])
    snap["eatery"] = shelf
    return snap


async def act(api_key: str, key_id: int, kind: str, target: str = "") -> dict[str, Any]:
    verb = (kind or "").strip()
    if verb == "look":
        snap = await snapshot(api_key, key_id)
        snap["event"] = {
            "title": "岸畔小馆",
            "narrative": (snap.get("eatery") or {}).get("line") or "先看看谁在开火。",
            "kind": "eatery",
        }
        return snap
    command = _command(verb, target)
    try:
        await game.require_steward(key_id, exempt_duty=verb == "dine")
    except ValueError as exc:
        raise classify(exc) from exc
    try:
        narrative = await kitchen.kitchen_ops(key_id, command)
    except ValueError as exc:
        raise classify(exc) from exc
    snap = await snapshot(api_key, key_id)
    snap["event"] = {
        "title": TITLES.get(verb, "岸畔小馆"),
        "narrative": humanize(narrative),
        "kind": "eatery",
    }
    return snap
