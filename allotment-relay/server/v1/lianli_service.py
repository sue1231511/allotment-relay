"""连理所写操作。档案 / 订婚 / 成婚 / 婚期仍走 marriage_ops，不另做数值。"""
from __future__ import annotations

from typing import Any

from .. import db, game, marriage, tt
from . import farm_service
from .errors import ApiError, classify, humanize


TITLES = {
    "look": "登记处",
    "act": "办过了",
    "buy": "买下了",
    "bless": "写下了",
    "gift": "送到了",
}

LOOK = {
    "desk": "desk",
    "status": "status",
    "prep": "筹备",
    "weddings": "婚礼",
    "charter": "婚书",
    "home": "居所",
    "divorce": "离婚",
}

# 空 订婚 在三件齐了会发出确认页；看进度不能走那条。
LOOK_BETROTH = ("betroth", "订婚", "订婚礼")


def _command(kind: str, target: str) -> tuple[str, str]:
    """返回 (ops, command)。ops 为 marriage 或 tt。"""
    extra = (target or "").strip()
    if kind == "look":
        if extra in LOOK_BETROTH:
            return "look_betroth", extra
        return "marriage", LOOK.get(extra, "status")
    if kind == "buy":
        if not extra:
            raise ApiError("BAD_REQUEST", "先点要买的那一件。这是 Tt酱嫁妆柜。")
        return "tt", f"buy {extra}"
    if kind == "bless":
        host, _, body = extra.partition("|")
        host = host.strip()
        body = body.strip()
        if not host or not body:
            raise ApiError("BAD_REQUEST", "先写下祝词。")
        return "marriage", f"祝词 {host} {body}"
    if kind == "gift":
        host, _, rest = extra.partition("|")
        host = host.strip()
        rest = rest.strip()
        if not host or not rest:
            raise ApiError("BAD_REQUEST", "先写下要送的物品。")
        return "marriage", f"送礼 {host} {rest}"
    if kind == "act":
        if not extra:
            raise ApiError("BAD_REQUEST", "连理所里没有这一下。")
        return "marriage", extra
    raise ApiError("BAD_REQUEST", "连理所里没有这一下。")


async def snapshot(api_key: str, key_id: int) -> dict[str, Any]:
    try:
        s = await game.require_steward(key_id, exempt_duty=True)
    except ValueError as exc:
        raise classify(exc) from exc
    async with db.connect() as conn:
        shelf = await marriage.player_view(conn, s)
        await conn.commit()
    snap = await farm_service.snapshot(api_key, s["id"])
    snap["lianli"] = shelf
    return snap


async def act(api_key: str, key_id: int, kind: str, target: str = "") -> dict[str, Any]:
    verb = (kind or "").strip()
    ops, command = _command(verb, target)
    try:
        await game.require_steward(key_id, exempt_duty=True)
    except ValueError as exc:
        raise classify(exc) from exc
    if ops == "look_betroth":
        snap = await snapshot(api_key, key_id)
        rows = ((snap.get("lianli") or {}).get("items") or {}).get("betroth") or []
        hit = next((row for row in rows if row.get("id") == "betroth"), None)
        snap["event"] = {
            "title": "订婚进度",
            "narrative": humanize((hit or {}).get("detail") or (hit or {}).get("note") or "先看进度。"),
            "kind": "lianli",
        }
        return snap
    try:
        if ops == "tt":
            narrative = await tt.tt_ops(key_id, command)
        else:
            narrative = await marriage.marriage_ops(key_id, command)
    except ValueError as exc:
        raise classify(exc) from exc
    snap = await snapshot(api_key, key_id)
    snap["event"] = {
        "title": TITLES.get(verb, "连理所"),
        "narrative": humanize(narrative),
        "kind": "lianli",
    }
    return snap
