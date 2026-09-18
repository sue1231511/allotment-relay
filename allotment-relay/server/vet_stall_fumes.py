"""蹄角棚麻烦档：治完牲口后棚里氨气冲，三选一（通风 / 换草 / 硬留）。"""
from __future__ import annotations

import json
import random
from typing import Any

from . import db, energy


HAZARD_FUMES = "fumes"


async def ensure_columns(conn) -> None:
    for ddl in (
        "ALTER TABLE stewards ADD COLUMN vet_hazard TEXT",
        "ALTER TABLE stewards ADD COLUMN vet_hazard_json TEXT",
    ):
        try:
            await conn.execute(ddl)
        except Exception:
            pass


async def get_hazard(conn, steward_id: int) -> str:
    await ensure_columns(conn)
    cur = await conn.execute(
        "SELECT vet_hazard FROM stewards WHERE id=?",
        (steward_id,),
    )
    row = await cur.fetchone()
    return (row[0] or "") if row else ""


async def maybe_after_treat(conn, steward_id: int) -> str | None:
    if await get_hazard(conn, steward_id):
        return None
    if random.random() > 0.12:
        return None
    await ensure_columns(conn)
    await conn.execute(
        """
        UPDATE stewards SET vet_hazard=?, vet_hazard_json=?
        WHERE id=?
        """,
        (
            HAZARD_FUMES,
            json.dumps({"kind": "stall_fumes"}, ensure_ascii=False),
            steward_id,
        ),
    )
    return (
        "碘酒味混着氨气，棚里呛人！"
        " visit_ops 兽医 棚险 通风|换草|硬留"
        "（通风=5精力；换草=堆肥×1或6票；硬留=9精力）"
        "上手页小屋「找兽医」同一套。"
    )


async def assert_not_blocked(conn, steward_id: int) -> None:
    if await get_hazard(conn, steward_id) == HAZARD_FUMES:
        raise ValueError(
            "棚里还呛，先 visit_ops 兽医 棚险 通风|换草|硬留。"
        )


def ui_actions(*, tickets: int, stock: dict[str, int], energy_now: int) -> list[dict[str, Any]]:
    compost = int(stock.get("compost") or 0)
    return [
        {
            "action": "通风",
            "label": "通风",
            "hint": "5 精力",
            "can": energy_now >= 5,
            "disabled_reason": "精力不够 5",
        },
        {
            "action": "换草",
            "label": "换草",
            "hint": "堆肥×1 或 6 票",
            "can": compost >= 1 or tickets >= 6,
            "disabled_reason": "缺堆肥且票不够 6",
        },
        {
            "action": "硬留",
            "label": "硬留",
            "hint": "9 精力",
            "can": energy_now >= 9,
            "disabled_reason": "精力不够 9",
        },
    ]


async def resolve(conn, steward: dict[str, Any], choice: str) -> str:
    if await get_hazard(conn, steward["id"]) != HAZARD_FUMES:
        raise ValueError("没有棚险待决。visit_ops 兽医 status 看栏")
    ch = (choice or "").strip().lower()
    norm = None
    for zh, en in (("通风", "air"), ("换草", "bedding"), ("硬留", "stay")):
        if ch in (zh, en):
            norm = zh
            break
    if not norm:
        raise ValueError("棚险处置：通风 · 换草 · 硬留（例 visit_ops 兽医 棚险 通风）")
    sid = steward["id"]

    if norm == "通风":
        await energy.spend(conn, sid, 5, action="蹄角棚通风")
        await _clear(conn, sid)
        return "推开侧窗，风把闷气带走。"

    if norm == "换草":
        paid = ""
        if not await db.take_item(conn, sid, "compost", 1):
            cost = 6
            have = int((await (await conn.execute(
                "SELECT tickets FROM stewards WHERE id=?", (sid,)
            )).fetchone())[0])
            if have < cost:
                raise ValueError("换草要堆肥×1 或 6 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (cost, sid),
            )
            paid = f"-{cost} 票"
        else:
            paid = "堆肥×1"
        await _clear(conn, sid)
        return f"铺一层新垫草，牲口气淡了。（{paid}）"

    await energy.spend(conn, sid, 9, action="蹄角棚硬留")
    await _clear(conn, sid)
    return "捏着鼻子把活干完，霍衡递来一块薄荷皂。"


async def _clear(conn, steward_id: int) -> None:
    await ensure_columns(conn)
    await conn.execute(
        "UPDATE stewards SET vet_hazard=NULL, vet_hazard_json=NULL WHERE id=?",
        (steward_id,),
    )
