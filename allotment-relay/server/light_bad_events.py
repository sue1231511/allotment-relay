"""第一批：轻微随机坏事件（鸟啄、脱钩提示、家具发潮等）。"""
from __future__ import annotations

import random

from . import db


async def roll_tend_glitch(conn, steward_id: int, plot: dict) -> str | None:
    if random.random() > 0.08:
        return None
    crop = plot.get("crop")
    if not crop:
        return None
    roll = random.random()
    if roll < 0.4:
        left = int(plot.get("harvest_left") or 0)
        if left > 1:
            await conn.execute(
                "UPDATE parcels SET harvest_left=MAX(1, harvest_left-1) WHERE id=?",
                (plot["id"],),
            )
            return "斑鸠啄了一口，这茬收成少了一把（还能收，不是枯病）。"
    if roll < 0.65:
        return "灶台不好点火：今天做饭精力多耗 1（下次 cook 时生效，不是岸维）。"
    if roll < 0.85:
        return "潮气进棚，软装有发潮味——不影响数值，换晴会好。"
    return "鱼线打结了：下次坐钓空杆率略高（心理作用，真的）。"
