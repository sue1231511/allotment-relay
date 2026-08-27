"""作物季节：现实一周换一季（春→夏→秋→冬循环）。

买种和露天/果园 sow 看当季；温室种菜种树都不受季节。已种的继续长。
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Iterator

_CST = timezone(timedelta(hours=8))

SEASONS = ("春", "夏", "秋", "冬")
SEASON_ALIASES = {
    "春": "春",
    "spring": "春",
    "夏": "夏",
    "summer": "夏",
    "秋": "秋",
    "autumn": "秋",
    "fall": "秋",
    "冬": "冬",
    "winter": "冬",
}

# 2026-01-05 周一 00:00 东八区起算第一周为春，之后每 7 天换一季。
SEASON_EPOCH = datetime(2026, 1, 5, tzinfo=_CST)

# 测试可钉死季节；None = 按纪元周循环
_override_season: str | None = None


def normalize_season(token: str | int | None) -> str | None:
    if token is None:
        return None
    if isinstance(token, int):
        if 1 <= token <= 4:
            return SEASONS[token - 1]
        raise ValueError(f"季节序号须为 1–4，收到 {token}")
    raw = str(token).strip().lower()
    if raw.isdigit():
        return normalize_season(int(raw))
    hit = SEASON_ALIASES.get(raw) or SEASON_ALIASES.get(str(token).strip())
    if not hit:
        raise ValueError(f"季节须为 春/夏/秋/冬，收到 {token!r}")
    return hit


def set_season(season: str | int | None) -> None:
    global _override_season
    _override_season = None if season is None else normalize_season(season)


@contextmanager
def pinned_season(season: str | int | None) -> Iterator[None]:
    global _override_season
    prev = _override_season
    set_season(season)
    try:
        yield
    finally:
        _override_season = prev


def month_to_season(month: int) -> str:
    if month in (12, 1, 2):
        return "冬"
    if month in (3, 4, 5):
        return "春"
    if month in (6, 7, 8):
        return "夏"
    if month in (9, 10, 11):
        return "秋"
    raise ValueError(f"月份须为 1–12，收到 {month}")


@contextmanager
def pinned_month(month: int | None) -> Iterator[None]:
    """兼容旧测试：日历月映射到春夏秋冬。新测试请用 pinned_season。"""
    if month is None:
        with pinned_season(None):
            yield
        return
    with pinned_season(month_to_season(int(month))):
        yield


def _as_cst(at: datetime | None) -> datetime:
    if at is None:
        from . import db
        return db.cst_dt()
    if at.tzinfo is None:
        return at.replace(tzinfo=_CST)
    return at.astimezone(_CST)


def _week_index(at: datetime | None = None) -> int:
    now = _as_cst(at)
    days = (now - SEASON_EPOCH).days
    return max(0, days) // 7


def current_season(at: datetime | None = None) -> str:
    if _override_season is not None:
        return _override_season
    return SEASONS[_week_index(at) % 4]


def current_season_index(at: datetime | None = None) -> int:
    """1=春 … 4=冬。公开统计兼容旧 month 字段。"""
    return SEASONS.index(current_season(at)) + 1


def season_remaining_days(at: datetime | None = None) -> int:
    """本季还剩几天（含今天），1–7。钉季节时返回 7。"""
    if _override_season is not None:
        return 7
    now = _as_cst(at)
    days = max(0, (now - SEASON_EPOCH).days)
    return 7 - (days % 7)


def season_name(season: str | None = None) -> str:
    return current_season() if season is None else normalize_season(season) or current_season()


def current_month() -> int:
    """兼容旧调用：返回当季序号 1–4，不再是日历月。"""
    return current_season_index()


def month_name(month: int | None = None) -> str:
    """兼容旧调用：返回当季名。"""
    if month is None:
        return current_season()
    if 1 <= int(month) <= 4:
        return SEASONS[int(month) - 1]
    return month_to_season(int(month))


def _crops() -> dict:
    from .catalog import CROPS

    return CROPS


def crop_seasons(key: str) -> tuple[str, ...] | None:
    """None = 全年可种。"""
    meta = _crops().get(key) or {}
    seasons = meta.get("seasons")
    if not seasons:
        return None
    return tuple(normalize_season(s) or s for s in seasons)


def crop_in_season(key: str, season: str | int | None = None) -> bool:
    seasons = crop_seasons(key)
    if not seasons:
        return True
    now = current_season() if season is None else (normalize_season(season) or current_season())
    return now in seasons


def next_in_season(key: str, season: str | int | None = None) -> str | None:
    seasons = crop_seasons(key)
    if not seasons:
        return None
    now = current_season() if season is None else (normalize_season(season) or current_season())
    start = SEASONS.index(now)
    for i in range(1, 5):
        cand = SEASONS[(start + i) % 4]
        if cand in seasons:
            return cand
    return None


def next_in_season_month(key: str, month: int | None = None) -> int | None:
    """兼容旧测试：下一开窗季节的序号 1–4。"""
    season = None if month is None else month_to_season(int(month)) if month > 4 else SEASONS[int(month) - 1]
    nxt = next_in_season(key, season)
    if not nxt:
        return None
    return SEASONS.index(nxt) + 1


def seasons_label(key: str) -> str:
    seasons = crop_seasons(key)
    if not seasons:
        return "全年"
    return "、".join(seasons)


def months_label(key: str) -> str:
    """兼容旧调用。"""
    return seasons_label(key)


def season_tag(key: str, season: str | int | None = None) -> str:
    if crop_in_season(key, season):
        return "当季可种"
    nxt = next_in_season(key, season)
    if nxt:
        return f"休市（{nxt}再开）"
    return "休市"


def in_season_crops(season: str | int | None = None) -> list[str]:
    return [k for k in _crops() if crop_in_season(k, season)]


def month_line(season: str | int | None = None) -> str:
    now = current_season() if season is None else (normalize_season(season) or current_season())
    left = season_remaining_days()
    return (
        f"季节 {now}（一周一季，本季还剩 {left} 天）· 当季可种见 plot_ops catalog"
        "（温室 棚N 种菜种树都不受季节；sow 99=棚1）"
    )


def assert_crop_in_season(key: str, *, greenhouse: bool = False) -> None:
    if greenhouse:
        return
    if crop_in_season(key):
        return
    crops = _crops()
    meta = crops.get(key) or {"name": key}
    name = f"{meta.get('emoji', '')}{meta.get('name', key)}"
    now = current_season()
    nxt = next_in_season(key)
    nxt_s = f"{nxt}再开" if nxt else "暂无开窗"
    extra = "已种的继续长；过季种子可等开窗，或 sow 棚1（温室种菜种树都不受季节）。"
    raise ValueError(
        f"{name} 不在当季（{now}）。开窗：{seasons_label(key)}。{nxt_s}。{extra}"
    )
