"""花房麻烦档：做干花后花粉扑面，三选一（开窗 / 洒水 / 硬做）。"""
from __future__ import annotations

import json
import random
from typing import Any

from . import db, energy


HAZARD_SNIFF = "sniff"


async def ensure_columns(conn) -> None:
    for ddl in (
        "ALTER TABLE stewards ADD COLUMN florist_hazard TEXT",
        "ALTER TABLE stewards ADD COLUMN florist_hazard_json TEXT",
    ):
        try:
            await conn.execute(ddl)
        except Exception:
            pass


async def get_hazard(conn, steward_id: int) -> str:
    await ensure_columns(conn)
    cur = await conn.execute(
        "SELECT florist_hazard FROM stewards WHERE id=?",
        (steward_id,),
    )
    row = await cur.fetchone()
    return (row[0] or "") if row else ""


async def maybe_after_dry(conn, steward_id: int) -> str | None:
    if await get_hazard(conn, steward_id):
        return None
    if random.random() > 0.11:
        return None
    await ensure_columns(conn)
    await conn.execute(
        """
        UPDATE stewards SET florist_hazard=?, florist_hazard_json=?
        WHERE id=?
        """,
        (
            HAZARD_SNIFF,
            json.dumps({"kind": "pollen_sniff"}, ensure_ascii=False),
            steward_id,
        ),
    )
    return (
        "干花屑一扬，满屋花粉呛人！"
        " visit_ops 默默 花险 开窗|洒水|硬做"
        "（开窗=4精力；洒水=雾豆×1或5票；硬做=9精力）"
        "人类 /island 花店也能点。"
    )


async def assert_not_blocked(conn, steward_id: int) -> None:
    if await get_hazard(conn, steward_id) == HAZARD_SNIFF:
        raise ValueError(
            "花粉还呛着，先 visit_ops 默默 花险 开窗|洒水|硬做。"
            "人类 /island 花店也能点。"
        )


def ui_actions(*, tickets: int, stock: dict[str, int], energy_now: int) -> list[dict[str, Any]]:
    return [
        {
            "action": "开窗",
            "label": "开窗",
            "hint": "4 精力",
            "can": energy_now >= 4,
            "disabled_reason": "精力不够 4",
        },
        {
            "action": "洒水",
            "label": "洒水",
            "hint": "甜菜×1 或 5 票",
            "can": int(stock.get("crop_sweet_beet") or 0) >= 1 or tickets >= 5,
            "disabled_reason": "缺甜菜且票不够 5",
        },
        {
            "action": "硬做",
            "label": "硬做",
            "hint": "9 精力",
            "can": energy_now >= 9,
            "disabled_reason": "精力不够 9",
        },
    ]


async def resolve(conn, steward: dict[str, Any], choice: str) -> str:
    if await get_hazard(conn, steward["id"]) != HAZARD_SNIFF:
        raise ValueError("没有花险待决。visit_ops 默默 visit 进店")
    ch = (choice or "").strip().lower()
    norm = None
    for zh, en in (("开窗", "air"), ("洒水", "mist"), ("硬做", "hold")):
        if ch in (zh, en):
            norm = zh
            break
    if not norm:
        raise ValueError("花险处置：开窗 · 洒水 · 硬做（例 visit_ops 默默 花险 开窗）")
    sid = steward["id"]

    if norm == "开窗":
        await energy.spend(conn, sid, 4, action="花房开窗")
        await _clear(conn, sid, flash_summary=f"花险：{norm}，已结。")
        return "推开窗，潮风把花粉吹散。"

    if norm == "洒水":
        paid = ""
        if not await db.take_item(conn, sid, "crop_sweet_beet", 1):
            cost = 5
            have = int((await (await conn.execute(
                "SELECT tickets FROM stewards WHERE id=?", (sid,)
            )).fetchone())[0])
            if have < cost:
                raise ValueError("洒水要甜菜×1 或 5 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (cost, sid),
            )
            paid = f"-{cost} 票"
        else:
            paid = "甜菜×1"
        await _clear(conn, sid, flash_summary=f"花险：{norm}，已结。")
        return f"洒点水雾，默默不再打喷嚏。（{paid}）"

    await energy.spend(conn, sid, 9, action="花房硬做")
    await _clear(conn, sid, flash_summary=f"花险：{norm}，已结。")
    return "捂着鼻子把活干完，花房恢复安静。"


async def _clear(
    conn,
    steward_id: int,
    *,
    flash_summary: str = "",
) -> None:
    await ensure_columns(conn)
    await conn.execute(
        "UPDATE stewards SET florist_hazard=NULL, florist_hazard_json=NULL WHERE id=?",
        (steward_id,),
    )

    if flash_summary:
        from . import hazard_flash as hf

        await hf.on_trouble_cleared(
            conn, steward_id, "florist", flash_summary, "florist_pollen",
        )
