"""海边写操作。

MIGRATION BOUNDARY
------------------
撒网 / 坐钓的扣费、精力、渔获与随机事件仍走 `game.tide_ops`。
本模块只做结构化入参、工具/精力预检、稳定错误码和事件卡回包。
下一步把 net/cast 从 tide_ops 抽成 shore_actions，MCP 与 REST 共用。
"""
from __future__ import annotations

from typing import Any

from .. import db, game
from .errors import ApiError, classify, humanize
from . import views


async def snapshot(api_key: str, steward_id: int) -> dict[str, Any]:
    from .. import play, steward_dashboard

    dash = await steward_dashboard.fetch_dashboard(api_key)
    gear = await _gear_view(steward_id)
    return {
        "ok": True,
        "me": views.player_view(dash, enrolled=True),
        "world": views.world_view(play.climate_bits()),
        "shore": gear,
    }


async def _gear_view(steward_id: int) -> dict[str, Any]:
    from .. import energy as energy_mod, gear

    stock = await db.get_satchel(steward_id)
    async with db.connect() as conn:
        stats = await gear.get_stats(conn, steward_id)
        energy_cost, *_ = await energy_mod.net_energy_cost(conn, steward_id)
    net = stats["net"]
    rod = stats["rod"]
    bait_qty = int(stock.get("bait_worm") or 0)
    return {
        "net_tier": int(net.get("tier") or 0),
        "rod_tier": int(rod.get("tier") or 0),
        "bait_worm": bait_qty,
        "can_net": int(net.get("tier") or 0) >= 1,
        "can_cast": int(rod.get("tier") or 0) >= 1 and bait_qty > 0,
        "net_cost_tickets": 4,
        "cast_cost_tickets": 3,
        "net_energy": int(energy_cost),
        "cast_energy": int(rod.get("energy") or 0),
    }


async def cast(api_key: str, key_id: int, mode: str = "net") -> dict[str, Any]:
    verb = (mode or "net").strip().lower()
    if verb in ("撒网", "网"):
        verb = "net"
    if verb in ("坐钓", "钓", "钓鱼"):
        verb = "cast"
    if verb not in ("net", "cast"):
        raise ApiError("BAD_REQUEST", "海边现在只能撒网或坐钓。")

    try:
        s = await game.require_steward(key_id)
    except ValueError as exc:
        raise classify(exc) from exc
    gear = await _gear_view(s["id"])
    if verb == "net" and not gear["can_net"]:
        raise ApiError("TOOL_REQUIRED", "还没有渔网。先把粗渔网升上来再撒。", status=409)
    if verb == "cast" and int(gear["rod_tier"] or 0) < 1:
        raise ApiError("TOOL_REQUIRED", "还没有钓竿。先备一把竹钓竿。", status=409)
    if verb == "cast" and int(gear["bait_worm"] or 0) <= 0:
        raise ApiError("ITEM_REQUIRED", "没有蚯蚓饵，坐钓下不去钩。", status=409)

    # MIGRATION BOUNDARY: 仍调 tide_ops 文本动词，不把 command 回给客户端。
    try:
        narrative = await game.tide_ops(key_id, verb)
    except ValueError as exc:
        raise classify(exc) from exc

    snap = await snapshot(api_key, s["id"])
    title = "撒网" if verb == "net" else "坐钓"
    snap["event"] = {
        "title": title,
        "narrative": humanize(narrative),
        "kind": "shore",
        "mode": verb,
    }
    return snap
