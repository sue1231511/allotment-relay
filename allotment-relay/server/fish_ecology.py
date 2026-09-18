"""鱼群生态 — 第三批：按海域与捕捞压力调权重。"""
from __future__ import annotations

import random
from typing import Any

from . import db
from .catalog import SEA_CATCH, weighted_fish_pick

ZONE_FOR_MODE = {
    "net": {"shore", "near"},
    "cast": {"shore", "near"},
    "voyage_near": {"near", "far"},
    "voyage_far": {"far", "deep"},
    "voyage_deep": {"deep", "far"},
}


async def ensure_table(conn) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fish_ecology_pressure (
            week_id INTEGER NOT NULL,
            species TEXT NOT NULL,
            pressure INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (week_id, species)
        )
        """
    )


def _week_id() -> int:
    return int(db.day_id()) // 7


async def _pressure(conn, species: str) -> int:
    await ensure_table(conn)
    wk = _week_id()
    cur = await conn.execute(
        "SELECT pressure FROM fish_ecology_pressure WHERE week_id=? AND species=?",
        (wk, species),
    )
    row = await cur.fetchone()
    return int(row[0]) if row else 0


async def bump_pressure(conn, species: str, amount: int = 1) -> None:
    await ensure_table(conn)
    from . import layer_link as layer_link_mod
    relief = await layer_link_mod.fish_pressure_relief(conn)
    if relief < 1.0 and amount > 0:
        amount = max(1, int(amount * relief))
    wk = _week_id()
    await conn.execute(
        """
        INSERT INTO fish_ecology_pressure (week_id, species, pressure)
        VALUES (?, ?, ?)
        ON CONFLICT(week_id, species) DO UPDATE SET pressure = pressure + ?
        """,
        (wk, species, amount, amount),
    )


def pick_with_ecology(
    *,
    tide: str | None,
    zones: set[str] | None,
    rarity_cap: int | None,
    allow_cast_only: bool,
    pressure_map: dict[str, int],
) -> str:
    pool: list[tuple[str, int]] = []
    for key, meta in SEA_CATCH.items():
        if meta.get("cast_only") and not allow_cast_only:
            continue
        if tide and tide not in meta.get("tides", []):
            continue
        if zones and not zones.intersection(meta.get("zones", [])):
            continue
        if rarity_cap and meta.get("rarity", 1) > rarity_cap:
            continue
        seasons = meta.get("seasons")
        if seasons:
            from . import season as season_mod
            if season_mod.current_season() not in seasons:
                continue
        weight = max(1, 7 - meta.get("rarity", 1))
        pres = int(pressure_map.get(key) or 0)
        if pres >= 12:
            weight = max(1, weight // 3)
        elif pres >= 6:
            weight = max(1, int(weight * 0.65))
        elif pres <= 1 and meta.get("rarity", 1) >= 3:
            weight += 2
        pool.append((key, weight))
    if not pool:
        return weighted_fish_pick(
            tide=tide, zones=zones, rarity_cap=rarity_cap, allow_cast_only=allow_cast_only,
        )
    keys, weights = zip(*pool)
    return random.choices(keys, weights=weights, k=1)[0]


async def pick(
    conn,
    *,
    mode: str,
    tide: str | None,
    rarity_cap: int | None,
    allow_cast_only: bool = False,
) -> str:
    zones = ZONE_FOR_MODE.get(mode, {"shore", "near"})
    await ensure_table(conn)
    wk = _week_id()
    cur = await conn.execute(
        "SELECT species, pressure FROM fish_ecology_pressure WHERE week_id=?",
        (wk,),
    )
    pressure_map = {r[0]: int(r[1]) for r in await cur.fetchall()}
    species = pick_with_ecology(
        tide=tide,
        zones=zones,
        rarity_cap=rarity_cap,
        allow_cast_only=allow_cast_only,
        pressure_map=pressure_map,
    )
    await bump_pressure(conn, species, 1)
    return species


async def status_line(conn) -> str:
    await ensure_table(conn)
    wk = _week_id()
    cur = await conn.execute(
        """
        SELECT species, pressure FROM fish_ecology_pressure
        WHERE week_id=? ORDER BY pressure DESC LIMIT 5
        """,
        (wk,),
    )
    rows = await cur.fetchall()
    if not rows:
        return "本周鱼群压力：尚平（多捞同种会稀）"
    bits = []
    for sp, pr in rows:
        name = SEA_CATCH.get(sp, {}).get("name", sp)
        bits.append(f"{name}×{pr}")
    return "本周鱼群压力：" + " · ".join(bits)
