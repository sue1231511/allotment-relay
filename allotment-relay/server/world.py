from .config import DAY_PHASE_CYCLE, TIDE_CYCLE, TIDE_LABELS, WEATHER_CYCLE, WEATHER_LABELS

DAY_PHASE_LABELS = {
    "day": "昼",
    "dusk": "暮",
    "night": "夜",
}


def current_weather() -> str:
    phase = int(__import__("time").time() // WEATHER_CYCLE) % 3
    return ["clear", "misty", "gale"][phase]


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
        f"月令 {season_mod.month_name()}"
    )


WEATHER_NOW = {
    "clear": "晴朗：热带播种生长目标 ×0.90；赶海贝壳权重 +5；意外 ×0.85",
    "misty": "海雾：已 tend 生长 ×0.85；赶海珠砂/海玻璃等 +8；出海耗时 ×1.15；酒吧小费 +2",
    "gale": "阵风：生长未 tend ×1.60 / 已 tend ×1.35（放任长得快，但虫害/野兽/被薅也专挑没人看的地）；意外 ×1.45；出海失败 +0.12；黑旗战力 −8",
}
TIDE_NOW = {
    "ebb": "退潮：赶海 dig 贝壳/渔获权重↑",
    "slack": "平潮：probe 掏洞（权重略补）",
    "flood": "涨潮：dig 和 probe 都不可用，只有 beach scan 还能看一眼",
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
        "买种 + 露天/果园 sow 须当月；已种的继续长、继续收。温室 #99 种菜不受月令。",
        WEATHER_NOW[w],
        TIDE_NOW[t],
        PHASE_NOW[p],
        "查法：plot_ops weather · plot_ops catalog · steward_ops sheet · relay_manual",
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
