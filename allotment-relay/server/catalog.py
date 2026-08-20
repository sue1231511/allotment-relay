# 份地作物 — 偏北欧/沿海/湿地，与常见农场游戏区分
CROPS = {
    "kale": {"name": "羽衣甘蓝", "emoji": "🥬", "seed_price": 7, "sell": 16, "grow": 280, "tags": ["leaf"]},
    "beet": {"name": "甜菜", "emoji": "🫘", "seed_price": 9, "sell": 21, "grow": 340, "tags": ["root"]},
    "rye": {"name": "黑麦", "emoji": "🌾", "seed_price": 8, "sell": 19, "grow": 400, "tags": ["grain"]},
    "bramble": {"name": "荆棘莓", "emoji": "🫐", "seed_price": 14, "sell": 32, "grow": 360, "tags": ["berry"]},
    "kelp": {"name": "浅海藻", "emoji": "🌿", "seed_price": 11, "sell": 24, "grow": 300, "tags": ["sea"]},
    "fogpea": {"name": "雾豌豆", "emoji": "🫛", "seed_price": 10, "sell": 23, "grow": 320, "tags": ["legume"]},
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

ITEM_PRICES = {f"seed_{k}": v["seed_price"] for k, v in CROPS.items()}
ITEM_PRICES.update({f"crop_{k}": v["sell"] for k, v in CROPS.items()})
ITEM_PRICES.update({f"fish_{k}": v["sell"] for k, v in SEA_CATCH.items()})
ITEM_PRICES.update({"compost": 6, "wild_mint": 8, "drift_twine": 5, "sea_glass": 12})
ITEM_PRICES.update({f"meal_{i}": r["sell"] for i, r in enumerate(HEARTH_RECIPES.values(), 1)})

ITEM_NAMES = {f"seed_{k}": f"{v['name']}种" for k, v in CROPS.items()}
ITEM_NAMES.update({f"crop_{k}": v["name"] for k, v in CROPS.items()})
ITEM_NAMES.update({f"fish_{k}": v["name"] for k, v in SEA_CATCH.items()})
ITEM_NAMES.update({
    "compost": "堆肥", "wild_mint": "野薄荷", "drift_twine": "漂绳",
    "ticket_stub": "旧票根", "sea_glass": "海玻璃",
})
for i, r in enumerate(HEARTH_RECIPES.values(), 1):
    ITEM_NAMES[f"meal_{i}"] = r["name"]


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
