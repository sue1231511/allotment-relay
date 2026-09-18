"""集市麻烦档：阵风掀摊，三选一（压石 / 收摊 / 硬摆）。"""
from __future__ import annotations

import json
import random
from typing import Any

from . import db, energy


HAZARD_GUST = "gust"


async def ensure_columns(conn) -> None:
    for ddl in (
        "ALTER TABLE stewards ADD COLUMN market_hazard TEXT",
        "ALTER TABLE stewards ADD COLUMN market_hazard_json TEXT",
    ):
        try:
            await conn.execute(ddl)
        except Exception:
            pass


async def get_hazard(conn, steward_id: int) -> str:
    await ensure_columns(conn)
    cur = await conn.execute(
        "SELECT market_hazard FROM stewards WHERE id=?",
        (steward_id,),
    )
    row = await cur.fetchone()
    return (row[0] or "") if row else ""


def _chance() -> float:
    from . import world

    w = world.current_weather()
    base = 0.09
    if w in ("gale", "storm"):
        base = 0.22
    elif w == "rain":
        base = 0.14
    return base


async def maybe_after_sell(conn, steward_id: int) -> str | None:
    if await get_hazard(conn, steward_id):
        return None
    if random.random() > _chance():
        return None
    await ensure_columns(conn)
    await conn.execute(
        """
        UPDATE stewards SET market_hazard=?, market_hazard_json=?
        WHERE id=?
        """,
        (HAZARD_GUST, json.dumps({"kind": "stall_gust"}, ensure_ascii=False), steward_id),
    )
    return (
        "一阵风把摊布掀起来了！"
        " tote_ops 摊险 压石|收摊|硬摆"
        "（压石=砖×1或8票；收摊=6精力撤一单；硬摆=10精力可能丢货）"
    )


async def assert_not_blocked(conn, steward_id: int) -> None:
    if await get_hazard(conn, steward_id) == HAZARD_GUST:
        raise ValueError(
            "摊还在晃，先 tote_ops 摊险 压石|收摊|硬摆。"
            "人类 /island 集市「我的摊」也能点。"
        )


def ui_actions(*, tickets: int, stock: dict[str, int], energy_now: int) -> list[dict[str, Any]]:
    brick = int(stock.get("quarry_brick") or 0)
    return [
        {
            "action": "压石",
            "label": "压石",
            "hint": "砖×1 或 8 票",
            "can": brick >= 1 or tickets >= 8,
            "disabled_reason": "缺砖且票不够 8",
        },
        {
            "action": "收摊",
            "label": "收摊",
            "hint": "6 精力撤一单",
            "can": energy_now >= 6,
            "disabled_reason": "精力不够 6",
        },
        {
            "action": "硬摆",
            "label": "硬摆",
            "hint": "10 精力",
            "can": energy_now >= 10,
            "disabled_reason": "精力不够 10",
        },
    ]


async def resolve(conn, steward: dict[str, Any], choice: str) -> str:
    if await get_hazard(conn, steward["id"]) != HAZARD_GUST:
        raise ValueError("没有掀摊待决。tote_ops market mine 看摊")
    ch = (choice or "").strip().lower()
    norm = None
    for zh, en in (("压石", "weight"), ("收摊", "fold"), ("硬摆", "hold")):
        if ch in (zh, en):
            norm = zh
            break
    if not norm:
        raise ValueError("摊险处置：压石 · 收摊 · 硬摆（例 tote_ops 摊险 压石）")
    sid = steward["id"]

    if norm == "压石":
        paid = ""
        if not await db.take_item(conn, sid, "quarry_brick", 1):
            cost = 8
            have = int((await (await conn.execute(
                "SELECT tickets FROM stewards WHERE id=?", (sid,)
            )).fetchone())[0])
            if have < cost:
                raise ValueError("压石要页岩砖×1 或 8 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (cost, sid),
            )
            paid = f"-{cost} 票"
        else:
            paid = "页岩砖×1"
        await _clear(conn, sid)
        return f"压好角石，摊布不再乱飞。（{paid}）"

    if norm == "收摊":
        await energy.spend(conn, sid, 6, action="集市收摊")
        cur = await conn.execute(
            """
            SELECT id, item, quantity FROM market_listings
            WHERE seller_id=? AND buyer_id IS NULL ORDER BY created_at DESC LIMIT 1
            """,
            (sid,),
        )
        row = await cur.fetchone()
        if row:
            await db.add_item(conn, sid, row[1], int(row[2]))
            await conn.execute("DELETE FROM market_listings WHERE id=?", (row[0],))
            extra = f"最新一单 #{row[0]} 已下架回行囊。"
        else:
            extra = "摊上空了，风也停了。"
        await _clear(conn, sid)
        return f"收摊喘口气。（{extra}）"

    await energy.spend(conn, sid, 10, action="集市硬摆")
    lost = ""
    if random.random() < 0.35:
        cur = await conn.execute(
            """
            SELECT id, item, quantity FROM market_listings
            WHERE seller_id=? AND buyer_id IS NULL ORDER BY created_at LIMIT 1
            """,
            (sid,),
        )
        row = await cur.fetchone()
        if row and int(row[2]) > 1:
            await conn.execute(
                "UPDATE market_listings SET quantity=quantity-1 WHERE id=?",
                (row[0],),
            )
            lost = "有一件货被风刮跑了。"
        elif row:
            await conn.execute("DELETE FROM market_listings WHERE id=?", (row[0],))
            lost = "有一单被风刮没了。"
    await _clear(conn, sid)
    return f"硬拽住摊脚，继续卖。{lost}"


async def _clear(conn, steward_id: int) -> None:
    await ensure_columns(conn)
    await conn.execute(
        "UPDATE stewards SET market_hazard=NULL, market_hazard_json=NULL WHERE id=?",
        (steward_id,),
    )
