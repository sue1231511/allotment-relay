"""精力 — 出海/撒网/赶海消耗，吃饭恢复。"""

from __future__ import annotations

from typing import Any

import aiosqlite

from . import config, flavor


async def spend(
    conn: aiosqlite.Connection,
    steward_id: int,
    amount: int,
    *,
    action: str = "",
) -> None:
    if amount <= 0:
        return
    from . import health

    ailments = await health.list_ailments(conn, steward_id)
    amount += health.energy_extra(ailments)
    cur = await conn.execute("SELECT energy FROM stewards WHERE id=?", (steward_id,))
    row = await cur.fetchone()
    current = row[0] if row else config.START_ENERGY
    if current < amount:
        label = action or "此操作"
        nag = ""
        if ailments:
            nag = f"（还带伤：{'、'.join(a['name'] for a in ailments[:2])}，visit_ops clinic treat）"
        raise ValueError(
            f"精力不足（{current}/{config.MAX_ENERGY}），需要 {amount}。"
            f"先 kitchen_ops eat 吃饭回精力{nag}"
        )
    await conn.execute(
        "UPDATE stewards SET energy = energy - ? WHERE id=?",
        (amount, steward_id),
    )


async def restore(
    conn: aiosqlite.Connection,
    steward_id: int,
    amount: int,
) -> int:
    cur = await conn.execute("SELECT energy FROM stewards WHERE id=?", (steward_id,))
    row = await cur.fetchone()
    current = row[0] if row else config.START_ENERGY
    new_val = min(config.MAX_ENERGY, current + amount)
    await conn.execute(
        "UPDATE stewards SET energy = ? WHERE id=?",
        (new_val, steward_id),
    )
    return new_val - current


async def soft_regen(conn: aiosqlite.Connection, steward_id: int) -> None:
    """查看档口时微量回精力。"""
    await conn.execute(
        """
        UPDATE stewards SET energy = MIN(?, energy + ?)
        WHERE id=? AND energy < ?
        """,
        (config.MAX_ENERGY, config.ENERGY_REGEN_IDLE, steward_id, config.MAX_ENERGY - 2),
    )


def meter_line(steward: dict[str, Any]) -> str:
    e = steward.get("energy", config.START_ENERGY)
    hint = ""
    if e < 20:
        hint = flavor.pick([
            "快饿扁了，厨房见",
            "没劲撒网，先整口热乎的",
            "精力见底，别硬撑",
        ])
    return f"精力 {e}/{config.MAX_ENERGY}" + (f"（{hint}）" if hint else "")


async def net_energy_cost(conn: aiosqlite.Connection, steward_id: int) -> tuple[int, float, int, float]:
    """Return (energy, catch_bonus, rarity_bonus, empty_reduce) from net tier."""
    from . import gear

    stats = await gear.get_stats(conn, steward_id)
    net = stats["net"]
    if net["tier"] <= 0:
        return 14, 0.0, 0, 0.0
    return net["energy"], net["catch"], net["rarity"], net["empty"]
