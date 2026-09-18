"""第一批：轻微随机坏事件（鸟啄、脱钩提示、家具发潮等）。"""
from __future__ import annotations

import random

from . import db


async def ensure_flags_table(conn) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS steward_moment_flags (
            steward_id INTEGER NOT NULL REFERENCES stewards(id),
            flag_key TEXT NOT NULL,
            PRIMARY KEY (steward_id, flag_key)
        )
        """
    )


async def set_flag(conn, steward_id: int, flag_key: str) -> None:
    await ensure_flags_table(conn)
    await conn.execute(
        "INSERT OR REPLACE INTO steward_moment_flags (steward_id, flag_key) VALUES (?, ?)",
        (steward_id, flag_key),
    )


async def has_flag(conn, steward_id: int, flag_key: str) -> bool:
    await ensure_flags_table(conn)
    cur = await conn.execute(
        "SELECT 1 FROM steward_moment_flags WHERE steward_id=? AND flag_key=?",
        (steward_id, flag_key),
    )
    return (await cur.fetchone()) is not None


async def take_flag(conn, steward_id: int, flag_key: str) -> bool:
    await ensure_flags_table(conn)
    cur = await conn.execute(
        "SELECT 1 FROM steward_moment_flags WHERE steward_id=? AND flag_key=?",
        (steward_id, flag_key),
    )
    if not await cur.fetchone():
        return False
    await conn.execute(
        "DELETE FROM steward_moment_flags WHERE steward_id=? AND flag_key=?",
        (steward_id, flag_key),
    )
    return True


async def roll_tend_glitch(conn, steward_id: int, plot: dict) -> str | None:
    if random.random() > 0.08:
        return None
    crop = plot.get("crop")
    if not crop:
        return None
    roll = random.random()
    if roll < 0.4:
        left = int(plot.get("harvest_left") or 0)
        if left > 1:
            await conn.execute(
                "UPDATE parcels SET harvest_left=MAX(1, harvest_left-1) WHERE id=?",
                (plot["id"],),
            )
            return "斑鸠啄了一口，这茬收成少了一把（还能收，不是枯病）。"
    if roll < 0.65:
        await set_flag(conn, steward_id, "stove_stubborn")
        return "灶台不好点火：下次做饭多耗 1 精力（已记下，做一次饭就消）。"
    if roll < 0.85:
        return "潮气进棚，软装有发潮味——不影响数值，换晴会好。"
    await set_flag(conn, steward_id, "line_tangle")
    return "鱼线打结了：下次坐钓空杆率 +12%（已记下，坐钓一次就消）。"


async def apply_stove_penalty(conn, steward_id: int) -> int:
    """若灶台难点火，做一次饭多耗 1 精力。返回额外精力。"""
    if await take_flag(conn, steward_id, "stove_stubborn"):
        return 1
    return 0


async def cast_empty_bonus(conn, steward_id: int) -> float:
    """鱼线打结：空杆率加成（消费一次）。"""
    if await take_flag(conn, steward_id, "line_tangle"):
        return 0.12
    return 0.0
