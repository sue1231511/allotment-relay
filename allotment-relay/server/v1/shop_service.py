"""杂货铺写操作。货架与扣票仍走 visit_ops tt，不另做数值。"""
from __future__ import annotations

from typing import Any

from .. import db, game, tt
from . import farm_service
from .errors import ApiError, classify, humanize


async def catalog(api_key: str, key_id: int) -> dict[str, Any]:
    try:
        s = await game.require_steward(key_id)
    except ValueError as exc:
        raise classify(exc) from exc
    async with db.connect() as conn:
        shelf = await tt.shelf_view(conn, s)
        await conn.commit()
    snap = await farm_service.snapshot(api_key, s["id"])
    gift = shelf.pop("gift", "")
    snap["shop"] = shelf
    if gift:
        snap["event"] = {
            "title": "Tt酱心情好",
            "narrative": humanize(gift),
            "kind": "shop",
        }
    return snap


async def buy(api_key: str, key_id: int, item: str, qty: int = 1) -> dict[str, Any]:
    name = (item or "").strip()
    if not name:
        raise ApiError("BAD_REQUEST", "先点货架上的东西。")
    n = max(1, min(24, int(qty or 1)))
    try:
        await game.require_steward(key_id)
    except ValueError as exc:
        raise classify(exc) from exc
    try:
        narrative = await tt.tt_ops(key_id, f"buy {name} {n}")
    except ValueError as exc:
        raise classify(exc) from exc
    snap = await catalog(api_key, key_id)
    snap["event"] = {
        "title": "买下了",
        "narrative": humanize(narrative),
        "kind": "shop",
    }
    return snap
