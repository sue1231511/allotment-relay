"""船体损耗 — 第二批：航程磨 hull，低则 boat_damaged。"""
from __future__ import annotations

import random

from . import db

DEFAULT_HULL = 100


async def ensure_table(conn) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS steward_boat_hull (
            steward_id INTEGER PRIMARY KEY,
            hull INTEGER NOT NULL,
            max_hull INTEGER NOT NULL
        )
        """
    )


async def get_hull(conn, steward_id: int) -> tuple[int, int]:
    await ensure_table(conn)
    cur = await conn.execute(
        "SELECT hull, max_hull FROM steward_boat_hull WHERE steward_id=?",
        (steward_id,),
    )
    row = await cur.fetchone()
    if row:
        return int(row[0]), int(row[1])
    await conn.execute(
        "INSERT INTO steward_boat_hull (steward_id, hull, max_hull) VALUES (?, ?, ?)",
        (steward_id, DEFAULT_HULL, DEFAULT_HULL),
    )
    return DEFAULT_HULL, DEFAULT_HULL


async def wear_after_voyage(conn, steward_id: int, route_key: str, *, storm: bool = False) -> str:
    loss_map = {"near": 4, "far": 7, "deep": 11}
    loss = loss_map.get(route_key, 6)
    if storm:
        loss += 6
    hull, mx = await get_hull(conn, steward_id)
    hull = max(0, hull - loss)
    await conn.execute(
        "UPDATE steward_boat_hull SET hull=? WHERE steward_id=?",
        (hull, steward_id),
    )
    note = f"船体 {hull}/{mx}"
    if hull <= 20:
        if random.random() < 0.45:
            await conn.execute(
                "UPDATE stewards SET boat_damaged=1 WHERE id=?",
                (steward_id,),
            )
            note += "，船体吃不住→待修"
    elif hull <= 35:
        note += "，该保养了"
    return note


async def repair_full(conn, steward_id: int) -> None:
    hull, mx = await get_hull(conn, steward_id)
    await conn.execute(
        "UPDATE steward_boat_hull SET hull=max_hull WHERE steward_id=?",
        (steward_id,),
    )


async def status_line(conn, steward_id: int) -> str:
    hull, mx = await get_hull(conn, steward_id)
    pct = int(100 * hull / mx) if mx else 0
    return f"船体 {hull}/{mx}（{pct}%）tide_ops voyage repair 会一并补满"
