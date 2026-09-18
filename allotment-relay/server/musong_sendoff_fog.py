"""渡口麻烦档：目送后晨雾糊册，三选一（候潮 / 燃灯 / 硬别）。"""
from __future__ import annotations

import json
import random
from typing import Any

from . import db, energy


HAZARD_FOG = "fog"


async def ensure_columns(conn) -> None:
    for ddl in (
        "ALTER TABLE stewards ADD COLUMN musong_hazard TEXT",
        "ALTER TABLE stewards ADD COLUMN musong_hazard_json TEXT",
    ):
        try:
            await conn.execute(ddl)
        except Exception:
            pass


async def get_hazard(conn, steward_id: int) -> str:
    await ensure_columns(conn)
    cur = await conn.execute(
        "SELECT musong_hazard FROM stewards WHERE id=?",
        (steward_id,),
    )
    row = await cur.fetchone()
    return (row[0] or "") if row else ""


def _chance() -> float:
    from . import world

    if world.current_day_phase() in ("dawn", "night"):
        return 0.18
    return 0.11


async def maybe_after_send(conn, steward_id: int) -> str | None:
    if await get_hazard(conn, steward_id):
        return None
    if random.random() > _chance():
        return None
    await ensure_columns(conn)
    await conn.execute(
        """
        UPDATE stewards SET musong_hazard=?, musong_hazard_json=?
        WHERE id=?
        """,
        (
            HAZARD_FOG,
            json.dumps({"kind": "sendoff_fog"}, ensure_ascii=False),
            steward_id,
        ),
    )
    return (
        "雾把册页洇糊了！"
        " visit_ops musong 别险 候潮|燃灯|硬别"
        "（候潮=4精力；燃灯=矿灯芯×1或7票；硬别=8精力）"
        "只有 MCP/visit_ops，无岛景。"
    )


async def assert_not_blocked(conn, steward_id: int) -> None:
    if await get_hazard(conn, steward_id) == HAZARD_FOG:
        raise ValueError(
            "册子还糊着，先 visit_ops musong 别险 候潮|燃灯|硬别。"
        )


async def resolve(conn, steward: dict[str, Any], choice: str) -> str:
    if await get_hazard(conn, steward["id"]) != HAZARD_FOG:
        raise ValueError("没有别险待决。visit_ops musong remember 看册")
    ch = (choice or "").strip().lower()
    norm = None
    for zh, en in (("候潮", "wait"), ("燃灯", "lamp"), ("硬别", "stay")):
        if ch in (zh, en):
            norm = zh
            break
    if not norm:
        raise ValueError("别险处置：候潮 · 燃灯 · 硬别（例 visit_ops musong 别险 候潮）")
    sid = steward["id"]

    if norm == "候潮":
        await energy.spend(conn, sid, 4, action="渡口候潮")
        await _clear(conn, sid)
        return "等潮息一页，册上的字又清楚了。"

    if norm == "燃灯":
        paid = ""
        if not await db.take_item(conn, sid, "craft_lamp_wick", 1):
            cost = 7
            have = int((await (await conn.execute(
                "SELECT tickets FROM stewards WHERE id=?", (sid,)
            )).fetchone())[0])
            if have < cost:
                raise ValueError("燃灯要矿灯芯×1 或 7 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (cost, sid),
            )
            paid = f"-{cost} 票"
        else:
            paid = "矿灯芯×1"
        await _clear(conn, sid)
        return f"灯下烘干册页，阿槐继续记名。（{paid}）"

    await energy.spend(conn, sid, 8, action="渡口硬别")
    await _clear(conn, sid)
    return "硬把名字描完，雾还在栈桥上。"


async def _clear(conn, steward_id: int) -> None:
    await ensure_columns(conn)
    await conn.execute(
        "UPDATE stewards SET musong_hazard=NULL, musong_hazard_json=NULL WHERE id=?",
        (steward_id,),
    )
