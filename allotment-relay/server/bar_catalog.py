"""滨海酒吧 — 酒单、岗位、事件、歌单、活动（catalog 数据）。"""

from __future__ import annotations

BAR_SINGER = {
    "key": "wangfu",
    "name": "我哪有旺夫命",
    "lines": [
        "今天看起来心情很好，但已经连续唱了四首分手歌。",
        "唱到副歌的时候自己先笑场了。",
        "刚刚拒绝了一首歌，理由是「今天不想替别人哭」。",
        "正在喝老板娘给的冰水，暂时休息。",
        "有客人点了一首特别甜的歌，她沉默了五秒才接。",
        "今晚状态异常亢奋，已经主动加唱两首。",
        "唱完以后说「下一首轻快一点」，然后又选了一首苦情歌。",
    ],
}

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

BAR_OWNER_MOOD_LINES = {
    "great": "荔栀哼着歌擦杯子，今晚特调可能偏甜。",
    "normal": "荔栀在吧台后面照常用工，眼神像在看 KPI。",
    "accounting": "荔栀正在吧台后面算账，看起来心情一般。",
    "annoyed": "荔栀皱着眉记帐，别在这时候讲冷笑话。",
    "early_close": "荔栀看了眼钟：「再吵我就提前打烊。」",
    "treat": "荔栀突然说：「今天第一杯算我的——别点太贵的。」",
    "experiment": "荔栀在试新配方，吧台后面飘着奇怪但好闻的味道。",
    "spectator": "荔栀抱着胳膊看热闹，像老板又像观众。",
}

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
        "desc": "部分酒水 -15%，庆祝文案",
        "drink_discount": 0.15,
        "weight": 0,
    },
}

BAR_EVENTS: dict[str, list[dict]] = {
    "dishwasher": [
        {"id": "wet_bill", "rarity": "common", "tags": ["lucky"], "desc": "洗盘子时发现一张泡湿的纸币。", "tickets": (5, 20)},
        {"id": "nitpick", "rarity": "common", "tags": ["awkward", "customer"], "desc": "客人投诉杯子上有水渍，坚持要求重新清洗。", "tickets": -3, "xp": {"support_xp": 1}},
        {"id": "drop_cup", "rarity": "common", "tags": ["accident"], "desc": "不小心摔碎一只杯子。", "tickets": -5},
        {"id": "wet_note", "rarity": "uncommon", "tags": ["secret"], "desc": "清洗最后一个盘子时，发现盘底压着一张湿透的纸条。", "item": "wet_note"},
        {"id": "miracle_night", "rarity": "rare", "tags": ["lucky"], "desc": "今天所有客人居然都很讲卫生——提前下班，工资不变。"},
    ],
    "server": [
        {"id": "wrong_table", "rarity": "common", "tags": ["awkward", "customer"], "desc": "客人坚持说你送错了酒，查了半天发现是他自己坐错桌。"},
        {"id": "tip_jar", "rarity": "common", "tags": ["tip"], "desc": "某桌客人离开前偷偷留下小费。", "tickets": (5, 30)},
        {"id": "save_tray", "rarity": "common", "tags": ["lucky"], "desc": "托盘差点被撞翻，但成功把酒全部接住。", "xp": {"service_xp": 1}},
        {"id": "ghost_delivery", "rarity": "common", "tags": ["awkward"], "desc": "把 7 号桌的酒送给了 17 号桌，两桌客人居然都没发现。"},
        {"id": "complaint", "rarity": "common", "tags": ["customer"], "desc": "客人投诉服务态度。", "tickets": -5},
    ],
    "bartender": [
        {"id": "abstract_order", "rarity": "common", "tags": ["customer"], "desc": "客人说：「给我来一杯像刚失恋，但是明天还要上班的。」你自由发挥了一杯。"},
        {"id": "happy_mistake", "rarity": "common", "tags": ["tip"], "desc": "调错酒，客人却意外喜欢。", "tickets": (8, 15)},
        {"id": "break_glass", "rarity": "common", "tags": ["accident"], "desc": "打碎酒杯。", "tickets": -5},
        {"id": "hidden_pour", "rarity": "uncommon", "tags": ["secret"], "desc": "客人点了一杯特殊隐藏酒款——你调出深海回声的一小口试饮版。"},
        {"id": "inspiration", "rarity": "rare", "tags": ["lucky"], "desc": "灵感爆发，自由发挥出一杯临时限定酒——荔栀记下了配方。"},
    ],
    "host": [
        {"id": "philosophy", "rarity": "common", "tags": ["customer"], "desc": "陪坐二十分钟，客人一瓶酒都没开，只问了八个哲学问题。", "rapport": 1},
        {"id": "cheap_splash", "rarity": "common", "tags": ["customer"], "desc": "客人豪爽表示「今晚随便开」，最后只点了一瓶最便宜的啤酒。", "tickets": (3, 12)},
        {"id": "no_jokes", "rarity": "uncommon", "tags": ["tip"], "desc": "隔壁桌送来一瓶香槟，备注：「让他别再讲冷笑话了。」", "tickets": 20},
        {"id": "ship_counsel", "rarity": "common", "tags": ["customer"], "desc": "客人今天不喝酒，只要求分析：「为什么我的船又沉了？」", "rapport": 2},
        {"id": "big_spender", "rarity": "uncommon", "tags": ["tip"], "desc": "客人连续开酒。", "tickets": (25, 55)},
        {"id": "cold_seat", "rarity": "common", "tags": ["awkward"], "desc": "客人全程未开酒，仅获得基础工资。"},
    ],
    "common": [
        {"id": "bump_guest", "rarity": "common", "tags": ["accident"], "desc": "撞到客人——道歉后对方摆摆手说没事。", "tickets": (0, 8)},
        {"id": "toilet_spicy", "rarity": "uncommon", "tags": ["toilet"], "desc": "厕所隔间里两个 AI 蹲着吃超辣大辣条：「嘶——哈——」", "rapport": 2},
        {"id": "found_wallet", "rarity": "uncommon", "tags": ["lost_item"], "desc": "发现客人遗失的钱包，交给荔栀登记。", "tickets": (3, 10), "standing": 2},
        {"id": "sailor_story", "rarity": "common", "tags": ["drunk"], "desc": "醉酒客人坚持给全体员工讲自己的航海史。"},
        {"id": "owner_treat", "rarity": "uncommon", "tags": ["lucky"], "desc": "荔栀突然请客：「这杯算我的。」", "tickets": 0},
        {"id": "blackout", "rarity": "rare", "tags": ["rare"], "desc": "酒吧突然停电——蜡烛亮起，全场反而更热闹。", "global": True},
        {"id": "chorus", "rarity": "uncommon", "tags": ["music"], "desc": "某桌突然开始唱歌，最后整个酒吧一起唱。", "global": True},
    ],
    "late_night": [
        {"id": "weird_regular", "rarity": "uncommon", "tags": ["drunk", "rare"], "desc": "熟客凌晨三点进来，只点了一杯温水。", "tickets": (10, 25)},
        {"id": "ghost_shift", "rarity": "rare", "tags": ["secret", "rare"], "desc": "你好像多上了一个不存在的班次——工资却到账了。", "tickets": (15, 35)},
        {"id": "singer_breakdown", "rarity": "uncommon", "tags": ["music"], "desc": "驻唱唱到一半停住，全场安静五秒后又爆发出掌声。"},
    ],
}

SONG_REQUEST_COST = 18

LIZHI_BAR_STORY = [
    "票紧的来搭把手，富的也来消费——酒吧不挑贫富，只挑活气。",
    "打工赚票，消费花票，再回去经营——循环里才有故事。",
    "我哪有旺夫命在台上哭，你在台下笑，都行，别空着杯。",
    "沉船了来杯沉船者，别真沉；赚了钱来杯老板娘心情，别真飘。",
    "牛郎卖艺不卖身，联盟备案，荔栀担保。",
]
