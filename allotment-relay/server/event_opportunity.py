"""坏事件里的低概率机会 — §五（坏事也能带来机会）。"""
from __future__ import annotations

import random

from . import db


async def maybe_voyage_hard_luck(conn, steward: dict, encounter: dict) -> str | None:
    """硬撑出航后归港，小概率捡到漂流箱。"""
    if not encounter.get("hard_sail"):
        return None
    if random.random() > 0.11:
        return None
    roll = random.random()
    if roll < 0.45:
        await db.add_item(conn, steward["id"], "drift_twine", 2)
        await db.add_chronicle(
            "sea", f"{steward['name']} 硬撑归港，潮里漂来一捆绳", steward["id"], conn=conn,
        )
        return "硬撑虽险，归港时网边挂住一只漂流箱：漂绳×2"
    if roll < 0.75:
        await db.add_item(conn, steward["id"], "sea_glass", 3)
        return "浪尖吐出几枚海玻璃，像补偿。"
    await db.add_item(conn, steward["id"], "relic_iron", 1)
    return "船帮刮到半块锈铁 relic——硬撑的意外收成。"
