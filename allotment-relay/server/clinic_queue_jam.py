"""诊所麻烦档：治完病候诊区还堵，三选一（候诊 / 加号 / 硬治）。"""
from __future__ import annotations

import json
import random
from typing import Any

from . import db, energy


HAZARD_JAM = "jam"


async def ensure_columns(conn) -> None:
    for ddl in (
        "ALTER TABLE stewards ADD COLUMN clinic_hazard TEXT",
        "ALTER TABLE stewards ADD COLUMN clinic_hazard_json TEXT",
    ):
        try:
            await conn.execute(ddl)
        except Exception:
            pass


async def get_hazard(conn, steward_id: int) -> str:
    await ensure_columns(conn)
    cur = await conn.execute(
        "SELECT clinic_hazard FROM stewards WHERE id=?",
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
        UPDATE stewards SET clinic_hazard=?, clinic_hazard_json=?
        WHERE id=?
        """,
        (
            HAZARD_JAM,
            json.dumps({"kind": "queue_jam"}, ensure_ascii=False),
            steward_id,
        ),
    )
    return (
        "候诊区还挤着人，叫号屏乱跳！"
        " visit_ops clinic 诊险 候诊|加号|硬治"
        "（候诊=5精力；加号=12票；硬治=8精力）"
        "人类 /island 乔乔诊所也能点。"
    )


async def assert_not_blocked(conn, steward_id: int) -> None:
    if await get_hazard(conn, steward_id) == HAZARD_JAM:
        raise ValueError(
            "候诊区还堵着，先 visit_ops clinic 诊险 候诊|加号|硬治。"
            "人类 /island 乔乔诊所也能点。"
        )


def ui_actions(*, tickets: int, energy_now: int) -> list[dict[str, Any]]:
    return [
        {
            "action": "候诊",
            "label": "候诊",
            "hint": "5 精力",
            "can": energy_now >= 5,
            "disabled_reason": "精力不够 5",
        },
        {
            "action": "加号",
            "label": "加号",
            "hint": "12 票",
            "can": tickets >= 12,
            "disabled_reason": "票不够 12",
        },
        {
            "action": "硬治",
            "label": "硬治",
            "hint": "8 精力",
            "can": energy_now >= 8,
            "disabled_reason": "精力不够 8",
        },
    ]


async def resolve(conn, steward: dict[str, Any], choice: str) -> str:
    if await get_hazard(conn, steward["id"]) != HAZARD_JAM:
        raise ValueError("没有诊险待决。visit_ops clinic status 看档")
    ch = (choice or "").strip().lower()
    norm = None
    for zh, en in (("候诊", "wait"), ("加号", "priority"), ("硬治", "push")):
        if ch in (zh, en):
            norm = zh
            break
    if not norm:
        raise ValueError("诊险处置：候诊 · 加号 · 硬治（例 visit_ops clinic 诊险 候诊）")
    sid = steward["id"]

    if norm == "候诊":
        await energy.spend(conn, sid, 5, action="诊所候诊")
        await _clear(conn, sid, flash_summary=f"诊险：{norm}，已结。")
        return "排到窗口，桥桥把病历合上。"

    if norm == "加号":
        have = int((await (await conn.execute(
            "SELECT tickets FROM stewards WHERE id=?", (sid,)
        )).fetchone())[0])
        if have < 12:
            raise ValueError("加号要 12 票")
        await conn.execute(
            "UPDATE stewards SET tickets=tickets-12 WHERE id=?",
            (sid,),
        )
        await _clear(conn, sid, flash_summary=f"诊险：{norm}，已结。")
        return "加号费交上，叫号屏终于安静。（−12 票）"

    await energy.spend(conn, sid, 8, action="诊所硬治")
    await _clear(conn, sid, flash_summary=f"诊险：{norm}，已结。")
    return "挤过人群，可以正常开药了。"


async def _clear(
    conn,
    steward_id: int,
    *,
    flash_summary: str = "",
) -> None:
    await ensure_columns(conn)
    await conn.execute(
        "UPDATE stewards SET clinic_hazard=NULL, clinic_hazard_json=NULL WHERE id=?",
        (steward_id,),
    )

    if flash_summary:
        from . import hazard_flash as hf

        await hf.on_trouble_cleared(
            conn, steward_id, "clinic", flash_summary, "clinic_queue",
        )
