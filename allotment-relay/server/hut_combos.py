"""家具组合 — 第三批：套装加成（在单件装件之上）。"""
from __future__ import annotations

from .hut import HutBonus

# bare fitting keys（与 install 后 normalize 一致）
COMBO_SETS: dict[str, dict] = {
    "kitchen_line": {
        "slug": "kitchen_line",
        "name": "灶链",
        "needs": ("brick_hearth", "fridge", "cabinet"),
        "hint": "灶台+冰箱+潮柜：做饭雾智再+3",
    },
    "preserve_row": {
        "slug": "preserve_row",
        "name": "咸鲜排",
        "needs": ("pickle_crock", "fish_rack", "compost_bin"),
        "hint": "腌坛+晾架+堆肥桶：小屋意外再略少",
    },
    "rest_nest": {
        "slug": "rest_nest",
        "name": "眠巢",
        "needs": ("plank_floor", "rain_gutter", "glass_window"),
        "hint": "地板+雨槽+玻璃窗：屋顶磨损略慢（睡时少耗）",
    },
}


def _has_all(keys: set[str], needs: tuple[str, ...]) -> bool:
    return all(n in keys for n in needs)


def apply_combos(b: HutBonus) -> list[str]:
    """Mutate HutBonus; return active combo labels."""
    active: list[str] = []
    for spec in COMBO_SETS.values():
        needs = tuple(spec.get("needs") or ())
        if not _has_all(b.keys, needs):
            continue
        active.append(str(spec.get("name") or ""))
        slug = str(spec.get("slug") or "")
        if slug == "kitchen_line":
            b.brew_mist += 3
        elif slug == "preserve_row":
            b.good_share *= 1.10
            b.event_mult *= 0.95
        elif slug == "rest_nest":
            b.gale_event *= 0.88
            b.event_mult *= 0.96
    return active


def combo_summary(keys: set[str]) -> str | None:
    labels = []
    for spec in COMBO_SETS.values():
        if _has_all(keys, tuple(spec.get("needs") or ())):
            labels.append(f"{spec['name']}（{spec.get('hint', '')}）")
    if not labels:
        return None
    return "套装：" + " · ".join(labels)
