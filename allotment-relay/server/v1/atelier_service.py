"""衣泊坊写操作。买现货 / 取 / 穿 / 脱 / 见漾漾仍走 cloth_ops，不另做数值。"""
from __future__ import annotations

from typing import Any

from .. import cloth, db, game
from . import farm_service
from .errors import ApiError, classify, humanize


TITLES = {
    "take": "取到了",
    "buy": "买下现货",
    "wear": "换上了",
    "remove": "脱下了",
    "visit": "见了漾漾",
}


def _command(kind: str, target: str) -> str:
    name = (target or "").strip()
    if kind == "take":
        return "取"
    if kind == "buy":
        if not name:
            raise ApiError("BAD_REQUEST", "先点要买的那挂。现货只有婚服和订婚服。")
        return f"买 {name}"
    if kind == "wear":
        if not name:
            raise ApiError("BAD_REQUEST", "先点衣橱里要穿的那件。")
        return f"穿 {name}"
    if kind == "remove":
        return "脱"
    if kind == "visit":
        return "漾漾"
    raise ApiError("BAD_REQUEST", "衣泊坊里没有这一下。")


async def snapshot(api_key: str, key_id: int) -> dict[str, Any]:
    try:
        s = await game.require_steward(key_id, exempt_duty=True)
    except ValueError as exc:
        raise classify(exc) from exc
    async with db.connect() as conn:
        shelf = await cloth.player_view(conn, s)
        await conn.commit()
    snap = await farm_service.snapshot(api_key, s["id"])
    snap["atelier"] = shelf
    return snap


async def act(api_key: str, key_id: int, kind: str, target: str = "") -> dict[str, Any]:
    verb = (kind or "").strip()
    if verb == "look":
        snap = await snapshot(api_key, key_id)
        desk = (snap.get("atelier") or {}).get("desk") or {}
        snap["event"] = {
            "title": "衣泊坊",
            "narrative": desk.get("take_note") or "日常不卖成衣。现货只有婚服和订婚服。",
            "kind": "atelier",
        }
        return snap
    command = _command(verb, target)
    try:
        await game.require_steward(key_id, exempt_duty=True)
    except ValueError as exc:
        raise classify(exc) from exc
    try:
        narrative = await cloth.cloth_ops(key_id, command)
    except ValueError as exc:
        raise classify(exc) from exc
    snap = await snapshot(api_key, key_id)
    snap["event"] = {
        "title": TITLES.get(verb, "衣泊坊"),
        "narrative": humanize(narrative),
        "kind": "atelier",
    }
    return snap
