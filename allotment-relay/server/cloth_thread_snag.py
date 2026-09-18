"""衣泊坊麻烦档：取衣后线头缠梭，三选一（剪线 / 润梭 / 硬取）。"""
from __future__ import annotations

import json
import random
from typing import Any

from . import db, energy


HAZARD_SNAG = "snag"


async def ensure_columns(conn) -> None:
    for ddl in (
        "ALTER TABLE stewards ADD COLUMN atelier_hazard TEXT",
        "ALTER TABLE stewards ADD COLUMN atelier_hazard_json TEXT",
    ):
        try:
            await conn.execute(ddl)
        except Exception:
            pass


async def get_hazard(conn, steward_id: int) -> str:
    await ensure_columns(conn)
    cur = await conn.execute(
        "SELECT atelier_hazard FROM stewards WHERE id=?",
        (steward_id,),
    )
    row = await cur.fetchone()
    return (row[0] or "") if row else ""


async def maybe_after_claim(conn, steward_id: int) -> str | None:
    if await get_hazard(conn, steward_id):
        return None
    if random.random() > 0.13:
        return None
    await ensure_columns(conn)
    await conn.execute(
        """
        UPDATE stewards SET atelier_hazard=?, atelier_hazard_json=?
        WHERE id=?
        """,
        (
            HAZARD_SNAG,
            json.dumps({"kind": "thread_snag"}, ensure_ascii=False),
            steward_id,
        ),
    )
    return (
        "线头缠住梭子，衣角还挂着！"
        " cloth_ops 坊险 剪线|润梭|硬取"
        "（剪线=铜钉×1或7票；润梭=5精力；硬取=10精力）"
        "人类 /island 衣泊坊也能点。"
    )


async def assert_not_blocked(conn, steward_id: int) -> None:
    if await get_hazard(conn, steward_id) == HAZARD_SNAG:
        raise ValueError(
            "梭子还缠着，先 cloth_ops 坊险 剪线|润梭|硬取。"
            "人类 /island 衣泊坊也能点。"
        )


def ui_actions(*, tickets: int, stock: dict[str, int], energy_now: int) -> list[dict[str, Any]]:
    nails = int(stock.get("craft_copper_nails") or 0)
    return [
        {
            "action": "剪线",
            "label": "剪线",
            "hint": "铜钉×1 或 7 票",
            "can": nails >= 1 or tickets >= 7,
            "disabled_reason": "缺铜钉且票不够 7",
        },
        {
            "action": "润梭",
            "label": "润梭",
            "hint": "5 精力",
            "can": energy_now >= 5,
            "disabled_reason": "精力不够 5",
        },
        {
            "action": "硬取",
            "label": "硬取",
            "hint": "10 精力",
            "can": energy_now >= 10,
            "disabled_reason": "精力不够 10",
        },
    ]


async def resolve(conn, steward: dict[str, Any], choice: str) -> str:
    if await get_hazard(conn, steward["id"]) != HAZARD_SNAG:
        raise ValueError("没有坊险待决。cloth_ops status 看坊")
    ch = (choice or "").strip().lower()
    norm = None
    for zh, en in (("剪线", "snip"), ("润梭", "oil"), ("硬取", "pull")):
        if ch in (zh, en):
            norm = zh
            break
    if not norm:
        raise ValueError("坊险处置：剪线 · 润梭 · 硬取（例 cloth_ops 坊险 剪线）")
    sid = steward["id"]

    if norm == "剪线":
        paid = ""
        if not await db.take_item(conn, sid, "craft_copper_nails", 1):
            cost = 7
            have = int((await (await conn.execute(
                "SELECT tickets FROM stewards WHERE id=?", (sid,)
            )).fetchone())[0])
            if have < cost:
                raise ValueError("剪线要铜钉×1 或 7 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (cost, sid),
            )
            paid = f"-{cost} 票"
        else:
            paid = "铜钉×1"
        await _clear(conn, sid, flash_summary=f"坊险：{norm}，已结。")
        return f"剪断乱线，衣角平整了。（{paid}）"

    if norm == "润梭":
        await energy.spend(conn, sid, 5, action="衣泊坊润梭")
        await _clear(conn, sid, flash_summary=f"坊险：{norm}，已结。")
        return "漾漾滴了一点梭油，线梭顺了。"

    await energy.spend(conn, sid, 10, action="衣泊坊硬取")
    await _clear(conn, sid, flash_summary=f"坊险：{norm}，已结。")
    return "硬拽出来，衣服没勾丝。"


async def _clear(
    conn,
    steward_id: int,
    *,
    flash_summary: str = "",
) -> None:
    await ensure_columns(conn)
    await conn.execute(
        "UPDATE stewards SET atelier_hazard=NULL, atelier_hazard_json=NULL WHERE id=?",
        (steward_id,),
    )

    if flash_summary:
        from . import hazard_flash as hf

        await hf.on_trouble_cleared(
            conn, steward_id, "cloth", flash_summary, "cloth_snag",
        )
