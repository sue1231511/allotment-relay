"""共耕 — 高协作邻居：assist 时顺带帮浇一块地（每日一次）。"""
from __future__ import annotations

from . import db

RAPPORT_NEED = 45
COFARM_DAYS = 14


async def ensure_table(conn) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS neighbor_cofarm (
            steward_id INTEGER NOT NULL,
            partner_id INTEGER NOT NULL,
            until_day INTEGER NOT NULL,
            last_assist_day INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (steward_id, partner_id)
        )
        """
    )


async def _rapport(conn, a: int, b: int) -> int:
    from . import social as social_mod
    return await social_mod.get_rapport(a, b, conn=conn)


async def subscribe(conn, owner: dict, partner_name: str) -> str:
    await ensure_table(conn)
    peer = await db.get_steward_by_name(partner_name)
    if not peer:
        raise ValueError("找不到该岛民")
    if peer["id"] == owner["id"]:
        raise ValueError("不能和自己共耕")
    r = await _rapport(conn, owner["id"], peer["id"])
    if r < RAPPORT_NEED:
        raise ValueError(f"共耕需要协作度 ≥{RAPPORT_NEED}（当前 {r}）")
    until = db.day_id() + COFARM_DAYS
    await conn.execute(
        """
        INSERT OR REPLACE INTO neighbor_cofarm
        (steward_id, partner_id, until_day, last_assist_day)
        VALUES (?,?,?,0)
        """,
        (owner["id"], peer["id"], until),
    )
    await db.add_chronicle(
        "assist",
        f"{owner['name']} 与 {peer['name']} 结成共耕（{COFARM_DAYS} 日）",
        owner["id"],
        peer["id"],
        conn=conn,
    )
    return (
        f"已和 {peer['name']} 共耕 {COFARM_DAYS} 日。"
        f"你 assist 对方时，每日首次会多帮浇 1 块未浇的份地。"
    )


async def status(conn, steward_id: int) -> str:
    await ensure_table(conn)
    day = db.day_id()
    cur = await conn.execute(
        """
        SELECT partner_id, until_day FROM neighbor_cofarm
        WHERE steward_id=? AND until_day>=?
        """,
        (steward_id, day),
    )
    rows = await cur.fetchall()
    if not rows:
        return "没有进行中的共耕。alliance_ops 共耕 订 名字"
    lines = ["共耕中（assist 每日首次多浇 1 块地）："]
    for pid, until in rows:
        p = await db.get_steward_by_id(int(pid))
        nm = p["name"] if p else "?"
        lines.append(f"  · {nm}（至游戏日 {until}）")
    return "\n".join(lines)


async def cancel(conn, owner: dict, partner_name: str) -> str:
    peer = await db.get_steward_by_name(partner_name)
    if not peer:
        raise ValueError("找不到该岛民")
    await conn.execute(
        "DELETE FROM neighbor_cofarm WHERE steward_id=? AND partner_id=?",
        (owner["id"], peer["id"]),
    )
    return f"已解除与 {peer['name']} 的共耕"


async def after_assist(conn, helper_id: int, target_id: int) -> str | None:
    """assist 成功后调用。"""
    await ensure_table(conn)
    day = db.day_id()
    cur = await conn.execute(
        """
        SELECT until_day, last_assist_day FROM neighbor_cofarm
        WHERE steward_id=? AND partner_id=? AND until_day>=?
        """,
        (helper_id, target_id, day),
    )
    row = await cur.fetchone()
    if not row or int(row[1]) >= day:
        return None
    cur = await conn.execute(
        """
        SELECT id FROM parcels
        WHERE steward_id=? AND crop IS NOT NULL AND watered=0
        ORDER BY RANDOM() LIMIT 1
        """,
        (target_id,),
    )
    prow = await cur.fetchone()
    if not prow:
        await conn.execute(
            """
            UPDATE neighbor_cofarm SET last_assist_day=?
            WHERE steward_id=? AND partner_id=?
            """,
            (day, helper_id, target_id),
        )
        return None
    await conn.execute("UPDATE parcels SET watered=1 WHERE id=?", (prow[0],))
    await conn.execute(
        """
        UPDATE neighbor_cofarm SET last_assist_day=?
        WHERE steward_id=? AND partner_id=?
        """,
        (day, helper_id, target_id),
    )
    return "共耕：顺手帮浇了 1 块份地。"


async def league_extra_after_assist(conn, helper_id: int, target_id: int) -> str | None:
    """共耕中且本周目标是 assist 时，额外 +1 周目标进度。"""
    await ensure_table(conn)
    day = db.day_id()
    cur = await conn.execute(
        """
        SELECT 1 FROM neighbor_cofarm
        WHERE steward_id=? AND partner_id=? AND until_day>=?
        """,
        (helper_id, target_id, day),
    )
    if not await cur.fetchone():
        return None
    from . import multi as multi_mod
    row = await multi_mod._ensure_league_week(conn)
    if row["completed"] or row["goal_key"] != "assist":
        return None
    bonus = await multi_mod._league_add_progress(conn, helper_id, 1)
    if bonus:
        return bonus
    return "共耕加成：本周 assist 周目标 +1"


async def dispatch(conn, steward: dict, parts: list[str]) -> str:
    await ensure_table(conn)
    if not parts:
        return await status(conn, steward["id"])
    sub = parts[0].lower()
    if sub in ("订", "sub", "结") and len(parts) >= 2:
        return await subscribe(conn, steward, parts[1])
    if sub in ("状态", "status", "list"):
        return await status(conn, steward["id"])
    if sub in ("解", "cancel") and len(parts) >= 2:
        return await cancel(conn, steward, parts[1])
    raise ValueError("共耕 订 名字 · 共耕 状态 · 共耕 解 名字")
