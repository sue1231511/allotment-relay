import random
import re
from typing import Any

import aiosqlite

from .. import config, db, events, flavor, farming, health, survival, world
from .. import commons
from ..catalog import (
    CROPS,
    resolve_crop_key,
    resolve_item_key,
    unknown_crop_message,
    unknown_item_message,
    FORAGE_LOOT,
    ITEM_NAMES,
    ITEM_PRICES,
    SEA_CATCH,
    item_label,
    item_stack_cap,
    suggested_price,
    weighted_fish_pick,
)
from ..config import (
    BADGES,
    BOATS,
    GUILD_SHIFT_DAILY,
    GUILD_TICKETS,
    MARKET_LIST_MAX,
    MARKET_LIST_SLOTS_MAX,
    MARKET_SLOT_COST,
    SWAP_CLAIM_FEE,
    BAR_MANDATORY_DAYS,
)


from .base import _parse_int, _parcel_line, _load_named_plot, require_steward


async def tide_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    pulse = await events.maybe_world_pulse(s)
    parts = command.strip().split()
    verb = parts[0].lower() if parts else "status"
    tide = world.current_tide()

    if verb == "status":
        stock = await db.get_satchel(s["id"])
        sea = {k: v for k, v in stock.items() if k.startswith("fish_")}
        msg = f"潮汐 {world.tide_label(tide)}\n" + (
            "\n".join(f"{ITEM_NAMES.get(k,k)} x{v}" for k, v in sea.items()) or "暂无渔获"
        )
        return f"{pulse}\n{msg}" if pulse else msg

    if verb == "catalog":
        from .. import catches as catches_mod
        async with db.connect() as conn:
            return await catches_mod.fish_catalog(conn, s["id"])

    if verb in ("搏鱼", "fight-fish", "fishfight"):
        from .. import big_fish_fight as fight_mod
        sub = " ".join(parts[1:]) if len(parts) > 1 else "status"
        async with db.connect() as conn:
            msg = await fight_mod.resolve(conn, s, sub.split()[0] if sub.split() else "status")
            await conn.commit()
        return f"{pulse}\n{msg}" if pulse else msg

    if verb in ("解挂", "unsnag", "snag"):
        from .. import fishing_parts as parts_mod
        sub = parts[1] if len(parts) > 1 else ""
        async with db.connect() as conn:
            msg = await parts_mod.clear_snag(conn, s["id"], sub or "status")
            await conn.commit()
        return msg

    if verb in ("水层", "layer", "zone"):
        from .. import sea_layer_pref as layer_mod
        sub = parts[1].lower() if len(parts) > 1 else "status"
        async with db.connect() as conn:
            if sub in ("status", "查看", ""):
                ly = await layer_mod.get_layer(conn, s["id"])
                return f"当前水层偏好：{ly}（岸带/栈桥 · 近海/礁/船尾 · 外海 · 深槽）"
            msg = await layer_mod.set_layer(conn, s["id"], sub)
            await conn.commit()
        return msg

    if verb == "net":
        cost = 4
        async with db.connect() as conn:
            await commons.maybe_spawn_commons(conn, steward_id=s["id"])
            from .. import energy as energy_mod, gear
            energy_cost, catch_bonus, rarity_bonus, empty_reduce = await energy_mod.net_energy_cost(conn, s["id"])
            stats = await gear.get_stats(conn, s["id"])
            if stats["net"]["tier"] < 1:
                raise ValueError("先 tide_ops gear upgrade net 升到 T1 粗渔网（或 tide_ops tool buy net_basic 兼容）")
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < cost:
                raise ValueError(f"撒网需要 {cost} 工分票")
            await conn.execute("UPDATE stewards SET tickets=tickets-? WHERE id=?", (cost, s["id"]))
            await energy_mod.spend(conn, s["id"], energy_cost, action="撒网")
            from .. import gear_wear as gear_wear_mod
            net_dur, net_mx = await gear_wear_mod.wear(conn, s["id"], "net")
            extra = await events.roll_after_action(s, "net", conn)
            disc = await commons.roll_discovery(conn, s, "net")
            from .. import shaonian as shaonian_mod
            daily = await shaonian_mod.get_daily(conn, s["id"])
            fortune_key = daily.get("fortune") or ""
            no_empty = await shaonian_mod.fishing_no_empty(conn, s["id"])
            from .. import craft as craft_mod
            net_patch = await craft_mod.active_net_patch(conn, s["id"])
            from .. import boat_parts as boat_parts_mod
            net_part_adj = await boat_parts_mod.net_empty_adjust(conn, s["id"])
            await boat_parts_mod.wear_net_winch(conn, s["id"])
            from .. import light_bad_events as light_mod
            snag_note = await light_mod.roll_net_snag(conn, s["id"])
            weed_adj, weed_clear_luck = await light_mod.net_empty_bonus(conn, s["id"])
            await conn.commit()
        weed_clear_luck = weed_clear_luck or ""
        empty_chance = (
            0.18 - await events.net_bonus_chance() - empty_reduce - catch_bonus * 0.4
            + await events.net_fog_penalty() - net_patch + net_part_adj + weed_adj
        )
        if not no_empty and random.random() < max(0.04, empty_chance):
            msg = f"空网 T{stats['net']['tier']}，只有水草"
            if snag_note:
                msg += f"\n{snag_note}"
            if extra:
                msg += f"\n{extra}"
            if disc:
                msg += f"\n{disc}"
            if weed_clear_luck:
                msg += f"\n{weed_clear_luck}"
            return f"{pulse}\n{msg}" if pulse else msg
        rarity_cap = 3 + rarity_bonus
        meta = None
        fight_msg = None
        storm_luck = ""
        async with db.connect() as conn:
            from .. import fish_ecology as fish_ecology_mod
            from .. import fish_ban as fish_ban_mod
            from .. import sea_layer_pref as layer_mod
            layer = await layer_mod.get_layer(conn, s["id"])
            cap = min(6, rarity_cap + 1) if fortune_key == "fish_catch" else rarity_cap
            catch = await fish_ecology_mod.pick(
                conn, mode="net", tide=tide, rarity_cap=cap, layer_override=layer,
            )
            if catch_bonus and random.random() < catch_bonus:
                catch = await fish_ecology_mod.pick(
                    conn, mode="net", tide=tide, rarity_cap=min(6, rarity_cap + 1),
                    layer_override=layer,
                )
            ban_msg = await fish_ban_mod.enforce(conn, s["id"], catch)
            if ban_msg:
                await conn.commit()
                parts_out = [x for x in (pulse, ban_msg, extra, disc) if x]
                return "\n".join(parts_out)
            meta = SEA_CATCH[catch]
            val_mult, tier_bonus = gear.fish_catch_payout(stats, mode="net")
            gear_bonus = int(meta["sell"] * max(0.0, val_mult - 1.0)) + tier_bonus
            from .. import item_traits as traits_mod
            state = traits_mod.roll_fish_state(catch)
            weight = traits_mod.roll_fish_weight_kg(catch)
            from .. import big_fish_fight as fight_mod
            fight_msg = await fight_mod.maybe_start(
                conn, s["id"], catch, weight_kg=weight, state=state, rod_tier=stats["net"]["tier"],
            )
            if not fight_msg:
                await traits_mod.grant_satchel(
                    conn, s["id"], f"fish_{catch}", 1,
                    quality=state, weight_kg=weight,
                )
                from .. import ledger as ledger_mod
                await ledger_mod.note_gain(
                    conn, s["id"], f"fish_{catch}", 1,
                    f"{meta['emoji']}{meta['name']}{weight}kg·{traits_mod.FISH_STATE_LABEL.get(state, state)}"
                    f"由{s['name']}于{ledger_mod.calendar_phrase()}"
                    f"在{world.tide_label(tide)}捞起",
                )
            if gear_bonus > 0 and not fight_msg:
                await conn.execute(
                    "UPDATE stewards SET tickets=tickets+? WHERE id=?",
                    (gear_bonus, s["id"]),
                )
            from .. import catches as catches_mod
            if not fight_msg:
                await catches_mod.record_catch(conn, s["id"], f"fish_{catch}")
            await survival.bump(conn, s["id"], satiety=5 if not fight_msg else 2)
            from .. import marine as marine_mod
            voyage = await marine_mod._get_voyage(conn, s["id"])
            if voyage and voyage.get("status") == "sailing" and not fight_msg:
                await marine_mod.append_voyage_fish(conn, voyage, f"fish_{catch}")
            # 未命名小鱼不能网：撒网不触发遭遇，渔获池也排除 walkblue
            from .. import tale as tale_mod
            if not fight_msg:
                await tale_mod.check_item_progress(conn, s["id"], f"fish_{catch}", 1)
            from .. import event_opportunity as opp_mod

            storm_luck = await opp_mod.maybe_storm_beach_luck(conn, s["id"], context="net")
            tale_extra = await tale_mod.check_action_progress(conn, s["id"], "sea")
            await conn.commit()
        storm_luck = storm_luck or ""
        from .. import gear_wear as gear_wear_mod
        acc = await gear_wear_mod.maybe_accident_note(net_dur, net_mx)
        if fight_msg:
            parts_out = [x for x in (pulse, fight_msg, extra, disc) if x]
            return "\n".join(parts_out)
        msg = (
            f"{s['name']} 在{world.tide_label(tide)}网到 {meta['emoji']}{meta['name']} "
            f"{weight}kg [{traits_mod.FISH_STATE_LABEL.get(state, state)}][网T{stats['net']['tier']}]"
        )
        if acc:
            msg += f" {acc}"
        if gear_bonus > 0:
            msg += f" 渔具加成+{gear_bonus}票"
        msg += flavor.maybe_suffix(flavor.NET_SUFFIX)
        await db.add_chronicle("tide", msg, s["id"])
        from .. import multi
        bonus = await multi.on_league_item(s["id"], f"fish_{catch}", 1)
        if bonus:
            await db.add_chronicle("league", bonus, None)
            msg = msg + f"\n{bonus}"
        if snag_note:
            msg += f"\n{snag_note}"
        if weed_clear_luck:
            msg += f"\n{weed_clear_luck}"
        if storm_luck:
            msg += f"\n{storm_luck}"
        if extra:
            msg += f"\n{extra}"
        if disc:
            msg += f"\n{disc}"
        if tale_extra:
            msg += f"\n\n{tale_extra}"
        return f"{pulse}\n{msg}" if pulse else msg

    if verb == "cast":
        cost = 3
        fight_msg = None
        async with db.connect() as conn:
            from .. import energy as energy_mod, gear
            from .. import fishing_parts as fish_parts_mod
            from .. import big_fish_fight as fight_mod
            await fish_parts_mod.assert_can_cast(conn, s["id"])
            if await fight_mod.get_pending(conn, s["id"]):
                raise ValueError("有大鱼在搏斗。先 tide_ops 搏鱼 硬拉|放走|切线")
            stats = await gear.get_stats(conn, s["id"])
            rod, bait = stats["rod"], stats["bait"]
            if rod["tier"] < 1:
                raise ValueError("先 tide_ops gear upgrade rod（T1 竹钓竿 30票）")
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < cost:
                raise ValueError(f"坐钓需要 {cost} 工分票")
            if not await db.take_item(conn, s["id"], "bait_worm", 1):
                raise ValueError("缺少蚯蚓饵 bait_worm（tend 地块 / tide_ops dig 获取）")
            await conn.execute("UPDATE stewards SET tickets=tickets-? WHERE id=?", (cost, s["id"]))
            await energy_mod.spend(conn, s["id"], rod["energy"], action="坐钓")
            from .. import gear_wear as gear_wear_mod
            rod_dur, rod_mx = await gear_wear_mod.wear(conn, s["id"], "rod")
            line_dur, line_mx = await gear_wear_mod.wear(conn, s["id"], "line")
            snagged, snag_note = await fish_parts_mod.wear_cast(conn, s["id"])
            extra = await events.roll_after_action(s, "net", conn)
            disc = await commons.roll_discovery(conn, s, "net")
            from .. import shaonian as shaonian_mod
            daily = await shaonian_mod.get_daily(conn, s["id"])
            fortune_key = daily.get("fortune") or ""
            no_empty = await shaonian_mod.fishing_no_empty(conn, s["id"])
            await conn.commit()
            if snagged:
                parts_out = [x for x in (pulse, snag_note, extra, disc) if x]
                return "\n".join(parts_out)
        catch_b, rarity_b, empty_b, _ = gear.combined_fish_bonus(bait=bait, rod=rod)
        snap_p = gear_wear_mod.line_snap_chance(line_dur, line_mx)
        if snap_p > 0 and random.random() < snap_p:
            msg = (
                f"断线了 饵T{bait['tier']} 竿T{rod['tier']} 线{line_dur}/{line_mx}"
                "——大鱼或旧线，票和饵已花。tide_ops gear repair line 或换线"
            )
            parts = [x for x in (pulse, msg, extra) if x]
            return "\n".join(parts)
        empty_chance = 0.24 - empty_b - await events.net_bonus_chance() + await events.net_fog_penalty()
        async with db.connect() as conn:
            from .. import light_bad_events as light_mod
            tangle = await light_mod.cast_empty_bonus(conn, s["id"])
            await conn.commit()
        empty_chance += tangle
        if not no_empty and random.random() < max(0.05, empty_chance):
            msg = f"空杆 饵T{bait['tier']} 竿T{rod['tier']}——鱼看了直摇头"
            parts = [x for x in (pulse, msg, extra) if x]
            return "\n".join(parts)
        rarity_cap = 3 + rarity_b
        async with db.connect() as conn:
            from .. import fish_ecology as fish_ecology_mod
            from .. import fish_ban as fish_ban_mod
            from .. import sea_layer_pref as layer_mod
            from .. import big_fish_fight as fight_mod
            layer = await layer_mod.get_layer(conn, s["id"])
            cap = min(6, rarity_cap + 1) if fortune_key == "fish_catch" else rarity_cap
            catch = await fish_ecology_mod.pick(
                conn, mode="cast", tide=tide, rarity_cap=cap, allow_cast_only=True,
                layer_override=layer,
            )
            if catch_b and random.random() < catch_b + 0.08:
                catch = await fish_ecology_mod.pick(
                    conn, mode="cast", tide=tide,
                    rarity_cap=min(6, rarity_cap + 1), allow_cast_only=True,
                    layer_override=layer,
                )
            ban_msg = await fish_ban_mod.enforce(conn, s["id"], catch)
            if ban_msg:
                await conn.commit()
                parts = [x for x in (pulse, ban_msg, extra) if x]
                return "\n".join(parts)
            meta = SEA_CATCH[catch]
            val_mult, tier_bonus = gear.fish_catch_payout(stats, mode="cast")
            gear_bonus = int(meta["sell"] * max(0.0, val_mult - 1.0)) + tier_bonus
            from .. import item_traits as traits_mod
            state = traits_mod.roll_fish_state(catch)
            weight = traits_mod.roll_fish_weight_kg(catch)
            fight_msg = await fight_mod.maybe_start(
                conn, s["id"], catch, weight_kg=weight, state=state, rod_tier=rod["tier"],
            )
            refind_note = ""
            if not fight_msg:
                await traits_mod.grant_satchel(
                    conn, s["id"], f"fish_{catch}", 1,
                    quality=state, weight_kg=weight,
                )
                from .. import event_opportunity as opp_mod

                refind_note = await opp_mod.maybe_consume_hook_refind(conn, s["id"]) or ""
                from .. import ledger as ledger_mod
                await ledger_mod.note_gain(
                    conn, s["id"], f"fish_{catch}", 1,
                    f"{meta['emoji']}{meta['name']}{weight}kg·{traits_mod.FISH_STATE_LABEL.get(state, state)}"
                    f"由{s['name']}于{ledger_mod.calendar_phrase()}"
                    f"在{world.tide_label(tide)}捞起",
                )
            if gear_bonus > 0 and not fight_msg:
                await conn.execute(
                    "UPDATE stewards SET tickets=tickets+? WHERE id=?",
                    (gear_bonus, s["id"]),
                )
            from .. import catches as catches_mod
            if not fight_msg:
                await catches_mod.record_catch(conn, s["id"], f"fish_{catch}")
            await survival.bump(conn, s["id"], satiety=4 if not fight_msg else 2)
            from .. import marine as marine_mod
            voyage = await marine_mod._get_voyage(conn, s["id"])
            legged = None
            curse_line = None
            if catch == "walkblue":
                curse_line = await marine_mod.on_obtain_walkblue(conn, s["id"])
            if voyage and voyage.get("status") == "sailing" and not fight_msg:
                await marine_mod.append_voyage_fish(conn, voyage, f"fish_{catch}")
                if catch != "walkblue":
                    legged = await marine_mod.try_legged_fish_encounter(conn, s, voyage)
                    if not legged:
                        breach = await marine_mod.try_hull_breach_encounter(conn, s, voyage)
                        if breach:
                            legged = breach
            from .. import tale as tale_mod
            if not fight_msg:
                await tale_mod.check_item_progress(conn, s["id"], f"fish_{catch}", 1)
            tale_extra = await tale_mod.check_action_progress(conn, s["id"], "sea")
            await conn.commit()
        acc = await gear_wear_mod.maybe_accident_note(rod_dur, rod_mx)
        if fight_msg:
            parts_out = [x for x in (pulse, fight_msg, extra, disc) if x]
            return "\n".join(parts_out)
        msg = (
            f"坐钓 {meta['emoji']}{meta['name']} {weight}kg "
            f"[{traits_mod.FISH_STATE_LABEL.get(state, state)}][饵T{bait['tier']} 竿T{rod['tier']}]"
        )
        if acc:
            msg += f" {acc}"
        if gear_bonus > 0:
            msg += f" 渔具加成+{gear_bonus}票"
        msg += flavor.maybe_suffix(["竿弯了，票没白花", "饵对路，鱼自来"])
        await db.add_chronicle("tide", f"{s['name']} 坐钓 {meta['name']}", s["id"])
        if refind_note:
            msg += f"\n{refind_note}"
        if extra:
            msg += f"\n{extra}"
        if disc:
            msg += f"\n{disc}"
        if curse_line:
            msg += f"\n{curse_line}"
        if legged:
            msg += f"\n{legged}"
        if tale_extra:
            msg += f"\n\n{tale_extra}"
        return f"{pulse}\n{msg}" if pulse else msg

    if verb in ("bottle", "漂流瓶", "捞瓶", "投瓶", "回瓶", "看瓶", "扫瓶"):
        from .. import bottles
        raw = command.strip()
        if verb in ("bottle", "漂流瓶"):
            bits = raw.split(None, 1)
            raw = bits[1] if len(bits) > 1 else "scan"
        return await bottles.bottle_ops(key_id, raw)

    raise ValueError(f"未知 tide 指令: {command}")



async def _collect_bottle_replies(conn: aiosqlite.Connection, steward_id: int) -> list[str]:
    prev = conn.row_factory
    conn.row_factory = aiosqlite.Row
    try:
        rows = await (await conn.execute(
            """
            SELECT b.id, b.reply_body, r.name AS from_name
            FROM drift_bottles b
            JOIN stewards r ON r.id=b.reply_by
            WHERE b.author_id=? AND b.reply_at IS NOT NULL
            ORDER BY b.reply_at DESC LIMIT 3
            """,
            (steward_id,),
        )).fetchall()
    finally:
        conn.row_factory = prev
    return [
        f"漂流瓶 #{r['id']} 有回瓶：{r['from_name']} — {r['reply_body'][:60]}"
        for r in rows
    ]



async def _collect_handoffs(conn: aiosqlite.Connection, steward_id: int) -> list[str]:
    """台阶上的离线交接进袋，并标已取。"""
    prev = conn.row_factory
    conn.row_factory = aiosqlite.Row
    try:
        rows = await (await conn.execute(
            """
            SELECT h.id, h.item, h.quantity, p.name AS from_name
            FROM handoffs h JOIN stewards p ON p.id=h.from_id
            WHERE h.to_id=? AND h.picked_up=0
            ORDER BY h.created_at
            """,
            (steward_id,),
        )).fetchall()
    finally:
        conn.row_factory = prev
    notes = []
    for r in rows:
        await db.add_item(conn, steward_id, r["item"], r["quantity"])
        await conn.execute("UPDATE handoffs SET picked_up=1 WHERE id=?", (r["id"],))
        label = ITEM_NAMES.get(r["item"], r["item"])
        notes.append(f"台阶交接：{r['from_name']} 放下的 {label} x{r['quantity']} 已入袋")
    return notes

