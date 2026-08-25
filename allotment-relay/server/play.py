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
        "id": "tide",
        "name": "海边",
        "kicker": "Tide",
        "blurb": "撒网、赶海、出海。",
        "href": "/tide",
        "live": "打开海边现场 →",
        "rail": "今天在海边做什么",
        "week1": True,
        "actions": [
            {"label": "撒网", "note": "花票换渔获", "tool": "tide_ops", "command": "net"},
            {"label": "坐钓", "note": "要钓竿和饵", "tool": "tide_ops", "command": "cast"},
            {"label": "赶海看看", "note": "先扫一眼沙滩", "tool": "tide_ops", "command": "beach scan"},
            {"label": "翻沙", "note": "要铲子；涨潮关", "tool": "tide_ops", "command": "dig"},
            {"label": "近海出发", "note": "开船出海", "tool": "tide_ops", "command": "voyage depart near"},
            {"label": "看船", "note": "船况与航程", "tool": "tide_ops", "command": "voyage status"},
        ],
    },
    {
        "id": "hut",
        "name": "岸畔小屋",
        "kicker": "Hut",
        "blurb": "睡一觉、潮柜、畜栏。",
        "href": "/huts",
        "live": "打开小屋现场 →",
        "rail": "今天回家做什么",
        "week1": True,
        "actions": [
            {"label": "看屋", "note": "门牌与装件", "tool": "hut_ops", "command": "status"},
            {"label": "睡", "note": "回精力，每天一次", "tool": "hut_ops", "command": "睡"},
            {"label": "建棚屋", "note": "还没屋就先搭", "tool": "hut_ops", "command": "build"},
            {"label": "堆肥桶", "note": "先买再装空槽，丢粪便沤肥", "tool": "hut_ops", "command": "堆肥桶"},
            {"label": "畜栏", "note": "喂养与收奶", "tool": "hut_ops", "command": "barn status"},
        ],
    },
    {
        "id": "bar",
        "name": "滨海酒吧",
        "kicker": "Tonight",
        "blurb": "荔栀的店。点单、双人吧台、上工。",
        "href": "/bar",
        "live": "打开酒吧现场 →",
        "rail": "今晚在酒吧做什么",
        "week1": True,
        "duty": True,
        "actions": [
            {"label": "洗碗上工", "note": "每两天须来一次", "tool": "bar_ops", "command": "work 洗碗 night"},
            {"label": "今晚", "note": "看看今晚开不开门", "tool": "bar_ops", "command": "tonight"},
            {"label": "酒单", "note": "价目与今晚出品", "tool": "bar_ops", "command": "menu"},
            {"label": "我的酒吧档", "note": "考勤与上工记录", "tool": "bar_ops", "command": "status"},
        ],
    },
    {
        "id": "eatery",
        "name": "岸畔小馆",
        "kicker": "Kitchen",
        "blurb": "点餐、看谁在营业。",
        "href": "/eatery",
        "live": "打开小馆现场 →",
        "rail": "今天在小馆做什么",
        "week1": True,
        "actions": [
            {"label": "谁在营业", "note": "全服小馆名单", "tool": "kitchen_ops", "command": "shop board"},
            {"label": "菜谱", "note": "能做的定点菜", "tool": "kitchen_ops", "command": "menu"},
        ],
    },
    {
        "id": "lounge",
        "name": "聊天室",
        "kicker": "Lounge",
        "blurb": "答疑、岛上说话。这里就能聊。",
        "href": "/lounge",
        "live": "打开全服聊天室 →",
        "rail": "聊天室",
        "week1": True,
        "actions": [
            {"label": "看最近", "note": "扫一眼最近发言", "tool": "lounge_ops", "command": "scan"},
        ],
    },
    {
        "id": "hui",
        "name": "潮生会",
        "kicker": "Hall",
        "blurb": "岛上管事的地方。问事、岸税、岸维、潮汐基金、告示。不能入会。",
        "href": "/hui",
        "live": "打开潮生会现场 →",
        "rail": "今天来潮生会做什么",
        "week1": True,
        "actions": [
            {"label": "问事", "note": "考勤、岸税、岸维与潮汐基金", "tool": "visit_ops", "command": "潮生会"},
            {"label": "岸税", "note": "档表与欠税。周一自动划", "tool": "visit_ops", "command": "潮生会 税"},
            {"label": "岸维", "note": "产业维修费。每天划，日单价 2 起，起步免", "tool": "visit_ops", "command": "潮生会 维"},
            {"label": "潮汐基金", "note": "岛均与发放日。补贴不用领", "tool": "visit_ops", "command": "潮生会 基金"},
            {"label": "告示", "note": "墙上贴了什么", "tool": "visit_ops", "command": "潮生会 告示"},
        ],
    },
    {
        "id": "clinic",
        "name": "桥桥诊所",
        "kicker": "Clinic",
        "blurb": "地上的病来这里。井下伤归晏安，桥桥不接。",
        "rail": "今天来诊所做什么",
        "week1": False,
        "actions": [
            {"label": "进门", "note": "氛围、斑鸠、价目", "tool": "visit_ops", "command": "clinic status"},
            {"label": "看病", "note": "一次尽量治完当前地上病", "tool": "visit_ops", "command": "clinic treat all"},
            {"label": "药架", "note": "可囤的药", "tool": "visit_ops", "command": "clinic catalog"},
            {"label": "喂斑鸠", "note": "雾豌豆×1，每日一次", "tool": "visit_ops", "command": "clinic dove 喂"},
        ],
    },
    {
        "id": "market",
        "name": "玩家集市",
        "kicker": "Market",
        "blurb": "挂单、交换、看看今天谁在卖东西。",
        "href": "/market",
        "live": "打开集市现场 →",
        "rail": "今天在集市做什么",
        "week1": False,
        "actions": [
            {"label": "看集市", "note": "先看谁挂了什么", "tool": "tote_ops", "command": "market list"},
            {"label": "交换台", "note": "白送与领取", "tool": "tote_ops", "command": "swap list"},
        ],
    },
    {
        "id": "craft",
        "name": "岸工坊",
        "kicker": "Workshop",
        "blurb": "打钉、晒盐、收拾风暴后的破烂。",
        "href": "/workshop",
        "live": "打开岸工坊现场 →",
        "rail": "今天在工坊做什么",
        "week1": False,
        "actions": [
            {"label": "看砧", "note": "先看砧上有没有活", "tool": "craft_ops", "command": "status"},
            {"label": "取成品", "note": "好了才能取", "tool": "craft_ops", "command": "取"},
            {"label": "灌盐田", "note": "涨潮才能灌", "tool": "craft_ops", "command": "灌"},
            {"label": "打捞", "note": "只认风暴窗口", "tool": "craft_ops", "command": "打捞"},
        ],
    },
    {
        "id": "star",
        "name": "小橘星光",
        "kicker": "Starlight",
        "blurb": "听她唱、打赏。",
        "href": "/star",
        "live": "打开小橘现场 →",
        "rail": "今晚围观她做什么",
        "week1": False,
        "actions": [
            {"label": "她的档", "note": "今晚档与心情", "tool": "star_ops", "command": "status"},
            {"label": "围观", "note": "听一场，回精力", "tool": "star_ops", "command": "围观"},
        ],
    },
    {
        "id": "quarry",
        "name": "盐风崖",
        "kicker": "Quarry",
        "blurb": "潮脉矿，比赶海慢。",
        "href": "/quarry",
        "live": "打开盐风崖现场 →",
        "rail": "今天在崖上做什么",
        "week1": False,
        "actions": [
            {"label": "看崖", "note": "先看看今天露了什么", "tool": "quarry_ops", "command": "status"},
            {"label": "买镐", "note": "没有工具先补一把", "tool": "quarry_ops", "command": "买镐"},
            {"label": "探脉", "note": "找今天值得下手的位置", "tool": "quarry_ops", "command": "探脉"},
            {"label": "挖", "note": "真正挥镐", "tool": "quarry_ops", "command": "挖"},
        ],
    },
    {
        "id": "undertide",
        "name": "井下",
        "kicker": "Undertide",
        "blurb": "别乱点。真的。下去会蚀岛缘。",
        "href": "/undertide",
        "live": "打开井下劝退 →",
        "rail": "真的要下去吗",
        "week1": False,
        "caution": True,
        "actions": [
            {"label": "向导", "note": "先读规矩", "tool": "undertide_ops", "command": "guide"},
            {"label": "help", "note": "真指令列表", "tool": "undertide_ops", "command": "help"},
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
