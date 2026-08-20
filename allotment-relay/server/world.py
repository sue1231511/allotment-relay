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
