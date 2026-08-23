"""自由组合做饭 — 材料扔进锅，按搭配出星级；垃圾菜几乎没价。"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from typing import Any

from .catalog import (
    ITEM_PRICES,
    KITCHEN_DISHES,
    mix_energy,
    mix_item_key,
    mix_sell_price,
    mix_title,
    register_mix_item,
)

SEASONING = {
    "crop_garlic", "crop_chili", "crop_ginger", "crop_lemongrass",
    "crop_lime", "wild_mint", "pickles",
}
FOOD_SHELLS = {"shell_scallop", "shell_mussel"}
PROTEIN_EXTRAS = {
    "beach_crab", "beach_squid", "myth_octopus", "meat_rabbit", "meat_pork",
}
RICH = {"egg", "duck_egg", "milk", "honey", "goat_cheese"}
REFUSE_PREFIX = ("live_", "tool_", "deco_", "fit_", "dish_", "meal_")
JUNK_PREFIX = ("manure_", "shell_rough_")
JUNK_EXACT = {"compost", "wet_note", "drift_twine"}

MIX_COMMENTS = {
    "j": [
        "姜姨看了一眼：「这也能上桌？」",
        "灶台：我尽力了，别问我发生了什么",
        "闻着像事故。建议自吃，别拿去卖。",
    ],
    "o": [
        "能吃。档口便饭。",
        "姜姨：填肚子可以，别对外说是我教的",
        "星不多，但比生啃强。",
    ],
    "g": [
        "姜姨点头：够味",
        "灶台：这锅有想法",
        "搭配站得住，可以 vend。",
    ],
    "x": [
        "灶台：这锅有灵魂",
        "姜姨难得没损你。",
        "碰巧神了。按星级卖。",
    ],
}


@dataclass
class MixResult:
    grade: str
    tier: int
    stars: int
    sig: str
    item: str
    sell: int
    energy: int
    display: str
    comment: str


def classify(item: str) -> str:
    if item.startswith(REFUSE_PREFIX):
        return "refuse"
    if item.startswith("seed_"):
        return "junk"
    if item.startswith(JUNK_PREFIX) or item in JUNK_EXACT:
        return "junk"
    if item.startswith("shell_") and item not in FOOD_SHELLS:
        return "junk"
    if item.startswith("ut_"):
        return "junk"
    if item == "myth_octopus":
        return "myth"
    if item.startswith("fish_") or item.startswith("meat_") or item in PROTEIN_EXTRAS or item in FOOD_SHELLS:
        return "protein"
    if item in SEASONING:
        return "season"
    if item.startswith("crop_"):
        return "produce"
    if item in RICH:
        return "rich"
    return "odd"


def match_named_recipe(ings: list[str]) -> str | None:
    bag = sorted(ings)
    for key, meta in KITCHEN_DISHES.items():
        if sorted(meta["ings"]) == bag:
            return key
    return None


def resolve_dish_key(token: str) -> str | None:
    raw = (token or "").strip()
    if not raw:
        return None
    key = raw.lower().replace(" ", "_")
    if key in KITCHEN_DISHES:
        return key
    for k, meta in KITCHEN_DISHES.items():
        if meta.get("name") == raw:
            return k
    return None


def _sig(ings: list[str]) -> str:
    blob = "|".join(sorted(ings))
    return hashlib.sha1(blob.encode()).hexdigest()[:8]


def score_mix(ings: list[str], steward: dict[str, Any] | None = None) -> MixResult:
    if len(ings) < 2:
        raise ValueError("自由组合至少 2 样材料")
    if len(ings) > 5:
        raise ValueError("一次最多 5 样，灶台就那么大")
    kinds = [classify(i) for i in ings]
    if "refuse" in kinds:
        raise ValueError("活物、工具、装饰、熟菜不能下锅")
    n_junk = kinds.count("junk") + kinds.count("odd")
    n_prot = kinds.count("protein") + kinds.count("myth")
    n_prod = kinds.count("produce")
    n_sea = kinds.count("season")
    n_rich = kinds.count("rich")
    n_myth = kinds.count("myth")
    food_value = sum(
        ITEM_PRICES.get(i, 1)
        for i, k in zip(ings, kinds)
        if k not in ("junk", "odd", "refuse")
    )
    if n_junk:
        grade = "j"
        stars = 1
        if random.random() < 0.2:
            stars = 2
        # 乱炖也按全部材料身价定档：mix_sell_price 里 j 档按 tier 兜底 45%，
        # 好料错搭不至于两三票贱卖（粪/泥壳 tier 低，照旧不值钱）
        tier = min(9, sum(ITEM_PRICES.get(i, 1) for i in ings) // 20)
    elif n_myth:
        grade = "x"
        stars = 4
        tier = min(9, food_value // 20)
    elif n_prot and n_sea:
        grade = "x" if food_value >= 55 else "g"
        stars = 4 if food_value >= 55 else 3
        tier = min(9, food_value // 20)
    elif n_prot and (n_prod or n_rich):
        grade = "g"
        stars = 3
        tier = min(9, food_value // 20)
    elif n_prod >= 2 and n_sea:
        grade = "g"
        stars = 3
        tier = min(9, food_value // 20)
    elif n_prot or n_prod >= 2 or (n_prod and n_rich):
        grade = "o"
        stars = 2
        tier = min(9, food_value // 20)
    else:
        grade = "j"
        stars = 1
        tier = min(9, sum(ITEM_PRICES.get(i, 1) for i in ings) // 20)

    if steward and steward.get("hut_built") and steward.get("hut_level", 0) >= 2 and grade != "j":
        stars += 1
    if grade != "j" and random.random() < 0.08:
        stars += 1
    if n_myth and grade != "j":
        stars = min(5, stars + 1)
    if grade == "j":
        stars = min(2, max(1, stars))
    else:
        stars = min(5, max(1, stars))

    sig = _sig(ings)
    item = mix_item_key(grade, tier, sig, stars)
    register_mix_item(item)
    emoji, name = mix_title(grade, sig)
    sell = mix_sell_price(grade, tier, stars)
    energy = mix_energy(grade, stars)
    comment = random.choice(MIX_COMMENTS[grade])
    return MixResult(
        grade=grade,
        tier=tier,
        stars=stars,
        sig=sig,
        item=item,
        sell=sell,
        energy=energy,
        display=f"{emoji}{name}{'★' * stars}",
        comment=comment,
    )
