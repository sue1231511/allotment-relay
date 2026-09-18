"""何敬山麻烦档：送糕后木箱松脱，三选一（捆扎 / 垫木 / 硬提）。"""
from __future__ import annotations

import json
import random
from typing import Any

from . import db, energy


HAZARD_CRATE = "crate"


async def ensure_columns(conn) -> None:
    for ddl in (
        "ALTER TABLE stewards ADD COLUMN jingshan_hazard TEXT",
        "ALTER TABLE stewards ADD COLUMN jingshan_hazard_json TEXT",
    ):
        try:
            await conn.execute(ddl)
        except Exception:
            pass


async def get_hazard(conn, steward_id: int) -> str:
    await ensure_columns(conn)
    cur = await conn.execute(
        "SELECT jingshan_hazard FROM stewards WHERE id=?",
        (steward_id,),
    )
    row = await cur.fetchone()
    return (row[0] or "") if row else ""


async def maybe_after_deliver(conn, steward_id: int) -> str | None:
    if await get_hazard(conn, steward_id):
        return None
    if random.random() > 0.13:
        return None
    await ensure_columns(conn)
    await conn.execute(
        """
        UPDATE stewards SET jingshan_hazard=?, jingshan_hazard_json=?
        WHERE id=?
        """,
        (
            HAZARD_CRATE,
            json.dumps({"kind": "crate_loose"}, ensure_ascii=False),
            steward_id,
        ),
    )
    return (
        "木箱箍松了，糕点晃荡！"
        " visit_ops jingshan 箱险 捆扎|垫木|硬提"
        "（捆扎=麻绳×1或8票；垫木=岸木×1或10票；硬提=9精力）"
        "只有 MCP/visit_ops，无岛景。"
    )


async def assert_not_blocked(conn, steward_id: int) -> None:
    if await get_hazard(conn, steward_id) == HAZARD_CRATE:
        raise ValueError(
            "箱子还松着，先 visit_ops jingshan 箱险 捆扎|垫木|硬提。"
        )


async def resolve(conn, steward: dict[str, Any], choice: str) -> str:
    if await get_hazard(conn, steward["id"]) != HAZARD_CRATE:
        raise ValueError("没有箱险待决。visit_ops jingshan status 看进度")
    ch = (choice or "").strip().lower()
    norm = None
    for zh, en in (("捆扎", "tie"), ("垫木", "pad"), ("硬提", "lift")):
        if ch in (zh, en):
            norm = zh
            break
    if not norm:
        raise ValueError("箱险处置：捆扎 · 垫木 · 硬提（例 visit_ops jingshan 箱险 捆扎）")
    sid = steward["id"]

    if norm == "捆扎":
        paid = ""
        if not await db.take_item(conn, sid, "craft_rope", 1):
            cost = 8
            have = int((await (await conn.execute(
                "SELECT tickets FROM stewards WHERE id=?", (sid,)
            )).fetchone())[0])
            if have < cost:
                raise ValueError("捆扎要麻绳×1 或 8 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (cost, sid),
            )
            paid = f"-{cost} 票"
        else:
            paid = "麻绳×1"
        await _clear(conn, sid)
        return f"箍紧木箱，糕点稳了。（{paid}）"

    if norm == "垫木":
        paid = ""
        if not await db.take_item(conn, sid, "craft_timber", 1):
            cost = 10
            have = int((await (await conn.execute(
                "SELECT tickets FROM stewards WHERE id=?", (sid,)
            )).fetchone())[0])
            if have < cost:
                raise ValueError("垫木要岸木×1 或 10 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (cost, sid),
            )
            paid = f"-{cost} 票"
        else:
            paid = "岸木×1"
        await _clear(conn, sid)
        return f"垫好木楔，箱底不晃了。（{paid}）"

    await energy.spend(conn, sid, 9, action="敬山硬提")
    await _clear(conn, sid)
    return "硬提进门，何敬山接过去没说什么。"


async def _clear(conn, steward_id: int) -> None:
    await ensure_columns(conn)
    await conn.execute(
        "UPDATE stewards SET jingshan_hazard=NULL, jingshan_hazard_json=NULL WHERE id=?",
        (steward_id,),
    )
