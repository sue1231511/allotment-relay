"""潮下炼制 — 井底材料与崖盐闭环（§井下经济样板）。"""
from __future__ import annotations

from . import db, energy
from .catalog import ITEM_NAMES, resolve_item_key

RECIPES: dict[str, dict] = {
    "brine_crystal": {
        "label": "焖晶",
        "emoji": "💎",
        "ings": [("ut_pit_silt", 2), ("quarry_salt", 1)],
        "out": ("ut_brine_crystal", 1),
        "energy": 10,
        "hint": "斗场淤泥 + 崖上盐晶 → 卤晶（可卖或留作深潜货）",
    },
    "surface_black_salt": {
        "label": "岸黑盐",
        "emoji": "🧂",
        "ings": [("ut_black_salt", 2), ("quarry_salt", 1)],
        "out": ("proc_black_salt", 1),
        "energy": 8,
        "hint": "潮下黑盐 + 崖盐 → 岸上厨房用的黑盐（黑盐炖鱼）",
    },
    "brine_nails": {
        "label": "卤浸钉",
        "emoji": "🔩",
        "ings": [("ut_brine_crystal", 1), ("craft_copper_nails", 2)],
        "out": ("craft_copper_nails", 4),
        "energy": 9,
        "hint": "井底卤晶 + 岸工坊铜钉 → 多两枚铜钉（崖↔潮下↔工坊闭环）",
    },
}


def _resolve(token: str) -> str:
    key = resolve_item_key(token)
    if key:
        return key
    low = token.strip().lower().replace(" ", "_")
    if low in RECIPES:
        return low
    for rk, meta in RECIPES.items():
        if meta["label"] == token or rk == low:
            return rk
    raise ValueError(f"不认识炼制项 {token}。undertide_ops 炼 list")


async def list_text() -> str:
    lines = ["潮下炼制（行囊扣料，在井口/后室都能炼）："]
    for key, meta in RECIPES.items():
        need = " + ".join(
            f"{ITEM_NAMES.get(i, i)}×{q}" for i, q in meta["ings"]
        )
        out = ITEM_NAMES.get(meta["out"][0], meta["out"][0])
        lines.append(
            f"  {meta['emoji']}{meta['label']} ({key}) — {need} → {out} · -{meta['energy']}精力"
        )
        lines.append(f"    {meta['hint']}")
    lines.append("例：undertide_ops 炼 brine_crystal · 炼 岸黑盐")
    return "\n".join(lines)


async def refine(conn, steward: dict, recipe_key: str) -> str:
    if recipe_key not in RECIPES:
        raise ValueError(f"没有这条炼制线。undertide_ops 炼 list")
    meta = RECIPES[recipe_key]
    for item, qty in meta["ings"]:
        if not await db.take_item(conn, steward["id"], item, qty):
            need = ITEM_NAMES.get(item, item)
            raise ValueError(f"缺 {need}×{qty}。斗场淤泥 undertide pit；崖盐 quarry_ops 挖+洗")
    await energy.spend(conn, steward["id"], meta["energy"], action="潮下炼制")
    out_item, out_qty = meta["out"]
    await db.add_item(conn, steward["id"], out_item, out_qty)
    out_name = ITEM_NAMES.get(out_item, out_item)
    await db.add_chronicle(
        "undertide",
        f"{steward['name']} 炼成 {out_name}×{out_qty}",
        steward["id"],
        conn=conn,
    )
    return (
        f"炼成 {meta['emoji']}{meta['label']} → {out_name}×{out_qty}"
        f"（-{meta['energy']} 精力）。"
        + ("可 kitchen 黑盐炖鱼。" if out_item == "proc_black_salt" else "可 undertide sell 或留作深货。")
    )


async def dispatch(conn, steward: dict, parts: list[str]) -> str:
    if not parts or parts[0].lower() in ("list", "列表", "help"):
        return await list_text()
    key = _resolve(" ".join(parts))
    return await refine(conn, steward, key)
