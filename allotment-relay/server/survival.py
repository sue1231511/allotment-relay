"""休闲生存感 — 饱食/雾智/档信，慢衰减、软惩罚，无 permadeath。"""

from __future__ import annotations

from typing import Any

import aiosqlite

from . import config, flavor

METER_NAMES = {
    "satiety": "饱食",
    "mist_wit": "雾智",
    "standing": "档信",
}


async def _set_meter(
    conn: aiosqlite.Connection,
    steward_id: int,
    column: str,
    delta: int,
) -> None:
    if not delta:
        return
    await conn.execute(
        f"UPDATE stewards SET {column} = MAX(0, MIN(100, {column} + ?)) WHERE id=?",
        (delta, steward_id),
    )


async def bump(
    conn: aiosqlite.Connection,
    steward_id: int,
    *,
    satiety: int = 0,
    mist_wit: int = 0,
    standing: int = 0,
) -> None:
    await _set_meter(conn, steward_id, "satiety", satiety)
    await _set_meter(conn, steward_id, "mist_wit", mist_wit)
    await _set_meter(conn, steward_id, "standing", standing)


ACTION_DRAIN = {
    "tend": (-1, 0, 0),
    "gather": (-1, 0, 0),
    "sow": (-1, 0, 0),
    "forage": (0, 0, 0),
    "net": (-2, 0, 0),
    "pen_feed": (-1, 0, 0),
    "pen_harvest": (-1, 0, 0),
    "pen_stock": (-1, 0, 0),
    "voyage_depart": (-2, -2, 0),
    "voyage_return": (-2, -1, 0),
    "guild": (0, 1, 0),
    "brew": (0, 0, 0),
}


async def on_action(conn: aiosqlite.Connection, steward_id: int, trigger: str) -> None:
    drain = ACTION_DRAIN.get(trigger)
    if drain:
        await bump(conn, steward_id, satiety=drain[0], mist_wit=drain[1], standing=drain[2])


def event_multiplier(steward: dict[str, Any]) -> float:
    mult = 1.0
    if steward.get("satiety", 100) < config.SATIETY_LOW:
        mult *= 1.12
    if steward.get("mist_wit", 100) < config.MIST_WIT_LOW:
        mult *= 1.08
    if steward.get("standing", 100) < config.STANDING_LOW:
        mult *= 1.06
    return mult


def guild_ticket_multiplier(steward: dict[str, Any]) -> tuple[float, str]:
    standing = steward.get("standing", config.START_STANDING)
    if standing < config.STANDING_SHUT:
        return 0.35, flavor.pick(flavor.GUILD_STANDING_SHUT)
    if standing < config.STANDING_LOW:
        return 0.65, flavor.pick(flavor.GUILD_STANDING_LOW)
    return 1.0, ""


def naval_bad_bias(steward: dict[str, Any]) -> float:
    if steward.get("mist_wit", 100) < config.MIST_WIT_LOW:
        return 0.14
    if steward.get("satiety", 100) < config.SATIETY_LOW:
        return 0.08
    return 0.0


def meter_line(steward: dict[str, Any]) -> str:
    s = steward.get("satiety", config.START_SATIETY)
    m = steward.get("mist_wit", config.START_MIST_WIT)
    d = steward.get("standing", config.START_STANDING)
    bits = [f"饱食 {s}", f"雾智 {m}", f"档信 {d}"]
    hints = []
    if s < config.SATIETY_LOW:
        hints.append(flavor.METER_HINT_SATIETY)
    if m < config.MIST_WIT_LOW:
        hints.append(flavor.METER_HINT_MIST)
    if d < config.STANDING_LOW:
        hints.append(flavor.METER_HINT_STANDING)
    line = " · ".join(bits)
    if hints:
        line += f"（{ '，'.join(hints) }）"
    return line


def low_meter_hint(steward: dict[str, Any]) -> str | None:
    if steward.get("standing", 100) < config.STANDING_SHUT:
        return flavor.pick(flavor.LOW_STANDING_HINT)
    if steward.get("satiety", 100) < config.SATIETY_LOW:
        return flavor.pick(flavor.LOW_SATIETY_HINT)
    return None
