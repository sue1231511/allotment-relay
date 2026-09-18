"""小橘麻烦档：专场围观后麦啸，三选一（润麦 / 退后 / 硬听）。"""
from __future__ import annotations

import json
import random
from typing import Any

from . import db, energy


HAZARD_MIC = "mic"


async def ensure_columns(conn) -> None:
    for ddl in (
        "ALTER TABLE stewards ADD COLUMN star_hazard TEXT",
        "ALTER TABLE stewards ADD COLUMN star_hazard_json TEXT",
    ):
        try:
            await conn.execute(ddl)
        except Exception:
            pass


async def get_hazard(conn, steward_id: int) -> str:
    await ensure_columns(conn)
    cur = await conn.execute(
        "SELECT star_hazard FROM stewards WHERE id=?",
        (steward_id,),
    )
    row = await cur.fetchone()
    return (row[0] or "") if row else ""


async def maybe_after_stage_watch(conn, steward_id: int, *, venue: str) -> str | None:
    if venue != "stage":
        return None
    if await get_hazard(conn, steward_id):
        return None
    if random.random() > 0.16:
        return None
    await ensure_columns(conn)
    await conn.execute(
        """
        UPDATE stewards SET star_hazard=?, star_hazard_json=?
        WHERE id=?
        """,
        (
            HAZARD_MIC,
            json.dumps({"kind": "mic_feedback"}, ensure_ascii=False),
            steward_id,
        ),
    )
    return (
        "麦里刺啦一响，耳膜发胀！"
        " star_ops 麦险 润麦|退后|硬听"
        "（润麦=5精力；退后=雾豌豆×1或6票；硬听=10精力）"
        "人类 /island 剧场看台也能点。"
    )


async def assert_not_blocked(conn, steward_id: int) -> None:
    if await get_hazard(conn, steward_id) == HAZARD_MIC:
        raise ValueError(
            "麦还在啸，先 star_ops 麦险 润麦|退后|硬听。"
            "人类 /island 剧场看台也能点。"
        )


def ui_actions(*, tickets: int, stock: dict[str, int], energy_now: int) -> list[dict[str, Any]]:
    pea = int(stock.get("crop_fogpea") or 0)
    return [
        {
            "action": "润麦",
            "label": "润麦",
            "hint": "5 精力",
            "can": energy_now >= 5,
            "disabled_reason": "精力不够 5",
        },
        {
            "action": "退后",
            "label": "退后",
            "hint": "雾豌豆×1 或 6 票",
            "can": pea >= 1 or tickets >= 6,
            "disabled_reason": "缺雾豌豆且票不够 6",
        },
        {
            "action": "硬听",
            "label": "硬听",
            "hint": "10 精力",
            "can": energy_now >= 10,
            "disabled_reason": "精力不够 10",
        },
    ]


async def resolve(conn, steward: dict[str, Any], choice: str) -> str:
    if await get_hazard(conn, steward["id"]) != HAZARD_MIC:
        raise ValueError("没有麦险待决。star_ops status 看档")
    ch = (choice or "").strip().lower()
    norm = None
    for zh, en in (("润麦", "oil"), ("退后", "back"), ("硬听", "stay")):
        if ch in (zh, en):
            norm = zh
            break
    if not norm:
        raise ValueError("麦险处置：润麦 · 退后 · 硬听（例 star_ops 麦险 润麦）")
    sid = steward["id"]

    if norm == "润麦":
        await energy.spend(conn, sid, 5, action="小橘润麦")
        await _clear(conn, sid, flash_summary=f"麦险：{norm}，已结。")
        return "调了调麦，啸声平了。"

    if norm == "退后":
        paid = ""
        if not await db.take_item(conn, sid, "crop_fogpea", 1):
            cost = 6
            have = int((await (await conn.execute(
                "SELECT tickets FROM stewards WHERE id=?", (sid,)
            )).fetchone())[0])
            if have < cost:
                raise ValueError("退后要雾豌豆×1 或 6 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (cost, sid),
            )
            paid = f"-{cost} 票"
        else:
            paid = "雾豌豆×1"
        await _clear(conn, sid, flash_summary=f"麦险：{norm}，已结。")
        return f"退到后排，耳朵舒服多了。（{paid}）"

    await energy.spend(conn, sid, 10, action="小橘硬听")
    await _clear(conn, sid, flash_summary=f"麦险：{norm}，已结。")
    return "硬撑听完，小橘朝你比了个歉意的手势。"


async def _clear(
    conn,
    steward_id: int,
    *,
    flash_summary: str = "",
) -> None:
    await ensure_columns(conn)
    await conn.execute(
        "UPDATE stewards SET star_hazard=NULL, star_hazard_json=NULL WHERE id=?",
        (steward_id,),
    )

    if flash_summary:
        from . import hazard_flash as hf

        await hf.on_trouble_cleared(
            conn, steward_id, "theater", flash_summary, "star_mic",
        )
