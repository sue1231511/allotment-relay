"""小馆麻烦档：灶台糊烟，三选一（开窗 / 换锅 / 硬烧）。"""
from __future__ import annotations

import json
import random
from typing import Any

from . import db, energy


HAZARD_SMOKE = "smoke"


async def ensure_columns(conn) -> None:
    for ddl in (
        "ALTER TABLE stewards ADD COLUMN eatery_hazard TEXT",
        "ALTER TABLE stewards ADD COLUMN eatery_hazard_json TEXT",
    ):
        try:
            await conn.execute(ddl)
        except Exception:
            pass


async def get_hazard(conn, steward_id: int) -> str:
    await ensure_columns(conn)
    cur = await conn.execute(
        "SELECT eatery_hazard FROM stewards WHERE id=?",
        (steward_id,),
    )
    row = await cur.fetchone()
    return (row[0] or "") if row else ""


async def maybe_after_stock(conn, steward_id: int) -> str | None:
    if await get_hazard(conn, steward_id):
        return None
    if random.random() > 0.14:
        return None
    await ensure_columns(conn)
    await conn.execute(
        """
        UPDATE stewards SET eatery_hazard=?, eatery_hazard_json=?
        WHERE id=?
        """,
        (HAZARD_SMOKE, json.dumps({"kind": "stove"}, ensure_ascii=False), steward_id),
    )
    return (
        "灶台糊了满屋烟！"
        " kitchen_ops 灶险 开窗|换锅|硬烧"
        "（开窗=4精力；换锅=盐×1或10票；硬烧=可能呛咳）"
    )


async def assert_not_blocked(conn, steward_id: int) -> None:
    if await get_hazard(conn, steward_id) == HAZARD_SMOKE:
        raise ValueError(
            "烟还没散，先 kitchen_ops 灶险 开窗|换锅|硬烧。"
            "人类 /island 小馆「我的馆」也能点。"
        )


def ui_actions(*, tickets: int, stock: dict[str, int], energy_now: int) -> list[dict[str, Any]]:
    salt = int(stock.get("quarry_salt") or 0)
    return [
        {
            "action": "开窗",
            "label": "开窗",
            "hint": "4 精力",
            "can": energy_now >= 4,
            "disabled_reason": "精力不够 4",
        },
        {
            "action": "换锅",
            "label": "换锅",
            "hint": "盐×1 或 10 票",
            "can": salt >= 1 or tickets >= 10,
            "disabled_reason": "缺盐且票不够 10",
        },
        {"action": "硬烧", "label": "硬烧", "hint": "免费", "can": True, "disabled_reason": ""},
    ]


async def resolve(conn, steward: dict[str, Any], choice: str) -> str:
    if await get_hazard(conn, steward["id"]) != HAZARD_SMOKE:
        raise ValueError("没有灶险待决。kitchen_ops shop menu 看馆")
    ch = (choice or "").strip().lower()
    norm = None
    for zh, en in (("开窗", "air"), ("换锅", "pan"), ("硬烧", "burn")):
        if ch in (zh, en):
            norm = zh
            break
    if not norm:
        raise ValueError("灶险处置：开窗 · 换锅 · 硬烧（例 kitchen_ops 灶险 开窗）")
    sid = steward["id"]

    if norm == "开窗":
        await energy.spend(conn, sid, 4, action="小馆开窗")
        await _clear(conn, sid)
        return "推开窗，烟散了大半。"

    if norm == "换锅":
        paid = ""
        if not await db.take_item(conn, sid, "quarry_salt", 1):
            cost = 10
            have = int((await (await conn.execute(
                "SELECT tickets FROM stewards WHERE id=?", (sid,)
            )).fetchone())[0])
            if have < cost:
                raise ValueError("换锅要海盐晶×1 或 10 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (cost, sid),
            )
            paid = f"-{cost} 票"
        else:
            paid = "海盐晶×1"
        await _clear(conn, sid)
        return f"换了新锅，火稳了。（{paid}）"

    await _clear(conn, sid)
    from . import health

    ill = await health.maybe_roll_ailment(
        conn, sid, "cook", chance=0.26, source="eatery_smoke",
    )
    msg = "硬烧过关，墙都熏黄了一角。"
    if ill:
        msg += f"\n{ill}\n→ visit_ops clinic treat"
    return msg


async def _clear(conn, steward_id: int) -> None:
    await ensure_columns(conn)
    await conn.execute(
        "UPDATE stewards SET eatery_hazard=NULL, eatery_hazard_json=NULL WHERE id=?",
        (steward_id,),
    )
