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
    "sink_flood": "碗险处置",
    "tonight": "今晚",
    "staff": "今晚员工",
    "song": "驻唱",
    "request_song": "点歌",
    "tip": "给员工小费",
    "chat": "跟荔栀唠",
    "lodge": "包宿",
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
    if kind in ("tonight", "staff", "song", "lodge"):
        return kind
    if kind == "request_song":
        if not name or "\n" in name or len(name) > 40:
            raise ApiError("BAD_REQUEST", "写一个歌名，不超过 40 个字。")
        return f"request_song {name}"
    if kind == "chat":
        if "\n" in name or len(name) > 60:
            raise ApiError("BAD_REQUEST", "话题写一行，不超过 60 个字。")
        return f"chat {name}".strip()
    if kind == "tip":
        bits = name.split(maxsplit=2)
        if len(bits) < 2 or not bits[1].isdigit() or int(bits[1]) <= 0:
            raise ApiError("BAD_REQUEST", "写员工名和小费票数（正整数）。")
        note = bits[2] if len(bits) > 2 else ""
        if "\n" in note or len(note) > 60:
            raise ApiError("BAD_REQUEST", "备注写一行，不超过 60 个字。")
        return f"tip {bits[0]} {int(bits[1])}" + (f" {note}" if note else "")
    if kind == "sink_flood":
        if not name:
            raise ApiError("BAD_REQUEST", "先选疏通、加班或硬摞。")
        return f"碗险 {name}"
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
