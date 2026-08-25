"""人类上手页 — 同一张凭证、同一套 command，只是换成点按。"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from . import db, steward_dashboard, world
from . import mcp_dispatch as mux
from .catalog import CROPS

# 考勤逾期时，这些地点的动手按钮先换成「去上工」
_DUTY_LOCK_PLACE_IDS = frozenset({"tide", "craft", "quarry", "market"})


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


def _act(
    label: str,
    note: str,
    tool: str,
    command: str,
    *,
    primary: bool = False,
    go: str | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "label": label,
        "note": note,
        "tool": tool,
        "command": command,
    }
    if primary:
        row["primary"] = True
    if go:
        row["go"] = go
    return row


def _bar_work_action(*, overdue: bool) -> dict[str, Any]:
    """按当前时辰给出此刻能点的洗碗班，禁止写死 night。"""
    phase = world.current_day_phase()
    if phase == "night":
        return _act(
            "洗碗上工",
            "夜班 · 每两天须来一次",
            "bar_ops",
            "work 洗碗 night",
            primary=True,
        )
    if phase == "dusk":
        return _act(
            "洗碗上工",
            "暮场白班 · 每两天须来一次",
            "bar_ops",
            "work 洗碗 day",
            primary=True,
        )
    if overdue:
        return _act(
            "洗碗补班",
            "昼间补班 · 票 ×0.72 · 考勤逾期",
            "bar_ops",
            "work 洗碗 day",
            primary=True,
        )
    return _act(
        "洗碗上工",
        "现在昼间打烊，暮/夜再来",
        "bar_ops",
        "tonight",
    )


def _go_bar_duty() -> dict[str, Any]:
    return _act(
        "去上工",
        "酒吧考勤逾期，份地/出海/行囊/崖矿/工坊已锁",
        "",
        "",
        primary=True,
        go="bar",
    )


def _tide_actions(*, overdue: bool) -> list[dict[str, Any]]:
    if overdue:
        return [
            _go_bar_duty(),
            _act("看船", "船况与航程（只看不走）", "tide_ops", "voyage status"),
        ]
    tide = world.current_tide()
    dig = (
        _act("翻沙", "退潮/平潮 · 要铲子", "tide_ops", "dig")
        if tide in ("ebb", "slack")
        else _act("翻沙", "涨潮翻不了 · 先扫一眼沙滩", "tide_ops", "beach scan")
    )
    return [
        _act("撒网", "花票换渔获", "tide_ops", "net"),
        _act("坐钓", "要钓竿和饵", "tide_ops", "cast"),
        _act("赶海看看", "先扫一眼沙滩", "tide_ops", "beach scan"),
        dig,
        _act("近海出发", "开船出海", "tide_ops", "voyage depart near"),
        _act("看船", "船况与航程", "tide_ops", "voyage status"),
    ]


def _craft_actions(*, overdue: bool) -> list[dict[str, Any]]:
    if overdue:
        return [
            _go_bar_duty(),
            _act("看砧", "只看不打", "craft_ops", "status"),
        ]
    tide = world.current_tide()
    salt = (
        _act("灌盐田", "涨潮灌一池", "craft_ops", "灌")
        if tide == "flood"
        else _act("看盐田", "涨潮才能灌 · 先看池", "craft_ops", "盐田")
    )
    return [
        _act("看砧", "先看砧上有没有活", "craft_ops", "status"),
        _act("取成品", "好了才能取", "craft_ops", "取"),
        salt,
        _act("打捞", "只认风暴窗口", "craft_ops", "打捞"),
    ]


def _quarry_actions(*, overdue: bool) -> list[dict[str, Any]]:
    if overdue:
        return [
            _go_bar_duty(),
            _act("看崖", "只看不挖", "quarry_ops", "status"),
        ]
    return [
        _act("看崖", "先看看今天露了什么", "quarry_ops", "status"),
        _act("买镐", "没有工具先补一把", "quarry_ops", "买镐"),
        _act("探脉", "找今天值得下手的位置", "quarry_ops", "探脉"),
        _act("挖", "真正挥镐", "quarry_ops", "挖"),
    ]


def _market_actions(*, overdue: bool) -> list[dict[str, Any]]:
    if overdue:
        return [
            _go_bar_duty(),
            _act("看集市", "只看挂单", "tote_ops", "market list"),
        ]
    return [
        _act("看集市", "先看谁挂了什么", "tote_ops", "market list"),
        _act("交换台", "白送与领取", "tote_ops", "swap list"),
    ]


def _bar_actions(*, overdue: bool) -> list[dict[str, Any]]:
    return [
        _bar_work_action(overdue=overdue),
        _act("今晚", "看看今晚开不开门", "bar_ops", "tonight"),
        _act("酒单", "价目与今晚出品", "bar_ops", "menu"),
        _act("我的酒吧档", "考勤与上工记录", "bar_ops", "status"),
    ]


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
        "actions": [],  # live_places 按潮汐/考勤填
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
        "actions": [],  # live_places 按时辰填洗碗班
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
            {"label": "岸维", "note": "产业维修费。每天划，单价至少 10 票，起步免", "tool": "visit_ops", "command": "潮生会 维"},
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
        "actions": [],  # live_places 按考勤填
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
        "actions": [],  # live_places 按潮汐/考勤填
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
        "id": "quarry",
        "name": "盐风崖",
        "kicker": "Quarry",
        "blurb": "潮脉矿，比赶海慢。",
        "href": "/quarry",
        "live": "打开盐风崖现场 →",
        "rail": "今天在崖上做什么",
        "week1": False,
        "actions": [],  # live_places 按考勤填
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


def live_places(*, overdue: bool = False) -> list[dict[str, Any]]:
    """按此刻时辰 / 潮汐 / 考勤给出可点的动作，避免写死 night 班或涨潮关的翻沙。"""
    out: list[dict[str, Any]] = []
    for raw in PLACES:
        place = deepcopy(raw)
        pid = place["id"]
        if pid == "bar":
            place["actions"] = _bar_actions(overdue=overdue)
        elif pid == "tide":
            place["actions"] = _tide_actions(overdue=overdue)
        elif pid == "craft":
            place["actions"] = _craft_actions(overdue=overdue)
        elif pid == "quarry":
            place["actions"] = _quarry_actions(overdue=overdue)
        elif pid == "market":
            place["actions"] = _market_actions(overdue=overdue)
        elif overdue and pid in _DUTY_LOCK_PLACE_IDS:
            place["actions"] = [_go_bar_duty(), *place.get("actions", [])]
        out.append(place)
    return out


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
    """班次码与短说明。暮→day/白班，夜→night/夜班；昼间码仍是 day（仅逾期补班可用）。"""
    phase = world.current_day_phase()
    if phase == "night":
        return "night", "夜班"
    if phase == "dusk":
        return "day", "白班"
    return "day", "暮/夜开门；白班仅暮可上"


def bar_place_actions(*, overdue: bool = False) -> list[dict[str, Any]]:
    """兼容旧测试名；实际走 live_places 的酒吧动作（昼间未逾期会改成看今晚）。"""
    return _bar_actions(overdue=overdue)


def places_for_client(*, overdue: bool = False) -> list[dict[str, Any]]:
    """兼容旧入口；与 live_places 相同。"""
    return live_places(overdue=overdue)

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
    overdue = False
    if enrolled:
        from . import bar as bar_mod

        overdue = bar_mod.is_shift_overdue(s)
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
        "places": live_places(overdue=overdue),
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
