"""编剧社写操作。投稿 / 撤回仍走 theater_ops，不另做数值。"""
from __future__ import annotations

from typing import Any

from .. import db, game, theater
from . import farm_service
from .errors import ApiError, classify, humanize


TITLES = {
    "submit": "稿进编剧社了",
    "withdraw": "撤回了",
}


def _command(kind: str, target: str) -> str:
    name = (target or "").strip()
    if kind == "submit":
        if not name:
            raise ApiError("BAD_REQUEST", "先写下标题和正文。")
        return f"投稿 {name}"
    if kind == "withdraw":
        if not name:
            raise ApiError("BAD_REQUEST", "先点要撤回的那一篇。")
        return f"撤回 {name}"
    raise ApiError("BAD_REQUEST", "编剧社里没有这一下。")


async def snapshot(api_key: str, key_id: int) -> dict[str, Any]:
    try:
        s = await game.require_steward(key_id, exempt_duty=True)
    except ValueError as exc:
        raise classify(exc) from exc
    async with db.connect() as conn:
        shelf = await theater.writers_view(conn, s)
        await conn.commit()
    snap = await farm_service.snapshot(api_key, s["id"])
    snap["writers"] = shelf
    return snap


async def act(api_key: str, key_id: int, kind: str, target: str = "") -> dict[str, Any]:
    verb = (kind or "").strip()
    if verb == "look":
        snap = await snapshot(api_key, key_id)
        snap["event"] = {
            "title": "编剧社",
            "narrative": (snap.get("writers") or {}).get("submit_note") or "侧厅常开。",
            "kind": "writers",
        }
        return snap
    command = _command(verb, target)
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
        "title": TITLES.get(verb, "编剧社"),
        "narrative": humanize(narrative),
        "kind": "writers",
    }
    return snap
