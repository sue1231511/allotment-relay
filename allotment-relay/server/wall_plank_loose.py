"""听潮亭麻烦档：钉牌后木牌松脱，三选一（加固 / 换钉 / 硬钉）。"""
from __future__ import annotations

import json
import random
from typing import Any

from . import db, energy


HAZARD_LOOSE = "loose"


async def ensure_columns(conn) -> None:
    for ddl in (
        "ALTER TABLE stewards ADD COLUMN wall_hazard TEXT",
        "ALTER TABLE stewards ADD COLUMN wall_hazard_json TEXT",
    ):
        try:
            await conn.execute(ddl)
        except Exception:
            pass


async def get_hazard(conn, steward_id: int) -> str:
    await ensure_columns(conn)
    cur = await conn.execute(
        "SELECT wall_hazard FROM stewards WHERE id=?",
        (steward_id,),
    )
    row = await cur.fetchone()
    return (row[0] or "") if row else ""


async def maybe_after_post(conn, steward_id: int) -> str | None:
    if await get_hazard(conn, steward_id):
        return None
    if random.random() > 0.11:
        return None
    await ensure_columns(conn)
    await conn.execute(
        """
        UPDATE stewards SET wall_hazard=?, wall_hazard_json=?
        WHERE id=?
        """,
        (
            HAZARD_LOOSE,
            json.dumps({"kind": "plank_loose"}, ensure_ascii=False),
            steward_id,
        ),
    )
    return (
        "刚钉的木牌哐当一声，钉子松了！"
        " wall_ops 亭险 加固|换钉|硬钉"
        "（加固=铜钉×1或8票；换钉=6精力；硬钉=10精力）"
        "人类 /island 听潮亭也能点。"
    )


async def assert_not_blocked(conn, steward_id: int) -> None:
    if await get_hazard(conn, steward_id) == HAZARD_LOOSE:
        raise ValueError(
            "木牌还松着，先 wall_ops 亭险 加固|换钉|硬钉。"
            "人类 /island 听潮亭也能点。"
        )


def ui_actions(*, tickets: int, stock: dict[str, int], energy_now: int) -> list[dict[str, Any]]:
    nails = int(stock.get("craft_copper_nails") or 0)
    return [
        {
            "action": "加固",
            "label": "加固",
            "hint": "铜钉×1 或 8 票",
            "can": nails >= 1 or tickets >= 8,
            "disabled_reason": "缺铜钉且票不够 8",
        },
        {
            "action": "换钉",
            "label": "换钉",
            "hint": "6 精力",
            "can": energy_now >= 6,
            "disabled_reason": "精力不够 6",
        },
        {
            "action": "硬钉",
            "label": "硬钉",
            "hint": "10 精力",
            "can": energy_now >= 10,
            "disabled_reason": "精力不够 10",
        },
    ]


async def resolve(conn, steward: dict[str, Any], choice: str) -> str:
    if await get_hazard(conn, steward["id"]) != HAZARD_LOOSE:
        raise ValueError("没有亭险待决。wall_ops 看亭")
    ch = (choice or "").strip().lower()
    norm = None
    for zh, en in (("加固", "brace"), ("换钉", "renail"), ("硬钉", "hammer")):
        if ch in (zh, en):
            norm = zh
            break
    if not norm:
        raise ValueError("亭险处置：加固 · 换钉 · 硬钉（例 wall_ops 亭险 加固）")
    sid = steward["id"]

    if norm == "加固":
        paid = ""
        if not await db.take_item(conn, sid, "craft_copper_nails", 1):
            cost = 8
            have = int((await (await conn.execute(
                "SELECT tickets FROM stewards WHERE id=?", (sid,)
            )).fetchone())[0])
            if have < cost:
                raise ValueError("加固要铜钉×1 或 8 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (cost, sid),
            )
            paid = f"-{cost} 票"
        else:
            paid = "铜钉×1"
        await _clear(conn, sid)
        return f"多敲两枚钉，木牌稳了。（{paid}）"

    if norm == "换钉":
        await energy.spend(conn, sid, 6, action="听潮亭换钉")
        await _clear(conn, sid)
        return "换好新钉，亭柱不再晃。"

    await energy.spend(conn, sid, 10, action="听潮亭硬钉")
    await _clear(conn, sid)
    return "硬钉进去，木牌挂牢了。"


async def _clear(conn, steward_id: int) -> None:
    await ensure_columns(conn)
    await conn.execute(
        "UPDATE stewards SET wall_hazard=NULL, wall_hazard_json=NULL WHERE id=?",
        (steward_id,),
    )
