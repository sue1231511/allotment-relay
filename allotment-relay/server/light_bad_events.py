"""第一批：轻微随机坏事件（鸟啄、脱钩提示、家具发潮等）。"""
from __future__ import annotations

import random

from . import bad_event_tiers as tiers_mod
from . import db

DEBUFF_SYSTEM: dict[str, str] = {
    "stove_stubborn": "plot",
    "humid_soft": "plot",
    "line_tangle": "plot",
    "net_weed": "beach",
    "shovel_dull": "beach",
    "probe_sand": "beach",
    "barn_fuss": "barn",
}


async def ensure_flags_table(conn) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS steward_moment_flags (
            steward_id INTEGER NOT NULL REFERENCES stewards(id),
            flag_key TEXT NOT NULL,
            PRIMARY KEY (steward_id, flag_key)
        )
        """
    )


async def set_flag(conn, steward_id: int, flag_key: str) -> None:
    await ensure_flags_table(conn)
    await conn.execute(
        "INSERT OR REPLACE INTO steward_moment_flags (steward_id, flag_key) VALUES (?, ?)",
        (steward_id, flag_key),
    )


async def set_debuff(
    conn,
    steward_id: int,
    flag_key: str,
    tier: str,
    summary: str,
) -> None:
    await set_flag(conn, steward_id, flag_key)
    system = DEBUFF_SYSTEM.get(flag_key, "plot")
    await tiers_mod.record_open(
        conn, steward_id, system, tier, summary, ref_key=flag_key,
    )


async def has_flag(conn, steward_id: int, flag_key: str) -> bool:
    await ensure_flags_table(conn)
    cur = await conn.execute(
        "SELECT 1 FROM steward_moment_flags WHERE steward_id=? AND flag_key=?",
        (steward_id, flag_key),
    )
    return (await cur.fetchone()) is not None


async def take_flag(conn, steward_id: int, flag_key: str) -> bool:
    await ensure_flags_table(conn)
    cur = await conn.execute(
        "SELECT 1 FROM steward_moment_flags WHERE steward_id=? AND flag_key=?",
        (steward_id, flag_key),
    )
    if not await cur.fetchone():
        return False
    await conn.execute(
        "DELETE FROM steward_moment_flags WHERE steward_id=? AND flag_key=?",
        (steward_id, flag_key),
    )
    if flag_key in DEBUFF_SYSTEM:
        await tiers_mod.record_resolved(
            conn, steward_id, DEBUFF_SYSTEM[flag_key], ref_key=flag_key,
        )
    return True


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
            msg = "斑鸠啄了一口，这茬收成少了一把（还能收，不是枯病）。"
            await tiers_mod.record_flash(
                conn,
                steward_id,
                "plot",
                tiers_mod.TIER_MID,
                msg,
                ref_key="flash:bird_peck",
            )
            from . import event_opportunity as opp_mod

            luck = await opp_mod.maybe_bird_peck_luck(conn, steward_id, crop)
            out = tiers_mod.tag(tiers_mod.TIER_MID, msg)
            if luck:
                out += f"\n{luck}"
            from . import event_choice as choice_mod

            extra = await choice_mod.offer(conn, steward_id, "bird_peck")
            if extra:
                out += f"\n{extra}"
            return out
    if roll < 0.65:
        tier = tiers_mod.roll_tier(weights=(0.35, 0.40, 0.20, 0.05))
        msg = "灶台不好点火：下次做饭多耗 1 精力（已记下，做一次饭就消）。"
        await set_debuff(conn, steward_id, "stove_stubborn", tier, msg)
        from . import event_choice as choice_mod

        extra = await choice_mod.offer(conn, steward_id, "stove_stubborn")
        tagged = tiers_mod.tag(tier, msg)
        return f"{tagged}\n{extra}" if extra else tagged
    if roll < 0.85:
        tier = tiers_mod.roll_tier(weights=(0.30, 0.45, 0.20, 0.05))
        msg = "潮气进棚，软装有发潮味：下次睡觉少回 3 精力（已记下，睡一次就消）。"
        await set_debuff(conn, steward_id, "humid_soft", tier, msg)
        from . import event_choice as choice_mod

        extra = await choice_mod.offer(conn, steward_id, "humid_soft")
        tagged = tiers_mod.tag(tier, msg)
        return f"{tagged}\n{extra}" if extra else tagged
    tier = tiers_mod.TIER_LIGHT
    msg = "鱼线打结了：下次坐钓空杆率 +12%（已记下，坐钓一次就消）。"
    await set_debuff(conn, steward_id, "line_tangle", tier, msg)
    return tiers_mod.tag(tier, msg)


async def apply_stove_penalty(conn, steward_id: int) -> int:
    """若灶台难点火，做一次饭多耗 1 精力。返回额外精力。"""
    if await take_flag(conn, steward_id, "stove_stubborn"):
        return 1
    return 0


async def cast_empty_bonus(conn, steward_id: int) -> float:
    """鱼线打结：空杆率加成（消费一次）。"""
    if await take_flag(conn, steward_id, "line_tangle"):
        return 0.12
    return 0.0


async def net_empty_bonus(conn, steward_id: int) -> tuple[float, str | None]:
    """渔网挂水草：空网率加成（消费一次）。返回 (加成, 理网小确幸文案)。"""
    if not await take_flag(conn, steward_id, "net_weed"):
        return 0.0, None
    from . import event_opportunity as opp_mod

    luck = await opp_mod.maybe_net_weed_clear_luck(conn, steward_id)
    return 0.10, luck


async def roll_net_snag(conn, steward_id: int) -> str | None:
    """撒网后小概率挂水草，影响下次空网率。"""
    if random.random() > 0.07:
        return None
    tier = tiers_mod.roll_tier(weights=(0.45, 0.35, 0.15, 0.05))
    msg = (
        "渔网挂水草：下次撒网空网率 +10%（已记下，撒一次就消）。"
        + tiers_mod.repair_hint("beach")
    )
    await set_debuff(conn, steward_id, "net_weed", tier, msg)
    return tiers_mod.tag(tier, msg)


async def sleep_energy_penalty(conn, steward_id: int) -> int:
    if await take_flag(conn, steward_id, "humid_soft"):
        return 3
    return 0


async def dig_energy_penalty(conn, steward_id: int) -> int:
    if await take_flag(conn, steward_id, "shovel_dull"):
        return 2
    return 0


async def probe_energy_penalty(conn, steward_id: int) -> int:
    if await take_flag(conn, steward_id, "probe_sand"):
        return 2
    return 0


async def roll_probe_sand_glitch(conn, steward_id: int) -> str | None:
    if random.random() > 0.08:
        return None
    tier = tiers_mod.TIER_MID
    msg = (
        "沙坍回填：下次掏洞多耗 2 精力（已记下，掏一次就消）。"
        + tiers_mod.repair_hint("beach")
    )
    await set_debuff(conn, steward_id, "probe_sand", tier, msg)
    return tiers_mod.tag(tier, msg)


async def roll_beach_dig_glitch(conn, steward_id: int) -> str | None:
    """翻沙后小概率铲刃发钝，下次多耗精力。"""
    if random.random() > 0.09:
        return None
    tier = tiers_mod.roll_tier()
    msg = (
        "铲刃磕在礁上发钝：下次赶海翻沙多耗 2 精力（已记下，翻一次就消）。"
        + tiers_mod.repair_hint("beach")
    )
    await set_debuff(conn, steward_id, "shovel_dull", tier, msg)
    return tiers_mod.tag(tier, msg)
