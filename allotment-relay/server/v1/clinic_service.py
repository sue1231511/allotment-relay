"""乔乔诊所写操作。看病 / 调理 / 买药 / 喂斑鸠仍走 clinic_ops，不另做数值。"""
from __future__ import annotations

from typing import Any

from .. import clinic, db, game
from . import farm_service
from .errors import ApiError, classify, humanize


TITLES = {
    "treat": "看过病",
    "tonic": "调过了",
    "buy": "买到了",
    "use": "服下了",
    "dove": "喂了斑鸠",
    "chat": "聊了聊",
    "look": "乔乔诊所",
}


def _command(kind: str, target: str) -> str:
    extra = (target or "").strip()
    if kind == "look":
        if extra in ("chat", "闲聊"):
            return "chat"
        if extra in ("dove", "斑鸠", "窗台"):
            return "dove"
        if extra in ("catalog", "价目"):
            return "catalog"
        return "status"
    if kind == "treat":
        if not extra:
            raise ApiError("BAD_REQUEST", "先点要治的那一项。")
        if extra in ("all", "全部", "打包"):
            return "treat all"
        return f"treat {extra}"
    if kind == "tonic":
        if extra not in ("小", "中", "大"):
            raise ApiError("BAD_REQUEST", "调理只分小、中、大。")
        return f"调理 {extra}"
    if kind == "buy":
        if not extra:
            raise ApiError("BAD_REQUEST", "先点要买的药。")
        return f"buy {extra}"
    if kind == "use":
        if not extra:
            raise ApiError("BAD_REQUEST", "先点要服的药。")
        return f"use {extra}"
    if kind == "dove":
        return "dove 喂"
    if kind == "chat":
        return "chat"
    raise ApiError("BAD_REQUEST", "诊所用不上这一下。")


async def snapshot(api_key: str, key_id: int) -> dict[str, Any]:
    try:
        s = await game.require_steward(key_id, exempt_duty=True)
    except ValueError as exc:
        raise classify(exc) from exc
    async with db.connect() as conn:
        shelf = await clinic.player_view(conn, s)
        await conn.commit()
    snap = await farm_service.snapshot(api_key, s["id"])
    snap["clinic"] = shelf
    return snap


async def act(api_key: str, key_id: int, kind: str, target: str = "") -> dict[str, Any]:
    verb = (kind or "").strip()
    command = _command(verb, target)
    try:
        await game.require_steward(key_id, exempt_duty=True)
    except ValueError as exc:
        raise classify(exc) from exc
    try:
        narrative = await clinic.clinic_ops(key_id, command)
    except ValueError as exc:
        raise classify(exc) from exc
    snap = await snapshot(api_key, key_id)
    snap["event"] = {
        "title": TITLES.get(verb, "乔乔诊所"),
        "narrative": humanize(narrative),
        "kind": "clinic",
    }
    return snap
