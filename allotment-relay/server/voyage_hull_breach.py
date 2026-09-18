"""出海麻烦档：船体渗水，三选一（堵缝 / 泵水 / 硬航）。"""
from __future__ import annotations

import json
import random

from . import db, energy


async def maybe_mid_voyage(
    conn,
    steward_id: int,
    voyage_id: int,
    *,
    hull_ratio: float,
    route_key: str,
) -> str | None:
    chance = 0.05
    if hull_ratio < 0.35:
        chance = 0.2
    elif hull_ratio < 0.55:
        chance = 0.11
    from . import world

    if world.current_weather() in ("gale", "storm"):
        chance += 0.06
    if random.random() > chance:
        return None
    cur = await conn.execute("SELECT status FROM voyages WHERE id=?", (voyage_id,))
    row = await cur.fetchone()
    if not row or row[0] != "sailing":
        return None
    payload = {"type": "hull_breach", "route": route_key}
    await conn.execute(
        "UPDATE voyages SET status='hull_breach', encounter=? WHERE id=?",
        (json.dumps(payload, ensure_ascii=False), voyage_id),
    )
    return (
        "船底进了水！"
        " tide_ops 船漏 堵|泵|硬航"
        "（堵=铜钉×1或12票；泵=10精力；硬航=蚀 hull 再损）"
    )


async def resolve(conn, steward: dict, voyage: dict, choice: str) -> str:
    if voyage.get("status") != "hull_breach":
        raise ValueError("没有船漏待决。tide_ops voyage status")
    ch = (choice or "").strip().lower()
    norm = None
    for zh, en in (("堵", "plug"), ("泵", "pump"), ("硬航", "sail")):
        if ch in (zh, en):
            norm = zh
            break
    if not norm:
        raise ValueError("船漏：堵 · 泵 · 硬航（例 tide_ops 船漏 堵）")
    sid = steward["id"]
    vid = voyage["id"]

    if norm == "堵":
        paid = ""
        if not await db.take_item(conn, sid, "craft_copper_nails", 1):
            cost = 12
            have = int((await (await conn.execute(
                "SELECT tickets FROM stewards WHERE id=?", (sid,)
            )).fetchone())[0])
            if have < cost:
                raise ValueError("堵缝要铜钉×1 或 12 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (cost, sid),
            )
            paid = f"-{cost} 票"
        else:
            paid = "铜钉×1"
        await _resume(conn, vid)
        return f"钉上补丁，水止住了。（{paid}）继续航行。"

    if norm == "泵":
        await energy.spend(conn, sid, 10, action="船泵水")
        await _resume(conn, vid)
        return "一桶桶舀出去，甲板又干了。继续航行。"

    from . import boat_hull as hull_mod

    hull, mx = await hull_mod.get_hull(conn, sid)
    loss = max(8, int(mx * 0.08))
    await conn.execute(
        "UPDATE steward_boat_hull SET hull=MAX(0, hull-?) WHERE steward_id=?",
        (loss, sid),
    )
    await _resume(conn, vid)
    hull2, mx2 = await hull_mod.get_hull(conn, sid)
    return f"硬扛过去（船体 {hull2}/{mx2}）。再漏就待修。"


async def _resume(conn, voyage_id: int) -> None:
    await conn.execute(
        "UPDATE voyages SET status='sailing' WHERE id=? AND status='hull_breach'",
        (voyage_id,),
    )
