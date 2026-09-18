"""井蚀 — 第三批：潮下井壁随下井次数磨损。"""
from __future__ import annotations

from . import db

MAX_CORROSION = 100
WARN_AT = 70
BLOCK_AT = 92


async def ensure_column(conn) -> None:
    try:
        await conn.execute(
            "ALTER TABLE steward_undertide ADD COLUMN well_corrosion INTEGER NOT NULL DEFAULT 0"
        )
    except Exception:
        pass


async def get_level(conn, steward_id: int) -> int:
    await ensure_column(conn)
    cur = await conn.execute(
        "SELECT COALESCE(well_corrosion, 0) FROM steward_undertide WHERE steward_id=?",
        (steward_id,),
    )
    row = await cur.fetchone()
    return int(row[0]) if row else 0


async def bump(conn, steward_id: int, amount: int = 3) -> str | None:
    await ensure_column(conn)
    lvl = await get_level(conn, steward_id)
    if lvl >= BLOCK_AT:
        raise ValueError(
            f"井壁蚀穿（{lvl}/{MAX_CORROSION}），先 undertide_ops 清井 再 descend"
        )
    new = min(MAX_CORROSION, lvl + amount)
    await conn.execute(
        "UPDATE steward_undertide SET well_corrosion=? WHERE steward_id=?",
        (new, steward_id),
    )
    if new >= WARN_AT and lvl < WARN_AT:
        return f"井壁发潮（蚀 {new}/{MAX_CORROSION}）→ undertide_ops 清井"
    return None


async def clean(conn, steward_id: int, tickets: int = 20) -> str:
    lvl = await get_level(conn, steward_id)
    if lvl <= 5:
        return f"井壁尚净（{lvl}/{MAX_CORROSION}）"
    cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (steward_id,))
    have = int((await cur.fetchone())[0])
    if have < tickets:
        raise ValueError(f"清井要 {tickets} 票，你只有 {have}")
    await conn.execute(
        "UPDATE stewards SET tickets=tickets-? WHERE id=?",
        (tickets, steward_id),
    )
    cut = min(lvl, 35)
    await conn.execute(
        "UPDATE steward_undertide SET well_corrosion=MAX(0, well_corrosion-?) WHERE steward_id=?",
        (cut, steward_id),
    )
    return f"清井完成（-{tickets} 票，蚀度 -{cut}，现 {max(0, lvl-cut)}/{MAX_CORROSION}）"


async def status_line(conn, steward_id: int) -> str:
    lvl = await get_level(conn, steward_id)
    return f"井蚀 {lvl}/{MAX_CORROSION}" + (" ⚠" if lvl >= WARN_AT else "")
