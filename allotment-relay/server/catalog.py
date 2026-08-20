# 份地作物 — 偏北欧/沿海/湿地，与常见农场游戏区分
# grow=基准分钟；spread 控制播种时随机生长窗口
CROPS = {
    "kale": {"name": "羽衣甘蓝", "emoji": "🥬", "seed_price": 7, "sell": 16, "grow": 280, "spread": 0.32, "tags": ["leaf"]},
    "beet": {"name": "甜菜", "emoji": "🫘", "seed_price": 9, "sell": 21, "grow": 340, "spread": 0.26, "tags": ["root"]},
    "rye": {"name": "黑麦", "emoji": "🌾", "seed_price": 8, "sell": 19, "grow": 400, "spread": 0.28, "tags": ["grain"]},
    "bramble": {"name": "荆棘莓", "emoji": "🫐", "seed_price": 14, "sell": 32, "grow": 360, "spread": 0.38, "tags": ["berry"]},
    "kelp": {"name": "浅海藻", "emoji": "🌿", "seed_price": 11, "sell": 24, "grow": 300, "spread": 0.34, "tags": ["sea"]},
    "fogpea": {"name": "雾豌豆", "emoji": "🫛", "seed_price": 10, "sell": 23, "grow": 320, "spread": 0.30, "tags": ["legume"]},
    # ── 热带 / 调味 / 浆果 ──
    "blueberry": {"name": "蓝莓", "emoji": "🫐", "seed_price": 16, "sell": 36, "grow": 340, "spread": 0.30, "tags": ["berry", "tropic"]},
    "banana": {"name": "香蕉", "emoji": "🍌", "seed_price": 18, "sell": 28, "grow": 420, "spread": 0.28, "tags": ["fruit", "tropic"], "tree": True},
    "coconut": {"name": "椰子", "emoji": "🥥", "seed_price": 22, "sell": 24, "grow": 500, "spread": 0.25, "tags": ["fruit", "tropic"], "tree": True, "shake": True},
    "durian": {"name": "榴莲", "emoji": "🍈", "seed_price": 48, "sell": 95, "grow": 720, "spread": 0.40, "tags": ["fruit", "tropic"], "tree": True, "ultra_rare": True},
    "garlic": {"name": "大蒜", "emoji": "🧄", "seed_price": 9, "sell": 18, "grow": 260, "spread": 0.22, "tags": ["seasoning"]},
    "chili": {"name": "辣椒", "emoji": "🌶️", "seed_price": 11, "sell": 22, "grow": 280, "spread": 0.26, "tags": ["seasoning"]},
    "ginger": {"name": "姜", "emoji": "🫚", "seed_price": 12, "sell": 24, "grow": 300, "spread": 0.24, "tags": ["seasoning", "tropic"]},
}

# 渔获 — zones: shore/near/far/deep；pen=True 可渔排放养
SEA_CATCH = {
    "herring": {"name": "灰鲱", "emoji": "🐟", "sell": 14, "tides": ["ebb", "slack"], "zones": ["shore", "near"], "rarity": 1, "pen": True, "grow": 400, "stock_tickets": 9, "feed_item": "compost", "feed_qty": 1},
    "sandeel": {"name": "沙鳗", "emoji": "🪱", "sell": 11, "tides": ["ebb"], "zones": ["shore"], "rarity": 1, "pen": True, "grow": 360, "stock_tickets": 7, "feed_item": "compost", "feed_qty": 1},
    "flounder": {"name": "比目", "emoji": "🫠", "sell": 18, "tides": ["ebb", "slack"], "zones": ["shore", "near"], "rarity": 2, "pen": True, "grow": 480, "stock_tickets": 12, "feed_item": "compost", "feed_qty": 1},
    "cockle": {"name": "鸟蛤", "emoji": "🐚", "sell": 10, "tides": ["ebb"], "zones": ["shore"], "rarity": 1, "pen": False},
    "periwinkle": {"name": "滨螺", "emoji": "🐌", "sell": 8, "tides": ["ebb", "slack"], "zones": ["shore"], "rarity": 1, "pen": False},
    "mackerel": {"name": "鲭鱼", "emoji": "🐠", "sell": 22, "tides": ["slack", "flood"], "zones": ["near", "far"], "rarity": 2, "pen": True, "grow": 520, "stock_tickets": 14, "feed_item": "crop_kelp", "feed_qty": 1},
    "codling": {"name": "幼鳕", "emoji": "🐟", "sell": 20, "tides": ["slack"], "zones": ["near", "far"], "rarity": 2, "pen": True, "grow": 560, "stock_tickets": 15, "feed_item": "crop_kelp", "feed_qty": 1},
    "butterfish": {"name": "银鲳", "emoji": "🐡", "sell": 19, "tides": ["slack", "flood"], "zones": ["near"], "rarity": 2, "pen": True, "grow": 500, "stock_tickets": 13, "feed_item": "compost", "feed_qty": 1},
    "seatrout": {"name": "海鳟", "emoji": "🎣", "sell": 26, "tides": ["slack", "flood"], "zones": ["near", "far"], "rarity": 3, "pen": True, "grow": 600, "stock_tickets": 18, "feed_item": "wild_mint", "feed_qty": 1},
    "kelpcrab": {"name": "藻滩蟹", "emoji": "🦀", "sell": 26, "tides": ["ebb"], "zones": ["shore", "near"], "rarity": 2, "pen": True, "grow": 640, "stock_tickets": 20, "feed_item": "compost", "feed_qty": 2},
    "greenling": {"name": "青衣鱼", "emoji": "🐟", "sell": 24, "tides": ["ebb", "slack"], "zones": ["near"], "rarity": 2, "pen": True, "grow": 520, "stock_tickets": 16, "feed_item": "crop_kelp", "feed_qty": 1},
    "glassshrimp": {"name": "玻璃虾", "emoji": "🦐", "sell": 34, "tides": ["flood"], "zones": ["near", "far"], "rarity": 3, "pen": True, "grow": 580, "stock_tickets": 22, "feed_item": "crop_kelp", "feed_qty": 2},
    "pipefish": {"name": "管口鱼", "emoji": "🐡", "sell": 41, "tides": ["flood"], "zones": ["far", "deep"], "rarity": 3, "pen": False},
    "mullet": {"name": "鲻鱼", "emoji": "🐟", "sell": 17, "tides": ["flood"], "zones": ["near", "shore"], "rarity": 1, "pen": True, "grow": 440, "stock_tickets": 10, "feed_item": "compost", "feed_qty": 1},
    "streakbass": {"name": "纹鲈", "emoji": "🐠", "sell": 28, "tides": ["flood", "slack"], "zones": ["near", "far"], "rarity": 2, "pen": True, "grow": 580, "stock_tickets": 19, "feed_item": "wild_mint", "feed_qty": 1},
    "rockling": {"name": "岩鳕", "emoji": "🐟", "sell": 21, "tides": ["ebb", "slack"], "zones": ["near", "far"], "rarity": 2, "pen": True, "grow": 540, "stock_tickets": 17, "feed_item": "compost", "feed_qty": 2},
    "lingcod": {"name": "蛇鳕", "emoji": "🐉", "sell": 38, "tides": ["slack", "flood"], "zones": ["far", "deep"], "rarity": 4, "pen": False},
    "wolfeel": {"name": "狼鳗", "emoji": "🐍", "sell": 44, "tides": ["flood"], "zones": ["deep", "far"], "rarity": 4, "pen": False},
    "deepsaury": {"name": "深秋刀", "emoji": "🗡️", "sell": 36, "tides": ["slack", "flood"], "zones": ["far", "deep"], "rarity": 3, "pen": False},
    "lanternfish": {"name": "灯笼鱼", "emoji": "🏮", "sell": 48, "tides": ["flood"], "zones": ["deep"], "rarity": 5, "pen": False},
    "ghostskate": {"name": "幽灵鳐", "emoji": "👻", "sell": 55, "tides": ["ebb", "flood"], "zones": ["deep"], "rarity": 5, "pen": False},
    "moonjelly": {"name": "月水母", "emoji": "🌙", "sell": 15, "tides": ["slack", "flood"], "zones": ["near", "far"], "rarity": 2, "pen": False},
    "kingcrab": {"name": "石蟹王", "emoji": "👑", "sell": 62, "tides": ["ebb", "slack"], "zones": ["deep", "far"], "rarity": 5, "pen": True, "grow": 900, "stock_tickets": 35, "feed_item": "crop_kelp", "feed_qty": 3},
    "razorclam": {"name": "竹蛏", "emoji": "🔪", "sell": 16, "tides": ["ebb"], "zones": ["shore"], "rarity": 2, "pen": False},
    "seaurchin": {"name": "海胆", "emoji": "🦔", "sell": 30, "tides": ["ebb", "slack"], "zones": ["near", "shore"], "rarity": 3, "pen": False},
    "oarfish": {"name": "皇带鱼", "emoji": "🎏", "sell": 72, "tides": ["flood"], "zones": ["deep"], "rarity": 6, "pen": False},
}

RANDOM_LOOT = [
    ("compost", 1),
    ("compost", 2),
    ("wild_mint", 1),
    ("drift_twine", 1),
    ("drift_twine", 2),
    ("sea_glass", 1),
    ("ticket_stub", 1),
]

FORAGE_LOOT = [
    ("compost", "堆肥", 1, 35),
    ("wild_mint", "野薄荷", 1, 25),
    ("drift_twine", "漂绳", 1, 20),
    ("ticket_stub", "旧票根", 1, 15),
    ("sea_glass", "海玻璃", 1, 5),
]

STARTER_STOCK = {
    "seed_kale": 2,
    "seed_beet": 1,
    "seed_fogpea": 2,
    "compost": 1,
}

HEARTH_RECIPES = {
    "crop_beet|crop_kale": {"name": "赤绿泥汤", "sell": 38, "tags": ["root", "leaf"]},
    "crop_kale|crop_rye": {"name": "黑麦叶卷", "sell": 42, "tags": ["grain", "leaf"]},
    "crop_bramble|crop_fogpea": {"name": "雾莓酱", "sell": 45, "tags": ["berry", "legume"]},
    "crop_kelp|fish_herring": {"name": "潮线锅", "sell": 40, "tags": ["sea"]},
    "crop_kelp|fish_kelpcrab": {"name": "藻滩煲", "sell": 52, "tags": ["sea"]},
    "fish_mackerel|wild_mint": {"name": "薄荷熏鲭", "sell": 48, "tags": ["sea", "herb"]},
    "compost|crop_beet": {"name": "甜菜酵碗", "sell": 36, "tags": ["root", "ferment"]},
    "fish_seatrout|crop_kelp": {"name": "海鳟卷", "sell": 54, "tags": ["sea"]},
    "fish_glassshrimp|wild_mint": {"name": "水晶虾盘", "sell": 58, "tags": ["sea"]},
}

COMMONS_TEMPLATES = [
    {"key": "tide_chest", "label": "退潮铁箱", "domain": "shore", "item": "relic_iron", "qty": 1, "tickets": 0, "weight": 10},
    {"key": "glass_pocket", "label": "公共海玻璃堆", "domain": "shore", "item": "sea_glass", "qty": 3, "tickets": 0, "weight": 14},
    {"key": "compost_heap", "label": "联盟堆肥堆", "domain": "plot", "item": "compost", "qty": 4, "tickets": 0, "weight": 16},
    {"key": "mint_patch", "label": "野薄荷丛", "domain": "plot", "item": "wild_mint", "qty": 2, "tickets": 0, "weight": 12},
    {"key": "silver_net", "label": "借网点", "domain": "sea", "item": "drift_twine", "qty": 3, "tickets": 0, "weight": 11},
    {"key": "ticket_cache", "label": "档口遗票", "domain": "guild", "item": None, "qty": 0, "tickets": 22, "weight": 8},
    {"key": "amber_hunk", "label": "潮线琥珀", "domain": "shore", "item": "curio_amber", "qty": 1, "tickets": 0, "weight": 5},
    {"key": "pearl_grit", "label": "浅湾珠砂", "domain": "sea", "item": "curio_pearl", "qty": 1, "tickets": 0, "weight": 4},
    {"key": "seed_cache", "label": "公共种箱", "domain": "plot", "item": "seed_kale", "qty": 2, "tickets": 0, "weight": 9},
]

DISCOVERY_LOOT = {
    "tend": [
        ("curio_coin", 1, 12, "土下挖到旧币"),
        ("relic_iron", 1, 8, "一锹下去碰到铁疙瘩"),
        ("fossil_shell", 1, 6, "翻出化石贝壳"),
        ("compost", 1, 18, "土松了，顺手多一堆肥"),
        ("seed_fogpea", 1, 10, "埋着的雾豌豆种自己冒出来"),
    ],
    "forage": [
        ("curio_amber", 1, 5, "边际捡到琥珀块"),
        ("sea_glass", 1, 14, "海玻璃反光晃你眼"),
        ("wild_mint", 2, 16, "薄荷长得比你还精神"),
        ("ticket_stub", 2, 12, "旧票根成堆，像彩蛋"),
    ],
    "net": [
        ("curio_pearl", 1, 4, "网底卡了粒珠砂"),
        ("fish_moonjelly", 1, 7, "网到月水母——意外款"),
        ("drift_twine", 2, 15, "网缠漂绳，赚"),
        ("fish_razorclam", 1, 10, "网底竹蛏：惊喜"),
    ],
    "gather": [
        ("curio_coin", 1, 10, "收菜带起旧币"),
        ("seed_bramble", 1, 8, "藤间藏着荆棘莓种"),
        ("crop_kelp", 1, 9, "土里有浅海藻——谁种的"),
    ],
    "pen_harvest": [
        ("curio_pearl", 1, 6, "收网带出一粒珠砂"),
        ("fish_periwinkle", 2, 12, "渔排夹带滨螺"),
    ],
    "voyage_return": [
        ("curio_amber", 1, 4, "舱缝卡琥珀"),
        ("relic_iron", 1, 7, "锚链旁铁 relic"),
        ("fish_seaurchin", 1, 9, "归港网到海胆"),
    ],
}

RARE_CURIO = {
    "curio_coin": {"name": "旧潮币", "emoji": "🪙", "sell": 28},
    "curio_amber": {"name": "潮线琥珀", "emoji": "🟠", "sell": 42},
    "curio_pearl": {"name": "浅湾珠砂", "emoji": "⚪", "sell": 38},
    "relic_iron": {"name": "锈铁 relic", "emoji": "⚙️", "sell": 22},
    "fossil_shell": {"name": "化石贝壳", "emoji": "🐚", "sell": 26},
}

HUT_LEVELS = {
    1: {"name": "棚屋", "upgrade": 0, "hard": 1, "soft": 2},
    2: {"name": "岸畔小屋", "upgrade": 165, "hard": 2, "soft": 3},
    3: {"name": "联盟小宅", "upgrade": 290, "hard": 3, "soft": 5},
}

HUT_HARD = {
    "plank_floor": {"name": "防潮板地", "cost": 48, "emoji": "🪵", "hint": "脚感踏实，意外略少"},
    "rain_gutter": {"name": "雨水槽", "cost": 55, "emoji": "🌧️", "hint": "阵风天份地少点罪"},
    "storm_shutter": {"name": "风暴窗板", "cost": 72, "emoji": "🪟", "hint": "硬装护体，坏事件权重降"},
    "brick_hearth": {"name": "砖砌灶基", "cost": 88, "emoji": "🧱", "hint": "brew 多回一点雾智"},
    "glass_window": {"name": "海雾玻璃窗", "cost": 65, "emoji": "✨", "hint": "温室槽位更抗天气"},
}

HUT_SOFT = {
    "kelp_rug": {"name": "浅海藻毯", "cost": 32, "emoji": "🧶", "hint": "软装入门，脚不凉"},
    "tide_lamp": {"name": "潮汐灯", "cost": 38, "emoji": "💡", "hint": "暮夜雾智少掉一点"},
    "fog_curtain": {"name": "雾纱帘", "cost": 28, "emoji": "🪭", "hint": "档口看你顺眼些"},
    "herring_mobile": {"name": "鲱鱼风铃", "cost": 34, "emoji": "🎐", "hint": "风来有响，心情 +"},
    "mint_cushion": {"name": "薄荷靠垫", "cost": 26, "emoji": "🛋️", "hint": "guild 多一丢丢档信"},
    "sea_chart": {"name": "手绘海图", "cost": 45, "emoji": "🗺️", "hint": "出海归港略顺"},
    "bramble_wreath": {"name": "荆棘莓环", "cost": 30, "emoji": "🌸", "hint": "纯好看，访客爱拍"},
    "glass_float": {"name": "玻璃浮标", "cost": 36, "emoji": "🔮", "hint": "公共物资刷新略快——玄学"},
    "fridge": {"name": "冰箱", "cost": 120, "emoji": "🧊", "hint": "熟菜保鲜，kitchen store"},
}

TOOLS = {
    "hoe": {"name": "锄头", "cost": 35, "emoji": "⛏️"},
    "shovel": {"name": "铲子", "cost": 42, "emoji": "🪏"},
    "net_basic": {"name": "粗渔网", "cost": 28, "emoji": "🕸️", "fish_bonus": 0.0, "energy": 10},
    "net_fine": {"name": "细渔网", "cost": 75, "emoji": "🎣", "fish_bonus": 0.18, "energy": 7},
}

BEACH_LOOT = [
    ("shell_catseye", "猫眼螺", 1, 22, 18),
    ("shell_conch", "海螺", 1, 14, 25),
    ("shell_scallop", "扇贝壳", 1, 10, 30),
    ("fish_razorclam", "竹蛏", 1, 12, 20),
    ("bait_worm", "蚯蚓饵", 2, 16, 15),
]

MANURE = {
    "manure_sheep": {"name": "羊粪", "emoji": "💩", "compost_yield": 2, "sell": 4, "fertilize_boost": 0.14},
    "manure_pig": {"name": "猪粪", "emoji": "💩", "compost_yield": 3, "sell": 5, "fertilize_boost": 0.16},
    "manure_cow": {"name": "牛粪", "emoji": "💩", "compost_yield": 4, "sell": 6, "fertilize_boost": 0.20},
}

LARGE_LIVESTOCK = {"sheep", "pig", "cow"}

LIVESTOCK = {
    "rabbit": {"name": "兔", "emoji": "🐰", "buy": 55, "feed": "crop_fogpea", "feed_qty": 1, "grow": 600, "product": "meat_rabbit", "product_qty": 1},
    "chicken": {"name": "鸡", "emoji": "🐔", "buy": 48, "feed": "crop_rye", "feed_qty": 1, "grow": 480, "product": "egg", "product_qty": 2},
    "sheep": {"name": "羊", "emoji": "🐑", "buy": 95, "feed": "crop_kale", "feed_qty": 2, "grow": 900, "product": "wool", "product_qty": 1, "manure": "manure_sheep", "manure_feed": 1, "manure_harvest": 1},
    "pig": {"name": "猪", "emoji": "🐷", "buy": 110, "feed": "crop_beet", "feed_qty": 2, "grow": 840, "product": "meat_pork", "product_qty": 2, "manure": "manure_pig", "manure_feed": 1, "manure_harvest": 2},
    "cow": {"name": "牛", "emoji": "🐄", "buy": 180, "feed": "crop_rye", "feed_qty": 3, "grow": 1200, "product": "milk", "product_qty": 2, "manure": "manure_cow", "manure_feed": 2, "manure_harvest": 3},
    "dog": {"name": "狗", "emoji": "🐕", "buy": 70, "feed": "meat_rabbit", "feed_qty": 1, "grow": 0, "product": "guard", "product_qty": 0, "guard": True},
}

# 渔具数值 tier — gear_ops status / upgrade bait|rod|net
GEAR_TIERS = {
    "bait": [
        {"tier": 1, "name": "蚯蚓饵", "catch": 0.00, "rarity": 0, "empty": 0.00, "tickets": 0},
        {"tier": 2, "name": "发酵饵", "catch": 0.06, "rarity": 0, "empty": 0.05, "tickets": 32, "need": {"bait_worm": 10, "compost": 2}},
        {"tier": 3, "name": "腥香饵", "catch": 0.12, "rarity": 1, "empty": 0.09, "tickets": 58, "need": {"bait_worm": 15, "fish_herring": 3}},
        {"tier": 4, "name": "蛋白饵", "catch": 0.18, "rarity": 1, "empty": 0.13, "tickets": 92, "need": {"manure_cow": 2, "crop_kelp": 4}},
        {"tier": 5, "name": "龙涎拟饵", "catch": 0.26, "rarity": 2, "empty": 0.18, "tickets": 140, "need": {"bait_worm": 8, "fish_glassshrimp": 2}},
    ],
    "rod": [
        {"tier": 0, "name": "无竿", "catch": 0.00, "rarity": 0, "empty": 0.00, "energy": 0},
        {"tier": 1, "name": "竹钓竿", "catch": 0.04, "rarity": 0, "empty": 0.03, "energy": 9, "tickets": 30},
        {"tier": 2, "name": "碳素竿", "catch": 0.10, "rarity": 0, "empty": 0.06, "energy": 8, "tickets": 55, "need": {"drift_twine": 4}},
        {"tier": 3, "name": "海钓竿", "catch": 0.16, "rarity": 1, "empty": 0.10, "energy": 7, "tickets": 85, "need": {"fish_mackerel": 2, "sea_glass": 2}},
        {"tier": 4, "name": "投力竿", "catch": 0.22, "rarity": 1, "empty": 0.14, "energy": 6, "tickets": 120, "need": {"fish_seatrout": 1, "wool": 2}},
        {"tier": 5, "name": "潮纹竿", "catch": 0.30, "rarity": 2, "empty": 0.18, "energy": 5, "tickets": 170, "need": {"fish_lingcod": 1, "curio_pearl": 1}},
    ],
    "net": [
        {"tier": 0, "name": "无网", "catch": 0.00, "rarity": 0, "empty": 0.00, "energy": 14},
        {"tier": 1, "name": "粗渔网", "catch": 0.00, "rarity": 0, "empty": 0.02, "energy": 10, "tickets": 28},
        {"tier": 2, "name": "细渔网", "catch": 0.10, "rarity": 0, "empty": 0.06, "energy": 8, "tickets": 52, "need": {"drift_twine": 5}},
        {"tier": 3, "name": "染网", "catch": 0.18, "rarity": 1, "empty": 0.10, "energy": 7, "tickets": 82, "need": {"crop_kelp": 5, "compost": 3}},
        {"tier": 4, "name": "银丝网", "catch": 0.26, "rarity": 1, "empty": 0.14, "energy": 6, "tickets": 118, "need": {"curio_pearl": 1, "fish_kelpcrab": 1}},
        {"tier": 5, "name": "潮纹网", "catch": 0.34, "rarity": 2, "empty": 0.18, "energy": 5, "tickets": 168, "need": {"fish_kingcrab": 1, "drift_twine": 6}},
    ],
}

KITCHEN_DISHES = {
    "garlic_oyster": {
        "name": "蒜蓉生蚝", "emoji": "🦪",
        "ings": ["fish_seaurchin", "crop_garlic", "crop_chili"],
        "base_sell": 72, "energy": 22, "tags": ["sea", "spicy"],
    },
    "blanch_shrimp": {
        "name": "白灼虾", "emoji": "🦐",
        "ings": ["fish_glassshrimp", "crop_ginger"],
        "base_sell": 65, "energy": 20, "tags": ["sea"],
    },
    "steam_fish": {
        "name": "清蒸鱼", "emoji": "🐟",
        "ings": ["fish_seatrout", "crop_ginger", "crop_garlic"],
        "base_sell": 58, "energy": 18, "tags": ["sea"],
    },
    "cheese_lobster": {
        "name": "芝士龙虾", "emoji": "🦞",
        "ings": ["fish_kingcrab", "crop_kale", "milk"],
        "base_sell": 98, "energy": 28, "tags": ["sea", "rich"],
    },
    "braised_fish": {
        "name": "红烧鱼", "emoji": "🍲",
        "ings": ["fish_mackerel", "crop_garlic", "crop_chili", "crop_beet"],
        "base_sell": 62, "energy": 20, "tags": ["sea"],
    },
    "sour_fish": {
        "name": "酸汤鱼", "emoji": "🥘",
        "ings": ["fish_streakbass", "crop_chili", "crop_blueberry"],
        "base_sell": 68, "energy": 22, "tags": ["sea", "sour"],
    },
    "chop_head": {
        "name": "剁椒鱼头", "emoji": "🌶️",
        "ings": ["fish_lingcod", "crop_chili", "crop_garlic"],
        "base_sell": 88, "energy": 24, "tags": ["sea", "spicy"],
    },
    "blueberry_tart": {
        "name": "蓝莓派", "emoji": "🥧",
        "ings": ["crop_blueberry", "crop_rye", "milk"],
        "base_sell": 48, "energy": 16, "tags": ["dessert"],
    },
}

MYTH_INGREDIENTS = {
    "myth_octopus": {"name": "克系章鱼肉", "emoji": "🐙", "sell": 220, "energy": 40},
}

# 病症 — 随机事件致病，clinic_ops treat 花钱治（必须花票）
AILMENTS = {
    "sprain": {
        "name": "扭伤", "emoji": "🦵", "cost": 18, "health_loss": 10, "health_restore": 14,
        "hint": "干农活扭的，走路抽抽", "energy_extra": 2,
    },
    "cut": {
        "name": "篱笆划伤", "emoji": "🩹", "cost": 12, "health_loss": 8, "health_restore": 10,
        "hint": "铁丝网留的，别硬撑", "energy_extra": 1,
    },
    "backache": {
        "name": "腰肌劳损", "emoji": "💢", "cost": 20, "health_loss": 12, "health_restore": 15,
        "hint": "弯腰太多，直不起来", "energy_extra": 2, "max_energy_cut": 5,
    },
    "allergy": {
        "name": "花粉过敏", "emoji": "🤧", "cost": 16, "health_loss": 9, "health_restore": 12,
        "hint": "打喷嚏停不下来", "energy_extra": 1,
    },
    "cold": {
        "name": "海雾感冒", "emoji": "🤒", "cost": 15, "health_loss": 10, "health_restore": 13,
        "hint": "雾进肺里，咳", "energy_extra": 2,
    },
    "shell_scratch": {
        "name": "贝壳刮脚", "emoji": "🦶", "cost": 10, "health_loss": 6, "health_restore": 8,
        "hint": "退潮滩上血线一道", "energy_extra": 1,
    },
    "jelly_sting": {
        "name": "水母蛰", "emoji": "🌊", "cost": 22, "health_loss": 14, "health_restore": 16,
        "hint": "网底惊喜，又肿又痒", "energy_extra": 3,
    },
    "food_poison": {
        "name": "肠胃闹腾", "emoji": "🤢", "cost": 24, "health_loss": 15, "health_restore": 18,
        "hint": "吃了不该吃的", "energy_extra": 2, "max_energy_cut": 8,
    },
    "hangover": {
        "name": "宿醉", "emoji": "🍺", "cost": 18, "health_loss": 11, "health_restore": 14,
        "hint": "昨晚陪聊陪多了", "energy_extra": 2, "max_energy_cut": 10,
    },
    "sunburn": {
        "name": "日晒灼伤", "emoji": "☀️", "cost": 14, "health_loss": 8, "health_restore": 11,
        "hint": "赶海没涂泥，红成虾", "energy_extra": 1,
    },
    "blister": {
        "name": "磨起泡", "emoji": "💧", "cost": 11, "health_loss": 5, "health_restore": 8,
        "hint": "锄头柄握手处", "energy_extra": 1,
    },
    "crab_pinch": {
        "name": "蟹钳印", "emoji": "🦀", "cost": 16, "health_loss": 9, "health_restore": 12,
        "hint": "沙蟹脾气比嘴硬", "energy_extra": 2,
    },
}

WORLD_BOSS = {
    "key": "cthulhu_tide",
    "name": "潮渊之主",
    "hp": 5000,
    "loot": "myth_octopus",
    "loot_qty": 2,
}

NPC_FIXED = [
    {"key": "old_salt", "name": "老水手巴顿", "lines": ["今天潮线低，适合赶海", "细网比粗网省劲"]},
    {"key": "herb_aunt", "name": "姜姨", "lines": ["酸汤鱼要够辣", "种点姜，厨房才像样"]},
    {"key": "market_fan", "name": "集市范姐", "lines": ["缺啥上 market 挂单", "建议价仅供参考，别跟票置气"]},
    {"key": "lizhi", "name": "荔栀", "lines": [
        "滨海酒吧今晚缺人手，票紧的来搭把手",
        "别紧张，陪聊倒酒——联盟备案正规工",
        "穷人别硬撑面子，上工几轮票就回来",
        "笑自然点，小费在笑纹里",
        "shift 完记得 eat，别空肚跟客人拼酒",
    ]},
    {"key": "gugu_dove", "name": "咕咕斑鸠", "lines": [
        "咕咕咕咕咕咕——（它对你的庄稼更感兴趣）",
        "早晨准时到岗，联盟登记在册，伤不得也赶不走",
        "你挥胳膊它咕咕，你骂它它还咕咕——纯嘴炮免疫",
        "偷吃两口算它上班，别跟斑鸠讲理，讲不过",
        "稻草人瞪它，它对视咕咕咕——平局",
    ]},
    {"key": "qiaoqiao", "name": "桥桥大夫", "lines": [
        "诊所规矩：必须花钱，不赊账，不还价",
        "随机事件落下的病，找随机事件哭去——诊费照收",
        "扭了脚、着了凉、宿醉——都挂号，都花钱",
        "身体指标低了意外多，别硬撑到票都不够挂号",
        "npc_ops visit 只能聊天，真治得 clinic_ops treat",
    ]},
    {"key": "lili", "name": "栗栗", "lines": [
        "贝壳换装饰，装饰换心情——我只收现货",
        "驮包不会说话，我会——今天货不多",
        "路过就换，错过等下回，别跟摊儿置气",
        "稀有软装不进 hut catalog，只在我这",
        "lili_ops scan 看货架，trade 编号成交",
    ]},
]

# 栗栗流动摊 — 稀有装饰（deco_*），hut_ops install 到 soft 槽
LILI_DECOR = {
    "coral_lamp": {"name": "珊瑚小灯", "emoji": "🪸", "hint": "栗栗亲制，暮夜雾智少掉一点", "sell": 55},
    "shell_windchime": {"name": "贝壳风铃", "emoji": "🎐", "hint": "比鲱鱼风铃贵气，风来有响", "sell": 48},
    "pearl_garland": {"name": "珠串帘", "emoji": "📿", "hint": "档口看你顺眼些——玄学", "sell": 52},
    "tide_clock": {"name": "潮汐钟", "emoji": "🕰️", "hint": "退潮铃响，赶海更准", "sell": 50},
    "drift_bonsai": {"name": "漂木盆景", "emoji": "🪴", "hint": "枯而不死，访客爱拍", "sell": 46},
    "moon_mirror": {"name": "月海镜", "emoji": "🪞", "hint": "映潮线，纯好看", "sell": 58},
    "net_dreamcatcher": {"name": "渔网捕梦", "emoji": "🕸️", "hint": "噩运权重略降——信则灵", "sell": 44},
    "star_crown": {"name": "海星冠", "emoji": "⭐", "hint": "纯炫，肖像加成 vibe", "sell": 62},
    "amber_frame": {"name": "琥珀画框", "emoji": "🖼️", "hint": "装什么都是艺术品", "sell": 68},
    "kelp_tassel": {"name": "海藻流苏", "emoji": "🌿", "hint": "门帘响，心情 +", "sell": 38},
}

LILI_TRADE_POOL = [
    {"key": "conch_lamp", "give": {"shell_conch": 4, "shell_scallop": 2}, "get": "deco_coral_lamp", "weight": 12, "stock": 1},
    {"key": "catseye_chime", "give": {"shell_catseye": 5, "sea_glass": 2}, "get": "deco_shell_windchime", "weight": 14, "stock": 1},
    {"key": "pearl_garland", "give": {"shell_scallop": 3, "curio_pearl": 1}, "get": "deco_pearl_garland", "weight": 8, "stock": 1},
    {"key": "tide_clock", "give": {"shell_conch": 3, "shell_catseye": 3, "drift_twine": 2}, "get": "deco_tide_clock", "weight": 10, "stock": 1},
    {"key": "drift_bonsai", "give": {"shell_scallop": 4, "fish_cockle": 2, "compost": 1}, "get": "deco_drift_bonsai", "weight": 9, "stock": 1},
    {"key": "moon_mirror", "give": {"shell_catseye": 4, "curio_amber": 1}, "get": "deco_moon_mirror", "weight": 6, "stock": 1},
    {"key": "net_dream", "give": {"drift_twine": 5, "shell_scallop": 3}, "get": "deco_net_dreamcatcher", "weight": 11, "stock": 1},
    {"key": "star_crown", "give": {"shell_catseye": 6, "fish_periwinkle": 4}, "get": "deco_star_crown", "weight": 7, "stock": 1},
    {"key": "amber_frame", "give": {"curio_amber": 1, "shell_conch": 2, "sea_glass": 3}, "get": "deco_amber_frame", "weight": 5, "stock": 1},
    {"key": "kelp_tassel", "give": {"crop_kelp": 3, "shell_scallop": 2, "bait_worm": 4}, "get": "deco_kelp_tassel", "weight": 13, "stock": 2},
    {"key": "blueberry_glass", "give": {"crop_blueberry": 4, "shell_conch": 2, "sea_glass": 2}, "get": "deco_moon_mirror", "weight": 8, "stock": 1},
    {"key": "premium_float", "give": {"shell_conch": 3, "curio_pearl": 1}, "get": "deco_star_crown", "tickets": 8, "weight": 4, "stock": 1},
    {"key": "worm_special", "give": {"bait_worm": 8, "shell_scallop": 2}, "get": "deco_kelp_tassel", "weight": 10, "stock": 1},
    {"key": "fossil_deal", "give": {"fossil_shell": 1, "shell_catseye": 3}, "get": "deco_amber_frame", "weight": 5, "stock": 1},
]

COASTAL_BAR = {
    "name": "滨海酒吧",
    "emoji": "🍸",
    "owner": "lizhi",
    "owner_name": "荔栀",
    "open_phases": ["dusk", "night"],
}

BAR_SERVICES = {
    "chat": {"name": "陪聊一杯", "emoji": "🥃", "cost": 15, "desc": "听值班牛郎唠嗑一轮"},
    "listen": {"name": "海风故事", "emoji": "🌊", "cost": 24, "desc": "专属 storytelling 档"},
    "vip": {"name": "卡座驻场", "emoji": "✨", "cost": 48, "desc": "卡座一整晚的陪聊服务"},
}

NPC_THIEVES = ["篱笆手影", "逾篱阿窃", "夜行摘客", "档口惯偷"]

ITEM_PRICES = {f"seed_{k}": v["seed_price"] for k, v in CROPS.items()}
ITEM_PRICES.update({f"crop_{k}": v["sell"] for k, v in CROPS.items()})
ITEM_PRICES.update({f"fish_{k}": v["sell"] for k, v in SEA_CATCH.items()})
ITEM_PRICES.update({"compost": 6, "wild_mint": 8, "drift_twine": 5, "sea_glass": 12})
ITEM_PRICES.update({k: v["sell"] for k, v in RARE_CURIO.items()})
for cat in (HUT_HARD, HUT_SOFT):
    for k, v in cat.items():
        ITEM_PRICES[f"fit_{k}"] = v["cost"] // 2
ITEM_PRICES.update({f"meal_{i}": r["sell"] for i, r in enumerate(HEARTH_RECIPES.values(), 1)})
ITEM_PRICES.update({f"tool_{k}": v["cost"] for k, v in TOOLS.items()})
for k, _, _, _, price in BEACH_LOOT:
    ITEM_PRICES[k] = price
ITEM_PRICES.update({
    "bait_worm": 6,
    "shell_catseye": 18, "shell_conch": 25, "shell_scallop": 30,
    "egg": 14, "milk": 16, "wool": 22,
    "meat_rabbit": 20, "meat_pork": 28,
    "scarecrow": 35,
})
ITEM_PRICES.update({k: v["sell"] for k, v in MANURE.items()})
for k, v in LIVESTOCK.items():
    ITEM_PRICES[f"live_{k}"] = v["buy"]
for k, v in KITCHEN_DISHES.items():
    ITEM_PRICES[f"dish_{k}"] = v["base_sell"]
for k, v in MYTH_INGREDIENTS.items():
    ITEM_PRICES[k] = v["sell"]
for k, v in LILI_DECOR.items():
    ITEM_PRICES[f"deco_{k}"] = v["sell"]

ITEM_NAMES = {f"seed_{k}": f"{v['name']}种" for k, v in CROPS.items()}
ITEM_NAMES.update({f"crop_{k}": v["name"] for k, v in CROPS.items()})
ITEM_NAMES.update({f"fish_{k}": v["name"] for k, v in SEA_CATCH.items()})
ITEM_NAMES.update({
    "compost": "堆肥", "wild_mint": "野薄荷", "drift_twine": "漂绳",
    "ticket_stub": "旧票根", "sea_glass": "海玻璃",
})
ITEM_NAMES.update({k: f"{v['emoji']}{v['name']}" for k, v in RARE_CURIO.items()})
for cat in (HUT_HARD, HUT_SOFT):
    for k, v in cat.items():
        ITEM_NAMES[f"fit_{k}"] = f"{v['emoji']}{v['name']}"
for i, r in enumerate(HEARTH_RECIPES.values(), 1):
    ITEM_NAMES[f"meal_{i}"] = r["name"]
ITEM_NAMES.update({f"tool_{k}": f"{v['emoji']}{v['name']}" for k, v in TOOLS.items()})
for k, _, _, _, _ in BEACH_LOOT:
    ITEM_NAMES[k] = next(x[1] for x in BEACH_LOOT if x[0] == k)
ITEM_NAMES.update({
    "bait_worm": "蚯蚓饵",
    "shell_catseye": "🐚猫眼螺", "shell_conch": "🐚海螺", "shell_scallop": "🐚扇贝壳",
    "egg": "🥚鸡蛋", "milk": "🥛牛奶", "wool": "🧶羊毛",
    "meat_rabbit": "🍖兔肉", "meat_pork": "🥓猪肉",
    "scarecrow": "🌾稻草人",
})
ITEM_NAMES.update({k: f"{v['emoji']}{v['name']}" for k, v in MANURE.items()})
for k, v in LIVESTOCK.items():
    ITEM_NAMES[f"live_{k}"] = f"{v['emoji']}{v['name']}(幼)"
for k, v in KITCHEN_DISHES.items():
    ITEM_NAMES[f"dish_{k}"] = f"{v['emoji']}{v['name']}"
for k, v in MYTH_INGREDIENTS.items():
    ITEM_NAMES[k] = f"{v['emoji']}{v['name']}"
for k, v in LILI_DECOR.items():
    ITEM_NAMES[f"deco_{k}"] = f"{v['emoji']}{v['name']}"


def dish_item(key: str, stars: int = 3) -> str:
    return f"dish_{key}_s{max(1, min(5, stars))}"


def dish_display_name(key: str, stars: int) -> str:
    meta = KITCHEN_DISHES[key]
    suffix = "★" * stars
    return f"{meta['emoji']}{meta['name']}{suffix}"


def register_dish_item(key: str, stars: int) -> None:
    item = dish_item(key, stars)
    ITEM_NAMES[item] = dish_display_name(key, stars)
    ITEM_PRICES[item] = dish_sell_price(key, stars)


def dish_sell_price(key: str, stars: int) -> int:
    base = KITCHEN_DISHES[key]["base_sell"]
    mult = {1: 0.6, 2: 0.85, 3: 1.0, 4: 1.35, 5: 1.8}.get(stars, 1.0)
    return max(8, int(base * mult))


def suggested_price(item: str) -> int:
    if item.startswith("dish_") and "_s" in item:
        base, star_s = item.rsplit("_s", 1)
        if star_s.isdigit():
            key = base.replace("dish_", "", 1)
            if key in KITCHEN_DISHES:
                return dish_sell_price(key, int(star_s))
    if item.startswith("dish_"):
        key = item.replace("dish_", "", 1)
        if key in KITCHEN_DISHES:
            return KITCHEN_DISHES[key]["base_sell"]
    return ITEM_PRICES.get(item, 0)


for dk in KITCHEN_DISHES:
    for st in range(1, 6):
        register_dish_item(dk, st)


def pen_species_keys() -> list[str]:
    return [k for k, v in SEA_CATCH.items() if v.get("pen")]


def fish_keys_for_tide(tide: str) -> list[str]:
    return [k for k, v in SEA_CATCH.items() if tide in v.get("tides", [])]


def fish_keys_for_zones(zones: set[str]) -> list[str]:
    return [k for k, v in SEA_CATCH.items() if zones.intersection(v.get("zones", []))]


def weighted_fish_pick(
    *,
    tide: str | None = None,
    zones: set[str] | None = None,
    rarity_cap: int | None = None,
) -> str:
    import random

    pool: list[tuple[str, int]] = []
    for key, meta in SEA_CATCH.items():
        if tide and tide not in meta.get("tides", []):
            continue
        if zones and not zones.intersection(meta.get("zones", [])):
            continue
        if rarity_cap and meta.get("rarity", 1) > rarity_cap:
            continue
        weight = max(1, 7 - meta.get("rarity", 1))
        pool.append((key, weight))
    if not pool:
        return random.choice(list(SEA_CATCH.keys()))
    keys, weights = zip(*pool)
    return random.choices(keys, weights=weights, k=1)[0]


def random_fish_item(
    *,
    tide: str | None = None,
    zones: set[str] | None = None,
    qty: int = 1,
) -> tuple[str, int]:
    key = weighted_fish_pick(tide=tide, zones=zones)
    return f"fish_{key}", qty


def voyage_loot_table(route_key: str) -> list[str]:
    """Weighted loot ids for a voyage route — built from zones + misc."""
    import random

    zone_map = {
        "near": {"shore", "near"},
        "far": {"near", "far"},
        "deep": {"far", "deep"},
    }
    zones = zone_map.get(route_key, {"near"})
    rarity_cap = {"near": 3, "far": 4, "deep": 6}.get(route_key, 3)
    table: list[str] = []
    for _ in range(8):
        fk = weighted_fish_pick(zones=zones, rarity_cap=rarity_cap)
        table.append(f"fish_{fk}")
    for item, _ in RANDOM_LOOT:
        table.append(item)
    return table
