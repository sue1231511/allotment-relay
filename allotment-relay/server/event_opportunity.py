"""坏事件里的低概率机会 — §五（坏事也能带来机会）。"""
from __future__ import annotations

import random

from . import db
from .catalog import CROPS


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


async def maybe_bird_peck_luck(conn, steward_id: int, crop_key: str) -> str | None:
    """鸟啄少一把后，小概率啄落可留种。"""
    if random.random() > 0.12:
        return None
    if not crop_key or crop_key not in CROPS:
        return None
    seed_key = f"seed_{crop_key}"
    await db.add_item(conn, steward_id, seed_key, 1)
    name = CROPS[crop_key].get("name", crop_key)
    await db.add_chronicle(
        "plot",
        f"斑鸠啄菜后落下{name}种一粒",
        steward_id,
        conn=conn,
    )
    return f"斑鸠叼走一把，却落下 1 粒{name}种——坏事里捡到的。"


HOOK_REFIND_FLAG = "hook_refind"


async def maybe_line_cut_luck(conn, steward_id: int, *, context: str) -> str | None:
    """解挂/搏鱼切线后，小概率标记「旧钩可再钓回」或捡到海玻璃。"""
    if random.random() > 0.11:
        return None
    roll = random.random()
    if roll < 0.55:
        from . import light_bad_events as light_mod

        await light_mod.set_flag(conn, steward_id, HOOK_REFIND_FLAG)
        if context == "fight":
            return "线断了，但钩形还在潮里——下次坐钓上岸鱼，说不定把旧钩捎回来。"
        return "切线虽损，潮底还挂着旧钩——下次坐钓有鱼进袋，可能捎回一截耐久。"
    await db.add_item(conn, steward_id, "sea_glass", 2)
    return "断线处漂来两枚海玻璃，像海的找零。"


async def maybe_consume_hook_refind(conn, steward_id: int) -> str | None:
    """坐钓成功进袋时消费 hook_refind 标记，恢复钩耐久。"""
    from . import light_bad_events as light_mod
    from . import fishing_parts as parts_mod

    if not await light_mod.has_flag(conn, steward_id, HOOK_REFIND_FLAG):
        return None
    await light_mod.take_flag(conn, steward_id, HOOK_REFIND_FLAG)
    await parts_mod.ensure_table(conn)
    await conn.execute(
        """
        UPDATE steward_fish_parts
        SET durability=MIN(max_dur, durability+22)
        WHERE steward_id=? AND part_key='hook'
        """,
        (steward_id,),
    )
    return "进袋时线头一紧——潮里那只旧钩被捎回来了（钩耐久+22）。"
