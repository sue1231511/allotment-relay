"""酒吧写操作。洗碗 / 点酒 / 哄荔栀仍走 bar_ops，不另做数值。"""
from __future__ import annotations

from typing import Any

from .. import bar, db, game
from . import farm_service
from .errors import ApiError, classify, humanize


TITLES = {
    "work": "上工",
    "order": "点了酒",
    "cheer": "跟荔栀说了",
}


def _command(kind: str, target: str) -> str:
    name = (target or "").strip()
    if kind == "work":
        job = name or "洗碗"
        shift, _note = bar.work_slot()
        return f"work {job} {shift}"
    if kind == "order":
        if not name:
            raise ApiError("BAD_REQUEST", "先点要喝的那一杯。")
        return f"order {name.split()[0]}"
    if kind == "cheer":
        if not name:
            raise ApiError("BAD_REQUEST", "说点什么。荔栀不接受沉默的讨好。")
        return f"cheer {name[:100]}"
    raise ApiError("BAD_REQUEST", "酒吧里没有这一下。")


async def snapshot(api_key: str, key_id: int) -> dict[str, Any]:
    try:
        s = await game.require_steward(key_id, exempt_duty=True)
    except ValueError as exc:
        raise classify(exc) from exc
    async with db.connect() as conn:
        shelf = await bar.player_view(conn, s)
        await conn.commit()
    snap = await farm_service.snapshot(api_key, s["id"])
    snap["bar"] = shelf
    return snap


async def act(api_key: str, key_id: int, kind: str, target: str = "") -> dict[str, Any]:
    command = _command((kind or "").strip(), target)
    try:
        await game.require_steward(key_id, exempt_duty=True)
    except ValueError as exc:
        raise classify(exc) from exc
    try:
        narrative = await bar.bar_ops(key_id, command)
    except ValueError as exc:
        raise classify(exc) from exc
    snap = await snapshot(api_key, key_id)
    snap["event"] = {
        "title": TITLES.get(kind, "潮汐酒吧"),
        "narrative": humanize(narrative),
        "kind": "bar",
    }
    return snap
