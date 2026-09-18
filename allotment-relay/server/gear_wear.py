"""岸上用具耐久 — 渔网 / 钓竿 / 农具 / 镐。"""
from __future__ import annotations

import random
from typing import Any

from . import db

GEAR_KEYS = ("net", "rod", "hoe", "shovel", "pickaxe")
DEFAULT_MAX = {
    "net": 120,
    "rod": 100,
    "hoe": 140,
    "shovel": 130,
    "pickaxe": 160,
}
WEAR_PER_USE = {
    "net": 2,
    "rod": 2,
    "hoe": 1,
    "shovel": 1,
    "pickaxe": 3,
}


async def ensure_table(conn) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS steward_gear_wear (
            steward_id INTEGER NOT NULL,
            gear_key TEXT NOT NULL,
            durability INTEGER NOT NULL,
            max_dur INTEGER NOT NULL,
            PRIMARY KEY (steward_id, gear_key)
        )
        """
    )


async def _row(conn, steward_id: int, gear_key: str) -> tuple[int, int] | None:
    await ensure_table(conn)
    cur = await conn.execute(
        "SELECT durability, max_dur FROM steward_gear_wear WHERE steward_id=? AND gear_key=?",
        (steward_id, gear_key),
    )
    r = await cur.fetchone()
    if not r:
        return None
    return int(r[0]), int(r[1])


async def ensure_gear(conn, steward_id: int, gear_key: str) -> tuple[int, int]:
    if gear_key not in GEAR_KEYS:
        gear_key = "net"
    row = await _row(conn, steward_id, gear_key)
    if row:
        return row
    mx = DEFAULT_MAX.get(gear_key, 100)
    await conn.execute(
        """
        INSERT INTO steward_gear_wear (steward_id, gear_key, durability, max_dur)
        VALUES (?, ?, ?, ?)
        """,
        (steward_id, gear_key, mx, mx),
    )
    return mx, mx


def efficiency_mult(dur: int, max_dur: int) -> float:
    if max_dur <= 0:
        return 1.0
    ratio = dur / max_dur
    if ratio >= 0.6:
        return 1.0
    if ratio >= 0.35:
        return 0.92
    if ratio >= 0.15:
        return 0.82
    return 0.7


def accident_extra_chance(dur: int, max_dur: int) -> float:
    if max_dur <= 0:
        return 0.0
    ratio = dur / max_dur
    if ratio >= 0.5:
        return 0.0
    return min(0.12, (0.5 - ratio) * 0.25)


async def wear(conn, steward_id: int, gear_key: str, amount: int | None = None) -> tuple[int, int]:
    dur, mx = await ensure_gear(conn, steward_id, gear_key)
    loss = amount if amount is not None else WEAR_PER_USE.get(gear_key, 1)
    new = max(0, dur - loss)
    await conn.execute(
        """
        UPDATE steward_gear_wear SET durability=? WHERE steward_id=? AND gear_key=?
        """,
        (new, steward_id, gear_key),
    )
    return new, mx


async def repair(conn, steward_id: int, gear_key: str, tickets: int = 12) -> str:
    dur, mx = await ensure_gear(conn, steward_id, gear_key)
    if dur >= mx:
        return f"{gear_key} 耐久已满（{dur}/{mx}）"
    cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (steward_id,))
    have = int((await cur.fetchone())[0])
    if have < tickets:
        raise ValueError(f"修 {gear_key} 要 {tickets} 票，你只有 {have}")
    await conn.execute(
        "UPDATE stewards SET tickets=tickets-? WHERE id=?",
        (tickets, steward_id),
    )
    await conn.execute(
        """
        UPDATE steward_gear_wear SET durability=max_dur WHERE steward_id=? AND gear_key=?
        """,
        (steward_id, gear_key),
    )
    return f"已修 {gear_key}（-{tickets} 票，耐久回满 {mx}）"


async def status_line(conn, steward_id: int) -> str:
    lines = ["用具耐久（低则效率降、事故略增；tide_ops gear repair net|rod · plot_ops gear repair hoe）："]
    for key in GEAR_KEYS:
        dur, mx = await ensure_gear(conn, steward_id, key)
        pct = int(100 * dur / mx) if mx else 0
        lines.append(f"  {key} {dur}/{mx}（{pct}%）· 效率×{efficiency_mult(dur, mx):.2g}")
    return "\n".join(lines)


async def maybe_accident_note(dur: int, max_dur: int) -> str:
    if random.random() < accident_extra_chance(dur, max_dur):
        return "（用具发涩，差点出岔子）"
    return ""
