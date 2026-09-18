"""家庭随机事件 — 第三批：成婚且登记居所时，睡觉/看屋小插曲。"""
from __future__ import annotations

import random

from . import db


async def _home_context(conn, steward_id: int) -> dict | None:
    cur = await conn.execute(
        """
        SELECT partner_name, home_hut, status FROM marriages
        WHERE steward_id=? AND status IN ('married','engaged') AND home_hut=1
        ORDER BY id DESC LIMIT 1
        """,
        (steward_id,),
    )
    row = await cur.fetchone()
    if not row:
        return None
    return {"partner": row[0], "status": row[2]}


async def roll_on_sleep(conn, steward: dict) -> str | None:
    ctx = await _home_context(conn, steward["id"])
    if not ctx or random.random() > 0.14:
        return None
    partner = ctx["partner"] or "伴侣"
    roll = random.random()
    if roll < 0.35:
        await db.add_item(conn, steward["id"], "compost", 1)
        return f"夜里 {partner} 把厨余收进堆肥桶，多了一格堆肥。"
    if roll < 0.55:
        return f"{partner} 说屋顶又响了一声——不是坏事，只是潮风。hut_ops 修屋顶 可补。"
    if roll < 0.72:
        await conn.execute(
            "UPDATE stewards SET mist_wit=MIN(100, mist_wit+2) WHERE id=?",
            (steward["id"],),
        )
        return f"两人对坐说了会儿话，雾智 +2（{partner}）。"
    if roll < 0.88:
        cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (steward["id"],))
        have = int((await cur.fetchone())[0])
        if have >= 5:
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (5, steward["id"]),
            )
            return f"半夜灯芯爆了，{partner} 摸黑换了一截（-5 票）。"
        return f"{partner} 想换灯芯，口袋票不够，只好先睡。"
    return f"{partner} 把你的外套挂到门后，没吵醒你。"
