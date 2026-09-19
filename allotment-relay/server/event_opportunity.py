"""坏事件里的低概率机会 — §五（坏事也能带来机会）。"""
from __future__ import annotations

import random

from . import db, world
from .catalog import CROPS

STORM_WEATHER = frozenset({"rain", "storm", "gale"})


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


async def maybe_net_weed_clear_luck(conn, steward_id: int) -> str | None:
    """撒网消「挂水草」debuff 时，小概率从网里抠出货。"""
    if random.random() > 0.13:
        return None
    if random.random() < 0.52:
        await db.add_item(conn, steward_id, "bait_worm", 2)
        return "理网扯水草，抠出两包活饵——网虽挂过，虫没跑。"
    await db.add_item(conn, steward_id, "drift_twine", 1)
    return "水草里缠一截新漂绳，理网时不算白忙。"


async def maybe_storm_beach_luck(
    conn,
    steward_id: int,
    *,
    context: str,
    weather: str | None = None,
) -> str | None:
    """雨/风暴天气赶海或撒网，小概率冲出特殊贝壳。"""
    w = weather or world.current_weather()
    if w not in STORM_WEATHER:
        return None
    if random.random() > 0.12:
        return None
    shells = (
        ("fossil_shell", "暴雨冲出化石贝壳"),
        ("shell_conch", "浪涌推来一只海螺"),
        ("shell_catseye", "猫眼螺被浪打上岸"),
        ("shell_scallop", "扇贝壳从沙里翻出来"),
    )
    key, phrase = random.choice(shells)
    await db.add_item(conn, steward_id, key, 1)
    if context == "dig":
        return f"{phrase}——坏天气里多捡一件。"
    return f"{phrase}，网里竟夹着浪赏。"


async def maybe_runaway_trail_luck(conn, steward: dict, choice: str) -> str | None:
    """寻回逃畜时小概率跟足迹找到潮边藏货（急追略高）。"""
    norm = (choice or "").strip()
    chase = norm in ("急追",) or norm.lower() in ("chase",)
    if random.random() > (0.14 if chase else 0.08):
        return None
    sid = steward["id"]
    roll = random.random()
    if roll < 0.4:
        await db.add_item(conn, sid, "bait_worm", 3)
        return "追着蹄印拐进潮洼，捡到几包活饵——像隐藏补给点。"
    if roll < 0.7:
        await db.add_item(conn, sid, "shell_mussel", 2)
        return "牲口停过的石缝里嵌着青口贝，像谁藏的小宝库。"
    await db.add_item(conn, sid, "sea_glass", 2)
    await db.add_chronicle(
        "plot", f"{steward['name']} 寻回逃畜时摸到潮边藏贝点", sid, conn=conn,
    )
    return "跟着足迹摸到潮边藏贝点，拾两枚海玻璃。"


async def maybe_blight_pull_luck(conn, steward_id: int, pest_key: str) -> str | None:
    """拔除菌病病株时，小概率烧出灰肥。"""
    if pest_key != "blight":
        return None
    if random.random() > 0.22:
        return None
    await db.add_item(conn, steward_id, "ash_fert", 1)
    await db.add_chronicle(
        "plot", "病株烧成一把灰肥", steward_id, conn=conn,
    )
    return "病株烧成一把灰肥（施肥 1 灰肥，比普通堆肥猛一点）。"


async def maybe_storm_wreck_luck(conn, steward_id: int, *, storm: bool) -> str | None:
    """风暴折返/阵风归港，小概率捞到别人的残骸。"""
    if not storm:
        return None
    if random.random() > 0.16:
        return None
    await db.add_item(conn, steward_id, "wreck_scrap", 1)
    return "浪里挂住一截别人的船骸——潮骸残件×1（可打船模）。"
