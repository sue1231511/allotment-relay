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
    cap = health.max_energy_cap(ailments)
    cur = await conn.execute("SELECT energy FROM stewards WHERE id=?", (steward_id,))
    row = await cur.fetchone()
    current = row[0] if row else config.START_ENERGY
    if current < amount:
        nag = ""
        if ailments:
            nag = f"（还带伤：{'、'.join(a['name'] for a in ailments[:2])}，visit_ops clinic treat）"
        raise ValueError(
            f"精力不足（{current}/{cap}），需要 {amount}。"
            "恢复：kitchen_ops eat 熟菜，或生吃作物/生鱼/野薄荷（安全，不会感染）；"
            f"生肉也能垫但可能感染。steward_ops sheet 路过档口会慢慢回{nag}"
        )
    await conn.execute(
        "UPDATE stewards SET energy = energy - ? WHERE id=?",
        (amount, steward_id),
    )


async def _energy_cap(conn: aiosqlite.Connection, steward_id: int) -> int:
    from . import health

    ailments = await health.list_ailments(conn, steward_id)
    return health.max_energy_cap(ailments)


async def restore(
    conn: aiosqlite.Connection,
    steward_id: int,
    amount: int,
) -> int:
    from . import health

    ailments = await health.list_ailments(conn, steward_id)
    cap = health.max_energy_cap(ailments)
    cur = await conn.execute("SELECT energy FROM stewards WHERE id=?", (steward_id,))
    row = await cur.fetchone()
    stored = row[0] if row else config.START_ENERGY
    base = min(stored, cap)
    new_val = min(cap, base + amount)
    await conn.execute(
        "UPDATE stewards SET energy = ? WHERE id=?",
        (new_val, steward_id),
    )
    return max(0, new_val - stored) if stored <= cap else 0


async def soft_regen(conn: aiosqlite.Connection, steward_id: int) -> None:
    """查看档口时微量回精力。带长期耗精力的病时不回。"""
    from . import health

    if await health.has_chronic_drain(conn, steward_id):
        return
    cap = await _energy_cap(conn, steward_id)
    await conn.execute(
        """
        UPDATE stewards SET energy = MIN(?, energy + ?)
        WHERE id=? AND energy < ?
        """,
        (cap, config.ENERGY_REGEN_IDLE, steward_id, cap - 2),
    )


def meter_line(steward: dict[str, Any], ailments: list[dict[str, Any]] | None = None) -> str:
    from . import health

    e = steward.get("energy", config.START_ENERGY)
    cap = health.max_energy_cap(ailments or [])
    hint = ""
    if e < 20:
        hint = flavor.pick([
            "快饿扁了，厨房见",
            "没劲撒网，先整口热乎的",
            "精力见底，别硬撑",
        ])
    return f"精力 {e}/{cap}" + (f"（{hint}）" if hint else "")


async def net_energy_cost(conn: aiosqlite.Connection, steward_id: int) -> tuple[int, float, int, float]:
    """Return (energy, catch_bonus, rarity_bonus, empty_reduce) from net tier."""
    from . import gear

    stats = await gear.get_stats(conn, steward_id)
    net = stats["net"]
    if net["tier"] <= 0:
        return 14, 0.0, 0, 0.0
    return net["energy"], net["catch"], net["rarity"], net["empty"]
