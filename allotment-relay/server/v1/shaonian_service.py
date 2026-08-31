"""海边韶年写操作。卜卦 / 转运 / 买符仍走 visit_ops shaonian，不另做数值。"""
from __future__ import annotations

from typing import Any

from .. import db, game, shaonian
from . import farm_service
from .errors import ApiError, classify, humanize


TITLES = {
    "visit": "见了韶年",
    "fortune": "卜了一卦",
    "transfer": "转了运",
    "buy": "买到了符",
    "look": "卦书",
}


def _command(kind: str, target: str) -> str:
    extra = (target or "").strip()
    verb = (kind or "").strip().lower()
    if verb in {"visit", "fortune", "transfer"}:
        return verb
    if verb == "look":
        return "catalog"
    if verb == "buy":
        if not extra:
            raise ApiError("BAD_REQUEST", "先点要买的那张符。")
        return f"buy {extra}"
    raise ApiError("BAD_REQUEST", "滩头没有这一下。")


async def snapshot(api_key: str, key_id: int) -> dict[str, Any]:
    try:
        s = await game.require_steward(key_id, exempt_duty=True)
    except ValueError as exc:
        raise classify(exc) from exc
    async with db.connect() as conn:
        shelf = await shaonian.player_view(conn, s)
        await conn.commit()
    snap = await farm_service.snapshot(api_key, s["id"])
    snap["shaonian"] = shelf
    return snap


async def act(api_key: str, key_id: int, kind: str, target: str = "") -> dict[str, Any]:
    verb = (kind or "").strip()
    command = _command(verb, target)
    try:
        await game.require_steward(key_id, exempt_duty=True)
    except ValueError as exc:
        raise classify(exc) from exc
    try:
        narrative = await shaonian.shaonian_ops(key_id, command)
    except ValueError as exc:
        raise classify(exc) from exc
    snap = await snapshot(api_key, key_id)
    snap["event"] = {
        "title": TITLES.get(verb, "韶年"),
        "narrative": humanize(narrative),
        "kind": "shaonian",
        "speaker": "韶年",
    }
    return snap
