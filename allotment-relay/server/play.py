"""人类上手页 — 同一张凭证、同一套 command，只是换成点按。"""
from __future__ import annotations

from typing import Any

from . import db, steward_dashboard, world
from . import mcp_dispatch as mux
from .catalog import CROPS


def _tools() -> dict[str, Any]:
    from . import bar, craft, lounge, quarry, star, story, tale, theater, undertide

    return {
        "steward_ops": mux.steward_ops,
        "plot_ops": mux.plot_bundle,
        "hut_ops": mux.hut_bundle,
        "tide_ops": mux.tide_bundle,
        "tote_ops": mux.tote_bundle,
        "kitchen_ops": mux.kitchen_bundle,
        "alliance_ops": mux.alliance_bundle,
        "visit_ops": mux.visit_bundle,
        "bar_ops": bar.bar_ops,
        "star_ops": star.star_ops,
        "theater_ops": theater.theater_ops,
        "tale_ops": tale.tale_ops,
        "story_ops": story.story_ops,
        "lounge_ops": lounge.lounge_ops,
        "undertide_ops": undertide.undertide_ops,
        "quarry_ops": quarry.quarry_ops,
        "craft_ops": craft.craft_ops,
    }


PLACES: list[dict[str, Any]] = [
    {
        "id": "bar",
        "name": "滨海酒吧",
        "kicker": "Tonight",
        "blurb": "荔栀的店。点单、双人吧台、上工。",
        "week1": True,
        "duty": True,
        "actions": [
            {"label": "洗碗上工", "tool": "bar_ops", "command": "work 洗碗 night"},
            {"label": "今晚", "tool": "bar_ops", "command": "tonight"},
            {"label": "酒单", "tool": "bar_ops", "command": "menu"},
            {"label": "我的酒吧档", "tool": "bar_ops", "command": "status"},
        ],
    },
    {
        "id": "market",
        "name": "玩家集市",
        "kicker": "Market",
        "blurb": "挂单、交换、看看今天谁在卖东西。",
        "week1": False,
        "actions": [
            {"label": "看集市", "tool": "tote_ops", "command": "market list"},
            {"label": "交换台", "tool": "tote_ops", "command": "swap list"},
        ],
    },
    {
        "id": "tide",
        "name": "海边",
        "kicker": "Tide",
        "blurb": "撒网、赶海、出海。",
        "week1": True,
        "actions": [
            {"label": "撒网", "tool": "tide_ops", "command": "net"},
            {"label": "坐钓", "tool": "tide_ops", "command": "cast"},
            {"label": "赶海看看", "tool": "tide_ops", "command": "beach scan"},
            {"label": "翻沙", "tool": "tide_ops", "command": "dig"},
            {"label": "近海出发", "tool": "tide_ops", "command": "voyage depart near"},
            {"label": "看船", "tool": "tide_ops", "command": "voyage status"},
        ],
    },
    {
        "id": "eatery",
        "name": "岸畔小馆",
        "kicker": "Kitchen",
        "blurb": "点餐、看谁在营业。",
        "week1": True,
        "actions": [
            {"label": "谁在营业", "tool": "kitchen_ops", "command": "shop board"},
            {"label": "菜谱", "tool": "kitchen_ops", "command": "menu"},
        ],
    },
    {
        "id": "craft",
        "name": "岸工坊",
        "kicker": "Workshop",
        "blurb": "打钉、盐田、打捞。",
        "week1": False,
        "actions": [
            {"label": "看砧", "tool": "craft_ops", "command": "status"},
            {"label": "取成品", "tool": "craft_ops", "command": "取"},
            {"label": "灌盐田", "tool": "craft_ops", "command": "灌"},
            {"label": "打捞", "tool": "craft_ops", "command": "打捞"},
        ],
    },
    {
        "id": "star",
        "name": "小橘星光",
        "kicker": "Starlight",
        "blurb": "听她唱、打赏。",
        "week1": False,
        "actions": [
            {"label": "她的档", "tool": "star_ops", "command": "status"},
            {"label": "围观", "tool": "star_ops", "command": "围观"},
        ],
    },
    {
        "id": "hut",
        "name": "岸畔小屋",
        "kicker": "Hut",
        "blurb": "睡一觉、潮柜、畜栏。",
        "week1": True,
        "actions": [
            {"label": "看屋", "tool": "hut_ops", "command": "status"},
            {"label": "睡", "tool": "hut_ops", "command": "睡"},
            {"label": "建棚屋", "tool": "hut_ops", "command": "build"},
            {"label": "畜栏", "tool": "hut_ops", "command": "barn status"},
        ],
    },
    {
        "id": "lounge",
        "name": "聊天室",
        "kicker": "Lounge",
        "blurb": "答疑、岛上说话。",
        "week1": True,
        "actions": [
            {"label": "看最近", "tool": "lounge_ops", "command": "scan"},
        ],
    },
    {
        "id": "quarry",
        "name": "盐风崖",
        "kicker": "Quarry",
        "blurb": "潮脉矿，比赶海慢。",
        "week1": False,
        "actions": [
            {"label": "看崖", "tool": "quarry_ops", "command": "status"},
            {"label": "买镐", "tool": "quarry_ops", "command": "买镐"},
            {"label": "探脉", "tool": "quarry_ops", "command": "探脉"},
            {"label": "挖", "tool": "quarry_ops", "command": "挖"},
        ],
    },
    {
        "id": "undertide",
        "name": "井下",
        "kicker": "Undertide",
        "blurb": "别乱点。真的。",
        "week1": False,
        "caution": True,
        "actions": [
            {"label": "向导", "tool": "undertide_ops", "command": "guide"},
            {"label": "help", "tool": "undertide_ops", "command": "help"},
        ],
    },
]


def climate_bits() -> dict[str, str]:
    from . import season as season_mod

    w, t, p = world.current_weather(), world.current_tide(), world.current_day_phase()
    return {
        "weather": world.weather_label(w),
        "tide": world.tide_label(t),
        "phase": world.day_phase_label(p),
        "season": season_mod.season_name(),
        "line": world.climate_line(),
    }


def seed_options(stock: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for it in stock:
        item = str(it.get("item") or "")
        qty = int(it.get("qty") or 0)
        if not item.startswith("seed_") or qty <= 0:
            continue
        crop = item[5:]
        meta = CROPS.get(crop) or {}
        aliases = meta.get("aliases") or []
        sow_name = aliases[0] if aliases else (meta.get("name") or crop)
        out.append({
            "item": item,
            "crop": crop,
            "name": sow_name,
            "full": meta.get("name") or crop,
            "emoji": meta.get("emoji") or "🌱",
            "qty": qty,
            "tree": bool(meta.get("tree")),
        })
    return out


async def snapshot(api_key: str) -> dict[str, Any]:
    key = api_key.strip()
    row = await db.get_key_row(key)
    if not row:
        raise ValueError("凭证无效")
    s = await db.get_steward_by_key_id(row["id"])
    enrolled = bool(s and s.get("enrolled"))
    dash = None
    seeds: list[dict[str, Any]] = []
    neighbors: dict[str, Any] = {"total": 0, "listed": 0, "online": 0, "window_min": 0, "people": []}
    if enrolled:
        dash = await steward_dashboard.fetch_dashboard(key)
        seeds = seed_options(dash.get("stock") or [])
        from . import multi
        roster = await multi.neighbor_roster(s, online_only=False)
        neighbors = {
            "total": roster["total"],
            "listed": roster["listed"],
            "online": roster["online"],
            "window_min": roster["window_min"],
            "people": roster["people"],
        }
    return {
        "enrolled": enrolled,
        "dashboard": dash,
        "seeds": seeds,
        "neighbors": neighbors,
        "places": PLACES,
        "climate": climate_bits(),
    }


async def run_play(api_key: str, tool: str = "", command: str = "") -> dict[str, Any]:
    key = api_key.strip()
    row = await db.get_key_row(key)
    if not row:
        raise ValueError("凭证无效")
    text = ""
    verb = (tool or "").strip()
    if verb:
        table = _tools()
        if verb not in table:
            raise ValueError(f"未知工具: {verb}。人类上手页只调现有 MCP 工具。")
        text = await mux._call_ops(table[verb], row["id"], command or "")
    snap = await snapshot(key)
    snap["ok"] = True
    snap["text"] = text
    return snap
