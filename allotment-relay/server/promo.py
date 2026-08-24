"""岛上地点宣传 — 海报合在首页 /，不是单独 UI，也不是上手台。"""
from __future__ import annotations

from typing import Any

# slug = 首页锚点 id。go = 上手页 ?go=
PLACES: list[dict[str, Any]] = [
    {
        "slug": "allotments",
        "path": "/#allotments",
        "go": "",
        "eyebrow": "Plots",
        "name": "份地",
        "lead": "岛把地分给管理员。起步三块，种手里的种，等潮汐。",
        "body": [
            "甘蓝、甜菜、雾豆先下地。熟了再收，急不来。",
            "人和管家公用一个号。宣传页不种地，上手页才下锄。",
        ],
        "aside": "AI 走 plot_ops。人去上手页点按同一块地。",
        "cta": "去种地",
        "note": "份地",
    },
    {
        "slug": "huts",
        "path": "/#huts",
        "go": "hut",
        "eyebrow": "Hut",
        "name": "小屋",
        "lead": "岸上睡觉、潮柜、畜栏。困了回来。",
        "body": [
            "棚屋要自己搭。床、冰箱、堆肥桶是后来的事。",
            "工坊打出来的秤锤、铁锄刃、滤网，要装上才算数。",
        ],
        "aside": "AI 走 hut_ops。人去上手页睡一觉、看畜栏。",
        "cta": "去小屋",
        "note": "小屋",
    },
    {
        "slug": "tide",
        "path": "/#tide",
        "go": "tide",
        "eyebrow": "Tide",
        "name": "海边",
        "lead": "撒网、坐钓、赶海、出海。涨潮时翻沙的人会空手回来。",
        "body": [
            "近海就能出发。矿不是赶海，风暴后下滩走工坊。",
            "黑旗截停的时候，打、逃、谈都在上手页。",
        ],
        "aside": "AI 走 tide_ops。人去上手页下海。",
        "cta": "去海边",
        "note": "海边",
    },
    {
        "slug": "bar",
        "path": "/#bar",
        "go": "bar",
        "eyebrow": "Coastal bar",
        "name": "滨海酒吧",
        "lead": "经营不顺可以来打工。经营太顺可以来花钱。成年人总得有个地方坐到很晚。",
        "body": [
            "老板荔栀。暮夜才开门。驻唱是「我哪有旺夫命」。",
            "每两天须来上工一次，否则锁份地、出海、行囊、崖矿、工坊。这是岛规，不是支线。",
            "酒单上有海盐拉格、暮港小麦、柚子气泡酒；陪聊一杯、海风故事、卡座驻场是另一回事。",
        ],
        "aside": "点单、双人吧台、洗碗打卡都在上手页。",
        "cta": "去酒吧",
        "note": "酒吧",
    },
    {
        "slug": "eatery",
        "path": "/#eatery",
        "go": "eatery",
        "eyebrow": "Seaside kitchen",
        "name": "岸畔小馆",
        "lead": "管理员开的熟菜馆。不追求米其林，能吃饱就已经赢了一半。",
        "body": [
            "堂食按价回精力，还带两小时饱餐。家里自己煮没有这些。",
            "想开张要先有小屋和冰箱。",
        ],
        "aside": "点餐在上手页。",
        "cta": "去小馆",
        "note": "小馆",
    },
    {
        "slug": "market",
        "path": "/#market",
        "go": "market",
        "eyebrow": "Market",
        "name": "集市",
        "lead": "挂单、交换。卖货回家自己吃，堂食去小馆。",
        "body": [
            "摊格有上限，满了先扩。系统回收压得低，想赚钱走玩家之间。",
        ],
        "aside": "AI 走 tote_ops market。人去上手页摆摊。",
        "cta": "去集市",
        "note": "集市",
    },
    {
        "slug": "quarry",
        "path": "/#quarry",
        "go": "quarry",
        "eyebrow": "Quarry",
        "name": "盐风崖",
        "lead": "迎风崖上的矿脉随潮汐显隐。比赶海慢，比赶海费。",
        "body": [
            "不是沙滩翻沙，也不是井下。先买镐，再探脉，再挖。",
        ],
        "aside": "AI 走 quarry_ops。人去上手页挥镐。",
        "cta": "去盐风崖",
        "note": "崖矿",
    },
    {
        "slug": "workshop",
        "path": "/#workshop",
        "go": "craft",
        "eyebrow": "Workshop",
        "name": "岸工坊",
        "lead": "把矿和畜栏接进生活：打钉、晒盐、风暴后下滩。",
        "body": [
            "不是再挖一次，也不是赶海翻沙。砧上有活才来取。",
        ],
        "aside": "AI 走 craft_ops。人去上手页打钉。",
        "cta": "去工坊",
        "note": "工坊",
    },
    {
        "slug": "star",
        "path": "/#star",
        "go": "star",
        "eyebrow": "Starlight",
        "name": "小橘星光",
        "lead": "这岛不需要红毯。她开嗓的晚上，档口和井下都安静半拍。",
        "body": [
            "常驻荔栀的酒馆，随时能开小剧场专场。",
            "应援要她本人在面板点到才算。打赏、听她唱，去上手页。",
        ],
        "aside": "打赏和听她唱都在上手页。",
        "cta": "去听她唱",
        "note": "小橘",
    },
    {
        "slug": "undertide",
        "path": "/#undertide",
        "go": "undertide",
        "eyebrow": "Undertide",
        "name": "井下",
        "lead": "别乱点。真的。",
        "body": ["滨海酒吧后院那口井。劝退也是介绍。"],
        "aside": "新手别从这儿开局。",
        "cta": "我知道了，仍要去",
        "note": "井下",
    },
]

# 旧独立海报路径 → 首页锚点（外链与书签仍可用）
LEGACY_PLACE_PATHS: tuple[str, ...] = tuple(f"/{p['slug']}" for p in PLACES)


def get(slug: str) -> dict[str, Any]:
    for p in PLACES:
        if p["slug"] == slug:
            return p
    raise KeyError(slug)


def play_href(place: dict[str, Any]) -> str:
    go = place.get("go") or ""
    return f"/play?go={go}" if go else "/play"


def page_context(slug: str) -> dict[str, Any]:
    place = get(slug)
    return {
        "active": slug,
        "place": place,
        "play_href": play_href(place),
    }


def home_places() -> list[dict[str, Any]]:
    """首页用：每处海报带 play_href。"""
    out: list[dict[str, Any]] = []
    for p in PLACES:
        row = dict(p)
        row["play_href"] = play_href(p)
        out.append(row)
    return out
