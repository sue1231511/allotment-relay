"""待维修总览 — steward_ops 维修 聚合各系统。"""
from __future__ import annotations

from . import db


async def digest(conn, steward_id: int) -> str:
    lines = ["待办维修 / 处置（按优先级粗排）："]
    n = 0
    s = await db.get_steward_by_id(steward_id)
    cur = await conn.execute(
        "SELECT boat_damaged, boat_key FROM stewards WHERE id=?",
        (steward_id,),
    )
    row = await cur.fetchone()
    if row and int(row[0]):
        lines.append("  · 船体损坏 → tide_ops voyage repair")
        n += 1
    if row and row[1]:
        from . import boat_parts as parts_mod
        parts = await parts_mod.get_all(conn, steward_id)
        low = [parts_mod.PART_LABELS.get(k, k) for k, (d, mx) in parts.items() if d < mx * 0.35]
        if low:
            lines.append(f"  · 船部件偏低（{','.join(low[:4])}）→ tide_ops 船件 修")
            n += 1
        from . import boat_mods as bmods_mod
        await bmods_mod.ensure_table(conn)
        mod_line = await bmods_mod.status_line(conn, steward_id)
        if "0/" not in mod_line and "空" not in mod_line:
            lines.append(f"  · {mod_line}")
    cur = await conn.execute(
        """
        SELECT slot, hazard FROM quarry_claims
        WHERE steward_id=? AND hazard IS NOT NULL AND hazard != ''
        LIMIT 3
        """,
        (steward_id,),
    )
    for slot, haz in await cur.fetchall():
        lines.append(f"  · 盐风崖 #{slot} {haz} → quarry_ops 塌方 {slot}")
        n += 1
    from . import hut_chores as chore_mod
    ck = await chore_mod.get_chore(conn, steward_id)
    if ck:
        lines.append(f"  · 小屋杂务 pending → hut_ops 杂务")
        n += 1
    from . import undertide_well_crack as crack_mod
    await crack_mod.ensure_columns(conn)
    wh = await crack_mod.get_hazard(conn, steward_id)
    if wh:
        lines.append("  · 井壁裂 → undertide_ops 井险 清井|绑索|硬闯")
        n += 1
    cur = await conn.execute(
        "SELECT well_hazard FROM steward_undertide WHERE steward_id=?",
        (steward_id,),
    )
    r2 = await cur.fetchone()
    if r2 and r2[0] and not wh:
        lines.append(f"  · 潮下井况 {r2[0]} → undertide_ops 井险")
        n += 1
    if s:
        from . import bar as bar_mod
        if bar_mod.is_shift_overdue(s):
            lines.append("  · 酒吧考勤逾期 → bar_ops work")
            n += 1
    from . import bad_event_tier_store as tier_store_mod

    open_tiers = await tier_store_mod.list_open(conn, steward_id, limit=4)
    for row in open_tiers:
        lines.append(f"  · {row['line']}")
        n += 1
    if n == 0:
        return "暂无集中待维修项。分散 debuff 看 sheet；坏事件档位居【轻中重绝】。steward_ops 灾档 看持久化记录。"
    lines.append(f"共 {n} 类。详情仍看各工具 status · steward_ops 灾档")
    return "\n".join(lines)
