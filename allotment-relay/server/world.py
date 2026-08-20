from .config import TIDE_CYCLE, TIDE_LABELS, WEATHER_CYCLE, WEATHER_LABELS


def current_weather() -> str:
    phase = int(__import__("time").time() // WEATHER_CYCLE) % 3
    return ["clear", "misty", "gale"][phase]


def current_tide() -> str:
    phase = int(__import__("time").time() // TIDE_CYCLE) % 3
    return ["ebb", "slack", "flood"][phase]


def weather_label(code: str) -> str:
    return WEATHER_LABELS.get(code, code)


def tide_label(code: str) -> str:
    return TIDE_LABELS.get(code, code)


def grow_multiplier(weather: str, tended: bool, in_greenhouse: bool) -> float:
    if in_greenhouse:
        return 1.0
    if weather == "misty" and tended:
        return 0.85
    if weather == "gale":
        return 1.35 if tended else 1.6
    return 1.0
