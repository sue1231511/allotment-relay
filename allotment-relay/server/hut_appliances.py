"""小屋厨电耐久 — 冰箱 / 灶台（全局耐久框架余量）。"""
from __future__ import annotations

import random

from . import db

APPLIANCES = ("fridge", "stove")
DEFAULT_MAX = {"fridge": 100, "stove": 100}


async def ensure_table(conn) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS steward_hut_appliance (
            steward_id INTEGER NOT NULL,
            appliance_key TEXT NOT NULL,
            durability INTEGER NOT NULL,
            max_dur INTEGER NOT NULL,
            PRIMARY KEY (steward_id, appliance_key)
        )
        """
    )


async def get_durability(conn, steward_id: int, key: str) -> tuple[int, int]:
    return await _get(conn, steward_id, key)


async def _get(conn, steward_id: int, key: str) -> tuple[int, int]:
    await ensure_table(conn)
    cur = await conn.execute(
        """
        SELECT durability, max_dur FROM steward_hut_appliance
        WHERE steward_id=? AND appliance_key=?
        """,
        (steward_id, key),
    )
    row = await cur.fetchone()
    if row:
        return int(row[0]), int(row[1])
    mx = DEFAULT_MAX.get(key, 100)
    await conn.execute(
        """
        INSERT INTO steward_hut_appliance (steward_id, appliance_key, durability, max_dur)
        VALUES (?, ?, ?, ?)
        """,
        (steward_id, key, mx, mx),
    )
    return mx, mx


async def has_appliance(conn, steward_id: int, key: str) -> bool:
    if key == "fridge":
        from . import hut

        return await hut.has_fridge(conn, steward_id)
    if key == "stove":
        cur = await conn.execute(
            "SELECT hut_built, hut_level FROM stewards WHERE id=?", (steward_id,),
        )
        row = await cur.fetchone()
        return bool(row and row[0] and int(row[1] or 0) >= 2)
    return False


async def wear_stove(conn, steward_id: int) -> None:
    if not await has_appliance(conn, steward_id, "stove"):
        return
    dur, mx = await _get(conn, steward_id, "stove")
    loss = 2 if random.random() < 0.35 else 1
    await conn.execute(
        """
        UPDATE steward_hut_appliance SET durability=? WHERE steward_id=? AND appliance_key='stove'
        """,
        (max(0, dur - loss), steward_id),
    )


async def wear_fridge(conn, steward_id: int) -> None:
    if not await has_appliance(conn, steward_id, "fridge"):
        return
    dur, mx = await _get(conn, steward_id, "fridge")
    await conn.execute(
        """
        UPDATE steward_hut_appliance SET durability=? WHERE steward_id=? AND appliance_key='fridge'
        """,
        (max(0, dur - 1), steward_id),
    )


def stove_extra_energy(dur: int, max_dur: int) -> int:
    if max_dur <= 0:
        return 0
    ratio = dur / max_dur
    if ratio >= 0.45:
        return 0
    if ratio >= 0.2:
        return 1
    return 2


async def stove_penalty(conn, steward_id: int) -> int:
    if not await has_appliance(conn, steward_id, "stove"):
        return 0
    dur, mx = await _get(conn, steward_id, "stove")
    return stove_extra_energy(dur, mx)


async def fridge_spoil_mult(conn, steward_id: int) -> float:
    if not await has_appliance(conn, steward_id, "fridge"):
        return 1.0
    dur, mx = await _get(conn, steward_id, "fridge")
    if mx <= 0:
        return 1.0
    ratio = dur / mx
    if ratio >= 0.5:
        return 1.0
    if ratio >= 0.25:
        return 0.85
    return 0.65


async def repair(conn, steward_id: int, key: str, tickets: int = 16) -> str:
    if key not in APPLIANCES:
        raise ValueError("可修：fridge 冰箱 · stove 灶台（hut_ops 修冰箱 / 修灶）")
    if not await has_appliance(conn, steward_id, key):
        raise ValueError("还没装这件，先 buy 再 install")
    dur, mx = await _get(conn, steward_id, key)
    if dur >= mx:
        label = "冰箱" if key == "fridge" else "灶台"
        return f"{label}完好（{dur}/{mx}）"
    cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (steward_id,))
    have = int((await cur.fetchone())[0])
    if have < tickets:
        raise ValueError(f"修{key}要 {tickets} 票，你只有 {have}")
    await conn.execute(
        "UPDATE stewards SET tickets=tickets-? WHERE id=?", (tickets, steward_id),
    )
    await conn.execute(
        """
        UPDATE steward_hut_appliance SET durability=max_dur
        WHERE steward_id=? AND appliance_key=?
        """,
        (steward_id, key),
    )
    label = "冰箱" if key == "fridge" else "灶台"
    return f"{label}修好了（-{tickets} 票，{mx}/{mx}）"


async def status_line(conn, steward_id: int, *, hut_built: bool) -> str:
    if not hut_built:
        return ""
    bits = []
    for key, label in (("fridge", "冰箱"), ("stove", "灶")):
        if not await has_appliance(conn, steward_id, key):
            continue
        dur, mx = await _get(conn, steward_id, key)
        warn = "⚠" if dur / max(1, mx) < 0.35 else ""
        bits.append(f"{label}{dur}/{mx}{warn}")
    if not bits:
        return ""
    return "厨电 " + " · ".join(bits) + " · hut_ops 修冰箱|修灶"
