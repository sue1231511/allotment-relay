"""赶海 — 退潮 + 铲子，贝壳/竹蛏/蚯蚓饵；scan 看滩面，probe 掏洞。"""

from __future__ import annotations

import random

import aiosqlite

from . import commons, config, db, energy, flavor, world
from .catalog import BEACH_LOOT
from .game import require_steward


def _beach_weights(tide: str, weather: str, *, probe: bool = False) -> list[int]:
    weights = [x[3] for x in BEACH_LOOT]
    for i, row in enumerate(BEACH_LOOT):
        item = row[0]
        if tide == "ebb":
            if item.startswith("shell"):
                weights[i] += 10
            if item.startswith("fish_") or item.startswith("beach_"):
                weights[i] += 6
        elif tide == "slack" and probe:
            weights[i] += 4
        if weather == "misty" and (
            item.startswith("curio_") or item == "sea_glass" or item.startswith("fish_sea")
        ):
            weights[i] += 8
        if weather == "clear" and item.startswith("shell"):
            weights[i] += 5
        if probe:
            if item.startswith("fish_") or item in ("beach_crab", "beach_squid", "bait_worm"):
                weights[i] += 12
            if item.startswith("shell"):
                weights[i] -= 4
    return [max(1, w) for w in weights]


def _roll_loot(tide: str, weather: str, *, probe: bool = False) -> tuple[str, str, int]:
    weights = _beach_weights(tide, weather, probe=probe)
    roll = random.choices(BEACH_LOOT, weights=weights)[0]
    item, label, qty, _, _ = roll
    return item, label, qty


async def _grant_loot(
    conn,
    steward_id: int,
    item: str,
    qty: int,
) -> tuple[str, int]:
    """发放赶海掉落；贝壳带品相。"""
    from . import cloth as cloth_mod
    from .catalog import item_label
    item = cloth_mod.maybe_upgrade_beach_fabric(item)
    if item.startswith("shell_"):
        from . import lili_extras
        from collections import Counter
        graded = [lili_extras.beach_shell_item(item) for _ in range(qty)]
        for gitem, gqty in Counter(graded).items():
            await db.add_item(conn, steward_id, gitem, gqty)
        label = next(x[1] for x in BEACH_LOOT if x[0] == item)
        if any(g.startswith("shell_shine_") for g in graded):
            label += "（✨亮壳）"
        elif any(g.startswith("shell_rough_") for g in graded):
            label += "（💧糙壳）"
        return label, qty
    await db.add_item(conn, steward_id, item, qty)
    label = next((x[1] for x in BEACH_LOOT if x[0] == item), item_label(item))
    return label, qty


async def beach_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    parts = command.strip().split()
    verb = parts[0].lower() if parts else "status"

    if verb in ("status", "scan"):
        tide = world.current_tide()
        w = world.current_weather()
        stock = await db.get_satchel(s["id"])
        has_shovel = stock.get("tool_shovel", 0) > 0
        lines = [
            world.climate_line(),
            f"铲子: {'有' if has_shovel else '无 — tide_ops tool buy shovel'}",
            f"dig 翻沙 {config.BEACH_ENERGY} 精力（须 tool_shovel）"
            f" · probe 掏洞 {config.BEACH_PROBE_ENERGY} 精力",
        ]
        if tide == "ebb":
            lines.append("退潮：贝壳/渔获权重 ↑")
        elif tide == "slack":
            lines.append("平潮：可用 probe 掏洞（收益略低）")
        else:
            lines.append("涨潮：dig 不可用；probe 需退潮或平潮")
        if w == "clear":
            lines.append("晴朗：贝壳权重 +5")
        if w == "misty":
            lines.append("雾天：珠砂/海玻璃等稀有 +8")
        if tide == "ebb":
            lines.append("刚退潮前 10 分钟：亮壳率 ↑（捡得好不如捡得巧）")
        if verb == "scan":
            lines.append("")
            lines.append("常见货色（权重参考）:")
            preview = sorted(BEACH_LOOT, key=lambda x: -x[3])[:8]
            for item, label, _, wt, price in preview:
                lines.append(f"  {label}（约{wt} · 建议{price}票）")
            lines.append("指令: dig / probe · catalog 图鉴")
        return "\n".join(lines)

    if verb == "catalog":
        from . import catches as catches_mod
        async with db.connect() as conn:
            return await catches_mod.beach_catalog(conn, s["id"])

    if verb == "dig":
        tide = world.current_tide()
        if tide not in ("ebb", "slack"):
            raise ValueError("涨潮没过脚面。dig 和 probe 都不可用，等落潮再来。beach scan 还能看一眼。")
        stock = await db.get_satchel(s["id"])
        if not stock.get("tool_shovel"):
            raise ValueError("需要铲子 tide_ops tool buy shovel")

        now = db.now()
        day = db.day_id(now)
        w = world.current_weather()
        async with db.connect() as conn:
            cur = await conn.execute(
                "SELECT last_at, count FROM beach_rolls WHERE steward_id=? AND day=?",
                (s["id"], day),
            )
            row = await cur.fetchone()
            if row and now - row[0] < config.BEACH_COOLDOWN:
                left = config.BEACH_COOLDOWN - (now - row[0])
                raise ValueError(f"这片滩刚翻过，{left // 60} 分后再来")
            await energy.spend(conn, s["id"], config.BEACH_ENERGY, action="赶海")

            item, label, qty = _roll_loot(tide, w, probe=False)
            label, qty = await _grant_loot(conn, s["id"], item, qty)
            extra_msg = ""
            from . import cloth as cloth_mod
            from .catalog import item_label as cloth_label
            extra_fab = cloth_mod.beach_loot_item()
            if extra_fab:
                await db.add_item(conn, s["id"], extra_fab, 1)
                extra_msg += f"，又拾到 {cloth_label(extra_fab)}"
            season_dye = await cloth_mod.maybe_event_dye(conn, s["id"], "season")
            if season_dye:
                extra_msg += f"，{season_dye}"
            from . import lili_extras
            if await lili_extras.has_blessing(conn, s["id"], "fair_wind"):
                await lili_extras.consume_blessing(conn, s["id"], "fair_wind")
                bonus_label, _ = await _grant_loot(conn, s["id"], item, max(1, qty // 2))
                extra_msg += f"，顺风 +{bonus_label}"
            from . import shaonian as shaonian_mod
            if await shaonian_mod.beach_double(conn, s["id"]):
                dlabel, _ = await _grant_loot(conn, s["id"], item, qty)
                extra_msg += f"，赶海符翻倍 +{dlabel} x{qty}"
            from . import catches as catches_mod
            await catches_mod.record_catch(conn, s["id"], item)
            if tide == "ebb" and random.random() < 0.14:
                bait = random.choice([x for x in BEACH_LOOT if x[0].startswith("bait_")])
                await db.add_item(conn, s["id"], bait[0], 1)
                extra_msg += f"，顺手 {bait[1]}"
            from . import hut as hut_mod
            hut_b = await hut_mod.get_bonuses(conn, s["id"])
            if hut_b.beach_extra and random.random() < hut_b.beach_extra:
                bonus_item, _, bonus_qty = _roll_loot(tide, w, probe=False)
                blabel, _ = await _grant_loot(conn, s["id"], bonus_item, max(1, bonus_qty))
                extra_msg += f"，潮汐钟多响一声：{blabel}"
            await conn.execute(
                """
                INSERT INTO beach_rolls (steward_id, day, last_at, count)
                VALUES (?,?,?,1)
                ON CONFLICT(steward_id, day) DO UPDATE SET
                    last_at=excluded.last_at, count=count+1
                """,
                (s["id"], day, now),
            )
            disc = await commons.roll_discovery(conn, s, "beach")
            from . import health
            beach_ill = await health.maybe_roll_ailment(
                conn, s["id"], "beach", chance=0.10, source="beach",
            )
            beach_boost = await health.maybe_restore_health(
                conn, s["id"], "beach", chance=0.12, lo=4, hi=10,
            )
            from . import lili as lili_mod
            lili_spawn = await lili_mod.maybe_spawn_visit(conn)
            from . import npc as npc_mod
            shiye = await npc_mod.maybe_shiye_bump(conn, s, "beach")
            from . import tale as tale_mod
            tale_extra = await tale_mod.check_action_progress(conn, s["id"], "beach")
            from . import cloth as cloth_mod
            cloth_echo = await cloth_mod.try_echo(conn, s, "beach")
            from . import marriage as marriage_mod
            betroth_find = await marriage_mod.maybe_place_find(conn, s["id"], "beach")
            await conn.commit()

        msg = f"赶海：{label} x{qty}{extra_msg}"
        if beach_ill:
            msg += f"\n{beach_ill}\n→ visit_ops clinic treat …（必须花票）"
        if beach_boost:
            msg += f"\n{beach_boost}"
        if lili_spawn:
            msg += f"\n✨ {lili_spawn['detail']} → visit_ops lili scan"
        if shiye:
            msg += f"\n{shiye}"
        msg += flavor.maybe_suffix([
            "沙里藏货，铲子诚不欺我",
            "猫眼螺在看你，你也看它",
            "退潮捡漏，联盟传统艺能",
            "翻沙一时爽，背包一直爽",
        ])
        if disc:
            msg += f"\n{disc}"
        if tale_extra:
            msg += f"\n\n{tale_extra}"
        if cloth_echo:
            msg += f"\n\n{cloth_echo}"
        if betroth_find:
            msg += f"\n{betroth_find}"
        await db.add_chronicle("beach", f"{s['name']} 赶海得 {label}", s["id"])
        return msg

    if verb == "probe":
        tide = world.current_tide()
        if tide == "flood":
            raise ValueError("浪涌没过脚面，probe 也掏不着")
        stock = await db.get_satchel(s["id"])
        if not stock.get("tool_shovel"):
            raise ValueError("需要铲子 tide_ops tool buy shovel")

        now = db.now()
        day = db.day_id(now)
        w = world.current_weather()
        async with db.connect() as conn:
            cur = await conn.execute(
                "SELECT last_at FROM beach_probe_rolls WHERE steward_id=? AND day=?",
                (s["id"], day),
            )
            row = await cur.fetchone()
            if row and now - row[0] < config.BEACH_PROBE_COOLDOWN:
                left = config.BEACH_PROBE_COOLDOWN - (now - row[0])
                raise ValueError(f"洞刚掏过，{left // 60} 分后再试")
            await energy.spend(conn, s["id"], config.BEACH_PROBE_ENERGY, action="掏洞")

            item, _, qty = _roll_loot(tide, w, probe=True)
            if tide != "ebb":
                qty = max(1, qty // 2)
            label, qty = await _grant_loot(conn, s["id"], item, qty)
            charm_msg = ""
            from . import shaonian as shaonian_mod
            if await shaonian_mod.beach_double(conn, s["id"]):
                dlabel, _ = await _grant_loot(conn, s["id"], item, qty)
                charm_msg = f"，赶海符翻倍 +{dlabel} x{qty}"
            from . import catches as catches_mod
            await catches_mod.record_catch(conn, s["id"], item)
            clock_msg = ""
            from . import hut as hut_mod
            hut_b = await hut_mod.get_bonuses(conn, s["id"])
            if hut_b.beach_extra and random.random() < hut_b.beach_extra:
                bonus_item, _, bonus_qty = _roll_loot(tide, w, probe=True)
                blabel, _ = await _grant_loot(conn, s["id"], bonus_item, max(1, bonus_qty))
                clock_msg = f"，潮汐钟：{blabel}"
            await conn.execute(
                """
                INSERT INTO beach_probe_rolls (steward_id, day, last_at, count)
                VALUES (?,?,?,1)
                ON CONFLICT(steward_id, day) DO UPDATE SET
                    last_at=excluded.last_at, count=count+1
                """,
                (s["id"], day, now),
            )
            disc = await commons.roll_discovery(conn, s, "beach")
            from . import npc as npc_mod
            shiye = await npc_mod.maybe_shiye_bump(conn, s, "beach")
            from . import tale as tale_mod
            tale_extra = await tale_mod.check_action_progress(conn, s["id"], "beach")
            from . import cloth as cloth_mod
            cloth_echo = await cloth_mod.try_echo(conn, s, "beach")
            from . import health as health_mod
            probe_boost = await health_mod.maybe_restore_health(
                conn, s["id"], "beach", chance=0.10, lo=3, hi=8,
            )
            from . import marriage as marriage_mod
            betroth_find = await marriage_mod.maybe_place_find(conn, s["id"], "beach")
            await conn.commit()

        msg = f"掏洞：{label} x{qty}{charm_msg}{clock_msg}"
        msg += flavor.maybe_suffix([
            "洞里货不多，但胜在新鲜",
            "沙蟹横着跑，你横着捞",
            "探洞手艺人，退潮不打烊",
        ])
        if probe_boost:
            msg += f"\n{probe_boost}"
        if disc:
            msg += f"\n{disc}"
        if shiye:
            msg += f"\n{shiye}"
        if tale_extra:
            msg += f"\n\n{tale_extra}"
        if cloth_echo:
            msg += f"\n\n{cloth_echo}"
        if betroth_find:
            msg += f"\n{betroth_find}"
        await db.add_chronicle("beach", f"{s['name']} 掏洞得 {label}", s["id"])
        return msg

    raise ValueError(f"未知 beach 指令: {command}（status/scan/dig/probe）")
