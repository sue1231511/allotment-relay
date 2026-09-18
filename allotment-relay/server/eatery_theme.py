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
