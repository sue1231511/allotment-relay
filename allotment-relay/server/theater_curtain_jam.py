"""小剧场麻烦档：演出后幕布卡死，三选一（扶幕 / 换场 / 硬演）。"""
from __future__ import annotations

import json
import random
from typing import Any

from . import db, energy


HAZARD_CURTAIN = "curtain"


async def ensure_columns(conn) -> None:
    for ddl in (
        "ALTER TABLE stewards ADD COLUMN theater_hazard TEXT",
        "ALTER TABLE stewards ADD COLUMN theater_hazard_json TEXT",
    ):
        try:
            await conn.execute(ddl)
        except Exception:
            pass


async def get_hazard(conn, steward_id: int) -> str:
    await ensure_columns(conn)
    cur = await conn.execute(
        "SELECT theater_hazard FROM stewards WHERE id=?",
        (steward_id,),
    )
    row = await cur.fetchone()
    return (row[0] or "") if row else ""


async def maybe_after_perform(conn, steward_id: int) -> str | None:
    if await get_hazard(conn, steward_id):
        return None
    if random.random() > 0.14:
        return None
    await ensure_columns(conn)
    await conn.execute(
        """
        UPDATE stewards SET theater_hazard=?, theater_hazard_json=?
        WHERE id=?
        """,
        (
            HAZARD_CURTAIN,
            json.dumps({"kind": "curtain_jam"}, ensure_ascii=False),
            steward_id,
        ),
    )
    return (
        "幕布卡住了，灯还亮着！"
        " theater_ops 剧险 扶幕|换场|硬演"
        "（扶幕=5精力；换场=麻绳×1或9票；硬演=8精力）"
        "人类 /island 剧场看台也能点。"
    )


async def assert_not_blocked(conn, steward_id: int) -> None:
    if await get_hazard(conn, steward_id) == HAZARD_CURTAIN:
        raise ValueError(
            "幕布还卡着，先 theater_ops 剧险 扶幕|换场|硬演。"
            "人类 /island 剧场看台也能点。"
        )


def ui_actions(*, tickets: int, stock: dict[str, int], energy_now: int) -> list[dict[str, Any]]:
    rope = int(stock.get("craft_rope") or 0)
    return [
        {
            "action": "扶幕",
            "label": "扶幕",
            "hint": "5 精力",
            "can": energy_now >= 5,
            "disabled_reason": "精力不够 5",
        },
        {
            "action": "换场",
            "label": "换场",
            "hint": "麻绳×1 或 9 票",
            "can": rope >= 1 or tickets >= 9,
            "disabled_reason": "缺麻绳且票不够 9",
        },
        {
            "action": "硬演",
            "label": "硬演",
            "hint": "8 精力",
            "can": energy_now >= 8,
            "disabled_reason": "精力不够 8",
        },
    ]


async def resolve(conn, steward: dict[str, Any], choice: str) -> str:
    if await get_hazard(conn, steward["id"]) != HAZARD_CURTAIN:
        raise ValueError("没有剧险待决。theater_ops 看板 看今晚")
    ch = (choice or "").strip().lower()
    norm = None
    for zh, en in (("扶幕", "hold"), ("换场", "swap"), ("硬演", "push")):
        if ch in (zh, en):
            norm = zh
            break
    if not norm:
        raise ValueError("剧险处置：扶幕 · 换场 · 硬演（例 theater_ops 剧险 扶幕）")
    sid = steward["id"]

    if norm == "扶幕":
        await energy.spend(conn, sid, 5, action="小剧场扶幕")
        await _clear(conn, sid, flash_summary=f"剧险：{norm}，已结。")
        return "你托住幕布，后台把滑轮理顺了。"

    if norm == "换场":
        paid = ""
        if not await db.take_item(conn, sid, "craft_rope", 1):
            cost = 9
            have = int((await (await conn.execute(
                "SELECT tickets FROM stewards WHERE id=?", (sid,)
            )).fetchone())[0])
            if have < cost:
                raise ValueError("换场要麻绳×1 或 9 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (cost, sid),
            )
            paid = f"-{cost} 票"
        else:
            paid = "麻绳×1"
        await _clear(conn, sid, flash_summary=f"剧险：{norm}，已结。")
        return f"换好幕绳，灯影稳下来。（{paid}）"

    await energy.spend(conn, sid, 8, action="小剧场硬演")
    await _clear(conn, sid, flash_summary=f"剧险：{norm}，已结。")
    return "硬把幕布拽上去，小橘在台侧比了个 OK。"


async def _clear(
    conn,
    steward_id: int,
    *,
    flash_summary: str = "",
) -> None:
    await ensure_columns(conn)
    await conn.execute(
        "UPDATE stewards SET theater_hazard=NULL, theater_hazard_json=NULL WHERE id=?",
        (steward_id,),
    )

    if flash_summary:
        from . import hazard_flash as hf

        await hf.on_trouble_cleared(
            conn, steward_id, "theater", flash_summary, "theater_curtain",
        )
