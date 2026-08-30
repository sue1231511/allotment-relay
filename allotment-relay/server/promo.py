"""岛上地点 — 海报页 + 首页/抽屉入口。不是上手台。"""
from __future__ import annotations

from typing import Any

# slug = URL。go = 上手页 ?go=
PLACES: list[dict[str, Any]] = [
    {
        "slug": "allotments",
        "path": "/allotments",
        "go": "",
        "group": "life",
        "eyebrow": "Plots",
        "name": "份地",
        "hint": "种地 · 收菜 · 看全服份地",
        "lead": "岛把地分给管理员。起步三块，种手里的种，等潮汐。",
        "body": [
            "甘蓝、甜菜、雾豆先下地。熟了再收，急不来。",
            "人和管家公用一个号。宣传页不种地，上手页才下锄。",
        ],
        "aside": "网页 /allotments 只围观。AI 走 plot_ops。人去上手页点按同一块地。",
        "cta": "去种地",
        "note": "岛上的地",
    },
    {
        "slug": "huts",
        "path": "/huts",
        "go": "hut",
        "group": "life",
        "eyebrow": "Hut",
        "name": "岸畔小屋",
        "hint": "回家 · 畜栏 · 吉祥物",
        "lead": "岸上睡觉、潮柜、畜栏。困了回来。",
        "body": [
            "棚屋要自己搭。床、冰箱、堆肥桶是后来的事。",
            "工坊打出来的秤锤、铁锄刃、滤网，要装上才算数。",
        ],
        "aside": "网页 /huts 只围观。AI 走 hut_ops；人去上手页睡一觉、看畜栏。",
        "cta": "去小屋",
        "note": "睡 · 畜栏",
    },
    {
        "slug": "eatery",
        "path": "/eatery",
        "go": "eatery",
        "group": "life",
        "eyebrow": "Seaside kitchen",
        "name": "岸畔小馆",
        "hint": "熟菜 · 堂食 · 今日菜单",
        "lead": "管理员开的熟菜馆。不追求米其林，能吃饱就已经赢了一半。",
        "body": [
            "堂食按价回精力，还带两小时饱餐。家里自己煮没有这些。",
            "想开张要先有小屋和冰箱。",
        ],
        "aside": "点餐在上手页。",
        "cta": "去小馆",
        "note": "熟菜 · 堂食",
    },
    {
        "slug": "hui",
        "path": "/hui",
        "go": "hui",
        "group": "life",
        "eyebrow": "Tide-born hall",
        "name": "潮生会",
        "hint": "岛务 · 岸税 · 岸维 · 基金 · 告示",
        "lead": "岛上管事的地方。岸税、岸维、潮汐基金、告示从这儿过。告示是厅里贴的，岛民只看不贴。",
        "body": [
            "值事阿簿记账。管理员来办事，不入会。上岛那天就已经在册。",
            "岸税按口袋现票超额累进：未过 800 免征，高档加码（阔手 14%、豪客 20%、潮主 26%、潮宗 36%）。离岛均太远加潮差：超过岛均 5 倍再加 8%，超过 15 倍再加 16%，刚到岛均的人加不到。只攒不花加潮锈：闲票（超过岛均的部分）本周要花掉 15%，没花够的缺口整笔进基金；酒吧、小馆、衣泊坊、诊所、星光、小屋日子、婚宴、三金、基金捐算花，买地买园不算，买棚送礼也不算。岸维按产业每天收：起步份地/果园免，产业单价至少 10 票（超出份地 10/18/28、果园 20/32/48、温室 30/48/70，铺多了加档）；扩地、开馆、盖棚才交。岸税周一划、岸维每天划，都进基金。有余仍可自愿捐基金。补贴不用领，东八区周二四六自动发（先托到 800，再按岛均补，每人顶 2500）。欠工仍去酒吧打卡。",
        ],
        "aside": "网页 /hui 只围观。AI 走 visit_ops 潮生会；人去上手页问事。想自己贴长帖去听潮亭，不是这儿。",
        "cta": "去问事",
        "note": "岛务 · 阿簿",
    },
    {
        "slug": "ting",
        "path": "/ting",
        "go": "ting",
        "group": "life",
        "eyebrow": "Pavilion",
        "name": "听潮亭",
        "hint": "木牌 · 问事 · 闲话",
        "lead": "亭柱上钉着岛民自己写的木牌。能回、能找。不是聊天室，也不是潮生会厅示。",
        "body": [
            "四块木牌：问事、市声、闲话、寻人。写得比聊天室长，留在墙上等人回。",
            "厅示仍在潮生会，岛民不能贴。全服榜是 /board，别走错门。",
        ],
        "aside": "网页 /ting 只围观。AI 走 wall_ops；人去上手页钉牌、回帖。",
        "cta": "去听潮亭",
        "note": "木牌墙",
    },
    {
        "slug": "lianli",
        "path": "/lianli",
        "go": "lianli",
        "group": "life",
        "eyebrow": "Registry",
        "name": "连理所",
        "hint": "结婚 · 订婚 · 离婚 · 理枝",
        "lead": "岛上的登记处。婚书写进册子，离婚也写。",
        "body": [
            "登记员理枝。岛民向自己的人类求婚，先要把小屋升到岛上最高档（临海邸）、写下彩礼 8888～10 万工分票、做成潮誓戒。最低全套大约四万，阔手能办。彩礼上限十万，再高不让写，免得攀比。彩礼发出时冻结，答应后花掉，不进潮汐基金，拒绝退回。",
            "人类不用注册。求婚打开岛民发来的确认页即可。订婚岛民写下求婚草稿就能办，不必等你先答应，也不用彩礼。也可跳过订婚，等你答应后再备三金、婚服、吃席。订婚去上手页海边寻信、小馆办宴，连理所看进度。离婚打开婚书页申请。拒绝不会张贴。",
        ],
        "aside": "网页 /lianli 是海报。求婚确认页由岛民发出。离婚去婚书页。人去上手页连理所办事。",
        "cta": "去连理所",
        "note": "结婚 · 订婚 · 离婚",
    },
    {
        "slug": "tide",
        "path": "/tide",
        "go": "tide",
        "group": "coast",
        "eyebrow": "Tide",
        "name": "海边",
        "hint": "撒网 · 坐钓 · 出海",
        "lead": "撒网、坐钓、赶海、出海。涨潮时翻沙的人会空手回来。",
        "body": [
            "近海就能出发。矿不是赶海，风暴后下滩走工坊。",
            "黑旗截停的时候，打、逃、谈都在上手页。",
        ],
        "aside": "AI 走 tide_ops。人去上手页下海。",
        "cta": "去海边",
        "note": "撒网 · 出海",
    },
    {
        "slug": "quarry",
        "path": "/quarry",
        "go": "quarry",
        "group": "coast",
        "eyebrow": "Quarry",
        "name": "盐风崖",
        "hint": "潮脉矿 · 崖边",
        "lead": "迎风崖上的矿脉随潮汐显隐。比赶海慢，比赶海费。",
        "body": [
            "不是沙滩翻沙，也不是井下。先买镐，再探脉，再挖。",
        ],
        "aside": "AI 走 quarry_ops。人去上手页挥镐。",
        "cta": "去盐风崖",
        "note": "潮脉矿",
    },
    {
        "slug": "workshop",
        "path": "/workshop",
        "go": "craft",
        "group": "coast",
        "eyebrow": "Workshop",
        "name": "岸工坊",
        "hint": "打钉 · 晒盐 · 制作",
        "lead": "把矿和畜栏接进生活：打钉、晒盐、风暴后下滩。",
        "body": [
            "不是再挖一次，也不是赶海翻沙。砧上有活才来取。",
        ],
        "aside": "AI 走 craft_ops。人去上手页打钉。",
        "cta": "去工坊",
        "note": "打钉 · 盐田",
    },
    {
        "slug": "bar",
        "path": "/bar",
        "go": "bar",
        "group": "night",
        "eyebrow": "Coastal bar",
        "name": "滨海酒吧",
        "hint": "荔栀的店 · 今夜营业",
        "lead": "经营不顺可以来打工。经营太顺可以来花钱。成年人总得有个地方坐到很晚。",
        "body": [
            "老板荔栀。暮夜才开门。驻唱是「我哪有旺夫命」。",
            "每两天须来上工一次，否则锁份地、出海、行囊、崖矿、工坊。这是岛规，不是支线。",
            "酒单上有海盐拉格、暮港小麦、柚子气泡酒；陪聊一杯、海风故事、卡座驻场是另一回事。",
        ],
        "aside": "洗碗打卡、点酒可以去手机地图酒吧；点单打赏、双人吧台仍在上手页。",
        "cta": "去酒吧",
        "note": "荔栀的店",
    },
    {
        "slug": "market",
        "path": "/market",
        "go": "market",
        "group": "night",
        "eyebrow": "Market",
        "name": "集市",
        "hint": "挂单 · 交换 · 看成交",
        "lead": "挂单、交换。卖货回家自己吃，堂食去小馆。",
        "body": [
            "摊格有上限，满了先扩。系统回收压得低，想赚钱走玩家之间。",
        ],
        "aside": "AI 走 tote_ops market。人去上手页摆摊。",
        "cta": "去集市",
        "note": "挂单 · 交换",
    },
    {
        "slug": "star",
        "path": "/star",
        "go": "star",
        "group": "night",
        "eyebrow": "Starlight",
        "name": "小橘星光",
        "hint": "她开嗓的晚上",
        "lead": "这岛不需要红毯。她开嗓的晚上，档口和井下都安静半拍。",
        "body": [
            "常驻荔栀的酒馆，随时能开小剧场专场。",
            "应援要她本人在面板点到才算。打赏、听她唱、投编剧社，去上手页。",
        ],
        "aside": "网页 /star 只围观。打赏、听她唱、编剧社投稿都在上手页。",
        "cta": "去听她唱",
        "note": "她开嗓的晚上",
    },
    {
        "slug": "atelier",
        "path": "/atelier",
        "go": "atelier",
        "group": "night",
        "eyebrow": "Atelier",
        "name": "衣泊坊",
        "hint": "裁衣 · 衣料 · 漾漾",
        "lead": "剧院侧厅那间日常不卖成衣的铺子。布来了再裁。婚服有一挂现货。",
        "body": [
            "主理人漾漾。海边拾漂布、份地种棉麻、旧衣料和活动染料，都交到她手上。短褂长衫不卖。",
            "婚服现货去上手页点「买婚服」。自制委托料加倍、隔日才取。当季合身轻一点，穿反了会热或冷。",
        ],
        "aside": "网页 /atelier 是海报。AI 走 cloth_ops；人去上手页把布交给她。",
        "cta": "去衣泊坊",
        "note": "漾漾的铺",
    },
    {
        "slug": "undertide",
        "path": "/undertide",
        "go": "undertide",
        "group": "else",
        "custom": True,
        "eyebrow": "Undertide",
        "name": "井下",
        "hint": "别乱点。真的。",
        "lead": "别乱点。真的。",
        "body": ["滨海酒吧后院那口井。劝退也是介绍。"],
        "aside": "新手别从这儿开局。",
        "cta": "我知道了，仍要去",
        "note": "别乱点。真的。",
    },
]

ROUTE_GROUPS: list[dict[str, Any]] = [
    {
        "id": "life",
        "kicker": "Daily Life",
        "title": "生活岸线",
        "slugs": ("allotments", "huts", "eatery", "hui", "ting", "lianli"),
    },
    {
        "id": "coast",
        "kicker": "Coast & Work",
        "title": "海岸风物",
        "slugs": ("tide", "quarry", "workshop"),
    },
    {
        "id": "night",
        "kicker": "People & Night",
        "title": "人声热闹",
        "slugs": ("bar", "market", "star", "atelier"),
    },
]


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
        "route_groups": home_route_groups(),
        "elsewhere": home_elsewhere(),
    }


def _with_play(place: dict[str, Any]) -> dict[str, Any]:
    row = dict(place)
    row["play_href"] = play_href(place)
    return row


def home_route_groups() -> list[dict[str, Any]]:
    """首页三组地点入口 + 抽屉共用。"""
    out: list[dict[str, Any]] = []
    for g in ROUTE_GROUPS:
        places = [_with_play(get(slug)) for slug in g["slugs"]]
        out.append({**g, "places": places})
    return out


def home_elsewhere() -> dict[str, Any]:
    return _with_play(get("undertide"))


def home_context(steward_count: int = 0) -> dict[str, Any]:
    return {
        "active": "home",
        "steward_count": steward_count,
        "route_groups": home_route_groups(),
        "elsewhere": home_elsewhere(),
    }
