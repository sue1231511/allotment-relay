"""田间管理：肥力、留种、稻草人、监控、砍树腾地、摘收杂草野果、意外记录。

全部翻成已有的 plot_ops 子命令，不新增玩法和数值。虫害处置、浇水打理施肥收获在份地格子和「田间事件」里，不在这里。
"""
from __future__ import annotations

import re
from typing import Any

from .. import game
from .. import mcp_dispatch as mux
from . import farm_service
from .errors import ApiError, classify, humanize

TITLES = {
    "soil": "肥力",
    "seed_list": "种子血统",
    "seed_keep": "留种",
    "scarecrow": "扎稻草人",
    "camera_install": "装监控",
    "camera_remove": "拆监控",
    "camera_check": "监控记录",
    "chop": "砍树腾地",
    "gather": "采集",
    "forage": "觅食",
    "incident_history": "意外记录",
}
_SLOT = re.compile(r"^(?:[0-9]{1,3}|[园棚][0-9]{1,3})$")
_CROP = re.compile(r"^[^\s;\r\n]{1,24}$")


def _slot(value: str) -> str:
    text = (value or "").strip()
    if not _SLOT.match(text):
        raise ApiError("BAD_REQUEST", "地块写数字，或 园1、棚1。")
    return text


def _command(kind: str, target: str) -> str:
    kind = (kind or "").strip()
    target = (target or "").strip()
    if kind == "soil":
        return "肥力"
    if kind == "seed_list":
        return "留种 status"
    if kind == "seed_keep":
        if not _CROP.match(target):
            raise ApiError("BAD_REQUEST", "先写要留种的作物名。")
        return f"留种 {target}"
    if kind in ("scarecrow", "chop"):
        return f"{kind} {_slot(target)}"
    if kind == "camera_install":
        return f"camera install {_slot(target)}"
    if kind == "camera_remove":
        return f"camera remove {_slot(target)}"
    if kind == "camera_check":
        return f"camera check {_slot(target)}" if target else "camera check"
    if kind == "gather":
        return f"gather {_slot(target)}" if target else "gather"
    if kind == "forage":
        return "forage"
    if kind == "incident_history":
        if target and (not target.isdigit() or not 1 <= int(target) <= 50):
            raise ApiError("BAD_REQUEST", "条数写 1 到 50。")
        return f"incident history {target}".strip()
    raise ApiError("BAD_REQUEST", "这里没有这一下。")


async def act(api_key: str, key_id: int, kind: str, target: str = "") -> dict[str, Any]:
    command = _command(kind, target)
    try:
        await game.require_steward(key_id, exempt_duty=kind in ("soil", "seed_list", "camera_check", "incident_history"))
        narrative = await mux.plot_bundle(key_id, command)
    except ValueError as exc:
        raise classify(exc) from exc
    snap = await farm_service.snapshot(api_key, key_id)
    snap["event"] = {"title": TITLES.get(kind, "田间"), "narrative": humanize(narrative), "kind": "field"}
    return snap
