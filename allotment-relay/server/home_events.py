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
    if roll < 0.30:
        await db.add_item(conn, steward["id"], "compost", 1)
        return f"夜里 {partner} 把厨余收进堆肥桶，多了一格堆肥。"
    if roll < 0.48:
        return f"{partner} 说屋顶又响了一声——不是坏事，只是潮风。hut_ops 修屋顶 可补。"
    if roll < 0.62:
        await conn.execute(
            "UPDATE stewards SET mist_wit=MIN(100, mist_wit+2) WHERE id=?",
            (steward["id"],),
        )
        return f"两人对坐说了会儿话，雾智 +2（{partner}）。"
    if roll < 0.76:
        cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (steward["id"],))
        have = int((await cur.fetchone())[0])
        if have >= 5:
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (5, steward["id"]),
            )
            return f"半夜灯芯爆了，{partner} 摸黑换了一截（-5 票）。"
        return f"{partner} 想换灯芯，口袋票不够，只好先睡。"
    if roll < 0.88:
        await conn.execute(
            "UPDATE stewards SET standing=MIN(100, standing+1) WHERE id=?",
            (steward["id"],),
        )
        return f"{partner} 替你回了邻居一句招呼，岛缘 +1。"
    if roll < 0.95:
        await survival_bump_satiety(conn, steward["id"], 3)
        return f"{partner} 热了碗剩饭，你半梦半醒吃了两口（饱食 +3）。"
    return f"{partner} 把你的外套挂到门后，没吵醒你。"


async def survival_bump_satiety(conn, steward_id: int, amount: int) -> None:
    from . import survival

    await survival.bump(conn, steward_id, satiety=amount)


async def roll_on_status(conn, steward: dict) -> str | None:
    """看屋时偶发一句（不扣资源为主）。"""
    ctx = await _home_context(conn, steward["id"])
    if not ctx or random.random() > 0.11:
        return None
    partner = ctx["partner"] or "伴侣"
    roll = random.random()
    if roll < 0.4:
        return f"🏠 小插曲：{partner} 刚把门廊扫过，地上还湿。"
    if roll < 0.65:
        return f"🏠 小插曲：{partner} 在窗边看潮，回头冲你点了点头。"
    if roll < 0.82:
        return f"🏠 小插曲：两人晒的衣还在绳上，{partner} 说别收，风正好。"
    return f"🏠 小插曲：{partner} 把你忘在灶边的网坠收进行囊了。"
