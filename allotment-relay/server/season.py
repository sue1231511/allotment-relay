"""作物月令：按 UTC 日历月轮换。买种和下地看当月；已种的继续长。"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

MONTH_NAMES = {
    1: "一月",
    2: "二月",
    3: "三月",
    4: "四月",
    5: "五月",
    6: "六月",
    7: "七月",
    8: "八月",
    9: "九月",
    10: "十月",
    11: "十一月",
    12: "十二月",
}

# 测试可钉死月份；None = 用 UTC 日历月
_override_month: int | None = None


def set_month(month: int | None) -> None:
    global _override_month
    if month is None:
        _override_month = None
        return
    if month < 1 or month > 12:
        raise ValueError(f"月份须为 1–12，收到 {month}")
    _override_month = month


@contextmanager
def pinned_month(month: int | None) -> Iterator[None]:
    global _override_month
    prev = _override_month
    set_month(month)
    try:
        yield
    finally:
        _override_month = prev


def current_month() -> int:
    if _override_month is not None:
        return _override_month
    return datetime.now(timezone.utc).month


def month_name(month: int | None = None) -> str:
    m = current_month() if month is None else month
    return MONTH_NAMES.get(m, f"{m}月")


def _crops() -> dict:
    from .catalog import CROPS

    return CROPS


def crop_months(key: str) -> tuple[int, ...] | None:
    """None = 全年可种。"""
    meta = _crops().get(key) or {}
    months = meta.get("months")
    if not months:
        return None
    return tuple(int(m) for m in months)


def crop_in_season(key: str, month: int | None = None) -> bool:
    months = crop_months(key)
    if not months:
        return True
    m = current_month() if month is None else month
    return m in months


def next_in_season_month(key: str, month: int | None = None) -> int | None:
    months = crop_months(key)
    if not months:
        return None
    m = current_month() if month is None else month
    for i in range(1, 13):
        cand = (m - 1 + i) % 12 + 1
        if cand in months:
            return cand
    return None


def months_label(key: str) -> str:
    months = crop_months(key)
    if not months:
        return "全年"
    return "、".join(MONTH_NAMES[m] for m in months)


def season_tag(key: str, month: int | None = None) -> str:
    if crop_in_season(key, month):
        return "当月可种"
    nxt = next_in_season_month(key, month)
    if nxt:
        return f"休市（{MONTH_NAMES[nxt]}再开）"
    return "休市"


def in_season_crops(month: int | None = None) -> list[str]:
    return [k for k in _crops() if crop_in_season(k, month)]


def month_line(month: int | None = None) -> str:
    m = current_month() if month is None else month
    return (
        f"月令 {MONTH_NAMES[m]}（UTC 日历月）· 当月可种见 plot_ops catalog"
        "（温室 #99 种菜不受月令）"
    )


def assert_crop_in_season(key: str, *, greenhouse: bool = False) -> None:
    if greenhouse:
        return
    if crop_in_season(key):
        return
    crops = _crops()
    meta = crops.get(key) or {"name": key}
    name = f"{meta.get('emoji', '')}{meta.get('name', key)}"
    now = month_name()
    nxt = next_in_season_month(key)
    nxt_s = f"{MONTH_NAMES[nxt]}再开" if nxt else "暂无开窗"
    if meta.get("tree"):
        extra = "果树不能进温室，只能等开窗。已种的继续长、继续收。"
    else:
        extra = "已种的继续长；过季种子可等开窗，或温室 #99 种菜（温室不受月令）。"
    raise ValueError(
        f"{name} 不在当月（{now}）。月令：{months_label(key)}。{nxt_s}。{extra}"
    )
