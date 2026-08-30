"""第一周地点写操作：小屋、酒吧、小馆、潮生会。

MIGRATION BOUNDARY
------------------
仍走现有 hut_ops / bar_ops / kitchen_ops / visit_ops，不另做数值。
本模块只做结构化入参和事件卡回包。
"""
from __future__ import annotations

from typing import Any

from .. import game, play
from .errors import ApiError, classify, humanize
from . import farm_service


async def snapshot(api_key: str, steward_id: int) -> dict[str, Any]:
    return await farm_service.snapshot(api_key, steward_id)


def _event(title: str, narrative: str, kind: str) -> dict[str, str]:
    return {"title": title, "narrative": humanize(narrative), "kind": kind}


async def sleep(api_key: str, key_id: int) -> dict[str, Any]:
    try:
        s = await game.require_steward(key_id, exempt_duty=True)
    except ValueError as exc:
        raise classify(exc) from exc
    from .. import hut

    try:
        narrative = await hut.hut_ops(key_id, "睡")
    except ValueError as exc:
        raise classify(exc) from exc
    snap = await snapshot(api_key, s["id"])
    snap["event"] = _event("睡觉", narrative, "hut")
    return snap


async def build_hut(api_key: str, key_id: int) -> dict[str, Any]:
    try:
        s = await game.require_steward(key_id, exempt_duty=True)
    except ValueError as exc:
        raise classify(exc) from exc
    from .. import hut

    try:
        narrative = await hut.hut_ops(key_id, "build")
    except ValueError as exc:
        raise classify(exc) from exc
    snap = await snapshot(api_key, s["id"])
    snap["event"] = _event("搭棚屋", narrative, "hut")
    return snap


async def work(api_key: str, key_id: int) -> dict[str, Any]:
    try:
        s = await game.require_steward(key_id, exempt_duty=True)
    except ValueError as exc:
        raise classify(exc) from exc
    from .. import bar as bar_mod

    shift, _note = play.bar_work_slot()
    try:
        narrative = await bar_mod.bar_ops(key_id, f"work 洗碗 {shift}")
    except ValueError as exc:
        raise classify(exc) from exc
    snap = await snapshot(api_key, s["id"])
    snap["event"] = _event("上工", narrative, "bar")
    return snap


async def eat(api_key: str, key_id: int, item: str) -> dict[str, Any]:
    name = (item or "").strip()
    if not name:
        raise ApiError("BAD_REQUEST", "先选要吃的东西。")
    try:
        s = await game.require_steward(key_id, exempt_duty=True)
    except ValueError as exc:
        raise classify(exc) from exc
    from .. import kitchen

    try:
        narrative = await kitchen.kitchen_ops(key_id, f"eat {name}")
    except ValueError as exc:
        raise classify(exc) from exc
    snap = await snapshot(api_key, s["id"])
    snap["event"] = _event("吃饭", narrative, "eatery")
    return snap


async def pay(api_key: str, key_id: int, kind: str) -> dict[str, Any]:
    raw = (kind or "").strip().lower()
    if raw in ("tax", "税", "岸税"):
        command = "潮生会 税 交"
        title = "交岸税"
    elif raw in ("upkeep", "维", "岸维", "维修"):
        command = "潮生会 维 交"
        title = "交岸维"
    else:
        raise ApiError("BAD_REQUEST", "只能交岸税或岸维。")
    try:
        s = await game.require_steward(key_id, exempt_duty=True)
    except ValueError as exc:
        raise classify(exc) from exc
    from .. import mcp_dispatch as mux

    try:
        narrative = await mux.visit_bundle(key_id, command)
    except ValueError as exc:
        raise classify(exc) from exc
    snap = await snapshot(api_key, s["id"])
    snap["event"] = _event(title, narrative, "hui")
    return snap
