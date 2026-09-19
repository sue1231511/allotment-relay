"""四档坏事件点名册 + 缺档补齐。

轻微/麻烦/危险/灾难方案名单在这里对齐；真正掷骰仍走各系统原模块。
"""
from __future__ import annotations

import random
from typing import Any

from . import bad_event_tiers as tiers_mod

NAMED_EVENTS: tuple[dict[str, str], ...] = (
    # 轻微
    {"key": "bird_peck", "tier": tiers_mod.TIER_LIGHT, "name": "鸟啄菜", "mod": "light_bad_events"},
    {"key": "line_slip", "tier": tiers_mod.TIER_LIGHT, "name": "鱼脱钩", "mod": "fishing_parts"},
    {"key": "humid_soft", "tier": tiers_mod.TIER_LIGHT, "name": "家具发潮", "mod": "light_bad_events"},
    {"key": "stove_stubborn", "tier": tiers_mod.TIER_LIGHT, "name": "灶台不好点火", "mod": "light_bad_events"},
    {"key": "barn_fuss", "tier": tiers_mod.TIER_LIGHT, "name": "动物闹脾气", "mod": "event_catalog"},
    {"key": "line_tangle", "tier": tiers_mod.TIER_LIGHT, "name": "鱼线打结", "mod": "light_bad_events"},
    {"key": "net_weed", "tier": tiers_mod.TIER_LIGHT, "name": "渔网挂水草", "mod": "light_bad_events"},
    {"key": "shovel_dull", "tier": tiers_mod.TIER_LIGHT, "name": "铲刃发钝", "mod": "light_bad_events"},
    {"key": "probe_sand", "tier": tiers_mod.TIER_LIGHT, "name": "沙坍回填", "mod": "light_bad_events"},
    {"key": "frost_chore", "tier": tiers_mod.TIER_LIGHT, "name": "冰箱结霜", "mod": "hut_chores"},
    {"key": "door_hinge", "tier": tiers_mod.TIER_LIGHT, "name": "门轴坏", "mod": "hut_chores"},
    {"key": "roof_drip", "tier": tiers_mod.TIER_LIGHT, "name": "屋顶渗水", "mod": "hut_chores"},
    {"key": "lamp_out", "tier": tiers_mod.TIER_LIGHT, "name": "灯具坏", "mod": "hut_chores"},
    # 麻烦
    {"key": "fridge_break", "tier": tiers_mod.TIER_MID, "name": "冰箱坏", "mod": "hut_appliances"},
    {"key": "sheep_escape", "tier": tiers_mod.TIER_MID, "name": "羊逃跑", "mod": "barn"},
    {"key": "pest", "tier": tiers_mod.TIER_MID, "name": "病虫害", "mod": "plot_pests"},
    {"key": "sail_tear", "tier": tiers_mod.TIER_MID, "name": "船帆撕裂", "mod": "voyage_sail_event"},
    {"key": "gh_leak", "tier": tiers_mod.TIER_MID, "name": "温室漏风", "mod": "plot_pests"},
    {"key": "rats", "tier": tiers_mod.TIER_MID, "name": "鼠害", "mod": "plot_pests"},
    {"key": "wind_scorch", "tier": tiers_mod.TIER_MID, "name": "海风灼叶", "mod": "plot_pests"},
    {"key": "woodworm", "tier": tiers_mod.TIER_MID, "name": "木材虫蛀", "mod": "hut_chores"},
    {"key": "stove_clog", "tier": tiers_mod.TIER_MID, "name": "灶台堵塞", "mod": "hut_chores"},
    {"key": "mold_soft", "tier": tiers_mod.TIER_MID, "name": "家具发霉", "mod": "hut_chores"},
    {"key": "hold_leak", "tier": tiers_mod.TIER_MID, "name": "鱼舱进水", "mod": "event_catalog"},
    # 危险
    {"key": "bilge", "tier": tiers_mod.TIER_HEAVY, "name": "船底进水", "mod": "boat_parts"},
    {"key": "murrain", "tier": tiers_mod.TIER_HEAVY, "name": "牲畜传染病", "mod": "barn_disease"},
    {"key": "quarry_collapse", "tier": tiers_mod.TIER_HEAVY, "name": "矿坑塌方", "mod": "quarry_collapse"},
    {"key": "roof_leak_bad", "tier": tiers_mod.TIER_HEAVY, "name": "房屋漏雨严重", "mod": "hut_roof"},
    {"key": "hold_break", "tier": tiers_mod.TIER_HEAVY, "name": "鱼舱坏掉", "mod": "event_catalog"},
    {"key": "well_crack", "tier": tiers_mod.TIER_HEAVY, "name": "井裂", "mod": "undertide_well_crack"},
    {"key": "dystocia", "tier": tiers_mod.TIER_HEAVY, "name": "难产", "mod": "barn_breeding"},
    # 灾难
    {"key": "storm_wreck", "tier": tiers_mod.TIER_FATAL, "name": "强风暴重创船只", "mod": "marine"},
    {"key": "epidemic", "tier": tiers_mod.TIER_FATAL, "name": "大规模疫病", "mod": "event_catalog"},
    {"key": "tide_press", "tier": tiers_mod.TIER_FATAL, "name": "地下潮压异常", "mod": "layer_link"},
    {"key": "sinkhole", "tier": tiers_mod.TIER_FATAL, "name": "岸上地陷", "mod": "plot_pests"},
    {"key": "crop_wipe", "tier": tiers_mod.TIER_FATAL, "name": "大面积作物毁坏", "mod": "event_catalog"},
    # 已有系统补进册，凑规模
    {"key": "rabbit", "tier": tiers_mod.TIER_LIGHT, "name": "兔踩苗", "mod": "farming"},
    {"key": "deer", "tier": tiers_mod.TIER_LIGHT, "name": "鹿啃叶", "mod": "farming"},
    {"key": "boar", "tier": tiers_mod.TIER_MID, "name": "野猪拱地", "mod": "farming"},
    {"key": "gull", "tier": tiers_mod.TIER_LIGHT, "name": "鸥啄浆", "mod": "farming"},
    {"key": "slug", "tier": tiers_mod.TIER_LIGHT, "name": "蛞蝓", "mod": "farming"},
    {"key": "crow", "tier": tiers_mod.TIER_LIGHT, "name": "乌鸦", "mod": "farming"},
    {"key": "dove", "tier": tiers_mod.TIER_MID, "name": "斑鸠盯梢", "mod": "farming"},
    {"key": "woodpecker", "tier": tiers_mod.TIER_LIGHT, "name": "啄木鸟", "mod": "farming"},
    {"key": "dry_spell", "tier": tiers_mod.TIER_MID, "name": "旱风", "mod": "farming"},
    {"key": "canker", "tier": tiers_mod.TIER_HEAVY, "name": "树瘟", "mod": "farming"},
    {"key": "squirrel", "tier": tiers_mod.TIER_LIGHT, "name": "松鼠偷果", "mod": "farming"},
    {"key": "hail", "tier": tiers_mod.TIER_HEAVY, "name": "黑旗截停", "mod": "marine"},
    {"key": "clinic_queue", "tier": tiers_mod.TIER_MID, "name": "候诊区堵", "mod": "clinic"},
    {"key": "barn_choke", "tier": tiers_mod.TIER_MID, "name": "棚里呙", "mod": "vet"},
    {"key": "bar_sink", "tier": tiers_mod.TIER_LIGHT, "name": "吧槽溢水", "mod": "bar_sink_flood"},
    {"key": "eatery_smoke", "tier": tiers_mod.TIER_LIGHT, "name": "小馆走烟", "mod": "eatery_smoke_panic"},
    {"key": "stall_gust", "tier": tiers_mod.TIER_LIGHT, "name": "阵风掀摊", "mod": "market_stall_gust"},
    {"key": "salt_blot", "tier": tiers_mod.TIER_HEAVY, "name": "潮返盐斑", "mod": "layer_link"},
    {"key": "well_return", "tier": tiers_mod.TIER_MID, "name": "井口返潮", "mod": "layer_link"},
    {"key": "home_wick", "tier": tiers_mod.TIER_LIGHT, "name": "灯芯爆", "mod": "home_events"},
    {"key": "home_roof", "tier": tiers_mod.TIER_LIGHT, "name": "屋顶夜响", "mod": "home_events"},
    {"key": "leg_fish", "tier": tiers_mod.TIER_MID, "name": "腿鱼小咒", "mod": "marine"},
    {"key": "red_tide", "tier": tiers_mod.TIER_HEAVY, "name": "赤潮蛰伤", "mod": "health"},
    {"key": "hull_leak", "tier": tiers_mod.TIER_HEAVY, "name": "船体漏", "mod": "boat_hull"},
    {"key": "line_snap", "tier": tiers_mod.TIER_MID, "name": "断线", "mod": "fishing_parts"},
    {"key": "snag", "tier": tiers_mod.TIER_MID, "name": "挂底", "mod": "fishing_parts"},
    {"key": "big_fight", "tier": tiers_mod.TIER_MID, "name": "大鱼搏斗", "mod": "big_fish_fight"},
    {"key": "aphid", "tier": tiers_mod.TIER_MID, "name": "蚜虫", "mod": "plot_pests"},
    {"key": "root_rot", "tier": tiers_mod.TIER_MID, "name": "根腐", "mod": "plot_pests"},
    {"key": "blight", "tier": tiers_mod.TIER_HEAVY, "name": "菌病", "mod": "plot_pests"},
    {"key": "peach_worm", "tier": tiers_mod.TIER_MID, "name": "桃虫", "mod": "farming"},
    {"key": "grape_rot", "tier": tiers_mod.TIER_MID, "name": "葡萄雨烂", "mod": "farming"},
    {"key": "storm_wreck_part", "tier": tiers_mod.TIER_FATAL, "name": "风暴折帆", "mod": "voyage_sail_event"},
    {"key": "murrain_week", "tier": tiers_mod.TIER_FATAL, "name": "畜瘟潮", "mod": "world"},
    {"key": "quarry_dust", "tier": tiers_mod.TIER_MID, "name": "岩尘入肺", "mod": "quarry"},
    {"key": "well_fall", "tier": tiers_mod.TIER_HEAVY, "name": "井下落伤", "mod": "undertide"},
    {"key": "fish_ban", "tier": tiers_mod.TIER_MID, "name": "禁捕放生", "mod": "fish_ban"},
    {"key": "escape_cache", "tier": tiers_mod.TIER_LIGHT, "name": "逃畜足迹藏货", "mod": "event_opportunity"},
    {"key": "blight_ash", "tier": tiers_mod.TIER_LIGHT, "name": "病株灰肥", "mod": "event_opportunity"},
    {"key": "wreck_scrap", "tier": tiers_mod.TIER_MID, "name": "风暴残骸", "mod": "event_opportunity"},
)


def named_count() -> int:
    return len(NAMED_EVENTS)


def fatal_count() -> int:
    return sum(1 for e in NAMED_EVENTS if e["tier"] == tiers_mod.TIER_FATAL)


def plan_pool_ok() -> bool:
    names = {e["name"] for e in NAMED_EVENTS}
    need = {
        "鸟啄菜", "鱼脱钩", "家具发潮", "灶台不好点火", "动物闹脾气",
        "冰箱坏", "羊逃跑", "病虫害", "船帆撕裂", "温室漏风",
        "船底进水", "牲畜传染病", "矿坑塌方", "房屋漏雨严重", "鱼舱坏掉",
        "强风暴重创船只", "大规模疫病", "地下潮压异常", "岸上地陷", "大面积作物毁坏",
    }
    return need <= names


async def roll_barn_fuss(conn, steward_id: int) -> str | None:
    """畜栏轻微：动物闹脾气，下次 collect 少一把。"""
    if random.random() > 0.10:
        return None
    cur = await conn.execute(
        "SELECT id, slot, species FROM barn_animals "
        "WHERE steward_id=? AND species IS NOT NULL ORDER BY RANDOM() LIMIT 1",
        (steward_id,),
    )
    row = await cur.fetchone()
    if not row:
        return None
    from . import light_bad_events as light_mod

    msg = f"{row[1]}号栏闹脾气：下次收成少一把（已记下，收一次就消）。"
    await light_mod.set_debuff(
        conn, steward_id, "barn_fuss", tiers_mod.TIER_LIGHT, msg
    )
    await tiers_mod.record_flash(
        conn, steward_id, "barn", tiers_mod.TIER_LIGHT, msg, ref_key="flash:barn_fuss"
    )
    from . import event_choice as choice_mod

    extra = await choice_mod.offer(conn, steward_id, "barn_fuss")
    tagged = tiers_mod.tag(tiers_mod.TIER_LIGHT, msg)
    return f"{tagged}\n{extra}" if extra else tagged


async def take_barn_fuss(conn, steward_id: int) -> bool:
    from . import light_bad_events as light_mod

    return await light_mod.take_flag(conn, steward_id, "barn_fuss")


async def roll_hold_leak(conn, steward_id: int, *, fatal: bool = False) -> str | None:
    """出航后鱼舱进水 / 坏掉。"""
    from . import boat_parts as parts_mod

    parts = await parts_mod.get_all(conn, steward_id)
    hold, mx = parts.get("hold", (100, 100))
    if hold >= 70 and not fatal:
        return None
    loss = 28 if fatal else 12
    new = max(0, hold - loss)
    await conn.execute(
        "UPDATE steward_boat_parts SET durability=? WHERE steward_id=? AND part_key='hold'",
        (new, steward_id),
    )
    tier = tiers_mod.TIER_FATAL if fatal else tiers_mod.TIER_HEAVY
    if fatal:
        msg = f"鱼舱裂开进水（舱 {hold}→{new}）。可修 / 返航 / 硬撑。voyage_ops 部件 修"
    else:
        msg = f"鱼舱渗水（舱 {hold}→{new}）。可修 / 继续。voyage_ops 部件 修"
    await tiers_mod.record_flash(
        conn, steward_id, "voyage", tier, msg, ref_key="flash:hold_leak"
    )
    from . import event_choice as choice_mod

    extra = await choice_mod.offer(
        conn, steward_id, "hold_break" if fatal else "hold_leak"
    )
    tagged = tiers_mod.tag(tier, msg)
    return f"{tagged}\n{extra}" if extra else tagged


async def roll_crop_wipe(conn, steward_id: int) -> str | None:
    """灾难：大面积作物毁坏（风暴/疫病周才掴）。"""
    if random.random() > 0.04:
        return None
    cur = await conn.execute(
        """
        SELECT id, slot FROM parcels
        WHERE steward_id=? AND crop IS NOT NULL AND COALESCE(greenhouse,0)=0
        ORDER BY slot
        """,
        (steward_id,),
    )
    rows = await cur.fetchall()
    if len(rows) < 2:
        return None
    take = rows[: min(3, len(rows))]
    for pid, _slot in take:
        await conn.execute(
            "UPDATE parcels SET pest_key='blight', pest_level=2 WHERE id=?",
            (pid,),
        )
    slots = "、".join(str(r[1]) for r in take)
    msg = (
        f"大面积作物毁坏：{slots}号地染上菌病。"
        "可手工/施药/拔除（plot_ops 虫害）。"
    )
    await tiers_mod.record_flash(
        conn, steward_id, "plot", tiers_mod.TIER_FATAL, msg, ref_key="flash:crop_wipe"
    )
    return tiers_mod.tag(tiers_mod.TIER_FATAL, msg)


async def roll_epidemic(conn, steward_id: int) -> str | None:
    """灾难：栏里多只传染畜瘟。"""
    if random.random() > 0.03:
        return None
    cur = await conn.execute(
        "SELECT id FROM barn_animals WHERE steward_id=? AND species IS NOT NULL AND species!='bee'",
        (steward_id,),
    )
    ids = [int(r[0]) for r in await cur.fetchall()]
    if len(ids) < 2:
        return None
    from . import barn_disease as dis_mod

    for aid in ids:
        await dis_mod.apply_ailment(conn, aid, "murrain")
    msg = "大规模疫病：栏里非蜂箱牲口染上畜瘟。visit_ops 霍衡 treat"
    await tiers_mod.record_flash(
        conn, steward_id, "barn", tiers_mod.TIER_FATAL, msg, ref_key="flash:epidemic"
    )
    from . import event_choice as choice_mod

    extra = await choice_mod.offer(conn, steward_id, "epidemic")
    tagged = tiers_mod.tag(tiers_mod.TIER_FATAL, msg)
    return f"{tagged}\n{extra}" if extra else tagged
