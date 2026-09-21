"""出航途中的文本节点。纯状态 + 选择，不另开副本地图。"""
from __future__ import annotations

import json
import random

from . import db, world

KINDS = {
    "fog": {
        "line": "海面起雾，船头三丈外就看不清。",
        "choices": ("绕行", "继续", "停船"),
    },
    "crate": {
        "line": "左舷漂过一只封着蜡的货箱，绳已经烂了。",
        "choices": ("捞", "绕行", "继续"),
    },
    "buoy": {
        "line": "一只废弃浮标撞上船舷，上面还挂着半面黑旗布。",
        "choices": ("看", "绕行", "继续"),
    },
    "school": {
        "line": "水下有一片巨型鱼群，船跟着它们走会偏航。",
        "choices": ("下网", "绕行", "继续"),
    },
    "wreck": {
        "line": "雾散开一瞬，看见一截失事船肋骨。",
        "choices": ("靠近", "绕行", "继续"),
    },
    "shadow": {
        "line": "右舷有陌生岛影。海图上没有这个点。",
        "choices": ("靠近", "绕行", "停船"),
    },
}

ALIASES = {
    "绕行": "绕行", "detour": "绕行", "绕": "绕行",
    "继续": "继续", "go": "继续", "continue": "继续",
    "停船": "停船", "wait": "停船", "停": "停船",
    "捞": "捞", "salvage": "捞",
    "看": "看", "look": "看",
    "下网": "下网", "net": "下网",
    "靠近": "靠近", "approach": "靠近",
}


def _payload(voyage: dict) -> dict:
    try:
        return json.loads(voyage.get("encounter") or "{}")
    except json.JSONDecodeError:
        return {}


def _weather_kind() -> str:
    w = world.current_weather()
    t = world.current_tide()
    if w == "misty":
        return random.choice(("fog", "shadow", "buoy"))
    if w == "gale":
        return random.choice(("wreck", "crate", "fog"))
    if t == "flood":
        return random.choice(("school", "crate", "buoy"))
    return random.choice(list(KINDS))


async def maybe_on_watch(conn, voyage: dict) -> str | None:
    if voyage.get("status") != "sailing":
        return None
    payload = _payload(voyage)
    if payload.get("sea_node") or payload.get("sea_node_done"):
        return None
    now = db.now()
    departed = int(voyage.get("departed_at") or 0)
    returns = int(voyage.get("returns_at") or 0)
    span = max(1, returns - departed)
    if now < departed + int(span * 0.22):
        return None
    if now >= returns - 45:
        return None
    chance = 0.38
    if world.current_weather() == "misty":
        chance += 0.12
    if random.random() > chance:
        payload["sea_node_done"] = True
        await conn.execute(
            "UPDATE voyages SET encounter=? WHERE id=?",
            (json.dumps(payload, ensure_ascii=False), voyage["id"]),
        )
        return None
    kind = _weather_kind()
    meta = KINDS[kind]
    payload["sea_node"] = kind
    payload["type"] = "sea_node"
    await conn.execute(
        "UPDATE voyages SET status='sea_node', encounter=? WHERE id=?",
        (json.dumps(payload, ensure_ascii=False), voyage["id"]),
    )
    opts = " · ".join(meta["choices"])
    return f"{meta['line']}\n潮上三选：tide_ops {opts}（也可 voyage 绕行|继续|停船）"


def prompt(voyage: dict) -> str:
    payload = _payload(voyage)
    kind = payload.get("sea_node") or "fog"
    meta = KINDS.get(kind) or KINDS["fog"]
    opts = " · ".join(meta["choices"])
    return f"{meta['line']}\n先 tide_ops {opts}"


def fail_bonus_from_encounter(voyage: dict | None) -> float:
    if not voyage:
        return 0.0
    payload = _payload(voyage)
    return float(payload.get("sea_fail") or 0.0)


async def resolve(conn, steward: dict, voyage: dict, choice: str) -> str:
    if voyage.get("status") != "sea_node":
        raise ValueError("没有途中节点待决。出海 status 会写。")
    payload = _payload(voyage)
    kind = payload.get("sea_node") or "fog"
    meta = KINDS.get(kind) or KINDS["fog"]
    ch = ALIASES.get((choice or "").strip().lower()) or ALIASES.get((choice or "").strip())
    if ch not in meta["choices"]:
        raise ValueError(f"这回只能：{' / '.join(meta['choices'])}")
    loot = ""
    fail = 0.0
    extra_time = 0
    if ch == "绕行":
        extra_time = 90
        fail = -0.03
        line = "绕开了。船慢了一点，但没撞上去。"
    elif ch == "停船":
        extra_time = 120
        fail = -0.05
        line = "停船等雾薄一些。海面上安静得不像话。"
    elif ch == "继续":
        fail = 0.06
        line = "继续往前。有人说看见了什么，你权当浪。"
    elif ch == "捞":
        if random.random() < 0.55:
            await db.add_item(conn, steward["id"], "sea_glass", 1)
            loot = "捞上来一块海玻璃。"
        else:
            fail = 0.04
            loot = "箱子进水了，只捞到一把烂绳。"
        line = loot
    elif ch == "看":
        line = "浮标内侧划着「别靠近旧码头」。字是新的。"
        fail = 0.02
    elif ch == "下网":
        if random.random() < 0.5:
            await db.add_item(conn, steward["id"], "fish_mackerel", 1)
            loot = "网住一条马鲛。"
        else:
            fail = 0.05
            loot = "鱼群散了，网里只有水草。"
        line = loot
    else:  # 靠近
        if kind == "shadow" and random.random() < 0.4:
            fail = 0.10
            line = "岛影退了。海图还是空的。你有点怀疑自己看见过。"
        elif kind == "wreck" and random.random() < 0.5:
            await db.add_item(conn, steward["id"], "drift_twine", 1)
            line = "从肋骨上解下一截还能用的漂绳。"
        else:
            fail = 0.07
            line = "靠近之后什么都没有。浪把船拍偏了一点。"
    payload["sea_node_done"] = True
    payload["sea_fail"] = float(payload.get("sea_fail") or 0.0) + fail
    payload.pop("type", None)
    payload.pop("sea_node", None)
    returns = int(voyage.get("returns_at") or db.now()) + extra_time
    await conn.execute(
        "UPDATE voyages SET status='sailing', returns_at=?, encounter=? WHERE id=?",
        (returns, json.dumps(payload, ensure_ascii=False), voyage["id"]),
    )
    from . import voyage_chronicle as vlog_mod

    await vlog_mod.append(conn, steward["id"], f"途中：{kind}/{ch}")
    await db.add_chronicle(
        "voyage",
        f"{steward['name']} 出航途中选择了{ch}",
        steward["id"],
        conn=conn,
    )
    return line
