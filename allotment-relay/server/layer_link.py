"""上下层环境联动 + 岸上工程加成 — 第三批。"""
from __future__ import annotations

from . import db, world


async def undertide_tide_weather_mult(conn) -> float:
    """地面天气微调井下倍率（叠在景气分之上）。"""
    w = world.current_weather()
    if w in ("gale", "storm"):
        return 0.92
    if w == "rain":
        return 0.97
    if w == "clear":
        return 1.03
    return 1.0


async def effective_ut_mult(conn) -> tuple[float, str]:
    from . import undertide_tide as utide_mod
    base, line = await utide_mod.tide_mult(conn)
    wmult = await undertide_tide_weather_mult(conn)
    mult = round(base * wmult, 3)
    extra = ""
    if wmult != 1.0:
        extra = f"（地面{world.current_weather()}，井下×{wmult:g}）"
    return mult, line + extra


async def surface_well_drain(conn, steward_id: int) -> str | None:
    """井蚀过高，地面雾智略泄。"""
    from . import well_corrosion as wc_mod
    lvl = await wc_mod.get_level(conn, steward_id)
    if lvl < 75:
        return None
    if lvl >= 92:
        delta = 3
    else:
        delta = 1
    await conn.execute(
        "UPDATE stewards SET mist_wit=MAX(0, mist_wit-?) WHERE id=?",
        (delta, steward_id),
    )
    return f"井口返潮，雾智 -{delta}（井蚀 {lvl}，undertide_ops 清井）"


async def voyage_fail_mult(conn) -> float:
    from . import works as works_mod
    m = 1.0
    if await works_mod.active_bonus(conn, "dock"):
        m *= 0.90
    if await works_mod.active_bonus(conn, "shed"):
        m *= 0.97
    return m


async def fish_pressure_relief(conn) -> float:
    """听潮亭工程完工：全岛鱼群压力略缓。"""
    from . import works as works_mod
    if await works_mod.active_bonus(conn, "ting"):
        return 0.85
    return 1.0
