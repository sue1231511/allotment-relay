"""房屋耐久 — 第三批：屋顶随天气磨损。"""
from __future__ import annotations

import random

from . import db, world

DEFAULT_ROOF = 100


async def ensure_table(conn) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS steward_hut_roof (
            steward_id INTEGER PRIMARY KEY,
            roof INTEGER NOT NULL,
            max_roof INTEGER NOT NULL
        )
        """
    )


async def get_roof(conn, steward_id: int) -> tuple[int, int]:
    await ensure_table(conn)
    cur = await conn.execute(
        "SELECT roof, max_roof FROM steward_hut_roof WHERE steward_id=?",
        (steward_id,),
    )
    row = await cur.fetchone()
    if row:
        return int(row[0]), int(row[1])
    await conn.execute(
        "INSERT INTO steward_hut_roof (steward_id, roof, max_roof) VALUES (?, ?, ?)",
        (steward_id, DEFAULT_ROOF, DEFAULT_ROOF),
    )
    return DEFAULT_ROOF, DEFAULT_ROOF


async def maybe_weather_wear(conn, steward_id: int, *, hut_built: bool) -> str | None:
    if not hut_built:
        return None
    if random.random() > 0.22:
        return None
    loss = 2
    w = world.current_weather()
    if w in ("gale", "storm", "rain"):
        loss = 5
    elif w == "misty":
        loss = 3
    roof, mx = await get_roof(conn, steward_id)
    roof = max(0, roof - loss)
    await conn.execute(
        "UPDATE steward_hut_roof SET roof=? WHERE steward_id=?",
        (roof, steward_id),
    )
    if roof <= 25:
        return f"屋顶漏雨（耐久 {roof}/{mx}）→ hut_ops 修屋顶"
    return None


def sleep_penalty(roof: int, max_roof: int) -> int:
    if max_roof <= 0:
        return 0
    ratio = roof / max_roof
    if ratio >= 0.5:
        return 0
    if ratio >= 0.25:
        return 4
    return 8


async def repair(conn, steward_id: int, tickets: int = 14) -> str:
    roof, mx = await get_roof(conn, steward_id)
    if roof >= mx:
        return f"屋顶完好（{roof}/{mx}）"
    cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (steward_id,))
    have = int((await cur.fetchone())[0])
    if have < tickets:
        raise ValueError(f"修屋顶要 {tickets} 票，你只有 {have}")
    nail = await db.take_item(conn, steward_id, "drift_twine", 1)
    cost = tickets if nail else tickets + 4
    if have < cost:
        if nail:
            await db.add_item(conn, steward_id, "drift_twine", 1)
        raise ValueError(f"修屋顶要 {cost} 票{'（已用漂绳）' if nail else '（或备漂绳省4票）'}")
    await conn.execute(
        "UPDATE stewards SET tickets=tickets-? WHERE id=?",
        (cost, steward_id),
    )
    await conn.execute(
        "UPDATE steward_hut_roof SET roof=max_roof WHERE steward_id=?",
        (steward_id,),
    )
    extra = "，用了漂绳" if nail else ""
    return f"屋顶补好了（-{cost} 票{extra}，回满 {mx}）"


async def status_line(conn, steward_id: int) -> str:
    roof, mx = await get_roof(conn, steward_id)
    pct = int(100 * roof / mx) if mx else 0
    return f"屋顶 {roof}/{mx}（{pct}%）低则睡觉少回精力"
