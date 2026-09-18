"""酒吧麻烦档：洗碗后后厨积水，三选一（疏通 / 加班 / 硬摞）。"""
from __future__ import annotations

import json
import random
from typing import Any

from . import db, energy


HAZARD_FLOOD = "flood"


async def ensure_columns(conn) -> None:
    for ddl in (
        "ALTER TABLE stewards ADD COLUMN bar_hazard TEXT",
        "ALTER TABLE stewards ADD COLUMN bar_hazard_json TEXT",
    ):
        try:
            await conn.execute(ddl)
        except Exception:
            pass


async def get_hazard(conn, steward_id: int) -> str:
    await ensure_columns(conn)
    cur = await conn.execute(
        "SELECT bar_hazard FROM stewards WHERE id=?",
        (steward_id,),
    )
    row = await cur.fetchone()
    return (row[0] or "") if row else ""


async def maybe_after_work(conn, steward_id: int, *, job_id: str) -> str | None:
    if job_id != "dishwasher":
        return None
    if await get_hazard(conn, steward_id):
        return None
    if random.random() > 0.16:
        return None
    await ensure_columns(conn)
    await conn.execute(
        """
        UPDATE stewards SET bar_hazard=?, bar_hazard_json=?
        WHERE id=?
        """,
        (HAZARD_FLOOD, json.dumps({"kind": "sink"}, ensure_ascii=False), steward_id),
    )
    return (
        "后厨水槽堵了，碗堆成山！"
        " bar_ops 碗险 疏通|加班|硬摞"
        "（疏通=8票；加班=12精力；硬摞=6精力可能滑倒）"
    )


async def assert_not_blocked(conn, steward_id: int) -> None:
    if await get_hazard(conn, steward_id) == HAZARD_FLOOD:
        raise ValueError(
            "水槽还堵着，先 bar_ops 碗险 疏通|加班|硬摞。"
            "人类 /island 酒吧上工栏也能点。"
        )


def ui_actions(*, tickets: int, energy_now: int) -> list[dict[str, Any]]:
    return [
        {
            "action": "疏通",
            "label": "疏通",
            "hint": "8 票",
            "can": tickets >= 8,
            "disabled_reason": "票不够 8",
        },
        {
            "action": "加班",
            "label": "加班",
            "hint": "12 精力",
            "can": energy_now >= 12,
            "disabled_reason": "精力不够 12",
        },
        {
            "action": "硬摞",
            "label": "硬摞",
            "hint": "6 精力",
            "can": energy_now >= 6,
            "disabled_reason": "精力不够 6",
        },
    ]


async def resolve(conn, steward: dict[str, Any], choice: str) -> str:
    if await get_hazard(conn, steward["id"]) != HAZARD_FLOOD:
        raise ValueError("没有碗险待决。bar_ops status 看考勤")
    ch = (choice or "").strip().lower()
    norm = None
    for zh, en in (("疏通", "drain"), ("加班", "extra"), ("硬摞", "stack")):
        if ch in (zh, en):
            norm = zh
            break
    if not norm:
        raise ValueError("碗险处置：疏通 · 加班 · 硬摞（例 bar_ops 碗险 疏通）")
    sid = steward["id"]

    if norm == "疏通":
        cost = 8
        have = int((await (await conn.execute(
            "SELECT tickets FROM stewards WHERE id=?", (sid,)
        )).fetchone())[0])
        if have < cost:
            raise ValueError(f"疏通要 {cost} 票")
        await conn.execute(
            "UPDATE stewards SET tickets=tickets-? WHERE id=?",
            (cost, sid),
        )
        await _clear(conn, sid, flash_summary="酒吧碗险：疏通水槽，碗险已结。")
        return f"通下水了，碗能继续洗。（-{cost} 票）"

    if norm == "加班":
        await energy.spend(conn, sid, 12, action="酒吧加班")
        await _clear(conn, sid, flash_summary="酒吧碗险：加班摞碗，碗险已结。")
        return "加一班把碗摞完，地面也擦了。"

    await energy.spend(conn, sid, 6, action="酒吧硬摞")
    await _clear(conn, sid, flash_summary="酒吧碗险：硬摞过关，碗险已结。")
    from . import health

    ill = await health.maybe_roll_ailment(
        conn, sid, "bar", chance=0.22, source="bar_sink",
    )
    msg = "湿手硬摞，栈是稳了。"
    if ill:
        msg += f"\n{ill}\n→ visit_ops clinic treat"
    return msg


async def _clear(conn, steward_id: int, *, flash_summary: str = "") -> None:
    await ensure_columns(conn)
    await conn.execute(
        "UPDATE stewards SET bar_hazard=NULL, bar_hazard_json=NULL WHERE id=?",
        (steward_id,),
    )
    if flash_summary:
        from . import bad_event_tiers as tiers_mod

        await tiers_mod.record_flash(
            conn,
            steward_id,
            "bar",
            tiers_mod.TIER_LIGHT,
            flash_summary,
            ref_key="flash:bar_sink",
        )
