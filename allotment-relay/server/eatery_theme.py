"""小馆菜单主题 — 按上架菜 tag 推断招牌文案（AI board / 人类围观）。"""
from __future__ import annotations

from collections import Counter

from .catalog import KITCHEN_DISHES


def _dish_key_from_item(item: str) -> str | None:
    if not item.startswith("dish_"):
        return None
    raw = item.replace("dish_", "", 1)
    if "_s" in raw:
        base, star = raw.rsplit("_s", 1)
        if star.isdigit():
            return base
    return raw


def _tags_for_item(item: str) -> set[str]:
    dk = _dish_key_from_item(item)
    if dk and dk in KITCHEN_DISHES:
        return set(KITCHEN_DISHES[dk].get("tags") or ())
    if item.startswith("meal_"):
        return {"home"}
    return set()


def _tag_counts(items: list[str]) -> Counter[str]:
    c: Counter[str] = Counter()
    for it in items:
        for t in _tags_for_item(it):
            c[t] += 1
    return c


def menu_theme_line(items: list[str]) -> str:
    """一行主题，空菜单或无法归类时返回空串。"""
    if not items:
        return ""
    counts = _tag_counts(items)
    sea = int(counts.get("sea", 0))
    spec = int(counts.get("special", 0))
    spicy = int(counts.get("spicy", 0))
    sweet = int(counts.get("dessert", 0) + counts.get("sweet", 0))
    parts: list[str] = []
    if sea >= 3:
        parts.append("海味三连档")
    elif sea >= 2:
        parts.append("海味小馆")
    if spec >= 2:
        parts.append("雾潮私厨")
    elif spec == 1:
        parts.append("含特殊料理")
    if spicy >= 2:
        parts.append("烈火蒜椒")
    if sweet >= 2:
        parts.append("甜口窗位")
    if not parts and len(items) >= 3:
        parts.append("家常小馆")
    return " · ".join(parts)


def stock_combo_hint(menu_items: list[str], new_item: str) -> str | None:
    """上架后可选提示：凑齐主题或跨 craft 招牌。"""
    items = list(menu_items)
    if new_item not in items:
        items.append(new_item)
    keys = {_dish_key_from_item(i) for i in items}
    keys.discard(None)
    named = {k for k in keys if k}
    sea_special = {"tide_ginger_crab", "brine_clam_pot", "black_salt_fish", "brine_kelp_pot"}
    if len(named & sea_special) >= 2:
        return "招牌凑齐「潮卤海味」线，堂食可写进店名旁。"
    theme = menu_theme_line(items)
    if theme and len(items) >= 2:
        return f"菜单气质：{theme}（board 会显示）"
    return None


def board_suffix(items: list[str]) -> str:
    line = menu_theme_line(items)
    return f" — {line}" if line else ""


def _menu_dish_keys(items: list[str]) -> set[str]:
    out: set[str] = set()
    for it in items:
        dk = _dish_key_from_item(it)
        if dk:
            out.add(dk)
    return out


SET_MENUS: tuple[dict, ...] = (
    {
        "name": "潮卤海味双拼",
        "keys": frozenset({"tide_ginger_crab", "brine_clam_pot"}),
        "hint": "两菜分别 stock，价自定；堂食可连点。",
    },
    {
        "name": "雾潮三式",
        "keys": frozenset({"black_salt_fish", "fog_mushroom_soup", "lantern_sashimi"}),
        "hint": "三道特殊菜齐柜，适合写进招牌。",
    },
    {
        "name": "烈火海味",
        "keys": frozenset({"sichuan_kelp_fish", "chop_head"}),
        "hint": "椒香+鱼头，辣味爱好者会找。",
    },
)


def set_menu_lines(items: list[str]) -> list[str]:
    """套餐建议（不绑定价，只提示齐不齐）。"""
    keys = _menu_dish_keys(items)
    if not keys:
        return []
    lines: list[str] = []
    for spec in SET_MENUS:
        need = spec["keys"]
        if need <= keys:
            lines.append(f"  ✅ 套餐·{spec['name']} — 已齐。{spec['hint']}")
            continue
        overlap = keys & need
        if overlap:
            miss = need - keys
            labels = [
                KITCHEN_DISHES[k]["name"]
                for k in sorted(miss)
                if k in KITCHEN_DISHES
            ]
            if labels:
                lines.append(
                    f"  … 套餐·{spec['name']} 还差：{'、'.join(labels)}"
                )
    return lines


def set_menu_report(items: list[str]) -> str:
    lines = ["小馆套餐建议（价仍 shop stock 自定，不自动捆绑扣票）："]
    themed = set_menu_lines(items)
    if themed:
        lines.extend(themed)
    else:
        lines.append("  还没凑齐推荐套餐。先 stock 定点熟菜（dish_）。")
    theme = menu_theme_line(items)
    if theme:
        lines.append(f"当前气质：{theme}")
    return "\n".join(lines)
