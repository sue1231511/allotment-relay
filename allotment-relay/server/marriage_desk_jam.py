"""连理所麻烦档：订婚登记后册子乱页，三选一（理档 / 补章 / 硬签）。"""
from __future__ import annotations

import json
import random
from typing import Any

from . import db, energy


HAZARD_JAM = "jam"


async def ensure_columns(conn) -> None:
    for ddl in (
        "ALTER TABLE stewards ADD COLUMN marriage_hazard TEXT",
        "ALTER TABLE stewards ADD COLUMN marriage_hazard_json TEXT",
    ):
        try:
            await conn.execute(ddl)
        except Exception:
            pass


async def get_hazard(conn, steward_id: int) -> str:
    await ensure_columns(conn)
    cur = await conn.execute(
        "SELECT marriage_hazard FROM stewards WHERE id=?",
        (steward_id,),
    )
    row = await cur.fetchone()
    return (row[0] or "") if row else ""


async def maybe_after_betroth_step(conn, steward_id: int) -> str | None:
    if await get_hazard(conn, steward_id):
        return None
    if random.random() > 0.13:
        return None
    await ensure_columns(conn)
    await conn.execute(
        """
        UPDATE stewards SET marriage_hazard=?, marriage_hazard_json=?
        WHERE id=?
        """,
        (
            HAZARD_JAM,
            json.dumps({"kind": "desk_jam"}, ensure_ascii=False),
            steward_id,
        ),
    )
    return (
        "理枝刚合上的册子又被风吹乱页！"
        " visit_ops 连理所 所险 理档|补章|硬签"
        "（理档=6精力；补章=8票；硬签=10精力）"
        "人类 /island 连理所也能点。"
    )


async def assert_not_blocked(conn, steward_id: int) -> None:
    if await get_hazard(conn, steward_id) == HAZARD_JAM:
        raise ValueError(
            "册子还乱着，先 visit_ops 连理所 所险 理档|补章|硬签。"
            "人类 /island 连理所也能点。"
        )


def ui_actions(*, tickets: int, energy_now: int) -> list[dict[str, Any]]:
    return [
        {
            "action": "理档",
            "label": "理档",
            "hint": "6 精力",
            "can": energy_now >= 6,
            "disabled_reason": "精力不够 6",
        },
        {
            "action": "补章",
            "label": "补章",
            "hint": "8 票",
            "can": tickets >= 8,
            "disabled_reason": "票不够 8",
        },
        {
            "action": "硬签",
            "label": "硬签",
            "hint": "10 精力",
            "can": energy_now >= 10,
            "disabled_reason": "精力不够 10",
        },
    ]


async def resolve(conn, steward: dict[str, Any], choice: str) -> str:
    if await get_hazard(conn, steward["id"]) != HAZARD_JAM:
        raise ValueError("没有所险待决。visit_ops 连理所 订婚 看进度")
    ch = (choice or "").strip().lower()
    norm = None
    for zh, en in (("理档", "sort"), ("补章", "stamp"), ("硬签", "sign")):
        if ch in (zh, en):
            norm = zh
            break
    if not norm:
        raise ValueError("所险处置：理档 · 补章 · 硬签（例 visit_ops 连理所 所险 理档）")
    sid = steward["id"]

    if norm == "理档":
        await energy.spend(conn, sid, 6, action="连理所理档")
        await _clear(conn, sid, flash_summary=f"所险：{norm}，已结。")
        return "一页页理平，理枝把红章按回去。"

    if norm == "补章":
        have = int((await (await conn.execute(
            "SELECT tickets FROM stewards WHERE id=?", (sid,)
        )).fetchone())[0])
        if have < 8:
            raise ValueError("补章要 8 票")
        await conn.execute(
            "UPDATE stewards SET tickets=tickets-8 WHERE id=?",
            (sid,),
        )
        await _clear(conn, sid, flash_summary=f"所险：{norm}，已结。")
        return "盖了一枚小章，册子不再散页。（−8 票）"

    await energy.spend(conn, sid, 10, action="连理所硬签")
    await _clear(conn, sid, flash_summary=f"所险：{norm}，已结。")
    return "硬按住册角，理枝叹口气继续写。"


async def _clear(
    conn,
    steward_id: int,
    *,
    flash_summary: str = "",
) -> None:
    await ensure_columns(conn)
    await conn.execute(
        "UPDATE stewards SET marriage_hazard=NULL, marriage_hazard_json=NULL WHERE id=?",
        (steward_id,),
    )

    if flash_summary:
        from . import hazard_flash as hf

        await hf.on_trouble_cleared(
            conn, steward_id, "lianli", flash_summary, "marriage_desk",
        )
