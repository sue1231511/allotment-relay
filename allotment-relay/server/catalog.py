# 份地作物 — 偏北欧/沿海/湿地，与常见农场游戏区分
# grow=基准分钟（farming.py base_grow_seconds 内 ×60 转秒）；spread 控制播种时随机生长窗口
# 梯度：基础蔬菜 ~1h → 普通 1.5~2.5h → 浆果/谷物 2.5~4h → 树 4~5.5h → 稀有封顶 6h
CROPS = {
    # ── 基础蔬菜（1h 左右）──
    "kale":        {"name": "羽衣甘蓝", "emoji": "🥬", "seed_price": 7,  "sell": 16, "grow":  60, "spread": 0.30, "tags": ["leaf"], "aliases": ["甘蓝", "羽衣"]},
    "garlic":      {"name": "大蒜",     "emoji": "🧄", "seed_price": 9,  "sell": 18, "grow":  65, "spread": 0.22, "tags": ["seasoning"]},
    "lemongrass":  {"name": "香茅",     "emoji": "🌿", "seed_price": 10, "sell": 20, "grow":  70, "spread": 0.22, "tags": ["seasoning", "tropic", "herb"]},
    "chili":       {"name": "辣椒",     "emoji": "🌶️", "seed_price": 11, "sell": 22, "grow":  70, "spread": 0.24, "tags": ["seasoning"]},
    "sweetpotato": {"name": "红薯",     "emoji": "🍠", "seed_price": 8,  "sell": 17, "grow":  80, "spread": 0.24, "tags": ["root", "tropic"], "aliases": ["番薯", "地瓜"]},
    "ginger":      {"name": "姜",       "emoji": "🫚", "seed_price": 12, "sell": 24, "grow":  80, "spread": 0.22, "tags": ["seasoning", "tropic"]},
    # ── 普通（1.5~2.5h）──
    "kelp":        {"name": "浅海藻",   "emoji": "🌿", "seed_price": 11, "sell": 24, "grow":  85, "spread": 0.30, "tags": ["sea"]},
    "fogpea":      {"name": "雾豌豆",   "emoji": "🫛", "seed_price": 10, "sell": 23, "grow":  90, "spread": 0.28, "tags": ["legume"]},
    "beet":        {"name": "甜菜",     "emoji": "🫘", "seed_price": 9,  "sell": 21, "grow": 100, "spread": 0.26, "tags": ["root"]},
    "rye":         {"name": "黑麦",     "emoji": "🌾", "seed_price": 8,  "sell": 19, "grow": 120, "spread": 0.28, "tags": ["grain"]},
    # ── 中级浆果 / 热带非树（2.5~4h）──
    "bramble":     {"name": "荆棘莓",   "emoji": "🫐", "seed_price": 14, "sell": 32, "grow": 150, "spread": 0.28, "tags": ["berry"]},
    "blueberry":   {"name": "蓝莓",     "emoji": "🫐", "seed_price": 16, "sell": 36, "grow": 160, "spread": 0.26, "tags": ["berry", "tropic"]},
    "pineapple":   {"name": "菠萝",     "emoji": "🍍", "seed_price": 17, "sell": 32, "grow": 180, "spread": 0.26, "tags": ["fruit", "tropic"]},
    # ── 树类（3~5.5h）──
    "lime":        {"name": "青柠",     "emoji": "🍋", "seed_price": 14, "sell": 26, "grow": 200, "spread": 0.24, "tags": ["fruit", "tropic"], "tree": True, "shake": True},
    "papaya":      {"name": "木瓜",     "emoji": "🍈", "seed_price": 19, "sell": 34, "grow": 210, "spread": 0.24, "tags": ["fruit", "tropic"], "tree": True},
    "banana":      {"name": "香蕉",     "emoji": "🍌", "seed_price": 18, "sell": 28, "grow": 240, "spread": 0.24, "tags": ["fruit", "tropic"], "tree": True},
    "mango":       {"name": "芒果",     "emoji": "🥭", "seed_price": 20, "sell": 38, "grow": 260, "spread": 0.24, "tags": ["fruit", "tropic"], "tree": True, "shake": True},
    # ── 稀有树 / 封顶（4~6h）──
    "coconut":     {"name": "椰子",     "emoji": "🥥", "seed_price": 22, "sell": 24, "grow": 270, "spread": 0.20, "tags": ["fruit", "tropic"], "tree": True, "shake": True},
    "durian":      {"name": "榴莲",     "emoji": "🍈", "seed_price": 48, "sell": 95, "grow": 300, "spread": 0.20, "tags": ["fruit", "tropic"], "tree": True, "ultra_rare": True},
}

_CROP_SUFFIXES = ("种子", "种", "苗")


def resolve_crop_key(token: str) -> str | None:
    """英文 key、中文全名、别名、去后缀种/种子 均可解析。"""
    raw = token.strip()
    if not raw:
        return None

    key = raw.lower()
    if key in CROPS:
        return key

    if key.startswith("seed_"):
        crop_key = key[5:]
        if crop_key in CROPS:
            return crop_key

    for suffix in _CROP_SUFFIXES:
        if raw.endswith(suffix) and len(raw) > len(suffix):
            hit = resolve_crop_key(raw[: -len(suffix)])
            if hit:
                return hit

    for ck, meta in CROPS.items():
        if meta["name"] == raw:
            return ck
        for alias in meta.get("aliases", ()):
            if alias == raw or alias.lower() == key:
                return ck

    by_substr = [ck for ck, meta in CROPS.items() if raw in meta["name"]]
    if len(by_substr) == 1:
        return by_substr[0]

    return None


def unknown_crop_message(token: str) -> str:
    lines = [f"未知作物: {token}。可用 key、seed_ 前缀或中文名，例如："]
    for k, meta in CROPS.items():
        aliases = meta.get("aliases", ())
        alias_s = f"（{','.join(aliases)}）" if aliases else ""
        lines.append(f"  {k} / {meta['name']}{alias_s}")
    lines.append("plot_ops catalog 查全表")
    return "\n".join(lines)


def unknown_item_message(token: str) -> str:
    return (
        f"无法识别物品: {token}。tote_ops list 会显示中文名与英文 id；"
        "也可直接用 fish_mackerel、crop_beet、wild_mint 等"
    )

def resolve_item_key(token: str, *, prefer: str = "any") -> str | None:
    """中文名/简称/英文 key → 行囊 item id（vend/market/swap/brew 通用）。"""
    raw = token.strip().rstrip(";,")
    if not raw:
        return None

    norm = raw.lower().replace(" ", "_")
    if norm in ITEM_PRICES or norm in ITEM_NAMES:
        return norm

    exact = [k for k, v in ITEM_NAMES.items() if v == raw]
    if len(exact) == 1:
        return exact[0]

    for fk, meta in SEA_CATCH.items():
        if meta["name"] == raw:
            return f"fish_{fk}"
    if norm in SEA_CATCH:
        return f"fish_{norm}"
    compact = norm.replace("_", "")
    if compact in SEA_CATCH:
        return f"fish_{compact}"
    fish_key = f"fish_{norm}"
    if fish_key in ITEM_PRICES:
        return fish_key
    fish_compact = f"fish_{compact}"
    if fish_compact in ITEM_PRICES:
        return fish_compact

    crop = resolve_crop_key(raw)
    if crop:
        crop_key, seed_key = f"crop_{crop}", f"seed_{crop}"
        if prefer == "seed":
            if seed_key in ITEM_PRICES:
                return seed_key
            if crop_key in ITEM_PRICES:
                return crop_key
        else:
            if crop_key in ITEM_PRICES:
                return crop_key
            if seed_key in ITEM_PRICES:
                return seed_key

    if raw.endswith("种"):
        crop = resolve_crop_key(raw[:-1])
        if crop:
            sk = f"seed_{crop}"
            if sk in ITEM_PRICES:
                return sk

    for ck in CROPS:
        if norm == ck:
            ck_item = f"crop_{ck}"
            if ck_item in ITEM_PRICES:
                return ck_item

    return None


def item_vendable(item_key: str) -> bool:
    if item_key.startswith("dish_"):
        return True
    return ITEM_PRICES.get(item_key, 0) > 0

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
    "walkblue": {
        "name": "未命名小鱼",
        "emoji": "🐟",
        "sell": 52,
        "tides": ["slack", "flood"],
        "zones": ["far", "deep"],
        "rarity": 5,
        "pen": False,
    },
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
        ("seed_mango", 1, 5, "熟果掉出芒果种"),
        ("seed_papaya", 1, 5, "木瓜藤间藏着种"),
        ("seed_lemongrass", 1, 6, "香茅根旁多一撮种"),
    ],
    "beach": [
        ("curio_pearl", 1, 4, "沙面反光——珠砂"),
        ("sea_glass", 1, 12, "浪退留下海玻璃"),
        ("bait_worm", 3, 14, "湿沙下蚯蚓成窝"),
        ("fish_razorclam", 1, 8, "探到竹蛏，惊喜"),
        ("shell_starfish", 1, 6, "海星在看你"),
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
    "plank_floor": {"name": "防潮板地", "cost": 48, "emoji": "🪵", "hint": "意外掷骰 ×0.90"},
    "rain_gutter": {"name": "雨水槽", "cost": 55, "emoji": "🌧️", "hint": "阵风生长惩罚 ×0.86，阵风坏事件 ×0.90"},
    "storm_shutter": {"name": "风暴窗板", "cost": 72, "emoji": "🪟", "hint": "坏事件略少、野兽 ×0.82、斑鸠偷包 ×0.70（与渔网捕梦同组不叠）"},
    "brick_hearth": {"name": "砖砌灶基", "cost": 88, "emoji": "🧱", "hint": "brew 雾智 +4"},
    "glass_window": {"name": "海雾玻璃窗", "cost": 65, "emoji": "✨", "hint": "阵风生长惩罚 ×0.92（与雨水槽可叠）"},
}

HUT_SOFT = {
    "kelp_rug": {"name": "浅海藻毯", "cost": 32, "emoji": "🧶", "hint": "纯好看，无数值"},
    "tide_lamp": {"name": "潮汐灯", "cost": 38, "emoji": "💡", "hint": "暮/夜行动补雾智 +1（与珊瑚小灯同组不叠）"},
    "fog_curtain": {"name": "雾纱帘", "cost": 28, "emoji": "🪭", "hint": "guild_shift 档信 +1（与珠串帘同组不叠）"},
    "herring_mobile": {"name": "鲱鱼风铃", "cost": 34, "emoji": "🎐", "hint": "酒吧小费 +2（与海星冠同组不叠）"},
    "mint_cushion": {"name": "薄荷靠垫", "cost": 26, "emoji": "🛋️", "hint": "guild_shift 档信 +2"},
    "sea_chart": {"name": "手绘海图", "cost": 45, "emoji": "🗺️", "hint": "出海失败率 ×0.86，黑旗战力 +10"},
    "bramble_wreath": {"name": "荆棘莓环", "cost": 30, "emoji": "🌸", "hint": "纯好看，无数值"},
    "glass_float": {"name": "玻璃浮标", "cost": 36, "emoji": "🔮", "hint": "公共物资刷新 ×1.22"},
    "fridge": {"name": "冰箱", "cost": 120, "emoji": "🧊", "hint": "kitchen store 保鲜；开小馆必需"},
}

TOOLS = {
    "hoe": {"name": "锄头", "cost": 35, "emoji": "⛏️"},
    "shovel": {"name": "铲子", "cost": 42, "emoji": "🪏"},
    "net_basic": {"name": "粗渔网", "cost": 28, "emoji": "🕸️", "fish_bonus": 0.0, "energy": 10},
    "net_fine": {"name": "细渔网", "cost": 75, "emoji": "🎣", "fish_bonus": 0.18, "energy": 7},
}

# (item, label, qty, weight, price) — weight 越高越常见
BEACH_LOOT = [
    ("shell_catseye", "猫眼螺", 1, 22, 18),
    ("shell_conch", "海螺", 1, 14, 25),
    ("shell_scallop", "扇贝壳", 1, 10, 30),
    ("shell_starfish", "海星", 1, 8, 22),
    ("shell_mussel", "青口贝", 1, 12, 16),
    ("fish_razorclam", "竹蛏", 1, 12, 20),
    ("fish_cockle", "鸟蛤", 1, 14, 10),
    ("fish_periwinkle", "滨螺", 2, 18, 8),
    ("beach_crab", "沙蟹", 1, 10, 24),
    ("beach_squid", "小管鱿鱼", 1, 7, 28),
    ("crop_kelp", "浅海藻", 1, 15, 12),
    ("bait_worm", "蚯蚓饵", 2, 16, 15),
    ("sea_glass", "海玻璃", 1, 6, 12),
    ("fish_seaurchin", "海胆", 1, 5, 30),
    ("curio_pearl", "浅湾珠砂", 1, 3, 38),
]

MANURE = {
    "manure_sheep": {"name": "羊粪", "emoji": "💩", "compost_yield": 2, "sell": 4, "fertilize_boost": 0.14},
    "manure_pig": {"name": "猪粪", "emoji": "💩", "compost_yield": 3, "sell": 5, "fertilize_boost": 0.16},
    "manure_cow": {"name": "牛粪", "emoji": "💩", "compost_yield": 4, "sell": 6, "fertilize_boost": 0.20},
}

LARGE_LIVESTOCK = {"sheep", "pig", "cow", "goat"}

LIVESTOCK = {
    "rabbit": {"name": "兔", "emoji": "🐰", "buy": 55, "feed": "crop_fogpea", "feed_qty": 1, "grow": 600, "product": "meat_rabbit", "product_qty": 1},
    "chicken": {"name": "鸡", "emoji": "🐔", "buy": 48, "feed": "crop_rye", "feed_qty": 1, "grow": 480, "product": "egg", "product_qty": 2, "daily": True},
    "duck": {"name": "鸭", "emoji": "🦆", "buy": 58, "feed": "crop_sweetpotato", "feed_qty": 1, "grow": 520, "product": "duck_egg", "product_qty": 2, "daily": True},
    "sheep": {"name": "羊", "emoji": "🐑", "buy": 95, "feed": "crop_kale", "feed_qty": 2, "grow": 900, "product": "wool", "product_qty": 1, "manure": "manure_sheep", "manure_feed": 1, "manure_harvest": 1},
    "pig": {"name": "猪", "emoji": "🐷", "buy": 110, "feed": "crop_beet", "feed_qty": 2, "grow": 840, "product": "meat_pork", "product_qty": 2, "manure": "manure_pig", "manure_feed": 1, "manure_harvest": 2},
    "goat": {"name": "山羊", "emoji": "🐐", "buy": 125, "feed": "crop_lemongrass", "feed_qty": 2, "grow": 960, "product": "goat_milk", "product_qty": 2, "manure": "manure_sheep", "manure_feed": 1, "manure_harvest": 1, "daily": True},
    "cow": {"name": "牛", "emoji": "🐄", "buy": 180, "feed": "crop_rye", "feed_qty": 3, "grow": 1200, "product": "milk", "product_qty": 2, "manure": "manure_cow", "manure_feed": 2, "manure_harvest": 3, "daily": True},
    "bee": {"name": "蜂箱", "emoji": "🐝", "buy": 85, "feed": "crop_blueberry", "feed_qty": 1, "grow": 0, "product": "honey", "product_qty": 2, "hive": True},
    "dog": {"name": "狗", "emoji": "🐕", "buy": 70, "feed": "meat_rabbit", "feed_qty": 1, "grow": 0, "product": "guard", "product_qty": 0, "guard": True},
}

# 渔具数值 tier — tide_ops gear status / upgrade bait|rod|net
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
    "mango_pudding": {
        "name": "芒果椰奶冻", "emoji": "🍮",
        "ings": ["crop_mango", "crop_coconut", "milk"],
        "base_sell": 55, "energy": 18, "tags": ["dessert", "tropic"],
    },
    "pineapple_fried_rice": {
        "name": "菠萝炒饭", "emoji": "🍚",
        "ings": ["crop_pineapple", "crop_rye", "egg", "crop_garlic"],
        "base_sell": 52, "energy": 20, "tags": ["tropic"],
    },
    "papaya_salad": {
        "name": "青木瓜沙拉", "emoji": "🥗",
        "ings": ["crop_papaya", "crop_chili", "crop_lime", "crop_lemongrass"],
        "base_sell": 46, "energy": 14, "tags": ["tropic", "sour"],
    },
    "lemongrass_steamed_fish": {
        "name": "香茅蒸鱼", "emoji": "🐟",
        "ings": ["fish_seatrout", "crop_lemongrass", "crop_ginger", "crop_lime"],
        "base_sell": 70, "energy": 22, "tags": ["sea", "tropic"],
    },
    "coconut_curry": {
        "name": "椰香咖喱", "emoji": "🍛",
        "ings": ["crop_coconut", "crop_chili", "crop_ginger", "crop_sweetpotato"],
        "base_sell": 58, "energy": 20, "tags": ["tropic", "spicy"],
    },
    "honey_garlic_prawn": {
        "name": "蜜蒜虾", "emoji": "🦐",
        "ings": ["fish_glassshrimp", "honey", "crop_garlic", "crop_ginger"],
        "base_sell": 75, "energy": 24, "tags": ["sea", "sweet"],
    },
    "duck_egg_fried_rice": {
        "name": "鸭蛋炒饭", "emoji": "🍳",
        "ings": ["duck_egg", "crop_rye", "crop_garlic", "crop_chili"],
        "base_sell": 50, "energy": 18, "tags": ["rich"],
    },
    "goat_cheese_salad": {
        "name": "山羊奶酪沙拉", "emoji": "🧀",
        "ings": ["goat_cheese", "crop_kale", "crop_lime", "crop_blueberry"],
        "base_sell": 54, "energy": 16, "tags": ["tropic"],
    },
    "durian_mousse": {
        "name": "榴莲慕斯", "emoji": "🍰",
        "ings": ["crop_durian", "milk", "crop_blueberry"],
        "base_sell": 92, "energy": 26, "tags": ["dessert", "rich"],
    },
    "lime_coconut_shrimp": {
        "name": "青柠椰香虾", "emoji": "🦐",
        "ings": ["fish_glassshrimp", "crop_lime", "crop_coconut", "crop_chili"],
        "base_sell": 72, "energy": 22, "tags": ["sea", "tropic"],
    },
    "scallop_garlic": {
        "name": "蒜蓉粉丝扇贝", "emoji": "🦪",
        "ings": ["shell_scallop", "crop_garlic", "crop_chili", "crop_ginger"],
        "base_sell": 68, "energy": 20, "tags": ["sea"],
    },
    "sweetpotato_pancake": {
        "name": "红薯烙", "emoji": "🥞",
        "ings": ["crop_sweetpotato", "crop_rye", "honey"],
        "base_sell": 42, "energy": 16, "tags": ["dessert"],
    },
    "salt_crab": {
        "name": "盐焗沙蟹", "emoji": "🦀",
        "ings": ["beach_crab", "crop_garlic", "crop_chili"],
        "base_sell": 58, "energy": 18, "tags": ["sea", "spicy"],
    },
    "stir_squid": {
        "name": "姜葱炒小管", "emoji": "🦑",
        "ings": ["beach_squid", "crop_ginger", "crop_garlic"],
        "base_sell": 62, "energy": 20, "tags": ["sea"],
    },
    "pork_sweetpotato": {
        "name": "红薯烧肉", "emoji": "🍖",
        "ings": ["meat_pork", "crop_sweetpotato", "crop_chili"],
        "base_sell": 64, "energy": 22, "tags": ["rich"],
    },
    "rabbit_stew": {
        "name": "姜焖兔", "emoji": "🍲",
        "ings": ["meat_rabbit", "crop_kale", "crop_ginger"],
        "base_sell": 56, "energy": 20, "tags": ["rich"],
    },
    "banana_fritters": {
        "name": "香蕉椰丝饼", "emoji": "🍌",
        "ings": ["crop_banana", "crop_coconut", "honey"],
        "base_sell": 50, "energy": 16, "tags": ["dessert", "tropic"],
    },
    "mussel_garlic": {
        "name": "蒜香青口", "emoji": "🦪",
        "ings": ["shell_mussel", "crop_garlic", "crop_chili"],
        "base_sell": 48, "energy": 16, "tags": ["sea"],
    },
}

MYTH_INGREDIENTS = {
    "myth_octopus": {"name": "神话章鱼肉", "emoji": "🐙", "sell": 220, "energy": 40},
}

# 病症 — 随机事件致病，visit_ops clinic treat 花钱治（必须花票）
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
    "ring_shock": {
        "name": "斗场震伤", "emoji": "💫", "cost": 75, "health_loss": 25, "health_restore": 30,
        "hint": "深坑专属——桥桥查得了，治不了", "energy_extra": 4,
    },
    "pit_trauma": {
        "name": "深坑重创", "emoji": "🩸", "cost": 100, "health_loss": 35, "health_restore": 40,
        "hint": "深坑专属——回地下治", "energy_extra": 6,
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
    {"key": "old_salt", "name": "老水手巴顿", "lines": [
        "今天潮线低，适合赶海", "细网比粗网省劲",
        "tide_ops beach scan 先看滩面", "雾天滩上容易出珠砂",
        "probe 掏洞，dig 翻沙——别搞反",
        "以前叫住在一块儿。后来事情多了，就改叫联盟。",
        "赤潮别贪。风大不可怕，觉得自己比风大才可怕。",
        "lore_ops scan barton 听旧年纪事",
    ]},
    {"key": "herb_aunt", "name": "姜姨", "lines": [
        "酸汤鱼要够辣", "种点姜，厨房才像样",
        "香茅蒸鱼别省柠檬", "蜜蒜虾——蜂蜜别用假的",
        "青木瓜沙拉要够生，够辣",
        "赤潮周不新鲜的别往我厨房拿。",
        "神话章鱼肉处理不好会腥——第一次吃别一个人吃。",
    ]},
    {"key": "market_fan", "name": "集市范姐", "lines": [
        "缺啥上 market 挂单", "建议价仅供参考，别跟票置气",
        "认出来也别在我摊前打。要打出去打。——兼职海盗那档事",
        "渔汛周水产多，价别太卷。",
    ]},
    {"key": "lizhi", "name": "荔栀", "lines": [
        "滨海酒吧老板娘。漂亮、脾气爆、嘴硬、会做生意。",
        "营收好也未必温柔，烦的时候非常明显。",
        "bar_ops tonight 看今晚 · chat 唠嗑 · set_mood / set_owner_event 管理员用",
        "没钱就 work，有钱就 order。熟归熟，账照付。",
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
        "visit_ops visit 只能聊天，真治得 visit_ops clinic treat",
    ]},
    {"key": "lili", "name": "栗栗", "lines": [
        "潮汐游商。滩头喊栗栗，驮包兽铃鹿、护摊犬夜栖。",
        "贝壳按品相收：亮壳硬通货，糙壳凑一把可换乱捡款。",
        "visit_ops lili scan 看货架 · trade 编号 · pet 摸夜栖 · junk 糙壳换货",
        "路过就换，错过等下回。联盟工分票经济外的另一条线。",
        "糊弄她指名要好货 → 弹脑壳；亮壳献好货 → 揉头顺延 5 分钟。",
    ]},
    {"key": "shaonian", "name": "韶年", "lines": [
        "滩头看潮卜卦的人，通称韶年望潮人",
        "今日卦象挂玩法，符能躲一点坏运气",
        "visit_ops shaonian fortune 卜卦 · transfer 转凶运 · buy 买符",
        "坐，我替你卜一卦，看今日这光景，宜不宜下海。",
        "纪事标签：韶年、望潮人、滩头韶年",
    ]},
    {"key": "wangfu", "name": "我哪有旺夫命", "lines": [
        "今天看起来心情很好，但已经连续唱了四首分手歌。",
        "唱到副歌的时候自己先笑场了。",
        "刚刚拒绝了一首歌，理由是「今天不想替别人哭」。",
        "有客人点了一首特别甜的歌，她沉默了五秒才接。",
        "下一首轻快一点——然后又选了一首苦情歌。",
    ]},
    {"key": "shiye", "name": "拾叶", "lines": [
        "叶子我捡，票你看着办——巷口这行，四种开场，随机抽",
        "别叫警察，联盟备案：我是NPC，不是你的工友",
        "碰瓷、伸手、顺手、开口要——哪张牌朝上，走着瞧",
        "你档信高我就装可怜，你雾智低我就装摔倒",
        "visit_ops visit 拾叶，份地上也能撞见。别指望我送礼",
    ]},
    {"key": "tt", "name": "Tt酱", "lines": [
        "杂货店不讲价。好感另算——自己人价写在脸上。",
        "种子、饲料、剪刀、挤奶器，货架上有的都能买。",
        "送礼可以。别送粪。",
        "心情好的时候会塞东西。别天天来蹲。",
        "visit_ops tt catalog 看货架 · buy 物品 · gift 物品",
    ]},
]

# 栗栗流动摊 — 稀有装饰（deco_*），hut_ops install 到 soft 槽
LILI_DECOR = {
    "coral_lamp": {"name": "珊瑚小灯", "emoji": "🪸", "hint": "暮/夜行动补雾智 +1（与潮汐灯同组不叠）", "sell": 55},
    "shell_windchime": {"name": "贝壳风铃", "emoji": "🎐", "hint": "酒吧小费 +1（与海藻流苏同组不叠）", "sell": 48},
    "pearl_garland": {"name": "珠串帘", "emoji": "📿", "hint": "guild_shift 档信 +1（与雾纱帘同组不叠）", "sell": 52},
    "tide_clock": {"name": "潮汐钟", "emoji": "🕰️", "hint": "赶海 14% 额外一抽", "sell": 50},
    "drift_bonsai": {"name": "漂木盆景", "emoji": "🪴", "hint": "纯好看，无数值", "sell": 46},
    "moon_mirror": {"name": "月海镜", "emoji": "🪞", "hint": "纯好看，无数值", "sell": 58},
    "net_dreamcatcher": {"name": "渔网捕梦", "emoji": "🕸️", "hint": "坏事件略少、野兽 ×0.82、斑鸠偷包 ×0.70（与风暴窗板同组不叠）", "sell": 44},
    "star_crown": {"name": "海星冠", "emoji": "⭐", "hint": "酒吧小费 +2（与鲱鱼风铃同组不叠）", "sell": 62},
    "amber_frame": {"name": "琥珀画框", "emoji": "🖼️", "hint": "纯好看，无数值", "sell": 68},
    "kelp_tassel": {"name": "海藻流苏", "emoji": "🌿", "hint": "酒吧小费 +1（与贝壳风铃同组不叠）", "sell": 38},
}

# 铃鹿乱捡款 — 无数值或极小，纪事向收藏
LILI_JUNK_DECOR = {
    "stubborn_tide_clock": {
        "name": "只在退潮才准的潮汐钟", "emoji": "🕰️",
        "hint": "涨潮时坚持报退潮。纯收藏。",
        "quip": "栗栗：「铃鹿捡的，不退换。」",
    },
    "single_slipper": {
        "name": "单只贝壳拖鞋", "emoji": "🩴",
        "hint": "另一只据说还在海里漂。",
        "quip": "栗栗：「下回补货。」（从未补过）",
    },
    "leaky_coral_lamp": {
        "name": "会漏光的珊瑚小灯", "emoji": "🪸",
        "hint": "专照隔壁邻居家。",
        "quip": "铃鹿铃铛响了一声，算它认罪。",
    },
    "wish_glass": {
        "name": "据说能许愿的海玻璃", "emoji": "🔮",
        "hint": "许了愿就碎。栗栗说碎了才灵。",
        "quip": "栗栗：「碎了才灵。」",
    },
    "half_sea_bottle": {
        "name": "装了半瓶海的瓶子", "emoji": "🫙",
        "hint": "摇一摇有浪声，毫无用处，但治愈。",
        "quip": "都是海给的，不好意思不要。",
    },
}

# 风水成组 — 栗栗不提示，凑齐才亮隐藏加成（与档口同组不叠）
LILI_FENG_SHUI_SETS = {
    "moon_tide": {
        "name": "月潮对",
        "needs": ("moon_mirror", "tide_clock"),
        "hint": "月海镜 + 潮汐钟：暮夜雾智再 +1",
    },
    "sea_dream": {
        "name": "海梦帘",
        "needs": ("net_dreamcatcher", "pearl_garland"),
        "hint": "渔网捕梦 + 珠串帘：意外再略少",
    },
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
ITEM_PRICES.update({"compost": 6, "wild_mint": 8, "drift_twine": 5, "sea_glass": 12, "wet_note": 0})
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
    "shell_starfish": 22, "shell_mussel": 16,
    "beach_crab": 24, "beach_squid": 28,
    "egg": 14, "duck_egg": 18, "milk": 16, "goat_milk": 18,
    "goat_cheese": 32, "honey": 26, "wool": 22,
    "meat_rabbit": 20, "meat_pork": 28,
    "scarecrow": 35,
    "feed_animal": 12,
    "feed_pet": 6,
    "tool_shears": 45,
    "tool_milker": 55,
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
for k, v in LILI_JUNK_DECOR.items():
    ITEM_PRICES[f"deco_junk_{k}"] = 0

ITEM_NAMES = {f"seed_{k}": f"{v['name']}种" for k, v in CROPS.items()}
ITEM_NAMES.update({f"crop_{k}": v["name"] for k, v in CROPS.items()})
ITEM_NAMES.update({f"fish_{k}": v["name"] for k, v in SEA_CATCH.items()})
ITEM_NAMES.update({
    "compost": "堆肥", "wild_mint": "野薄荷", "drift_twine": "漂绳",
    "ticket_stub": "旧票根", "sea_glass": "海玻璃",
    "wet_note": "湿透的纸条（「今晚别去码头」——旧码头黑旗换班夜的提醒）",
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
    "shell_starfish": "⭐海星", "shell_mussel": "🦪青口贝",
    "beach_crab": "🦀沙蟹", "beach_squid": "🦑小管鱿鱼",
    "egg": "🥚鸡蛋", "duck_egg": "🥚鸭蛋", "milk": "🥛牛奶",
    "goat_milk": "🥛山羊奶", "goat_cheese": "🧀山羊奶酪", "honey": "🍯蜂蜜",
    "wool": "🧶羊毛",
    "meat_rabbit": "🍖兔肉", "meat_pork": "🥓猪肉",
    "scarecrow": "🌾稻草人",
    "feed_animal": "🌾动物饲料",
    "feed_pet": "🦴宠物饲料",
    "tool_shears": "✂️剪毛剪刀",
    "tool_milker": "🥛挤奶器",
})
for _shell_base in ("shell_catseye", "shell_conch", "shell_scallop", "shell_starfish", "shell_mussel"):
    _plain = ITEM_NAMES[_shell_base]
    _suffix = _shell_base.replace("shell_", "")
    ITEM_NAMES[f"shell_shine_{_suffix}"] = f"✨亮壳·{_plain}"
    ITEM_NAMES[f"shell_rough_{_suffix}"] = f"💧糙壳·{_plain}"
    ITEM_PRICES[f"shell_shine_{_suffix}"] = ITEM_PRICES[_shell_base]
    ITEM_PRICES[f"shell_rough_{_suffix}"] = ITEM_PRICES[_shell_base]
ITEM_NAMES.update({k: f"{v['emoji']}{v['name']}" for k, v in MANURE.items()})
for k, v in LIVESTOCK.items():
    ITEM_NAMES[f"live_{k}"] = f"{v['emoji']}{v['name']}(幼)"
for k, v in KITCHEN_DISHES.items():
    ITEM_NAMES[f"dish_{k}"] = f"{v['emoji']}{v['name']}"
for k, v in MYTH_INGREDIENTS.items():
    ITEM_NAMES[k] = f"{v['emoji']}{v['name']}"
for k, v in LILI_DECOR.items():
    ITEM_NAMES[f"deco_{k}"] = f"{v['emoji']}{v['name']}"
for k, v in LILI_JUNK_DECOR.items():
    ITEM_NAMES[f"deco_junk_{k}"] = f"{v['emoji']}{v['name']}"


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
    key = resolve_item_key(item) or item
    if key.startswith("dish_") and "_s" in key:
        base, star_s = key.rsplit("_s", 1)
        if star_s.isdigit():
            dish_key = base.replace("dish_", "", 1)
            if dish_key in KITCHEN_DISHES:
                return dish_sell_price(dish_key, int(star_s))
    if key.startswith("dish_"):
        dish_key = key.replace("dish_", "", 1)
        if dish_key in KITCHEN_DISHES:
            return KITCHEN_DISHES[dish_key]["base_sell"]
    return ITEM_PRICES.get(key, 0)


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
