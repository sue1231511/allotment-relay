"""潮生会写操作。问事 / 税 / 维 / 基金 / 告示仍走 visit_ops 潮生会，不另做数值。"""
from __future__ import annotations

from typing import Any

from .. import chaoshen, db, game
from . import farm_service
from .errors import ApiError, classify, humanize


TITLES = {
    "look": "会厅",
    "pay": "交过了",
    "pay_part": "交过了",
    "donate": "捐进了",
}

LOOK = {
    "ask": "问",
    "tax": "税",
    "upkeep": "维",
    "fund": "基金",
    "notice": "告示",
}


def _command(kind: str, target: str) -> str:
    extra = (target or "").strip()
    if kind == "look":
        if extra.startswith("notice"):
            _, _, nid = extra.partition(":")
            nid = nid.strip()
            return f"告示 {nid}".strip() if nid else "告示"
        return LOOK.get(extra, "问")
    if kind in ("pay", "pay_part"):
        head, _, amt = extra.partition(":")
        head = head.strip() or extra
        amt = amt.strip()
        if head in ("tax", "税", "岸税"):
            return f"税 交 {amt}".strip() if amt else "税 交"
        if head in ("upkeep", "维", "岸维", "维修"):
            return f"维 交 {amt}".strip() if amt else "维 交"
        raise ApiError("BAD_REQUEST", "只能交岸税或岸维。")
    if kind == "donate":
        n = extra.split()[-1] if extra else ""
        if not n.isdigit():
            raise ApiError("BAD_REQUEST", "先写下要捐的票数。")
        return f"基金 捐 {n}"
    raise ApiError("BAD_REQUEST", "潮生会里没有这一下。")


async def snapshot(api_key: str, key_id: int) -> dict[str, Any]:
    try:
        s = await game.require_steward(key_id, exempt_duty=True)
    except ValueError as exc:
        raise classify(exc) from exc
    async with db.connect() as conn:
        shelf = await chaoshen.player_view(conn, s)
        await conn.commit()
    snap = await farm_service.snapshot(api_key, s["id"])
    snap["hui"] = shelf
    return snap


async def act(api_key: str, key_id: int, kind: str, target: str = "") -> dict[str, Any]:
    verb = (kind or "").strip()
    command = _command(verb, target)
    try:
        await game.require_steward(key_id, exempt_duty=True)
    except ValueError as exc:
        raise classify(exc) from exc
    try:
        narrative = await chaoshen.chaoshen_ops(key_id, command)
    except ValueError as exc:
        raise classify(exc) from exc
    snap = await snapshot(api_key, key_id)
    snap["event"] = {
        "title": TITLES.get(verb, "潮生会"),
        "narrative": humanize(narrative),
        "kind": "hui",
    }
    return snap
