import time

from .config import DAY_PHASE_CYCLE, TIDE_CYCLE, TIDE_LABELS, WEATHER_CYCLE, WEATHER_LABELS

DAY_PHASE_LABELS = {
    "day": "昼",
    "dusk": "暮",
    "night": "夜",
}


def weather_at(ts: int | None = None) -> str:
    t = int(ts if ts is not None else time.time())
    return ["clear", "misty", "gale"][int(t // WEATHER_CYCLE) % 3]


def current_weather() -> str:
    return weather_at()


def last_gale_end(now: int | None = None) -> int:
    """最近一段阵风结束的时间戳。正在刮时返回本段阵风的结束点。"""
    t = int(now if now is not None else time.time())
    idx = t // WEATHER_CYCLE
    phase = idx % 3
    if phase == 2:
        return (idx + 1) * WEATHER_CYCLE
    last_idx = idx - (1 if phase == 0 else 2)
    return (last_idx + 1) * WEATHER_CYCLE


def clear_seconds_between(start: int, end: int) -> int:
    """闭开区间 [start, end) 里晴天累计秒数。盐田只认晴。"""
    start, end = int(start), int(end)
    if end <= start:
        return 0
    acc = 0
    t = start
    while t < end:
        slot_end = (t // WEATHER_CYCLE + 1) * WEATHER_CYCLE
        nxt = min(slot_end, end)
        if weather_at(t) == "clear":
            acc += nxt - t
        t = nxt
    return acc


def salvage_window(
    *,
    now: int | None = None,
    boat_damaged: bool = False,
    weekly_tide: bool = False,
) -> dict:
    """风暴打捞窗口。阵风中 / 阵风后一段晴天 / 周潮 / 自家船损。不是赶海 dig。"""
    from . import config

    t = int(now if now is not None else time.time())
    w = weather_at(t)
    if w == "gale":
        return {
            "open": True, "kind": "gale", "label": "风暴中",
            "energy": 10, "empty": 0.22, "hazard": 0.18,
        }
    ended = last_gale_end(t)
    after = int(getattr(config, "CRAFT_SALVAGE_AFTER", WEATHER_CYCLE))
    if w == "clear" and t < ended + after:
        return {
            "open": True, "kind": "after", "label": "风暴余滩",
            "energy": 7, "empty": 0.14, "hazard": 0.10,
        }
    if weekly_tide:
        return {
            "open": True, "kind": "tide", "label": "周潮余浪",
            "energy": 8, "empty": 0.16, "hazard": 0.12,
        }
    if boat_damaged:
        return {
            "open": True, "kind": "boat", "label": "自家船搁浅",
            "energy": 8, "empty": 0.20, "hazard": 0.10,
        }
    return {
        "open": False, "kind": "", "label": "滩上没风暴货",
        "energy": 0, "empty": 1.0, "hazard": 0.0,
    }


def current_tide() -> str:
    phase = int(__import__("time").time() // TIDE_CYCLE) % 3
    return ["ebb", "slack", "flood"][phase]


def current_day_phase() -> str:
    phase = int(__import__("time").time() // DAY_PHASE_CYCLE) % 3
    return ["day", "dusk", "night"][phase]


def weather_label(code: str) -> str:
    return WEATHER_LABELS.get(code, code)


def tide_label(code: str) -> str:
    return TIDE_LABELS.get(code, code)


def day_phase_label(code: str) -> str:
    return DAY_PHASE_LABELS.get(code, code)


def climate_line() -> str:
    from . import season as season_mod

    w, t, p = current_weather(), current_tide(), current_day_phase()
    return (
        f"天气 {weather_label(w)}({w}) · "
        f"潮汐 {tide_label(t)}({t}) · "
        f"时辰 {day_phase_label(p)}({p}) · "
        f"季节 {season_mod.season_name()}（一周一季）"
    )


WEATHER_NOW = {
    "clear": "晴朗：热带播种生长目标 ×0.90；赶海贝壳权重 +5；意外 ×0.85",
    "misty": "海雾：已 tend 生长 ×0.85；赶海珠砂/海玻璃等 +8；出海耗时 ×1.15；酒吧小费 +2",
    "gale": "阵风：生长未 tend ×1.60 / 已 tend ×1.35（放任长得快，但虫害/野兽/被薅也专挑没人看的地）；意外 ×1.45；出海失败 +0.12；黑旗战力 −8；craft_ops 打捞 开窗（风暴中更危险）",
}
TIDE_NOW = {
    "ebb": "退潮：赶海 dig 贝壳/渔获权重↑；崖矿铁砂床/页岩层更肥",
    "slack": "平潮：probe 掏洞（权重略补）；崖矿铜绿缝略肥",
    "flood": "涨潮：dig 和 probe 都不可用，只有 beach scan 还能看一眼；崖矿不关，盐脉更肥；盐田 craft_ops 灌 只能这时灌",
}
PHASE_NOW = {
    "day": "昼：斑鸠只在这时出现；酒吧默认打烊（逾期补班票 ×0.72）",
    "dusk": "暮：酒吧开门；意外 ×1.04；潮汐灯可补雾智 +1；拾叶偏小偷/敲诈",
    "night": "夜：酒吧继续开；意外 ×1.10、野兽 ×1.12；户外生长 ×1.08；黑旗坏遭遇 +0.08；潮汐灯可补雾智 +1",
}


def climate_report() -> str:
    from . import season as season_mod

    w, t, p = current_weather(), current_tide(), current_day_phase()
    return "\n".join([
        climate_line(),
        season_mod.month_line(),
        "买种 + 露天/果园 sow 须当季（一周一季）；已种的继续长、继续收。温室种菜种树都不受季节。",
        WEATHER_NOW[w],
        TIDE_NOW[t],
        PHASE_NOW[p],
        "查法：plot_ops weather · plot_ops catalog · quarry_ops status · craft_ops status · steward_ops sheet · relay_manual",
    ])


def grow_multiplier(weather: str, tended: bool, in_greenhouse: bool) -> float:
    if in_greenhouse:
        return 1.0
    if weather == "misty" and tended:
        return 0.85
    if weather == "gale":
        return 1.35 if tended else 1.6
    if current_day_phase() == "night" and not in_greenhouse:
        return 1.08
    return 1.0


def incident_night_bias() -> float:
    phase = current_day_phase()
    if phase == "night":
        return 1.1
    if phase == "dusk":
        return 1.04
    return 1.0
