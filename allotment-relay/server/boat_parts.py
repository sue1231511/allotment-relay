"""船只部件 — 第二批：帆/舵/灯。"""
from __future__ import annotations

import random

from . import db

PARTS = ("sail", "rudder", "lantern")
DEFAULT = 100


async def ensure_table(conn) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS steward_boat_parts (
            steward_id INTEGER NOT NULL,
            part_key TEXT NOT NULL,
            durability INTEGER NOT NULL,
            max_dur INTEGER NOT NULL,
            PRIMARY KEY (steward_id, part_key)
        )
        """
    )


async def get_all(conn, steward_id: int) -> dict[str, tuple[int, int]]:
    await ensure_table(conn)
    out: dict[str, tuple[int, int]] = {}
    for p in PARTS:
        cur = await conn.execute(
            "SELECT durability, max_dur FROM steward_boat_parts WHERE steward_id=? AND part_key=?",
            (steward_id, p),
        )
        row = await cur.fetchone()
        if row:
            out[p] = (int(row[0]), int(row[1]))
        else:
            await conn.execute(
                """
                INSERT INTO steward_boat_parts (steward_id, part_key, durability, max_dur)
                VALUES (?, ?, ?, ?)
                """,
                (steward_id, p, DEFAULT, DEFAULT),
            )
            out[p] = (DEFAULT, DEFAULT)
    return out


async def wear_voyage(conn, steward_id: int, route: str, *, storm: bool) -> str:
    loss = {"near": 2, "far": 4, "deep": 6}.get(route, 3)
    if storm:
        loss += 4
    parts = await get_all(conn, steward_id)
    notes = []
    for key, (dur, mx) in parts.items():
        extra = 1 if key == "sail" and storm else 0
        new = max(0, dur - loss - extra)
        await conn.execute(
            "UPDATE steward_boat_parts SET durability=? WHERE steward_id=? AND part_key=?",
            (new, steward_id, key),
        )
        label = {"sail": "帆", "rudder": "舵", "lantern": "灯"}.get(key, key)
        notes.append(f"{label}{new}/{mx}")
    return "部件 " + " · ".join(notes)


def fail_bonus(parts: dict[str, tuple[int, int]]) -> float:
    sail = parts.get("sail", (100, 100))[0] / max(1, parts.get("sail", (100, 100))[1])
    rudder = parts.get("rudder", (100, 100))[0] / max(1, parts.get("rudder", (100, 100))[1])
    extra = 0.0
    if sail < 0.35:
        extra += 0.08
    elif sail < 0.55:
        extra += 0.04
    if rudder < 0.35:
        extra += 0.06
    return extra


async def repair_all(conn, steward_id: int, tickets: int = 18) -> str:
    cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (steward_id,))
    have = int((await cur.fetchone())[0])
    if have < tickets:
        raise ValueError(f"修部件要 {tickets} 票，你只有 {have}")
    nail = await db.take_item(conn, steward_id, "craft_copper_nails", 1)
    cost = tickets if nail else tickets + 6
    if have < cost:
        if nail:
            await db.add_item(conn, steward_id, "craft_copper_nails", 1)
        raise ValueError(f"修部件要 {cost} 票{'（或备铜钉省6票）' if not nail else ''}")
    await conn.execute(
        "UPDATE stewards SET tickets=tickets-? WHERE id=?", (cost, steward_id),
    )
    await conn.execute(
        "UPDATE steward_boat_parts SET durability=max_dur WHERE steward_id=?",
        (steward_id,),
    )
    return f"帆/舵/灯回满（-{cost} 票{'·用钉' if nail else ''}）"


async def status_line(conn, steward_id: int) -> str:
    parts = await get_all(conn, steward_id)
    bits = []
    for key in PARTS:
        d, mx = parts[key]
        label = {"sail": "帆", "rudder": "舵", "lantern": "灯"}[key]
        bits.append(f"{label}{d}/{mx}")
    return "船部件 " + " · ".join(bits) + " · voyage_ops 部件 修"
