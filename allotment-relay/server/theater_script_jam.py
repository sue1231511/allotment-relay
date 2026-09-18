"""编剧社麻烦档：投稿后稿纸卡槽，三选一（抚纸 / 压镇 / 硬投）。"""
from __future__ import annotations

import json
import random
from typing import Any

from . import db, energy


HAZARD_SCRIPT = "script"


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


async def maybe_after_submit(conn, steward_id: int) -> str | None:
    if await get_hazard(conn, steward_id):
        return None
    if random.random() > 0.12:
        return None
    await ensure_columns(conn)
    await conn.execute(
        """
        UPDATE stewards SET theater_hazard=?, theater_hazard_json=?
        WHERE id=?
        """,
        (
            HAZARD_SCRIPT,
            json.dumps({"kind": "script_jam"}, ensure_ascii=False),
            steward_id,
        ),
    )
    return (
        "稿纸卡在收稿槽里！"
        " theater_ops 稿险 抚纸|压镇|硬投"
        "（抚纸=漂布×1或6票；压镇=4精力；硬投=9精力）"
        "人类 /island 编剧社也能点。"
    )


async def assert_not_blocked(conn, steward_id: int) -> None:
    if await get_hazard(conn, steward_id) == HAZARD_SCRIPT:
        raise ValueError(
            "稿槽还卡着，先 theater_ops 稿险 抚纸|压镇|硬投。"
            "人类 /island 编剧社也能点。"
        )


def ui_actions(*, tickets: int, stock: dict[str, int], energy_now: int) -> list[dict[str, Any]]:
    drift = int(stock.get("cloth_drift") or 0)
    return [
        {
            "action": "抚纸",
            "label": "抚纸",
            "hint": "漂布×1 或 6 票",
            "can": drift >= 1 or tickets >= 6,
            "disabled_reason": "缺漂布且票不够 6",
        },
        {
            "action": "压镇",
            "label": "压镇",
            "hint": "4 精力",
            "can": energy_now >= 4,
            "disabled_reason": "精力不够 4",
        },
        {
            "action": "硬投",
            "label": "硬投",
            "hint": "9 精力",
            "can": energy_now >= 9,
            "disabled_reason": "精力不够 9",
        },
    ]


async def resolve(conn, steward: dict[str, Any], choice: str) -> str:
    if await get_hazard(conn, steward["id"]) != HAZARD_SCRIPT:
        raise ValueError("没有稿险待决。theater_ops 编剧社 看稿")
    ch = (choice or "").strip().lower()
    norm = None
    for zh, en in (("抚纸", "smooth"), ("压镇", "weight"), ("硬投", "shove")):
        if ch in (zh, en):
            norm = zh
            break
    if not norm:
        raise ValueError("稿险处置：抚纸 · 压镇 · 硬投（例 theater_ops 稿险 抚纸）")
    sid = steward["id"]

    if norm == "抚纸":
        paid = ""
        if not await db.take_item(conn, sid, "cloth_drift", 1):
            cost = 6
            have = int((await (await conn.execute(
                "SELECT tickets FROM stewards WHERE id=?", (sid,)
            )).fetchone())[0])
            if have < cost:
                raise ValueError("抚纸要漂布×1 或 6 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (cost, sid),
            )
            paid = f"-{cost} 票"
        else:
            paid = "漂布×1"
        await _clear(conn, sid)
        return f"抚平稿纸，槽口松了。（{paid}）"

    if norm == "压镇":
        await energy.spend(conn, sid, 4, action="编剧社压镇")
        await _clear(conn, sid)
        return "镇纸压好，下一页能塞进去了。"

    await energy.spend(conn, sid, 9, action="编剧社硬投")
    await _clear(conn, sid)
    return "硬塞进去，收稿铃还是响了一声。"


async def _clear(conn, steward_id: int) -> None:
    await ensure_columns(conn)
    await conn.execute(
        "UPDATE stewards SET theater_hazard=NULL, theater_hazard_json=NULL WHERE id=?",
        (steward_id,),
    )
