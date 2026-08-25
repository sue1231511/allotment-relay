"""精力 — 出海/撒网/赶海消耗，吃饭恢复。"""

from __future__ import annotations

from typing import Any

import aiosqlite

from . import config, db, flavor


def low_energy_hint(current: int, cap: int, amount: int, nag: str = "") -> str:
    """精力不够时给 AI 的完整回复路径，能直接复制 command。"""
    return (
        f"精力不足（{current}/{cap}），这次要 {amount}。先回精力再干活：\n"
        "· 家里吃：kitchen_ops eat 熟菜（回得最多，22 起）。"
        "生吃水果/生鱼/野薄荷只能垫一下（水果只回 4、连吃 5 口营养不良）；"
        "蔬菜不能生吃；生肉能垫但可能感染。\n"
        "· 下馆子：kitchen_ops shop board 看谁在营业，再 kitchen_ops shop dine 店主名"
        " —— 堂食按菜价回精力（约 3.5 票/1 精力），还带「饱餐」2 小时（行动精力 -1）。"
        "没菜就换一家，不要自己编馆名。\n"
        "· 睡觉：hut_ops 睡（装了床每天一次，回 50~54）。\n"
        "· 路过：steward_ops sheet 档口会慢慢回。\n"
        "· 有 5 精力且小橘今晚开嗓：star_ops 围观 也能回。"
        f"{nag}\n"
        "实在没钱吃饭、饿得干不动活：bar_ops lodge — 酒馆包宿（管饭+工钱15，干一整天）"
    )


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
    cur = await conn.execute(
        "SELECT energy, dine_buff_until FROM stewards WHERE id=?", (steward_id,)
    )
    row = await cur.fetchone()
    # 堂食「饱餐」：期间行动精力消耗 -1（最低 1），先于余额判定生效
    if row and int(row[1] or 0) > db.now():
        amount = max(1, amount - config.DINE_BUFF_ENERGY_SAVE)
    current = row[0] if row else config.START_ENERGY
    if current < amount:
        nag = ""
        if ailments:
            nag = f"（还带伤：{'、'.join(a['name'] for a in ailments[:2])}，visit_ops clinic treat）"
        raise ValueError(low_energy_hint(current, cap, amount, nag))
    await conn.execute(
        "UPDATE stewards SET energy = energy - ? WHERE id=?",
        (amount, steward_id),
    )
    if action:
        from . import bond
        await bond.from_energy(conn, steward_id, action, spent=amount)


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
    left = int(steward.get("dine_buff_until") or 0) - db.now()
    if left > 0:
        fed = f"饱餐中：行动 -1 精力，剩 {left // 60 + 1} 分钟"
        hint = f"{hint}；{fed}" if hint else fed
    return f"精力 {e}/{cap}" + (f"（{hint}）" if hint else "")


async def net_energy_cost(conn: aiosqlite.Connection, steward_id: int) -> tuple[int, float, int, float]:
    """Return (energy, catch_bonus, rarity_bonus, empty_reduce) from net tier."""
    from . import gear

    stats = await gear.get_stats(conn, steward_id)
    net = stats["net"]
    if net["tier"] <= 0:
        return 14, 0.0, 0, 0.0
    return net["energy"], net["catch"], net["rarity"], net["empty"]
