"""上下层环境联动 + 岸上工程加成 — 第三批。"""
from __future__ import annotations

import random

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


async def works_voyage_hint(conn) -> str | None:
    """岸上工程对海事的当前加成摘要。"""
    from . import works as works_mod

    bits: list[str] = []
    if await works_mod.active_bonus(conn, "dock"):
        bits.append("码头工程：出海失败×0.90")
    if await works_mod.active_bonus(conn, "shed"):
        bits.append("旧温室工程：失败×0.97")
    if await works_mod.active_bonus(conn, "ting"):
        bits.append("听潮亭工程：鱼群压力×0.85")
    if await works_mod.active_bonus(conn, "drain"):
        bits.append("排水工程：井蚀涨得慢、潮返盐斑少")
    if not bits:
        return None
    return "岸上工程加成：" + " · ".join(bits)


async def fish_pressure_relief(conn) -> float:
    """听潮亭工程完工：全岛鱼群压力略缓。"""
    from . import works as works_mod
    if await works_mod.active_bonus(conn, "ting"):
        return 0.85
    return 1.0


async def maybe_salt_blot_after_well(conn, steward_id: int) -> str | None:
    """井蚀高时，潮返地面随机露天地盐斑（§53 上下层联动）。"""
    from . import soil as soil_mod
    from . import well_corrosion as wc_mod
    from . import works as works_mod

    lvl = await wc_mod.get_level(conn, steward_id)
    if lvl < 78:
        return None
    chance = 0.08
    if await works_mod.active_bonus(conn, "dock"):
        chance *= 0.5
    if await works_mod.active_bonus(conn, "shed"):
        chance *= 0.85
    if await works_mod.active_bonus(conn, "drain"):
        chance *= 0.4
    if random.random() > chance:
        return None
    cur = await conn.execute(
        """
        SELECT id, slot FROM parcels
        WHERE steward_id=? AND NOT orchard AND NOT greenhouse AND crop IS NOT NULL
        ORDER BY RANDOM() LIMIT 1
        """,
        (steward_id,),
    )
    row = await cur.fetchone()
    if not row:
        return None
    fid, slot = int(row[0]), row[1]
    cur = await conn.execute(
        "SELECT COALESCE(soil_fertility, ?) FROM parcels WHERE id=?",
        (soil_mod.DEFAULT_FERTILITY, fid),
    )
    fert = int((await cur.fetchone())[0])
    new_f = max(soil_mod.MIN_FERTILITY, fert - 12)
    await conn.execute(
        "UPDATE parcels SET soil_fertility=? WHERE id=?",
        (new_f, fid),
    )
    return (
        f"潮返地面：{slot}号地起盐斑，肥力 {fert}→{new_f}"
        "（undertide_ops 清井；潮生会 工程 旧码头修完能略缓）"
    )
