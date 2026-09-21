"""岛上怪谈。每季几条传言，多数是屁话，少部分对得上真事。永远不标真假。"""
from __future__ import annotations

import hashlib

from . import db, season, world

RUMORS = (
    {
        "id": "lamp_knock",
        "text": "有人说凌晨三点灯塔下面有人敲门。不醒从来不回。",
        "true_when": "night_lighthouse",
    },
    {
        "id": "seventh_dock",
        "text": "大潮后盐风崖会出现不存在的第七码头。去的人回来都不记得路。",
        "true_when": "never",
    },
    {
        "id": "ghost_online",
        "text": "某个已经离岛的人还在聊天室显示在线。点开名字是空白。",
        "true_when": "never",
    },
    {
        "id": "fog_vein",
        "text": "海雾里盐风崖会多出一条平时看不见的脉。探到了也不要大声说。",
        "true_when": "misty_vein",
    },
    {
        "id": "flood_casino",
        "text": "涨潮那一阵，井下赌场会自己关门。恶猫说是进水，没人看见水。",
        "true_when": "flood_casino",
    },
    {
        "id": "rain_plots",
        "text": "阵风天不用浇地。雨自己会来。有人说那根本不是雨。",
        "true_when": "gale_rain",
    },
    {
        "id": "clear_ice",
        "text": "极晴的日子，小馆冰柜里的货会先坏。掌柜怪冰箱，冰箱不说话。",
        "true_when": "clear_ice",
    },
    {
        "id": "sea_shadow",
        "text": "远航有人看见陌生岛影。靠近的船有的回来了，有的把名字留在潮汐周报里。",
        "true_when": "voyage_shadow",
    },
)


def _week_seed() -> int:
    week = int(db.week_id())
    name = season.season_name()
    raw = f"{week}:{name}".encode("utf-8")
    return int(hashlib.sha256(raw).hexdigest()[:8], 16)


def week_rumors() -> list[dict]:
    """本周三条。内部可标真，对外只给 text。"""
    seed = _week_seed()
    order = list(RUMORS)
    n = len(order)
    # deterministic shuffle
    for i in range(n - 1, 0, -1):
        j = (seed + i * 17) % (i + 1)
        order[i], order[j] = order[j], order[i]
    picked = order[:3]
    out = []
    for i, row in enumerate(picked):
        true = _is_true_now(row["true_when"]) and i == seed % 3
        out.append({"id": row["id"], "text": row["text"], "true": true})
    return out


def public_lines() -> list[str]:
    return [r["text"] for r in week_rumors()]


def _is_true_now(kind: str) -> bool:
    if kind == "misty_vein":
        return world.current_weather() == "misty"
    if kind == "flood_casino":
        return world.current_tide() == "flood"
    if kind == "gale_rain":
        return world.current_weather() == "gale"
    if kind == "clear_ice":
        return world.current_weather() == "clear"
    if kind == "night_lighthouse":
        return world.current_day_phase() == "night"
    if kind == "voyage_shadow":
        return True
    return False


def weather_appendix() -> str:
    lines = public_lines()
    if not lines:
        return ""
    body = "\n".join(f"  · {ln}" for ln in lines)
    return "岛上最近在传：\n" + body + "\n（没人保证哪句是真的。）"
