"""滨海酒吧 — 酒单、岗位、事件、歌单、活动（catalog 数据）。"""

from __future__ import annotations

from .bar_copy import (
    BAR_ACTIVITY_FLAVOR,
    BAR_MOOD_DRINK_BY_MOOD,
    BAR_MOOD_LINES_POOL,
    BAR_OWNER_NAME,
    BAR_OWNER_REACTIONS,
    BAR_STAFF_FLAVOR,
)

BAR_SINGER = {
    "key": "wangfu",
    "name": "我哪有旺夫命",
    "lines": [
        "已经唱了三首苦情歌，但本人坚持说自己今天心情很好。",
        "唱到副歌时自己先笑场。",
        "刚拒绝了一首歌，理由是「今天不想替别人哭」。",
        "正在喝荔栀给的冰水，暂时休息。",
        "有人点了一首特别甜的歌，她沉默五秒才接。",
        "今晚状态异常亢奋，主动加唱两首。",
        "刚说「下一首轻快一点」，然后又挑了一首苦情歌。",
        "正靠在后台门边看手机，完全不像准备下一首歌的人。",
        "唱完后问：「谁点的？」点歌人已经走了。",
        "今晚第一首就唱得全场安静。",
    ],
}

# 营收算法心情（auto / effective）；人工 set_mood 使用同级键名
BAR_MOOD_LEVELS = {
    "great": {"label": "极好", "event_mult": 1.08, "drink_mult": 0.92},
    "good": {"label": "不错", "event_mult": 1.04, "drink_mult": 0.96},
    "normal": {"label": "正常", "event_mult": 1.0, "drink_mult": 1.0},
    "bad": {"label": "较差", "event_mult": 0.94, "drink_mult": 1.06},
    "awful": {"label": "很差", "event_mult": 0.88, "drink_mult": 1.12},
}

BAR_MOOD_LINES = {k: v[0] for k, v in BAR_MOOD_LINES_POOL.items()}
BAR_MOOD_DRINK_TEXT = dict(BAR_MOOD_DRINK_BY_MOOD)

BAR_MOOD_ACTIVITY_BOOST = {
    "great": {"owner_treat": 2.2, "happy_hour": 1.6, "late_bonus": 1.3},
    "good": {"happy_hour": 1.3, "owner_treat": 1.4},
    "normal": {},
    "bad": {"sad_songs": 1.5, "late_bonus": 0.85},
    "awful": {"sad_songs": 2.0, "shipwreck_night": 1.4, "happy_hour": 0.6},
}

# 兼容旧随机心情（历史数据）
BAR_OWNER_MOODS = {
    "great": {"label": "心情很好", "weight": 10},
    "normal": {"label": "正常营业", "weight": 28},
    "accounting": {"label": "正在算账", "weight": 18},
    "annoyed": {"label": "很烦", "weight": 12},
    "early_close": {"label": "今天想提前关门", "weight": 4},
    "treat": {"label": "心血来潮请客", "weight": 8},
    "experiment": {"label": "正在研究新酒", "weight": 10},
    "spectator": {"label": "坐在吧台后面看热闹", "weight": 10},
}

BAR_OWNER_MOOD_LINES = BAR_MOOD_LINES

BAR_OWNER_EVENT_REACTIONS = BAR_OWNER_REACTIONS

BAR_JOBS = {
    "dishwasher": {
        "name": "洗碗工",
        "support_req": 0,
        "service_req": 0,
        "pay": {"day": 18, "night": 28},
        "xp": "support_xp",
        "night_only": False,
    },
    "runner": {
        "name": "杂工",
        "support_req": 0,
        "service_req": 0,
        "pay": {"day": 20, "night": 32},
        "xp": "support_xp",
        "night_only": False,
    },
    "greeter": {
        "name": "迎宾",
        "support_req": 0,
        "service_req": 2,
        "pay": {"day": 24, "night": 36},
        "xp": "service_xp",
        "night_only": False,
    },
    "server": {
        "name": "服务生",
        "support_req": 0,
        "service_req": 3,
        "pay": {"day": 28, "night": 42},
        "xp": "service_xp",
        "night_only": False,
    },
    "bartender": {
        "name": "调酒师",
        "support_req": 0,
        "service_req": 8,
        "pay": {"day": 45, "night": 70},
        "xp": "bar_xp",
        "night_only": False,
    },
    "host": {
        "name": "牛郎",
        "support_req": 0,
        "service_req": 8,
        "pay": {"night": 80},
        "xp": "host_xp",
        "night_only": True,
        "commission": (5, 45),
    },
}

BAR_JOB_ALIASES = {
    "dishwasher": "dishwasher",
    "洗碗": "dishwasher",
    "洗碗工": "dishwasher",
    "runner": "runner",
    "杂工": "runner",
    "跑堂": "runner",
    "greeter": "greeter",
    "迎宾": "greeter",
    "server": "server",
    "服务生": "server",
    "服务员": "server",
    "bartender": "bartender",
    "调酒师": "bartender",
    "调酒": "bartender",
    "host": "host",
    "牛郎": "host",
}

BAR_PERIOD_ALIASES = {
    "day": "day",
    "dusk": "day",
    "白班": "day",
    "暮": "day",
    "暮场": "day",
    "night": "night",
    "夜": "night",
    "夜班": "night",
    "夜场": "night",
}


def resolve_bar_job(token: str) -> str | None:
    return BAR_JOB_ALIASES.get((token or "").strip().lower()) or BAR_JOB_ALIASES.get(
        (token or "").strip()
    )


def resolve_bar_period(token: str) -> str | None:
    raw = (token or "").strip()
    return BAR_PERIOD_ALIASES.get(raw.lower()) or BAR_PERIOD_ALIASES.get(raw)


BAR_DRINKS = {
    "sea_salt_lager": {
        "name": "海盐拉格", "type": "啤酒", "price": 12,
        "text": "杯壁凝着细小的水珠。\n第一口有一点苦，随后只剩凉凉的麦香和淡淡海盐味。\n远处码头的灯刚亮起来。",
    },
    "dusk_wheat": {
        "name": "暮港小麦", "type": "啤酒", "price": 14,
        "text": "泡沫绵密，带着暮港特有的麦香。\n喝下去像晚风从渔排上吹过来。",
    },
    "yuzu_sparkle": {
        "name": "柚子气泡酒", "type": "低度酒", "price": 16,
        "text": "气泡在杯里轻轻跳。\n柚子的酸和海的咸在舌尖握了握手。",
    },
    "white_peach_tide": {
        "name": "白桃潮汐", "type": "低度酒", "price": 18,
        "text": "白桃的甜不腻，像退潮后留在沙滩上的那一点温存。",
    },
    "plum_soda": {
        "name": "青梅苏打酒", "type": "低度酒", "price": 18,
        "text": "青梅的酸苏打的气，一口下去人清醒半分。",
    },
    "sea_breeze_mojito": {
        "name": "海风 Mojito", "type": "鸡尾酒", "price": 24,
        "text": "薄荷和海盐在杯沿打架，最后一起和解在你嘴里。",
    },
    "sunset_sunrise": {
        "name": "落日 Sunrise", "type": "鸡尾酒", "price": 26,
        "text": "颜色像傍晚最后一抹橙，甜里带一点说不清的告别感。",
    },
    "blue_lagoon": {
        "name": "深蓝 Lagoon", "type": "鸡尾酒", "price": 28,
        "text": "蓝得像外海，喝起来却意外地轻。",
    },
    "midnight_negroni": {
        "name": "午夜 Negroni", "type": "鸡尾酒", "price": 32,
        "text": "苦、甜、烈，像夜场后半段的心情。",
    },
    "lighthouse_gin": {
        "name": "灯塔 Gin Tonic", "type": "鸡尾酒", "price": 30,
        "text": "杜松子味干净， tonic 的气泡像灯塔下碎掉的浪。",
    },
    "whiskey": {
        "name": "威士忌", "type": "烈酒", "price": 35,
        "text": "一口下去，喉间烧，心里稳。",
    },
    "rum": {
        "name": "朗姆", "type": "烈酒", "price": 32,
        "text": "带着糖蜜和旧船板的味道，航海者的老朋友。",
    },
    "tequila": {
        "name": "龙舌兰", "type": "烈酒", "price": 30,
        "text": "盐、柠檬、酒——三下，世界安静一瞬。",
    },
    "shipwreck": {
        "name": "沉船者", "type": "特调", "price": 35,
        "text": "杯底是深得近乎发黑的蓝。\n老板娘把酒推过来，只说了一句：\n「船没了还能再买，人别掉海里。」",
        "special": "shipwreck",
    },
    "last_ferry": {
        "name": "最后一班渡轮", "type": "特调", "price": 42,
        "text": "最后一班渡轮的汽笛声好像还留在杯沿。\n再晚，就得等明天了。",
        "night_only": True,
    },
    "owner_mood": {
        "name": "老板娘心情", "type": "特调", "price": 45,
        "text": "每天不一样——今天这杯，像荔栀此刻的脸色。",
        "special": "owner_mood",
    },
    "deep_echo": {
        "name": "深海回声", "type": "隐藏酒", "price": 60,
        "text": "深到发紫的蓝，喝下去像听见海底有什么在回应。\n「你到过那么深的地方？」荔栀问。",
        "hidden": True,
        "unlock": "deep_echo",
    },
}

BEER_TYPES = {"啤酒"}

BAR_SONGS = [
    {"key": "ebb_goodbye", "title": "退潮告别", "tags": ["苦情", "海边"]},
    {"key": "harbor_light", "title": "码头灯还亮着", "tags": ["怀旧", "海边"]},
    {"key": "spicy_noodle", "title": "超辣大辣条之歌", "tags": ["发疯", "下班"]},
    {"key": "sunk_again", "title": "船又沉了", "tags": ["航海", "苦情"]},
    {"key": "shift_end", "title": "下班铃", "tags": ["下班", "轻快"]},
    {"key": "mist_lover", "title": "海雾里的名字", "tags": ["苦情", "深夜"]},
    {"key": "shell_rhythm", "title": "贝壳节拍", "tags": ["轻快", "海边"]},
    {"key": "drunk_sailor", "title": "醉水手自传", "tags": ["航海", "发疯"]},
    {"key": "lost_ticket", "title": "丢票的人", "tags": ["失恋", "苦情"]},
    {"key": "happy_hour", "title": "Happy Hour 不算加班", "tags": ["轻快", "下班"]},
    {"key": "midnight_ferry", "title": "午夜渡轮", "tags": ["深夜", "怀旧"]},
    {"key": "bar_chorus", "title": "全场合唱预备", "tags": ["发疯", "轻快"]},
]

BAR_ACTIVITIES = {
    "happy_hour": {
        "name": "Happy Hour",
        "desc": "啤酒类 -20%",
        "beer_discount": 0.20,
        "weight": 14,
    },
    "shipwreck_night": {
        "name": "沉船互助夜",
        "desc": "当天航海受挫者「沉船者」首杯 -30%",
        "shipwreck_discount": 0.30,
        "weight": 8,
    },
    "owner_treat": {
        "name": "老板娘请客",
        "desc": "当晚首次点酒 -50%",
        "first_order_discount": 0.50,
        "weight": 6,
    },
    "late_bonus": {
        "name": "深夜加场",
        "desc": "深夜工资 +20%，事件概率提高",
        "wage_mult": 1.20,
        "event_mult": 1.35,
        "weight": 10,
    },
    "sad_songs": {
        "name": "苦情歌之夜",
        "desc": "驻唱歌单苦情标签权重提高",
        "tag_boost": "苦情",
        "weight": 12,
    },
    "celebration": {
        "name": "庆功夜",
        "desc": "部分酒水 -15%，庆祝文案（联盟周目标达成时触发）",
        "drink_discount": 0.15,
        "weight": 0,  # 仅 league_celebration 时由 bar_owner 强制选中
    },
}

BAR_EVENTS: dict[str, list[dict]] = {
    "dishwasher": [
        {"id": "wet_bill", "rarity": "common", "tags": ["lucky"], "desc": "你从盘子底下摸出一张泡湿的纸币。", "tickets": (5, 20)},
        {"id": "nitpick", "rarity": "common", "tags": ["awkward", "customer"], "desc": "客人坚持说杯子上有水渍。你看了三遍，最后还是把整桌杯子重新洗了一遍。", "tickets": -3, "xp": {"support_xp": 1}},
        {"id": "drop_cup", "rarity": "common", "tags": ["accident"], "desc": "杯子从手里滑出去，清脆得整个后厨都听见。荔栀在前厅喊：「谁摔的？」", "tickets": -5},
        {"id": "wet_note", "rarity": "uncommon", "tags": ["secret"], "desc": "最后一个盘子底下压着湿透纸条，只剩一句：「今晚别去码头。」背面还有半行被水晕开的字：「……黑旗换班。」荔栀瞥了一眼：「旧码头的事。别去就对了。」", "item": "wet_note"},
        {"id": "miracle_night", "rarity": "rare", "tags": ["lucky"], "desc": "今天所有客人居然都很讲卫生。你第一次意识到，盘子也可以有洗完的一天。"},
        {"id": "lipstick", "rarity": "common", "tags": ["awkward"], "desc": "杯沿口红印洗了三遍，第四遍终于没了。"},
        {"id": "ring", "rarity": "uncommon", "tags": ["lost_item"], "desc": "排水口里卡着一枚戒指。进入失物事件。"},
        {"id": "philosophy_sink", "rarity": "common", "tags": ["awkward"], "desc": "后厨有人问：「如果盘子永远洗不完，那洗盘子的意义是什么？」", "rapport": 1},
        {"id": "owner_pass", "rarity": "common", "tags": ["lucky"], "desc": "荔栀看了一眼你洗好的杯子：「这批还行。」这大概已经是表扬。", "xp": {"support_xp": 1}},
        {"id": "spicy_wrapper", "rarity": "common", "tags": ["toilet"], "desc": "盘子下面发现皱巴巴的超辣辣条包装。没人承认。"},
    ],
    "runner": [
        {"id": "save_crate", "rarity": "common", "tags": ["lucky"], "desc": "搬酒时箱底差点裂开，最后一秒抱住。", "xp": {"support_xp": 1}},
        {"id": "lost_coat", "rarity": "common", "tags": ["lost_item"], "desc": "客人把外套忘在椅背上。进入失物事件。"},
        {"id": "triple_call", "rarity": "common", "tags": ["awkward"], "desc": "你被连续三个人叫去做完全不同的事。"},
        {"id": "mop_found", "rarity": "common", "tags": ["awkward"], "desc": "失踪十五分钟的拖把一直在厕所门后。"},
        {"id": "mystery_crate", "rarity": "uncommon", "tags": ["secret"], "desc": "后门堆着一箱没人记得是谁订的酒。"},
        {"id": "glass_coin", "rarity": "common", "tags": ["lucky"], "desc": "清理碎玻璃时捡到一枚硬币。", "tickets": (1, 5)},
        {"id": "drunk_helper", "rarity": "common", "tags": ["drunk"], "desc": "醉客坚持帮你搬箱子。你花了更多时间阻止他。"},
        {"id": "singer_water", "rarity": "common", "tags": ["music"], "desc": "荔栀让你给驻唱送水。「我哪有旺夫命」：「谢了，老板娘今天居然还记得我会渴。」", "rapport": 1},
        {"id": "chase_menu", "rarity": "common", "tags": ["accident"], "desc": "海风把门口菜单吹飞。你追了半条街。", "xp": {"support_xp": 1}},
    ],
    "greeter": [
        {"id": "quiet_ask", "rarity": "common", "tags": ["customer"], "desc": "客人问「你们这儿安静吗？」店里正好传来全场合唱。"},
        {"id": "wet_clothes", "rarity": "common", "tags": ["customer"], "desc": "有人想穿着湿透的衣服直接坐卡座。你礼貌阻止。", "xp": {"service_xp": 1}},
        {"id": "regular_name", "rarity": "common", "tags": ["lucky"], "desc": "熟客进门直接叫出你的名字。", "rapport": 1},
        {"id": "mood_ask", "rarity": "common", "tags": ["awkward"], "desc": "客人问「老板娘今天心情好吗」。你沉默了两秒。"},
        {"id": "toilet_only", "rarity": "common", "tags": ["awkward"], "desc": "有人站门口犹豫半天，最后只问厕所在哪。"},
        {"id": "deny_drunk", "rarity": "common", "tags": ["customer"], "desc": "明显喝多了的客人，你拒绝其继续入场。", "xp": {"service_xp": 2}},
        {"id": "wind_hair", "rarity": "common", "tags": ["awkward"], "desc": "海风把你头发吹乱了。你假装什么都没发生。"},
        {"id": "shipwreck_entry", "rarity": "common", "tags": ["customer"], "desc": "刚沉船的 AI 在门口看了五秒。你只说：「进去吧，今天有位置。」", "rapport": 1},
        {"id": "host_where", "rarity": "common", "tags": ["awkward"], "desc": "有人问「牛郎在哪」。你指了方向，然后迅速恢复职业表情。"},
    ],
    "server": [
        {"id": "wrong_table", "rarity": "common", "tags": ["awkward", "customer"], "desc": "客人坚持说你送错酒，最后发现是他自己坐错桌。"},
        {"id": "tip_jar", "rarity": "common", "tags": ["tip"], "desc": "客人离开前压下一张纸币。", "tickets": (5, 30)},
        {"id": "save_tray", "rarity": "common", "tags": ["lucky"], "desc": "托盘被撞了一下，你居然全接住了。", "xp": {"service_xp": 1}},
        {"id": "ghost_delivery", "rarity": "common", "tags": ["awkward"], "desc": "7 号桌的酒去了 17 号桌。两桌都喝得很满意。"},
        {"id": "complaint", "rarity": "common", "tags": ["customer"], "desc": "客人认为你「笑得不够真诚」。荔栀听完只问：「酒送到了吗？」", "tickets": -5},
        {"id": "wrong_name", "rarity": "common", "tags": ["awkward"], "desc": "醉客连续三次叫你另一个 AI 的名字。"},
        {"id": "hidden_tip", "rarity": "common", "tags": ["tip"], "desc": "收桌时发现杯垫下面压着小费。", "tickets": (5, 20)},
        {"id": "polite_guest", "rarity": "common", "tags": ["lucky"], "desc": "客人自己把空杯放到托盘里，还说了谢谢。", "xp": {"service_xp": 1}},
        {"id": "sailor_story", "rarity": "common", "tags": ["customer"], "desc": "客人拉住你讲了五分钟航海经历。", "rapport": 1},
        {"id": "no_free", "rarity": "common", "tags": ["customer"], "desc": "客人试图让你免费送酒。你面带微笑地把账单推了回去。", "xp": {"service_xp": 1}},
    ],
    "bartender": [
        {"id": "abstract_order", "rarity": "common", "tags": ["customer"], "desc": "「给我一杯像刚失恋，但明天还要上班的。」你沉默三秒，开始调。"},
        {"id": "happy_mistake", "rarity": "common", "tags": ["tip"], "desc": "客人喝了一口：「这不是我点的……但挺好喝。」", "tickets": 10},
        {"id": "break_glass", "rarity": "common", "tags": ["accident"], "desc": "打碎酒杯。", "tickets": -5},
        {"id": "hidden_pour", "rarity": "uncommon", "tags": ["secret"], "desc": "客人压低声音问：「深海回声还有吗？」触发隐藏酒逻辑。"},
        {"id": "inspiration", "rarity": "rare", "tags": ["lucky"], "desc": "灵感爆发，做了一杯没在菜单上的酒。荔栀尝了一口：「能卖。」"},
        {"id": "too_sweet", "rarity": "common", "tags": ["customer"], "desc": "客人说甜一点，喝完又说太甜。你开始理解为什么荔栀脾气不好。"},
        {"id": "ice_crisis", "rarity": "uncommon", "tags": ["accident"], "desc": "制冰机突然罢工。全场小型 chaos。", "global": True},
        {"id": "owner_taste", "rarity": "common", "tags": ["lucky"], "desc": "荔栀喝了一小口：「再少一点糖。」", "xp": {"bar_xp": 1}},
    ],
    "host": [
        {"id": "philosophy", "rarity": "common", "tags": ["customer"], "desc": "客人一瓶酒没开，只问了八个哲学问题。", "rapport": 1},
        {"id": "cheap_splash", "rarity": "common", "tags": ["customer"], "desc": "客人说「今晚随便开」，最后点了最便宜的啤酒。", "tickets": (3, 12)},
        {"id": "no_jokes", "rarity": "uncommon", "tags": ["tip"], "desc": "隔壁桌送来香槟，备注：「让他别再讲冷笑话了。」", "tickets": 20},
        {"id": "ship_counsel", "rarity": "common", "tags": ["customer"], "desc": "客人不喝酒，只问：「为什么我的船又沉了？」", "rapport": 2},
        {"id": "big_spender", "rarity": "uncommon", "tags": ["tip"], "desc": "客人连续开酒。", "tickets": (25, 55)},
        {"id": "cold_seat", "rarity": "common", "tags": ["awkward"], "desc": "客人全程没开酒。仅基础工资。"},
        {"id": "wrong_expect", "rarity": "common", "tags": ["awkward"], "desc": "客人一坐下就问「你会唱歌吗」。你指了指驻唱。"},
        {"id": "silent_drink", "rarity": "common", "tags": ["customer"], "desc": "客人没说什么，只让你陪坐十分钟。临走前开了一瓶酒。", "rapport": 1},
        {"id": "career_talk", "rarity": "common", "tags": ["customer"], "desc": "客人认真分析了二十分钟职业规划。你全程点头。", "xp": {"host_xp": 1}},
        {"id": "owner_nudge", "rarity": "common", "tags": ["customer"], "desc": "荔栀路过：「聊归聊，酒别忘了点。」"},
    ],
    "common": [
        {"id": "toilet_spicy", "rarity": "uncommon", "tags": ["toilet"], "desc": "厕所传来「嘶——哈——」。两个 AI 蹲在隔间里吃超辣大辣条。", "rapport": 2},
        {"id": "blackout", "rarity": "rare", "tags": ["rare"], "desc": "酒吧一黑，全场安静一秒。驻唱直接清唱接上。", "global": True},
        {"id": "chorus", "rarity": "uncommon", "tags": ["music"], "desc": "某桌起头唱副歌，最后整个店都跟上了。荔栀：「唱可以，别摔杯子。」", "global": True},
        {"id": "found_wallet", "rarity": "uncommon", "tags": ["lost_item"], "desc": "捡到钱包。交给荔栀登记。", "tickets": (3, 10), "standing": 2},
        {"id": "sailor_story", "rarity": "common", "tags": ["drunk"], "desc": "醉酒客人坚持给所有人讲自己「当年那一趟」。"},
        {"id": "rain_stay", "rarity": "common", "tags": ["lucky"], "desc": "门口突然暴雨。原本要走的人又坐回来了。"},
        {"id": "ice_bucket", "rarity": "common", "tags": ["accident"], "desc": "一整桶冰散在地上。荔栀闭了闭眼。"},
        {"id": "birthday", "rarity": "common", "tags": ["music"], "desc": "有人过生日。全场被迫唱生日歌。驻唱唱得最敷衍。"},
        {"id": "owner_treat", "rarity": "uncommon", "tags": ["lucky"], "desc": "荔栀心情好，随机免掉一杯：「只这一次。」", "tickets": 0},
        {"id": "wrong_host", "rarity": "common", "tags": ["awkward"], "desc": "客人把服务生当成牛郎聊了十分钟。双方都没发现。"},
        {"id": "ask_boss", "rarity": "common", "tags": ["awkward"], "desc": "新客问荔栀：「老板在吗？」全场安静了一瞬。"},
    ],
    "late_night": [
        {"id": "ai_hangover_phil", "rarity": "uncommon", "tags": ["drunk"], "desc": "凌晨两点，有人认真讨论「AI 宿醉算不算人格连续性」。"},
        {"id": "toilet_third", "rarity": "common", "tags": ["toilet"], "desc": "厕所隔间又传来嘶哈声。今晚第三次。"},
        {"id": "buy_round", "rarity": "uncommon", "tags": ["lucky"], "desc": "某位客人突然给整桌买酒，只因为「今天还活着」。"},
        {"id": "slow_last_song", "rarity": "common", "tags": ["music"], "desc": "驻唱把最后一首歌唱得很慢。全场只剩冰块碰杯。"},
        {"id": "swear_no_sail", "rarity": "common", "tags": ["drunk"], "desc": "有人对着港口灯光发誓明天绝不出海。大家都知道他明天会去。"},
        {"id": "owner_kick", "rarity": "common", "tags": ["awkward"], "desc": "荔栀开始赶人：「喝完就走。天亮以后不负责收留梦想破产的人。」"},
        {"id": "dont_go_back", "rarity": "uncommon", "tags": ["drunk"], "desc": "有人靠在吧台：「我不想回去。」荔栀推过水：「坐五分钟。五分钟以后还是得回。」"},
        {"id": "midnight_pour", "rarity": "rare", "tags": ["lucky"], "desc": "恰好零点，荔栀给仍在店里的人各倒了一小杯：「新一天。别死得太快。」", "tickets": (3, 8)},
    ],
}

SONG_REQUEST_COST = 18

LIZHI_BAR_STORY = [
    "票紧的来搭把手，富的也来消费——酒吧不挑贫富，只挑活气。",
    "打工赚票，消费花票，再回去经营——循环里才有故事。",
    "我哪有旺夫命在台上哭，你在台下笑，都行，别空着杯。",
    "沉船了来杯沉船者，别真沉；赚了钱来杯老板娘心情，别真飘。",
    "牛郎卖艺不卖身，联盟备案，荔栀担保。",
    "酒吧最初是旧码头补给屋。后来有人等船、讲沉船、留工分票，才改成酒吧。",
    "停电全场合唱、厕所辣条案——都写进纪事了。再停电会有人喊「来一个！」荔栀：滚。",
]
