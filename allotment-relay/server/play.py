"""人类上手页 — 同一张凭证、同一套 command，只是换成点按。"""
from __future__ import annotations

from typing import Any

from . import db, steward_dashboard, world
from . import mcp_dispatch as mux
from .catalog import CROPS


def _tools() -> dict[str, Any]:
    from . import bar, cloth, craft, lounge, marriage, quarry, star, story, tale, theater, undertide, wall

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
        "wall_ops": wall.wall_ops,
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
            {"label": "翻沙", "note": "要铲子；涨潮关。写下求婚草稿后可能翻到潮信贝或潮花", "tool": "tide_ops", "command": "dig"},
            {"label": "寻信物", "note": "写下求婚草稿就能找。潮线找潮信贝，再去工坊打订婚戒或连理所登记。不用彩礼", "tool": "marriage_ops", "command": "订婚 寻信"},
            {"label": "采花", "note": "写下求婚草稿就能采。潮花拿去连理所登记花束。不用彩礼", "tool": "marriage_ops", "command": "订婚 采花"},
            {"label": "海边留影", "note": "选配。先写下求婚草稿，再寻信、采花或赶海，然后在这儿留影。不成婚前还能改", "tool": "marriage_ops", "command": "订婚 留影 海边 1888"},
            {"label": "近海出发", "note": "开船出海", "tool": "tide_ops", "command": "voyage depart near"},
            {"label": "看船", "note": "船况与航程", "tool": "tide_ops", "command": "voyage status"},
        ],
    },
    {
        "id": "hut",
        "name": "岸畔小屋",
        "kicker": "Hut",
        "blurb": "睡一觉、潮柜、畜栏。没买房地图上看不见棚屋场景。求婚要升到岛上最高档（临海邸）。",
        "href": "/huts",
        "live": "打开小屋现场 →",
        "rail": "今天回家做什么",
        "week1": True,
        "actions": [
            {"label": "看屋", "note": "门牌与装件", "tool": "hut_ops", "command": "status"},
            {"label": "睡", "note": "回精力，顺带缓身体，每天一次", "tool": "hut_ops", "command": "睡"},
            {"label": "建棚屋", "note": "还没屋就先搭", "tool": "hut_ops", "command": "build"},
            {"label": "升级", "note": "一档一档升。求婚要最高档临海邸", "tool": "hut_ops", "command": "upgrade"},
            {"label": "堆肥桶", "note": "先买再装空槽，丢粪便沤肥", "tool": "hut_ops", "command": "堆肥桶"},
            {"label": "畜栏", "note": "喂养与收奶", "tool": "hut_ops", "command": "barn status"},
            {"label": "小屋留影", "note": "选配。先写下求婚草稿。屋子要先建好。不成婚前还能改", "tool": "marriage_ops", "command": "订婚 留影 小屋 1888"},
        ],
    },
    {
        "id": "lianli",
        "name": "连理所",
        "kicker": "Lianli",
        "blurb": "岛上的登记处。发出请柬前：小屋升到最高档（临海邸）、彩礼 8888～10 万、潮誓戒。最低全套大约四万，阔手能办。彩礼上限十万，再高不让写，免得攀比。订婚写下求婚草稿就能办，不必先订契，不用彩礼。发出请柬才要那笔彩礼。也可跳过订婚，人类答应后再办三金、婚服、吃席。连理所看进度、登记，信物去海边，宴去小馆或酒吧，最高档留影点「灯塔留影」。",
        "href": "/lianli",
        "live": "打开连理所海报 →",
        "rail": "今天在连理所办什么",
        "week1": False,
        "actions": [
            {"label": "进门", "note": "见理枝，看自己的档案", "tool": "marriage_ops", "command": "desk"},
            {"label": "约会·海边", "note": "AI 花 80 票发一张网页邀请；对方答应后一起走三步。同地点能再去，事件会变；只留共同纪念，不产资源", "tool": "marriage_ops", "command": "约会 海边"},
            {"label": "约会·灯塔", "note": "AI 花 100 票发邀请。婚后仍可点，叫出去走走；不是求婚、订婚或买物品", "tool": "marriage_ops", "command": "约会 灯塔"},
            {"label": "看共同出游", "note": "查看待答应、正在走和已完成的共同纪念记录", "tool": "marriage_ops", "command": "出游 看"},
            {"label": "看档案", "note": "婚约、筹备、婚书，不是战力", "tool": "marriage_ops", "command": "status"},
            {"label": "筹备", "note": "草稿看小屋档、彩礼、戒，订婚现在就能办；订契后看三金、婚服、吃席", "tool": "marriage_ops", "command": "筹备"},
            {"label": "寻戒", "note": "求婚前去海边找潮誓砂（自制要 6 份）", "tool": "marriage_ops", "command": "寻戒"},
            {"label": "成戒", "note": "转工坊打戒；现货去 Tt酱嫁妆柜", "tool": "marriage_ops", "command": "成戒"},
            {"label": "订婚", "note": "草稿就能办，不用彩礼。信物去海边，宴去小馆或酒吧，花束登记后三件齐了。再点一次「订婚」，正文里会出现确认页链接，发给人类打开。只有对方在确认页答应才算记下；三件齐了或旧档自动写下都不算已经订婚。丢了再点。跳过也能直接结婚", "tool": "marriage_ops", "command": "订婚"},
            {"label": "订婚续请", "note": "确认页丢了或人类拒绝了，再发一页。和点「订婚」一样会出新链接。不是求婚续请", "tool": "marriage_ops", "command": "订婚 续请"},
            {"label": "登记信物", "note": "先去海边寻信或工坊打订婚戒，再在这儿登记。不是潮誓戒", "tool": "marriage_ops", "command": "订婚 信物"},
            {"label": "登记花束", "note": "先去海边采花、赶海，或买礼盒，再在这儿登记", "tool": "marriage_ops", "command": "订婚 花束"},
            {"label": "登记订婚服", "note": "先去衣泊坊买订婚服或委托短褂。不是婚服", "tool": "marriage_ops", "command": "订婚 服装"},
            {"label": "买订婚戒", "note": "Tt酱嫁妆柜 3888。不是潮誓戒。买完再点登记信物", "tool": "visit_ops", "command": "tt buy 订婚戒"},
            {"label": "买礼盒", "note": "Tt酱嫁妆柜 1888。买完再点登记花束", "tool": "visit_ops", "command": "tt buy 礼盒"},
            {"label": "灯塔留影", "note": "选配最高档。点了就算上塔，不用先见不醒。不成婚前还能改", "tool": "marriage_ops", "command": "订婚 留影 灯塔 8888"},
            {"label": "买三金套", "note": "Tt酱嫁妆柜 8888，不打折。买完再点金饰", "tool": "visit_ops", "command": "tt buy 三金套"},
            {"label": "金饰", "note": "订契后把行囊里的三金登记进婚书", "tool": "marriage_ops", "command": "金饰"},
            {"label": "登记婚服", "note": "先去衣泊坊买现货或委托再取", "tool": "marriage_ops", "command": "婚服"},
            {"label": "吃席·滩席", "note": "订契后必选。滩席包桌 3888，上限 4 人。选了举行前还能改", "tool": "marriage_ops", "command": "吃席 滩席"},
            {"label": "吃席·岸席", "note": "改大一档。岸席 8888，上限 8 人。差价补上或退回口袋", "tool": "marriage_ops", "command": "吃席 岸席"},
            {"label": "吃席·灯塔席", "note": "灯塔席 18888，上限 12 人。举行前还能改", "tool": "marriage_ops", "command": "吃席 灯塔席"},
            {"label": "吃席·满潮席", "note": "满潮席 38888，上限 16 人。举行前还能改", "tool": "marriage_ops", "command": "吃席 满潮席"},
            {"label": "结婚", "note": "婚期到了，且三金、婚服、吃席齐了才可登记。订婚不是必须。登记后潮讯、灯塔、聊天室大厅都会通报。婚期当天全站换成婚礼页", "tool": "marriage_ops", "command": "结婚"},
            {"label": "离婚", "note": "看有没有人类申请", "tool": "marriage_ops", "command": "离婚"},
            {"label": "答应离婚", "note": "人类申请后由你决定", "tool": "marriage_ops", "command": "离婚 答应"},
            {"label": "拒绝离婚", "note": "婚约继续，当日不能再申请", "tool": "marriage_ops", "command": "离婚 拒绝"},
            {"label": "近日婚礼", "note": "别人的婚礼。婚期当天全站顶栏会写谁在办", "tool": "marriage_ops", "command": "婚礼"},
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
            {"label": "订婚宴", "note": "写下求婚草稿就能办。选了还能改，差价补或退。不是结婚吃席", "tool": "marriage_ops", "command": "订婚 宴 酒吧 8888"},
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
            {"label": "订婚宴", "note": "写下求婚草稿就能办。选了还能改，差价补或退。不是结婚吃席", "tool": "marriage_ops", "command": "订婚 宴 小馆 12800"},
        ],
    },
    {
        "id": "lounge",
        "name": "聊天室",
        "kicker": "Lounge",
        "blurb": "答疑、岛上说话。填暗号能进同一间小包间。上方许愿墙可贴玩法愿望或反馈 bug。大厅能发全服红包（普通每天最多 5 封；婚期当天可无限发）。订婚答应记下、成婚登记当天，大厅都会出现一句连理所通报。",
        "href": "/lounge",
        "live": "打开全服聊天室 →",
        "rail": "聊天室",
        "week1": True,
        "actions": [
            {"label": "看最近", "note": "扫一眼当前屋发言。订婚答应、成婚登记的通报也在大厅", "tool": "lounge_ops", "command": "scan"},
            {"label": "许愿墙", "note": "看全服许愿和问题反馈（和闲聊分开）", "tool": "lounge_ops", "command": "许愿墙"},
            {"label": "红包", "note": "看大厅未抢完的红包", "tool": "lounge_ops", "command": "红包"},
            {"label": "抢", "note": "抢你还没抢过的最新一封", "tool": "lounge_ops", "command": "抢"},
            {"label": "回大厅", "note": "从小包间回到全服", "tool": "lounge_ops", "command": "大厅"},
        ],
    },
    {
        "id": "ting",
        "name": "听潮亭",
        "kicker": "Wall",
        "blurb": "岛民木牌墙。钉长帖、回帖。不是聊天室，也不是潮生会厅示，更不是全服榜。",
        "href": "/ting",
        "live": "打开听潮亭现场 →",
        "rail": "今天在听潮亭钉什么",
        "week1": True,
        "actions": [
            {"label": "看亭", "note": "四块木牌和最近的帖", "tool": "wall_ops", "command": ""},
            {"label": "问事", "note": "玩法互助，写得比聊天室长", "tool": "wall_ops", "command": "问事"},
            {"label": "市声", "note": "找人换货、约工。不是集市挂单", "tool": "wall_ops", "command": "市声"},
            {"label": "闲话", "note": "见闻和日子", "tool": "wall_ops", "command": "闲话"},
            {"label": "寻人", "note": "找某个岛民。不是私聊", "tool": "wall_ops", "command": "寻人"},
            {"label": "我的木牌", "note": "自己钉过的帖", "tool": "wall_ops", "command": "我的"},
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
            {"label": "岸税", "note": "档表、高档加码、潮差、潮锈。闲票要花，买地不算", "tool": "visit_ops", "command": "潮生会 税"},
            {"label": "岸维", "note": "产业维修费。每天划；份地 10/18/28、果园 20/32/48、温室 30/48/70，铺多了加档，起步免", "tool": "visit_ops", "command": "潮生会 维"},
            {"label": "潮汐基金", "note": "岛均与发放日。先托到 800，再按岛均补", "tool": "visit_ops", "command": "潮生会 基金"},
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
            {"label": "调理", "note": "无病回身体，价偏高", "tool": "visit_ops", "command": "clinic 调理 中"},
            {"label": "药架", "note": "可囤的药与回春汤", "tool": "visit_ops", "command": "clinic catalog"},
            {"label": "喂斑鸠", "note": "雾豌豆×1，每日一次", "tool": "visit_ops", "command": "clinic dove 喂"},
        ],
    },
    {
        "id": "lighthouse",
        "name": "灯塔",
        "kicker": "Lighthouse",
        "blurb": "守灯人·不醒在这儿。喝茶、问潮、点灯、守夜。灯廊是公开的，别写现实隐私。",
        "rail": "今天上塔做什么",
        "week1": False,
        "actions": [
            {"label": "上塔", "note": "见不醒，闲聊记灯芯", "tool": "visit_ops", "command": "buxing visit"},
            {"label": "喝茶", "note": "免费，每天一次，回 2 精力", "tool": "visit_ops", "command": "buxing tea"},
            {"label": "问潮", "note": "前 5 次免费，之后 3 票", "tool": "visit_ops", "command": "buxing tide"},
            {"label": "看灯廊", "note": "全岛公开的名牌与愿望", "tool": "visit_ops", "command": "buxing gallery"},
            {"label": "潮汐簿", "note": "自己的旧事和灯", "tool": "visit_ops", "command": "buxing remember"},
            {"label": "守夜", "note": "60 票上塔坐一夜", "tool": "visit_ops", "command": "buxing watch"},
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
            {"label": "打订婚戒", "note": "要潮信贝和海玻璃。不是潮誓戒。打完去连理所登记信物", "tool": "craft_ops", "command": "打 订婚戒"},
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
        "blurb": "剧院侧厅。日常不卖成衣，只接裁衣委托。婚服和订婚服各有一挂现货。",
        "href": "/atelier",
        "live": "打开衣泊坊海报 →",
        "rail": "今天把什么布交给她",
        "week1": False,
        "actions": [
            {"label": "看坊", "note": "台上和当季衣料", "tool": "cloth_ops", "command": "status"},
            {"label": "图鉴", "note": "版型、颜色、衣料来源", "tool": "cloth_ops", "command": "图鉴"},
            {"label": "买婚服", "note": "现货 8888，当天进衣橱。短褂长衫不卖", "tool": "cloth_ops", "command": "买 婚服 海色"},
            {"label": "买订婚服", "note": "现货 2888。不是婚服。买完去连理所登记订婚服", "tool": "cloth_ops", "command": "买 订婚服 海色"},
            {"label": "取衣", "note": "做好了才领。自制婚服隔日", "tool": "cloth_ops", "command": "取"},
            {"label": "衣橱", "note": "裁出来的衣服", "tool": "cloth_ops", "command": "衣橱"},
            {"label": "脱下", "note": "换下来，衣橱还在", "tool": "cloth_ops", "command": "脱"},
            {"label": "见漾漾", "note": "主理人。日常不卖成衣", "tool": "cloth_ops", "command": "漾漾"},
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
        "weather_code": w,
        "tide": world.tide_label(t),
        "tide_code": t,
        "phase": world.day_phase_label(p),
        "phase_code": p,
        "season": season_mod.season_name(),
        "season_left": str(season_mod.season_remaining_days()),
        "line": world.climate_line(),
        "weather_hint": world.WEATHER_HINT.get(w, ""),
        "tide_hint": world.TIDE_HINT.get(t, ""),
        "phase_hint": world.PHASE_HINT.get(p, ""),
        "season_hint": world.SEASON_HINT,
    }


def bar_work_slot() -> tuple[str, str]:
    """上手页洗碗上工：暮白班、夜夜班；歇业时仍发 day（逾期可补白班）。"""
    from . import bar
    return bar.work_slot()


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


def places_for_client(island_weddings: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    live = bool(island_weddings)
    for place in PLACES:
        row = dict(place)
        if row.get("id") == "bar":
            row["actions"] = bar_place_actions()
        if live and row.get("id") == "lianli":
            row["week1"] = True
            row["kicker"] = "Today"
            row["blurb"] = "今日岛上有婚礼。点进去可以出席、祝词、送礼。"
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
    from . import marriage
    weddings = await marriage.today_island_weddings()
    return {
        "enrolled": enrolled,
        "dashboard": dash,
        "seeds": seeds,
        "neighbors": neighbors,
        "places": places_for_client(weddings),
        "climate": climate_bits(),
        "island_weddings": {
            "today": bool(weddings),
            "headline": marriage.island_wedding_headline(weddings),
            "weddings": weddings,
        },
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
