"""剧场看台写操作。试镜 / 对戏 / 演出 / 领薪仍走 theater_ops，不另做数值。"""
from __future__ import annotations

from typing import Any

from .. import db, game, theater
from . import farm_service
from .errors import ApiError, classify, humanize


KINDS = {
    "audition": "试镜",
    "rehearse": "对戏",
    "perform": "演出",
    "claim": "领薪",
}

TITLES = {
    "audition": "试镜",
    "rehearse": "对过戏",
    "perform": "演完了",
    "claim": "领了薪",
}


def _command(kind: str) -> str:
    verb = KINDS.get(kind)
    if not verb:
        raise ApiError("BAD_REQUEST", "剧场看台没有这一下。")
    return verb


async def snapshot(api_key: str, key_id: int) -> dict[str, Any]:
    try:
        s = await game.require_steward(key_id, exempt_duty=True)
    except ValueError as exc:
        raise classify(exc) from exc
    async with db.connect() as conn:
        shelf = await theater.hall_view(conn, s)
        await conn.commit()
    snap = await farm_service.snapshot(api_key, s["id"])
    snap["hall"] = shelf
    return snap


async def act(api_key: str, key_id: int, kind: str, target: str = "") -> dict[str, Any]:
    verb = (kind or "").strip()
    if verb == "look":
        snap = await snapshot(api_key, key_id)
        board = (snap.get("hall") or {}).get("board") or {}
        snap["event"] = {
            "title": board.get("title") or "看板",
            "narrative": board.get("note") or "先看看今晚有没有专场。",
            "kind": "hall",
            "speaker": "小橘",
        }
        return snap
    command = _command(verb)
    try:
        await game.require_steward(key_id, exempt_duty=True)
    except ValueError as exc:
        raise classify(exc) from exc
    try:
        narrative = await theater.theater_ops(key_id, command)
    except ValueError as exc:
        raise classify(exc) from exc
    snap = await snapshot(api_key, key_id)
    snap["event"] = {
        "title": TITLES.get(verb, "剧场看台"),
        "narrative": humanize(narrative),
        "kind": "hall",
        "speaker": "小橘",
    }
    return snap
