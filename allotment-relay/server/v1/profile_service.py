"""「这一号」：档案、岛缘、成就称呼、收集、引航、灾档灾选、周报、维修待办、改档。

文字都来自已有的 ``steward_ops`` 子命令；改岛民名走上手页同一条人类改名（不进 MCP）。
这里只把有限的点按翻成既有命令，不新增数值。
"""
from __future__ import annotations

import logging
import re
from typing import Any

from .. import db, event_choice, game, invite
from .. import mcp_dispatch as mux
from . import farm_service
from .errors import ApiError, classify, humanize

log = logging.getLogger(__name__)

TITLES = {
    "sheet": "档案",
    "bond": "岛缘",
    "titles": "成就与称呼",
    "title_wear": "佩戴称呼",
    "title_off": "卸下称呼",
    "collection": "收集簿",
    "invite": "引航",
    "invite_bind": "绑定引航",
    "tierlog": "灾档",
    "choice": "灾选",
    "gazette": "本周纪事",
    "repair": "待办",
    "gifts": "收礼",
    "revise": "改座右铭与肖像",
    "rename": "改岛民名",
}
_NO_ARG = {
    "sheet": "sheet",
    "bond": "岛缘",
    "titles": "成就",
    "title_off": "卸",
    "collection": "收集",
    "invite": "引航",
    "tierlog": "灾档",
    "gazette": "周报",
    "repair": "维修",
    "gifts": "收礼",
}
_CODE = re.compile(r"^[A-Za-z0-9]{4,16}$")
_WORD = re.compile(r"^[\w一-鿿]{1,24}$")


def _line(value: str, label: str, limit: int) -> str:
    text = (value or "").strip()
    if not text or len(text) > limit or any(ch in text for ch in "\r\n"):
        raise ApiError("BAD_REQUEST", f"{label}写一行，不超过 {limit} 个字。")
    return text


def _command(kind: str, target: str) -> str:
    kind = (kind or "").strip()
    target = (target or "").strip()
    if kind in _NO_ARG:
        return _NO_ARG[kind]
    if kind == "title_wear":
        return f"称呼 {_line(target, '称呼', 24)}"
    if kind == "invite_bind":
        if not _CODE.match(target):
            raise ApiError("BAD_REQUEST", "邀请码是 4 到 16 位字母数字。")
        return f"绑定 {target}"
    if kind == "choice":
        bits = target.split()
        if len(bits) != 2 or not all(_WORD.match(b) for b in bits):
            raise ApiError("BAD_REQUEST", "先选哪件事、哪一路。")
        return f"灾选 {bits[0]} {bits[1]}"
    if kind == "revise":
        motto, _, portrait = target.partition("|")
        motto, portrait = motto.strip(), portrait.strip()
        if not motto and not portrait:
            raise ApiError("BAD_REQUEST", "座右铭和肖像至少写一样。")
        for label, value in (("座右铭", motto), ("肖像", portrait)):
            if value and (len(value) > 200 or "\n" in value or "\r" in value):
                raise ApiError("BAD_REQUEST", f"{label}写一行，不超过 200 个字。")
        if motto and portrait:
            return f"revise {motto} portrait {portrait}"
        return f"revise portrait {portrait}" if portrait else f"revise {motto}"
    raise ApiError("BAD_REQUEST", "这里没有这一下。")


async def snapshot(api_key: str, key_id: int, base: str = "") -> dict[str, Any]:
    try:
        steward = await game.require_steward(key_id, exempt_duty=True)
        invite_view = await invite.player_view(steward, base=base)
        async with db.connect() as conn:
            choices = await event_choice.list_open(conn, int(steward["id"]))
    except ValueError as exc:
        raise classify(exc) from exc
    fresh = await db.get_steward_by_id(int(steward["id"])) or steward
    snap = await farm_service.snapshot(api_key, key_id)
    snap["profile"] = {
        "name": fresh.get("name") or "",
        "motto": fresh.get("motto") or "",
        "portrait": fresh.get("portrait") or "",
        "invite": {
            "code": invite_view.get("code") or "",
            "link": invite_view.get("link") or "",
            "bound": bool(invite_view.get("bound")),
            "can_bind": bool(invite_view.get("can_bind")),
            "inviter": (invite_view.get("inviter") or {}).get("name") or "",
            "valid_count": int(invite_view.get("valid_count") or 0),
            "invited": len(invite_view.get("invited") or []),
        },
        "choices": [
            {"key": row["key"], "via": row.get("via") or row["key"], "opts": list(row.get("opts") or [])}
            for row in choices
        ],
    }
    return snap


async def act(api_key: str, key_id: int, kind: str, target: str = "", base: str = "") -> dict[str, Any]:
    kind = (kind or "").strip()
    if kind == "rename":
        return await rename(api_key, key_id, target, base)
    command = _command(kind, target)
    try:
        narrative = await mux.steward_ops(key_id, command)
    except ValueError as exc:
        raise classify(exc) from exc
    snap = await snapshot(api_key, key_id, base)
    snap["event"] = {"title": TITLES.get(kind, "这一号"), "narrative": humanize(narrative), "kind": "profile"}
    return snap


async def rename(api_key: str, key_id: int, target: str, base: str = "") -> dict[str, Any]:
    """人类改岛民名：和上手页 /api/steward/rename 同一个 db.rename_steward，不进 MCP。"""
    try:
        steward = await game.require_steward(key_id, exempt_duty=True)
        old = steward["name"]
        updated = await db.rename_steward(int(steward["id"]), _line(target, "岛民名", 24))
    except ValueError as exc:
        raise classify(exc) from exc
    snap = await snapshot(api_key, key_id, base)
    snap["event"] = {
        "title": TITLES["rename"],
        "narrative": f"岛民名已从「{old}」改为「{updated['name']}」。",
        "kind": "profile",
    }
    return snap
