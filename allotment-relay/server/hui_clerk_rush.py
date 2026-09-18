"""潮生会麻烦档：交税交维后排队潮，三选一（排队 / 补票 / 硬挤）。"""
from __future__ import annotations

import json
import random
from typing import Any

from . import db, energy


HAZARD_RUSH = "rush"


async def ensure_columns(conn) -> None:
    for ddl in (
        "ALTER TABLE stewards ADD COLUMN hui_hazard TEXT",
        "ALTER TABLE stewards ADD COLUMN hui_hazard_json TEXT",
    ):
        try:
            await conn.execute(ddl)
        except Exception:
            pass


async def get_hazard(conn, steward_id: int) -> str:
    await ensure_columns(conn)
    cur = await conn.execute(
        "SELECT hui_hazard FROM stewards WHERE id=?",
        (steward_id,),
    )
    row = await cur.fetchone()
    return (row[0] or "") if row else ""


async def maybe_after_pay(conn, steward_id: int, *, taken: int) -> str | None:
    if taken < 1 or await get_hazard(conn, steward_id):
        return None
    if random.random() > 0.14:
        return None
    await ensure_columns(conn)
    await conn.execute(
        """
        UPDATE stewards SET hui_hazard=?, hui_hazard_json=?
        WHERE id=?
        """,
        (
            HAZARD_RUSH,
            json.dumps({"kind": "clerk_rush", "paid": taken}, ensure_ascii=False),
            steward_id,
        ),
    )
    return (
        "交完票门口还挤着一圈人，簿子乱翻！"
        " visit_ops 潮生会 会险 排队|补票|硬挤"
        "（排队=6精力；补票=5票；硬挤=10精力）"
        "人类 /island 潮生会也能点。"
    )


async def assert_not_blocked(conn, steward_id: int) -> None:
    if await get_hazard(conn, steward_id) == HAZARD_RUSH:
        raise ValueError(
            "会厅还堵着，先 visit_ops 潮生会 会险 排队|补票|硬挤。"
            "人类 /island 潮生会也能点。"
        )


def ui_actions(*, tickets: int, energy_now: int) -> list[dict[str, Any]]:
    return [
        {
            "action": "排队",
            "label": "排队",
            "hint": "6 精力",
            "can": energy_now >= 6,
            "disabled_reason": "精力不够 6",
        },
        {
            "action": "补票",
            "label": "补票",
            "hint": "5 票",
            "can": tickets >= 5,
            "disabled_reason": "票不够 5",
        },
        {
            "action": "硬挤",
            "label": "硬挤",
            "hint": "10 精力",
            "can": energy_now >= 10,
            "disabled_reason": "精力不够 10",
        },
    ]


async def resolve(conn, steward: dict[str, Any], choice: str) -> str:
    if await get_hazard(conn, steward["id"]) != HAZARD_RUSH:
        raise ValueError("没有会险待决。visit_ops 潮生会 问 看档")
    ch = (choice or "").strip().lower()
    norm = None
    for zh, en in (("排队", "queue"), ("补票", "tip"), ("硬挤", "push")):
        if ch in (zh, en):
            norm = zh
            break
    if not norm:
        raise ValueError("会险处置：排队 · 补票 · 硬挤（例 visit_ops 潮生会 会险 排队）")
    sid = steward["id"]

    if norm == "排队":
        await energy.spend(conn, sid, 6, action="潮生会排队")
        await _clear(conn, sid)
        return "排到窗口前，阿簿把簿子理平了。"

    if norm == "补票":
        have = int((await (await conn.execute(
            "SELECT tickets FROM stewards WHERE id=?", (sid,)
        )).fetchone())[0])
        if have < 5:
            raise ValueError("补票要 5 票")
        await conn.execute(
            "UPDATE stewards SET tickets=tickets-5 WHERE id=?",
            (sid,),
        )
        await _clear(conn, sid)
        return "塞了五票当谢仪，队伍让开一条缝。"

    await energy.spend(conn, sid, 10, action="潮生会硬挤")
    extra = ""
    if random.random() < 0.25:
        await conn.execute(
            "UPDATE stewards SET tickets=MAX(0, tickets-3) WHERE id=?",
            (sid,),
        )
        extra = "挤掉几张零票（−3 票）。"
    await _clear(conn, sid)
    return f"挤过人群，簿子终于合上。{extra}"


async def _clear(conn, steward_id: int) -> None:
    await ensure_columns(conn)
    await conn.execute(
        "UPDATE stewards SET hui_hazard=NULL, hui_hazard_json=NULL WHERE id=?",
        (steward_id,),
    )
