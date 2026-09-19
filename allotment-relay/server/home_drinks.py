"""自宅泡饮 — 材料→drink_* 物品，可带去酒吧减价。"""
from __future__ import annotations

from . import db, energy
from .catalog import ITEM_NAMES, resolve_item_key, unknown_item_message

# drink_item -> (bar 酒 key, 减价票)
BAR_BRING: dict[str, tuple[str, int]] = {
    "drink_mist_pea_tea": ("dusk_wheat", 6),
    "drink_brine_sour": ("plum_soda", 5),
    "drink_ginger_highball": ("lighthouse_gin", 8),
    "drink_fog_port": ("rum", 7),
    "drink_sea_lime": ("yuzu_sparkle", 6),
    "drink_peat_tea": ("dusk_wheat", 5),
    "drink_pomelo_tea": ("yuzu_sparkle", 6),
    "drink_lemon_water": ("plum_soda", 4),
    "drink_coffee": ("rum", 5),
    "drink_cocoa": ("dusk_wheat", 5),
    "drink_mint_tea": ("dusk_wheat", 4),
    "drink_ginger_tea": ("lighthouse_gin", 5),
    "drink_fruit_tea": ("yuzu_sparkle", 5),
    "drink_coconut_milk": ("rum", 6),
    "drink_soy_milk": ("dusk_wheat", 4),
    "drink_apple_juice": ("plum_soda", 4),
    "drink_grape_juice": ("yuzu_sparkle", 5),
    "drink_pomegranate_juice": ("rum", 5),
    "drink_honey_water": ("dusk_wheat", 4),
    "drink_pear_soup": ("plum_soda", 5),
}

RECIPES: dict[str, dict] = {
    "mist_pea_tea": {
        "label": "雾豆花青茶",
        "ings": [("crop_fogpea", 1), ("wild_mint", 1)],
        "out": "drink_mist_pea_tea",
        "energy": 6,
    },
    "brine_sour": {
        "label": "卤边酸汽",
        "ings": [("quarry_salt", 1), ("crop_beet", 1)],
        "out": "drink_brine_sour",
        "energy": 5,
    },
    "ginger_highball": {
        "label": "潮姜嗨棒",
        "ings": [("crop_tide_ginger", 1), ("proc_rice_wine", 1)],
        "out": "drink_ginger_highball",
        "energy": 8,
    },
    "fog_port": {
        "label": "雾港热朗姆",
        "ings": [("proc_black_salt", 1), ("crop_fogpea", 1), ("proc_syrup", 1)],
        "out": "drink_fog_port",
        "energy": 10,
    },
    "sea_lime": {
        "label": "海涯青柠汽",
        "ings": [("crop_lime", 2), ("quarry_salt", 1)],
        "out": "drink_sea_lime",
        "energy": 5,
    },
    "peat_tea": {
        "label": "岸灶麦茶",
        "ings": [("crop_beet", 1), ("proc_tea_leaf", 1)],
        "out": "drink_peat_tea",
        "energy": 6,
    },
    "pomelo_tea": {
        "label": "柚子茶",
        "ings": [("crop_pomelo", 1), ("proc_tea_leaf", 1)],
        "out": "drink_pomelo_tea",
        "energy": 6,
    },
    "lemon_water": {
        "label": "柠檬水",
        "ings": [("crop_lemon", 1), ("quarry_salt", 1)],
        "out": "drink_lemon_water",
        "energy": 4,
    },
    "coffee_cup": {
        "label": "手冲咖啡",
        "ings": [("crop_coffee", 1), ("proc_syrup", 1)],
        "out": "drink_coffee",
        "energy": 8,
    },
    "cocoa_cup": {
        "label": "热可可",
        "ings": [("crop_cacao", 1), ("milk", 1)],
        "out": "drink_cocoa",
        "energy": 7,
    },
}


def _resolve_key(token: str) -> str:
    t = token.strip().lower().replace(" ", "_")
    if t in RECIPES:
        return t
    for k, meta in RECIPES.items():
        if meta["label"] == token or meta["out"] == t:
            return k
    raise ValueError(f"未知泡饮 {token}。kitchen_ops 泡 list")


async def list_text() -> str:
    lines = ["自宅泡饮（kitchen_ops 泡 名 · 带去 bar_ops order 对应酒可减价）："]
    for key, meta in RECIPES.items():
        need = " + ".join(f"{ITEM_NAMES.get(i, i)}×{q}" for i, q in meta["ings"])
        out = ITEM_NAMES.get(meta["out"], meta["out"])
        bar = BAR_BRING.get(meta["out"])
        bar_bit = f" · 酒吧兑 {bar[1]}票 off" if bar else ""
        lines.append(f"  {meta['label']} ({key}) — {need} → {out} · -{meta['energy']}精力{bar_bit}")
    return "\n".join(lines)


async def brew(conn, steward: dict, recipe_key: str) -> str:
    meta = RECIPES[recipe_key]
    for item, qty in meta["ings"]:
        if not await db.take_item(conn, steward["id"], item, qty):
            raise ValueError(f"缺 {ITEM_NAMES.get(item, item)}×{qty}")
    await energy.spend(conn, steward["id"], meta["energy"], action="泡饮")
    await db.add_item(conn, steward["id"], meta["out"], 1)
    out_nm = ITEM_NAMES.get(meta["out"], meta["out"])
    bar = BAR_BRING.get(meta["out"])
    tip = f" 带去酒吧 order 可减 {bar[1]} 票。" if bar else ""
    return f"泡好 {meta['label']} → {out_nm}×1（-{meta['energy']} 精力）。{tip}"


async def dispatch(steward: dict, parts: list[str]) -> str:
    if not parts or parts[0].lower() in ("list", "列表", "help"):
        return await list_text()
    key = _resolve_key(" ".join(parts))
    async with db.connect() as conn:
        msg = await brew(conn, steward, key)
        from . import island_collections as coll_mod
        await coll_mod.sync_unlocks(conn, steward["id"])
        await conn.commit()
    return msg


def bar_discount_for_drink_item(item_key: str) -> tuple[str, int] | None:
    return BAR_BRING.get(item_key)
