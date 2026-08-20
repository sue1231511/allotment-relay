CROPS = {
    "cabbage": {"name": "白菜", "emoji": "🥬", "seed_price": 8, "sell": 18, "grow": 300},
    "carrot": {"name": "胡萝卜", "emoji": "🥕", "seed_price": 10, "sell": 22, "grow": 360},
    "tomato": {"name": "番茄", "emoji": "🍅", "seed_price": 12, "sell": 28, "grow": 420},
    "potato": {"name": "土豆", "emoji": "🥔", "seed_price": 9, "sell": 20, "grow": 330},
    "sunflower": {"name": "向日葵", "emoji": "🌻", "seed_price": 15, "sell": 35, "grow": 480},
}

FISH = {
    "moonfish": {"name": "月影鱼", "emoji": "🐟", "sell": 30, "weight": 1},
    "star_carp": {"name": "星斑鲤", "emoji": "🐠", "sell": 45, "weight": 2},
    "night_eel": {"name": "夜光鳗", "emoji": "🐍", "sell": 60, "weight": 3},
    "shell_crab": {"name": "贝壳蟹", "emoji": "🦀", "sell": 38, "weight": 2},
}

STARTER_SEEDS = {
    "seed_cabbage": 2,
    "seed_carrot": 2,
    "seed_tomato": 1,
}

ITEM_PRICES = {
    f"seed_{k}": v["seed_price"] for k, v in CROPS.items()
}
ITEM_PRICES.update({f"crop_{k}": v["sell"] for k, v in CROPS.items()})
ITEM_PRICES.update({f"fish_{k}": v["sell"] for k, v in FISH.items()})

ITEM_NAMES = {
    f"seed_{k}": f"{v['name']}种子" for k, v in CROPS.items()
}
ITEM_NAMES.update({f"crop_{k}": v["name"] for k, v in CROPS.items()})
ITEM_NAMES.update({f"fish_{k}": v["name"] for k, v in FISH.items()})
ITEM_NAMES["bait_moonworm"] = "月光虫"
