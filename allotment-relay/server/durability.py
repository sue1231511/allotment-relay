"""统一耐久框架 — 船件 / 屋顶 / 厨电 / 钓具 / 井下装备。

低耐久不锁死：效率降、故障升、可硬用。修走各系统原入口。
"""
from __future__ import annotations

from typing import Any


def efficiency(current: int, maximum: int) -> float:
    """0.45～1.0：越旧越慢，不归零。"""
    mx = max(1, int(maximum or 1))
    ratio = max(0.0, min(1.0, int(current or 0) / mx))
    return round(0.45 + 0.55 * ratio, 3)


def fail_bonus(current: int, maximum: int) -> float:
    """耐久低时额外失败率（0～0.22）。"""
    mx = max(1, int(maximum or 1))
    ratio = max(0.0, min(1.0, int(current or 0) / mx))
    if ratio >= 0.55:
        return 0.0
    return round((0.55 - ratio) * 0.4, 3)


def repair_cost(current: int, maximum: int, *, base: int = 16) -> int:
    """越残越贵，硬用过的更贵。"""
    mx = max(1, int(maximum or 1))
    missing = max(0, mx - int(current or 0))
    extra = 0 if missing < mx * 0.5 else 6
    return int(base + missing // 8 + extra)


SYSTEMS: tuple[dict[str, str], ...] = (
    {"key": "boat", "label": "船件", "fix": "tide_ops voyage 部件 修", "ui": "港口看出海栏修帆舵灯"},
    {"key": "roof", "label": "屋顶", "fix": "hut_ops 修屋顶", "ui": "让管家修屋顶"},
    {"key": "fridge", "label": "冰箱", "fix": "hut_ops 修冰箱", "ui": "小屋点修冰箱"},
    {"key": "stove", "label": "灶台", "fix": "hut_ops 修灶", "ui": "小屋点修灶"},
    {"key": "hook", "label": "鱼钩", "fix": "tide_ops gear repair hook", "ui": "渔具栏"},
    {"key": "reel", "label": "卷线器", "fix": "tide_ops gear repair reel", "ui": "渔具栏"},
    {"key": "ut_gear", "label": "井下装备", "fix": "undertide_ops repair", "ui": "潮下修理"},
)


async def snapshot(conn, steward_id: int) -> list[dict[str, Any]]:
    """各系统当前耐久。没有的件不出现。"""
    rows: list[dict[str, Any]] = []

    from . import boat_parts as boat_mod

    parts = await boat_mod.get_all(conn, steward_id)
    for key, (dur, mx) in parts.items():
        rows.append(
            _row(
                "boat",
                boat_mod.PART_LABELS.get(key, key),
                dur,
                mx,
                "tide_ops voyage 部件 修",
            )
        )

    from . import hut_roof as roof_mod

    roof, rmx = await roof_mod.get_roof(conn, steward_id)
    rows.append(_row("roof", "屋顶", roof, rmx, "hut_ops 修屋顶"))

    from . import hut_appliances as appl_mod

    for key, label in (("fridge", "冰箱"), ("stove", "灶台")):
        if await appl_mod.has_appliance(conn, steward_id, key):
            dur, mx = await appl_mod.get_durability(conn, steward_id, key)
            fix = "hut_ops 修冰箱" if key == "fridge" else "hut_ops 修灶"
            rows.append(_row(key, label, dur, mx, fix))

    from . import fishing_parts as fish_mod

    for key, label in (("hook", "鱼钩"), ("reel", "卷线器")):
        dur, mx, _snag = await fish_mod._get(conn, steward_id, key)
        rows.append(
            _row(key, label, dur, mx, f"tide_ops gear repair {key}")
        )

    cur = await conn.execute(
        "SELECT gear_key, COALESCE(gear_durability,0), COALESCE(gear_max,0) "
        "FROM steward_undertide WHERE steward_id=?",
        (steward_id,),
    )
    ut = await cur.fetchone()
    if ut and ut[0] and int(ut[2] or 0) > 0:
        rows.append(_row("ut_gear", "井下装备", int(ut[1]), int(ut[2]), "undertide_ops repair"))

    return rows


def _row(system: str, label: str, dur: int, mx: int, fix: str) -> dict[str, Any]:
    return {
        "system": system,
        "label": label,
        "dur": int(dur),
        "max": int(mx),
        "efficiency": efficiency(dur, mx),
        "fail_bonus": fail_bonus(dur, mx),
        "repair_cost": repair_cost(dur, mx),
        "fix": fix,
    }


def format_snapshot(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "还没有记过耐久的件。"
    warn = [r for r in rows if r["dur"] / max(1, r["max"]) < 0.35]
    bits = [
        f"{r['label']}{r['dur']}/{r['max']}"
        + ("⚠" if r["dur"] / max(1, r["max"]) < 0.35 else "")
        for r in rows
        if r["dur"] < r["max"] or r["system"] in ("roof", "fridge", "stove")
    ]
    if not bits:
        bits = [f"{r['label']}{r['dur']}/{r['max']}" for r in rows[:6]]
    line = "耐久 " + " · ".join(bits[:12])
    if warn:
        line += f" · 低件可硬用（效率降/故障升）：{warn[0]['fix']}"
    return line


async def status_line(conn, steward_id: int) -> str:
    return format_snapshot(await snapshot(conn, steward_id))
