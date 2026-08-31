"""集市写操作。挂单 / 买 / 下架 / 扩摊仍走 market_ops，不另做数值。"""
from __future__ import annotations

from typing import Any

from .. import db, game, market
from . import farm_service
from .errors import ApiError, classify, humanize


TITLES = {
    "buy": "买下了",
    "sell": "挂上了",
    "cancel": "下架了",
    "expand": "扩了摊",
}


def _command(kind: str, target: str) -> str:
    extra = (target or "").strip()
    if kind == "buy":
        if not extra:
            raise ApiError("BAD_REQUEST", "先点要买的那一单。")
        return f"buy {extra}"
    if kind == "sell":
        if not extra:
            raise ApiError("BAD_REQUEST", "先写下要挂的货、数量和单价。")
        return f"sell {extra}"
    if kind == "cancel":
        if not extra:
            raise ApiError("BAD_REQUEST", "先点要下架的那一单。")
        return f"cancel {extra}"
    if kind == "expand":
        n = extra or "1"
        return f"扩 {n}"
    raise ApiError("BAD_REQUEST", "集市里没有这一下。")


async def snapshot(api_key: str, key_id: int) -> dict[str, Any]:
    try:
        s = await game.require_steward(key_id, exempt_duty=True)
    except ValueError as exc:
        raise classify(exc) from exc
    async with db.connect() as conn:
        shelf = await market.player_view(conn, s)
        await conn.commit()
    snap = await farm_service.snapshot(api_key, s["id"])
    snap["market"] = shelf
    return snap


async def act(api_key: str, key_id: int, kind: str, target: str = "") -> dict[str, Any]:
    verb = (kind or "").strip()
    if verb == "look":
        snap = await snapshot(api_key, key_id)
        snap["event"] = {
            "title": "玩家集市",
            "narrative": (snap.get("market") or {}).get("line") or "先看看街上谁在卖。",
            "kind": "market",
        }
        return snap
    command = _command(verb, target)
    try:
        await game.require_steward(key_id)
    except ValueError as exc:
        raise classify(exc) from exc
    try:
        narrative = await market.market_ops(key_id, command)
    except ValueError as exc:
        raise classify(exc) from exc
    snap = await snapshot(api_key, key_id)
    snap["event"] = {
        "title": TITLES.get(verb, "集市"),
        "narrative": humanize(narrative),
        "kind": "market",
    }
    return snap
