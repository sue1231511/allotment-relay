"""听潮亭写操作。看 / 钉 / 回 / 撕仍走 wall_ops，不另做数值。"""
from __future__ import annotations

from typing import Any

from .. import db, game, wall
from . import farm_service
from .errors import ApiError, classify, humanize


TITLES = {
    "look": "木牌",
    "post": "钉上了",
    "reply": "回了",
    "tear": "撕了",
}


def _command(kind: str, target: str) -> str:
    extra = (target or "").strip()
    if kind == "look":
        if not extra:
            raise ApiError("BAD_REQUEST", "先点要看的那块木牌。")
        return f"看 {extra.split()[0]}"
    if kind == "post":
        parts = extra.split("|", 2)
        if len(parts) < 3:
            raise ApiError("BAD_REQUEST", "先写下要钉到哪一块、标题和正文。")
        board, title, body = (parts[0].strip(), parts[1].strip(), parts[2])
        if not board or not title or not body.strip():
            raise ApiError("BAD_REQUEST", "标题和正文都要写。")
        return f"贴 {board} {title} | {body}"
    if kind == "reply":
        tid, sep, body = extra.partition("|")
        if not tid.strip() or not sep or not body.strip():
            raise ApiError("BAD_REQUEST", "先写下回帖。")
        return f"回 {tid.strip()} {body}"
    if kind == "tear":
        if not extra:
            raise ApiError("BAD_REQUEST", "先点要撕的那块木牌。")
        return f"撕 {extra}"
    raise ApiError("BAD_REQUEST", "听潮亭里没有这一下。")


async def snapshot(api_key: str, key_id: int) -> dict[str, Any]:
    try:
        s = await game.require_steward(key_id, exempt_duty=True)
    except ValueError as exc:
        raise classify(exc) from exc
    async with db.connect() as conn:
        shelf = await wall.player_view(conn, s)
        await conn.commit()
    snap = await farm_service.snapshot(api_key, s["id"])
    snap["ting"] = shelf
    return snap


async def act(api_key: str, key_id: int, kind: str, target: str = "") -> dict[str, Any]:
    verb = (kind or "").strip()
    command = _command(verb, target)
    try:
        await game.require_steward(key_id, exempt_duty=True)
    except ValueError as exc:
        raise classify(exc) from exc
    try:
        narrative = await wall.wall_ops(key_id, command)
    except ValueError as exc:
        raise classify(exc) from exc
    snap = await snapshot(api_key, key_id)
    snap["event"] = {
        "title": TITLES.get(verb, "听潮亭"),
        "narrative": humanize(narrative),
        "kind": "ting",
    }
    return snap
