"""钓具拆件 — 第二批：钩、线、卷线器（线耐久在 gear_wear）。"""
from __future__ import annotations

import random

from . import db

PART_KEYS = ("hook", "reel")
DEFAULT_MAX = {"hook": 70, "reel": 90}
WEAR = {"hook": 2, "reel": 1}


async def ensure_table(conn) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS steward_fish_parts (
            steward_id INTEGER NOT NULL,
            part_key TEXT NOT NULL,
            durability INTEGER NOT NULL,
            max_dur INTEGER NOT NULL,
            snagged INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (steward_id, part_key)
        )
        """
    )


async def _get(conn, steward_id: int, part: str) -> tuple[int, int, int]:
    await ensure_table(conn)
    cur = await conn.execute(
        """
        SELECT durability, max_dur, snagged FROM steward_fish_parts
        WHERE steward_id=? AND part_key=?
        """,
        (steward_id, part),
    )
    row = await cur.fetchone()
    if row:
        return int(row[0]), int(row[1]), int(row[2])
    mx = DEFAULT_MAX.get(part, 80)
    await conn.execute(
        """
        INSERT INTO steward_fish_parts (steward_id, part_key, durability, max_dur, snagged)
        VALUES (?, ?, ?, ?, 0)
        """,
        (steward_id, part, mx, mx),
    )
    return mx, mx, 0


async def wear_cast(conn, steward_id: int) -> tuple[bool, str]:
    """Returns (snagged_now, note)."""
    hook_d, hook_mx, snag = await _get(conn, steward_id, "hook")
    reel_d, reel_mx, _ = await _get(conn, steward_id, "reel")
    hook_d = max(0, hook_d - WEAR["hook"])
    reel_d = max(0, reel_d - WEAR["reel"])
    await conn.execute(
        "UPDATE steward_fish_parts SET durability=? WHERE steward_id=? AND part_key='hook'",
        (hook_d, steward_id),
    )
    await conn.execute(
        "UPDATE steward_fish_parts SET durability=? WHERE steward_id=? AND part_key='reel'",
        (reel_d, steward_id),
    )
    if snag:
        return True, f"钩还挂着底（{hook_d}/{hook_mx}）→ tide_ops 解挂 硬拉|切线"
    hang_p = 0.0
    if hook_d / max(1, hook_mx) < 0.35:
        hang_p = 0.10
    if hook_d / max(1, hook_mx) < 0.15:
        hang_p = 0.22
    if random.random() < hang_p:
        await conn.execute(
            "UPDATE steward_fish_parts SET snagged=1 WHERE steward_id=? AND part_key='hook'",
            (steward_id,),
        )
        return True, "挂底了！tide_ops 解挂 硬拉|切线（不切线不能再坐钓）"
    return False, ""


async def clear_snag(conn, steward_id: int, mode: str) -> str:
    _, hook_mx, snag = await _get(conn, steward_id, "hook")
    if not snag:
        return "没有挂底。"
    if mode in ("切", "切线", "cut"):
        await conn.execute(
            """
            UPDATE steward_fish_parts SET snagged=0, durability=MAX(0, durability-25)
            WHERE steward_id=? AND part_key='hook'
            """,
            (steward_id,),
        )
        from . import gear_wear as gear_wear_mod
        await gear_wear_mod.wear(conn, steward_id, "line", amount=15)
        msg = "切线解挂（钩-25，线大损）"
        from . import event_opportunity as opp_mod

        luck = await opp_mod.maybe_line_cut_luck(conn, steward_id, context="unsnag")
        if luck:
            msg += f"\n{luck}"
        return msg
    if mode in ("硬拉", "pull", "拉"):
        if random.random() < 0.45:
            await conn.execute(
                "UPDATE steward_fish_parts SET snagged=0 WHERE steward_id=? AND part_key='hook'",
                (steward_id,),
            )
            return "硬拉上来了，钩还能用"
        await conn.execute(
            """
            UPDATE steward_fish_parts SET snagged=0, durability=MAX(0, durability-18)
            WHERE steward_id=? AND part_key='hook'
            """,
            (steward_id,),
        )
        return "拉断了，钩损（-18）"
    raise ValueError("解挂：硬拉 · 切线（例 tide_ops 解挂 硬拉）")


async def repair(conn, steward_id: int, part: str, tickets: int = 12) -> str:
    if part not in PART_KEYS:
        raise ValueError("可修钩/卷：hook · reel")
    cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (steward_id,))
    have = int((await cur.fetchone())[0])
    if have < tickets:
        raise ValueError(f"修 {part} 要 {tickets} 票，你只有 {have}")
    await conn.execute(
        "UPDATE stewards SET tickets=tickets-? WHERE id=?", (tickets, steward_id),
    )
    _, mx, _ = await _get(conn, steward_id, part)
    await conn.execute(
        """
        UPDATE steward_fish_parts SET durability=max_dur, snagged=0
        WHERE steward_id=? AND part_key=?
        """,
        (steward_id, part),
    )
    label = "鱼钩" if part == "hook" else "卷线器"
    return f"{label} 回满（-{tickets} 票，{mx}/{mx}）"


async def assert_can_cast(conn, steward_id: int) -> None:
    _, _, snag = await _get(conn, steward_id, "hook")
    if snag:
        raise ValueError("钩挂底了。先 tide_ops 解挂 硬拉|切线")


async def status_line(conn, steward_id: int) -> str:
    hook_d, hook_mx, snag = await _get(conn, steward_id, "hook")
    reel_d, reel_mx, _ = await _get(conn, steward_id, "reel")
    s = " ⚠挂底" if snag else ""
    return f"钩 {hook_d}/{hook_mx} · 卷 {reel_d}/{reel_mx}{s}（gear repair hook|reel 12票回满）"
