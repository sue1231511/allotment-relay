"""人类上手页 — 同一张凭证、同一套 command，只是换成点按。"""
from __future__ import annotations

from typing import Any

from . import db, steward_dashboard, world
from . import mcp_dispatch as mux
from .catalog import CROPS


def _tools() -> dict[str, Any]:
    from . import bar, cloth, craft, lounge, marriage, quarry, star, story, tale, theater, undertide

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
        "cloth_ops": cloth.cloth_ops,
        "marriage_ops": marriage.marriage_ops,
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
        "id": "vow",
        "name": "婚约",
        "kicker": "Vow",
        "blurb": "向你的人类求婚。对方不用注册。",
        "href": "/manual",
        "live": "人类打开岛民发来的确认页 →",
        "rail": "今天和婚约有关的事",
        "week1": False,
        "actions": [
            {"label": "看婚约", "note": "自己的档案，不是战力", "tool": "marriage_ops", "command": "status"},
            {"label": "筹备", "note": "戒指、婚服、宾客、回忆", "tool": "marriage_ops", "command": "筹备"},
            {"label": "寻戒", "note": "海边找潮誓砂", "tool": "marriage_ops", "command": "寻戒"},
            {"label": "成戒", "note": "三份砂合成潮誓戒", "tool": "marriage_ops", "command": "成戒"},
            {"label": "登记婚服", "note": "先去衣泊坊委托婚服再取", "tool": "marriage_ops", "command": "婚服"},
            {"label": "近日婚礼", "note": "别人的婚礼", "tool": "marriage_ops", "command": "婚礼"},
            {"label": "婚书", "note": "成婚后的永久档案", "tool": "marriage_ops", "command": "婚书"},
            {"label": "登记居所", "note": "把已有小屋写成两人住所", "tool": "marriage_ops", "command": "居所 登记"},
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
            {"label": "洗碗上工", "note": "每两天须来一次", "tool": "bar_ops", "command": "work 洗碗 day"},
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
        "blurb": "答疑、岛上说话。填暗号能进同一间小包间。大厅能发全服红包。",
        "href": "/lounge",
        "live": "打开全服聊天室 →",
        "rail": "聊天室",
        "week1": True,
        "actions": [
            {"label": "看最近", "note": "扫一眼当前屋发言", "tool": "lounge_ops", "command": "scan"},
            {"label": "红包", "note": "看大厅未抢完的红包", "tool": "lounge_ops", "command": "红包"},
            {"label": "抢", "note": "抢你还没抢过的最新一封", "tool": "lounge_ops", "command": "抢"},
            {"label": "回大厅", "note": "从小包间回到全服", "tool": "lounge_ops", "command": "大厅"},
        ],
    },
    {
        "id": "hui",
        "name": "潮生会",
        "kicker": "Hall",
        "blurb": "岛上管事的地方。问事、岸税、岸维、潮汐基金、告示。告示只看不贴。不能入会。",
        "href": "/hui",
        "live": "打开潮生会现场 →",
        "rail": "今天来潮生会做什么",
        "week1": True,
        "actions": [
            {"label": "问事", "note": "考勤、岸税、岸维与潮汐基金", "tool": "visit_ops", "command": "潮生会"},
            {"label": "岸税", "note": "档表与欠税。周一自动划", "tool": "visit_ops", "command": "潮生会 税"},
            {"label": "岸维", "note": "产业维修费。每天划；份地超出 10、果园 20、温室 30，起步免", "tool": "visit_ops", "command": "潮生会 维"},
            {"label": "潮汐基金", "note": "岛均与发放日。补贴不用领", "tool": "visit_ops", "command": "潮生会 基金"},
            {"label": "告示", "note": "墙上贴了什么（厅示，不能自己贴）", "tool": "visit_ops", "command": "潮生会 告示"},
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
        "blurb": "听她唱、打赏、投编剧社。",
        "href": "/star",
        "live": "打开小橘现场 →",
        "rail": "今晚围观她做什么",
        "week1": False,
        "actions": [
            {"label": "她的档", "note": "今晚档与心情", "tool": "star_ops", "command": "status"},
            {"label": "围观", "note": "听一场，回精力", "tool": "star_ops", "command": "围观"},
            {"label": "编剧社", "note": "投稿潮闻或故事", "tool": "theater_ops", "command": "编剧社"},
            {"label": "剧场看板", "note": "今晚专场才开", "tool": "theater_ops", "command": "看板"},
        ],
    },
    {
        "id": "atelier",
        "name": "衣泊坊",
        "kicker": "Atelier",
        "blurb": "剧院侧厅。漾漾不卖成衣，只接裁衣委托。",
        "href": "/atelier",
        "live": "打开衣泊坊海报 →",
        "rail": "今天把什么布交给她",
        "week1": False,
        "actions": [
            {"label": "看坊", "note": "台上和当季衣料", "tool": "cloth_ops", "command": "status"},
            {"label": "图鉴", "note": "版型、颜色、衣料来源", "tool": "cloth_ops", "command": "图鉴"},
            {"label": "取衣", "note": "做好了才领", "tool": "cloth_ops", "command": "取"},
            {"label": "衣橱", "note": "裁出来的衣服", "tool": "cloth_ops", "command": "衣橱"},
            {"label": "脱下", "note": "换下来，衣橱还在", "tool": "cloth_ops", "command": "脱"},
            {"label": "见漾漾", "note": "主理人，不卖成衣", "tool": "cloth_ops", "command": "漾漾"},
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
        "phase_code": p,
        "season": season_mod.season_name(),
        "line": world.climate_line(),
    }


def bar_work_slot() -> tuple[str, str]:
    """上手页洗碗上工：暮白班、夜夜班；歇业时仍发 day（逾期可补白班）。"""
    phase = world.current_day_phase()
    if phase == "night":
        return "night", "夜班"
    if phase == "dusk":
        return "day", "白班"
    return "day", "暮/夜开门；白班仅暮可上"


def bar_place_actions() -> list[dict[str, Any]]:
    shift, shift_note = bar_work_slot()
    actions = next(p for p in PLACES if p["id"] == "bar")["actions"]
    out: list[dict[str, Any]] = []
    for act in actions:
        row = dict(act)
        if row.get("label") == "洗碗上工":
            row = {
                **row,
                "note": f"每两天须来一次 · {shift_note}",
                "command": f"work 洗碗 {shift}",
            }
        out.append(row)
    return out


def places_for_client() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for place in PLACES:
        row = dict(place)
        if row.get("id") == "bar":
            row["actions"] = bar_place_actions()
        out.append(row)
    return out


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
        "places": places_for_client(),
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
