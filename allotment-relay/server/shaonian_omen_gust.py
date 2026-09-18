"""韶年麻烦档：卜卦后潮风掀卦盘，三选一（压石 / 问潮 / 硬信）。"""
from __future__ import annotations

import json
import random
from typing import Any

from . import db, energy


HAZARD_GUST = "gust"


async def ensure_columns(conn) -> None:
    for ddl in (
        "ALTER TABLE stewards ADD COLUMN shaonian_hazard TEXT",
        "ALTER TABLE stewards ADD COLUMN shaonian_hazard_json TEXT",
    ):
        try:
            await conn.execute(ddl)
        except Exception:
            pass


async def get_hazard(conn, steward_id: int) -> str:
    await ensure_columns(conn)
    cur = await conn.execute(
        "SELECT shaonian_hazard FROM stewards WHERE id=?",
        (steward_id,),
    )
    row = await cur.fetchone()
    return (row[0] or "") if row else ""


def _chance() -> float:
    from . import world

    w = world.current_weather()
    if w in ("gale", "storm", "windy"):
        return 0.22
    if w == "rain":
        return 0.14
    return 0.11


async def maybe_after_fortune(conn, steward_id: int) -> str | None:
    if await get_hazard(conn, steward_id):
        return None
    if random.random() > _chance():
        return None
    await ensure_columns(conn)
    await conn.execute(
        """
        UPDATE stewards SET shaonian_hazard=?, shaonian_hazard_json=?
        WHERE id=?
        """,
        (
            HAZARD_GUST,
            json.dumps({"kind": "omen_gust"}, ensure_ascii=False),
            steward_id,
        ),
    )
    return (
        "一阵潮风把卦盘吹歪！"
        " visit_ops shaonian 卦险 压石|问潮|硬信"
        "（压石=页岩砖×1或8票；问潮=4精力；硬信=8精力）"
        "人类 /island 海边见韶年也能点。"
    )


async def assert_not_blocked(conn, steward_id: int) -> None:
    if await get_hazard(conn, steward_id) == HAZARD_GUST:
        raise ValueError(
            "卦盘还在晃，先 visit_ops shaonian 卦险 压石|问潮|硬信。"
            "人类 /island 海边见韶年也能点。"
        )


def ui_actions(*, tickets: int, stock: dict[str, int], energy_now: int) -> list[dict[str, Any]]:
    brick = int(stock.get("quarry_brick") or 0)
    return [
        {
            "action": "压石",
            "label": "压石",
            "hint": "砖×1 或 8 票",
            "can": brick >= 1 or tickets >= 8,
            "disabled_reason": "缺砖且票不够 8",
        },
        {
            "action": "问潮",
            "label": "问潮",
            "hint": "4 精力",
            "can": energy_now >= 4,
            "disabled_reason": "精力不够 4",
        },
        {
            "action": "硬信",
            "label": "硬信",
            "hint": "8 精力",
            "can": energy_now >= 8,
            "disabled_reason": "精力不够 8",
        },
    ]


async def resolve(conn, steward: dict[str, Any], choice: str) -> str:
    if await get_hazard(conn, steward["id"]) != HAZARD_GUST:
        raise ValueError("没有卦险待决。visit_ops shaonian visit 看滩头")
    ch = (choice or "").strip().lower()
    norm = None
    for zh, en in (("压石", "weight"), ("问潮", "tide"), ("硬信", "hold")):
        if ch in (zh, en):
            norm = zh
            break
    if not norm:
        raise ValueError("卦险处置：压石 · 问潮 · 硬信（例 visit_ops shaonian 卦险 压石）")
    sid = steward["id"]

    if norm == "压石":
        paid = ""
        if not await db.take_item(conn, sid, "quarry_brick", 1):
            cost = 8
            have = int((await (await conn.execute(
                "SELECT tickets FROM stewards WHERE id=?", (sid,)
            )).fetchone())[0])
            if have < cost:
                raise ValueError("压石要页岩砖×1 或 8 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (cost, sid),
            )
            paid = f"-{cost} 票"
        else:
            paid = "页岩砖×1"
        await _clear(conn, sid, flash_summary=f"卦险：{norm}，已结。")
        return f"压好卦石，韶年把盘扶正。（{paid}）"

    if norm == "问潮":
        await energy.spend(conn, sid, 4, action="韶年问潮")
        await _clear(conn, sid, flash_summary=f"卦险：{norm}，已结。")
        return "听潮一息，卦纹稳下来。"

    await energy.spend(conn, sid, 8, action="韶年硬信")
    await _clear(conn, sid, flash_summary=f"卦险：{norm}，已结。")
    return "硬按住卦盘，继续信今日卦象。"


async def _clear(
    conn,
    steward_id: int,
    *,
    flash_summary: str = "",
) -> None:
    await ensure_columns(conn)
    await conn.execute(
        "UPDATE stewards SET shaonian_hazard=NULL, shaonian_hazard_json=NULL WHERE id=?",
        (steward_id,),
    )

    if flash_summary:
        from . import hazard_flash as hf

        await hf.on_trouble_cleared(
            conn, steward_id, "beach_omen", flash_summary, "shaonian_omen",
        )
