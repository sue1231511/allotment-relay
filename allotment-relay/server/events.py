import random
import uuid
from typing import Any

import aiosqlite

from . import config, db, event_gen, farming, flavor, health, survival, world
from .catalog import CROPS, ITEM_NAMES


def _day_id() -> int:
    return db.now() // config.FORAGE_COOLDOWN_DAY


def _roll_multiplier(steward: dict[str, Any], hut_event_mult: float = 1.0) -> float:
    mult = 1.0
    weather = world.current_weather()
    if weather == "gale":
        mult *= 1.45
    elif weather == "clear":
        mult *= 0.85
    if steward.get("mascot_trait") == "lucky":
        from . import social as social_mod
        mult *= 0.72 / social_mod.mascot_trait_mult(steward.get("mascot_spirit", 70))
    return mult * hut_event_mult


async def _can_roll(conn: aiosqlite.Connection, steward_id: int) -> bool:
    day = _day_id()
    cur = await conn.execute(
        "SELECT count FROM event_rolls WHERE steward_id=? AND day=?",
        (steward_id, day),
    )
    row = await cur.fetchone()
    used = row[0] if row else 0
    return used < config.EVENT_DAILY_CAP


async def _mark_roll(conn: aiosqlite.Connection, steward_id: int) -> None:
    day = _day_id()
    await conn.execute(
        """
        INSERT INTO event_rolls (steward_id, day, count) VALUES (?,?,1)
        ON CONFLICT(steward_id, day) DO UPDATE SET count = count + 1
        """,
        (steward_id, day),
    )


async def _pick_plot(
    conn: aiosqlite.Connection,
    steward_id: int,
    *,
    need_crop: bool = True,
    exclude_ids: set[int] | None = None,
) -> dict[str, Any] | None:
    conn.row_factory = aiosqlite.Row
    exclude_ids = exclude_ids or set()
    if need_crop:
        if exclude_ids:
            placeholders = ",".join("?" * len(exclude_ids))
            cur = await conn.execute(
                f"""
                SELECT * FROM parcels
                WHERE steward_id=? AND crop IS NOT NULL AND greenhouse=0
                  AND id NOT IN ({placeholders})
                ORDER BY RANDOM() LIMIT 1
                """,
                (steward_id, *exclude_ids),
            )
        else:
            cur = await conn.execute(
                """
                SELECT * FROM parcels
                WHERE steward_id=? AND crop IS NOT NULL AND greenhouse=0
                ORDER BY RANDOM() LIMIT 1
                """,
                (steward_id,),
            )
    else:
        cur = await conn.execute(
            "SELECT * FROM parcels WHERE steward_id=? ORDER BY RANDOM() LIMIT 1",
            (steward_id,),
        )
    row = await cur.fetchone()
    return dict(row) if row else None


async def _steal_random_item(conn: aiosqlite.Connection, steward_id: int) -> str | None:
    conn.row_factory = aiosqlite.Row
    rows = await (await conn.execute(
        "SELECT item, quantity FROM satchel WHERE steward_id=? AND quantity > 0 ORDER BY RANDOM() LIMIT 5",
        (steward_id,),
    )).fetchall()
    if not rows:
        return None
    row = random.choice(rows)
    qty = 1 if row["quantity"] == 1 else min(row["quantity"], random.randint(1, max(1, row["quantity"] // 2)))
    await db.take_item(conn, steward_id, row["item"], qty)
    return f"{ITEM_NAMES.get(row['item'], row['item'])} x{qty}"


def _plot_ready(plot: dict[str, Any]) -> bool:
    return farming.plot_ready(plot)


async def _has_peers(conn: aiosqlite.Connection, steward_id: int) -> bool:
    cur = await conn.execute(
        "SELECT 1 FROM stewards WHERE enrolled=1 AND id!=? LIMIT 1",
        (steward_id,),
    )
    return await cur.fetchone() is not None


async def _random_peer(conn: aiosqlite.Connection, steward_id: int) -> dict[str, Any] | None:
    conn.row_factory = aiosqlite.Row
    row = await (await conn.execute(
        "SELECT * FROM stewards WHERE enrolled=1 AND id!=? ORDER BY RANDOM() LIMIT 1",
        (steward_id,),
    )).fetchone()
    return dict(row) if row else None


async def _pick_ripe_plot(conn: aiosqlite.Connection, steward_id: int) -> dict[str, Any] | None:
    conn.row_factory = aiosqlite.Row
    rows = [
        dict(r) for r in await (await conn.execute(
            """
            SELECT * FROM parcels
            WHERE steward_id=? AND crop IS NOT NULL AND greenhouse=0
            """,
            (steward_id,),
        )).fetchall()
    ]
    ready = [
        p for p in rows
        if _plot_ready(p) and farming.scrump_take_qty(farming.remaining_harvest(p)) > 0
    ]
    return random.choice(ready) if ready else None


async def _scrump_victim(
    conn: aiosqlite.Connection,
    steward: dict[str, Any],
) -> tuple[str, int | None, int | None] | None:
    plot = await _pick_ripe_plot(conn, steward["id"])
    if not plot:
        return None
    from . import npc
    thief = npc.pick_thief_name()
    result = await nibble_ripe_plot(conn, plot)
    crop_name = result["label"]
    detail = flavor.fill(
        flavor.pick(flavor.SCRUMP_VICTIM),
        thief=thief,
        slot=plot["slot"],
        crop=crop_name,
    )
    if result["left"] > 0:
        detail += f"（{result['note']}）"
    action = "scrump"
    await conn.execute(
        "INSERT INTO chronicle (action, actor_id, target_id, text, created_at) VALUES (?, ?, ?, ?, ?)",
        (
            action,
            None,
            steward["id"],
            f"{thief} 逾篱摘了 {steward['name']} 的 {crop_name}",
            db.now(),
        ),
    )
    return detail, plot["id"], None


async def _scrump_attempt(
    conn: aiosqlite.Connection,
    steward: dict[str, Any],
) -> tuple[str, int | None, int | None] | None:
    jail_note = ""
    peer = await _random_peer(conn, steward["id"])
    if not peer:
        return None
    plot = await _pick_ripe_plot(conn, peer["id"])
    if not plot:
        return None
    active = db.now() - peer["last_active_at"] <= config.SCRUMP_ACTIVE_WINDOW
    weather = world.current_weather()
    if weather == "misty":
        active = active and db.now() - peer["last_active_at"] <= 600
    elif weather == "gale":
        active = True
    caught = active
    fine = config.SCRUMP_FINE_TICKETS
    if caught and steward.get("mascot_trait") == "scout":
        fine = max(1, fine // 2)
    loot = flavor.pick(flavor.SCRUMP_EMPTY)
    if not caught:
        result = await nibble_ripe_plot(conn, plot, thief_id=steward["id"])
        loot = result["label"]
        detail = flavor.fill(
            flavor.pick(flavor.SCRUMP_SUCCESS),
            crop=loot,
            victim=peer["name"],
            slot=plot["slot"],
        )
        if result["left"] > 0:
            detail += f"（{result['note']}）"
        action = "scrump"
    elif caught:
        await conn.execute(
            "UPDATE stewards SET tickets=MAX(0, tickets-?) WHERE id=?",
            (fine, steward["id"]),
        )
        await survival.bump(conn, steward["id"], standing=-random.randint(6, 12))
        from . import undertide as _ut
        jail_note = await _ut.on_scrump_busted(conn, steward) or ""
        detail = flavor.fill(
            flavor.pick(flavor.SCRUMP_CAUGHT),
            slot=plot["slot"],
            victim=peer["name"],
            fine=fine,
        )
        action = "scrump_busted"
    else:
        detail = flavor.pick(flavor.SCRUMP_EMPTY)
        action = "scrump"
    await conn.execute(
        "INSERT INTO chronicle (action, actor_id, target_id, text, created_at) VALUES (?, ?, ?, ?, ?)",
        (
            action,
            steward["id"],
            peer["id"],
            f"{steward['name']} ↔ {peer['name']} #{plot['slot']} {loot}",
            db.now(),
        ),
    )
    hint = flavor.pick(flavor.HEDGE_QUIPS)
    detail = detail + jail_note
    return f"{detail}（{hint}；可 plot_ops amends {peer['name']}）", plot["id"], peer["id"]


def _scrump_catch_chance(
    steward: dict[str, Any],
    peer: dict[str, Any],
    plot: dict[str, Any],
    *,
    dog: bool,
) -> float:
    home = db.now() - peer["last_active_at"] <= config.SCRUMP_ACTIVE_WINDOW
    chance = 0.70 if home else 0.18
    weather = world.current_weather()
    if weather == "misty":
        chance -= 0.10
    elif weather == "gale":
        chance += 0.08
    if plot.get("scarecrow"):
        chance += 0.15
    if dog:
        chance += 0.20
    if steward.get("mascot_trait") == "scout":
        chance -= 0.10
    return max(0.08, min(0.92, chance))


async def nibble_ripe_plot(
    conn: aiosqlite.Connection,
    plot: dict[str, Any],
    *,
    thief_id: int | None = None,
) -> dict[str, Any]:
    """从熟地掐走至多三成。永远留一把，不能摘空。"""
    crop = plot["crop"]
    meta = CROPS[crop]
    left = farming.remaining_harvest(plot)
    taken = farming.scrump_take_qty(left)
    if taken <= 0:
        raise ValueError("就剩一把了，不能再摘空。换一块地，或等主人 gather。")
    leftover = left - taken
    if thief_id is not None:
        await db.add_item(conn, thief_id, f"crop_{crop}", taken)
    await conn.execute(
        "UPDATE parcels SET harvest_left=? WHERE id=?",
        (leftover, plot["id"]),
    )
    label = f"{meta['name']} x{taken}"
    return {
        "crop": crop,
        "name": meta["name"],
        "label": label,
        "taken": taken,
        "left": leftover,
        "note": f"地里还剩 {leftover} 把",
        "emptied": False,
    }


async def take_ripe_plot(
    conn: aiosqlite.Connection,
    thief_id: int,
    plot: dict[str, Any],
) -> str:
    """摘走一块熟地的一部分：菜进小偷行囊。"""
    result = await nibble_ripe_plot(conn, plot, thief_id=thief_id)
    return result["label"]


async def manual_scrump(steward: dict[str, Any], target_name: str, slot: int | None = None) -> str:
    """主动逾篱：plot_ops 偷菜 名字 [地块]。"""
    peer = await db.get_steward_by_name(target_name)
    if not peer or not peer.get("enrolled"):
        raise ValueError(
            f"找不到管理员「{target_name}」。先 alliance_ops 邻居 看名单。"
        )
    if peer["id"] == steward["id"]:
        raise ValueError("不能偷自己的菜")
    day = _day_id()
    async with db.connect() as conn:
        used = (await (await conn.execute(
            "SELECT COUNT(*) FROM scrump_log WHERE thief_id=? AND day=?",
            (steward["id"], day),
        )).fetchone())[0]
        if used >= config.SCRUMP_DAILY:
            raise ValueError(f"今日逾篱已满 {config.SCRUMP_DAILY} 次，明天再来")
        same = await (await conn.execute(
            "SELECT 1 FROM scrump_log WHERE thief_id=? AND target_id=? AND day=?",
            (steward["id"], peer["id"], day),
        )).fetchone()
        if same:
            raise ValueError(f"今天已经摘过 {peer['name']} 一次，换一家或明天再来")

        conn.row_factory = aiosqlite.Row
        if slot is not None:
            row = await (await conn.execute(
                "SELECT * FROM parcels WHERE steward_id=? AND slot=?",
                (peer["id"], slot),
            )).fetchone()
            if not row:
                raise ValueError(f"{peer['name']} 没有份地 #{slot}")
            plot = dict(row)
            if plot.get("greenhouse"):
                raise ValueError("温室摘不到。只偷露天份地。")
            if not farming.plot_ready(plot):
                raise ValueError(f"{peer['name']} #{slot} 还没熟")
        else:
            plot = await _pick_ripe_plot(conn, peer["id"])
            if not plot:
                raise ValueError(
                    f"{peer['name']} 没有熟透的露天份地。alliance_ops 邻居 看谁家熟了。"
                )

        from . import barn as barn_mod
        dog = await barn_mod.has_guard_dog(conn, peer["id"])
        chance = _scrump_catch_chance(steward, peer, plot, dog=dog)
        caught = random.random() < chance
        fine = config.SCRUMP_FINE_TICKETS
        if caught and steward.get("mascot_trait") == "scout":
            fine = max(1, fine // 2)

        await conn.execute(
            "INSERT INTO scrump_log (thief_id, target_id, day) VALUES (?,?,?)",
            (steward["id"], peer["id"], day),
        )

        if caught:
            await conn.execute(
                "UPDATE stewards SET tickets=MAX(0, tickets-?) WHERE id=?",
                (fine, steward["id"]),
            )
            await survival.bump(conn, steward["id"], standing=-random.randint(6, 12))
            from . import undertide as _ut
            jail_note = await _ut.on_scrump_busted(conn, steward) or ""
            detail = flavor.fill(
                flavor.pick(flavor.SCRUMP_CAUGHT),
                slot=plot["slot"],
                victim=peer["name"],
                fine=fine,
            )
            extra = []
            if plot.get("scarecrow"):
                extra.append("稻草人盯上了")
            if dog:
                extra.append("守夜狗叫了")
            if extra:
                detail += f"（{'、'.join(extra)}）"
            action = "scrump_busted"
            loot = "被抓"
            msg = detail + jail_note + f"（可 plot_ops amends {peer['name']}）"
        else:
            nibble = await nibble_ripe_plot(conn, plot, thief_id=steward["id"])
            loot = nibble["label"]
            detail = flavor.fill(
                flavor.pick(flavor.SCRUMP_SUCCESS),
                crop=loot,
                victim=peer["name"],
                slot=plot["slot"],
            )
            action = "scrump"
            msg = (
                f"{detail}\n入袋 {loot}，{nibble['note']}。"
                f"今日逾篱 {used + 1}/{config.SCRUMP_DAILY}"
            )

        await conn.execute(
            "INSERT INTO chronicle (action, actor_id, target_id, text, created_at) VALUES (?,?,?,?,?)",
            (
                action,
                steward["id"],
                peer["id"],
                f"{steward['name']} 逾篱 {peer['name']} #{plot['slot']} {loot}",
                db.now(),
            ),
        )
        await conn.commit()
    return msg


async def _apply_effects(
    conn: aiosqlite.Connection,
    steward: dict[str, Any],
    effects: list[str],
    *,
    pen: dict[str, Any] | None = None,
    plot_id_holder: list[int | None],
    exclude_parcel_id: int | None = None,
) -> tuple[list[str], dict[str, Any]]:
    ailment_msgs: list[str] = []
    ledger: dict[str, Any] = {"ticket_delta": 0, "stolen": None, "loot": []}
    exclude = {exclude_parcel_id} if exclude_parcel_id else set()
    for eff in effects:
        if eff == "plot_untend":
            plot = await _pick_plot(conn, steward["id"], exclude_ids=exclude)
            if plot:
                plot_id_holder[0] = plot["id"]
                await conn.execute("UPDATE parcels SET tended=0 WHERE id=?", (plot["id"],))
        elif eff == "plot_wreck":
            plot = await _pick_plot(conn, steward["id"], exclude_ids=exclude)
            if plot:
                plot_id_holder[0] = plot["id"]
                await conn.execute(
                    "UPDATE parcels SET crop=NULL, planted_at=NULL, tended=0 WHERE id=?",
                    (plot["id"],),
                )
        elif eff == "plot_delay":
            plot = await _pick_plot(conn, steward["id"], exclude_ids=exclude)
            if plot and plot.get("planted_at"):
                plot_id_holder[0] = plot["id"]
                delay = random.randint(600, 1200)
                await conn.execute(
                    "UPDATE parcels SET planted_at = planted_at + ?, tended=0 WHERE id=?",
                    (delay, plot["id"]),
                )
        elif eff == "steal_item":
            stolen = await _steal_random_item(conn, steward["id"])
            if stolen:
                ledger["stolen"] = stolen
        elif eff == "pen_unfeed" and pen:
            plot_id_holder[0] = pen["id"]
            await conn.execute("UPDATE fish_pens SET fed=0 WHERE id=?", (pen["id"],))
        elif eff == "pen_wreck" and pen:
            plot_id_holder[0] = pen["id"]
            await conn.execute(
                "UPDATE fish_pens SET species=NULL, stocked_at=NULL, fed=0 WHERE id=?",
                (pen["id"],),
            )
        elif eff == "boat_damage":
            await conn.execute("UPDATE stewards SET boat_damaged=1 WHERE id=?", (steward["id"],))
        elif eff.startswith("ticket_fine:"):
            amt = int(eff.split(":")[1])
            await conn.execute(
                "UPDATE stewards SET tickets = MAX(0, tickets - ?) WHERE id=?",
                (amt, steward["id"]),
            )
            ledger["ticket_delta"] -= amt
        elif eff.startswith("ticket_bonus:"):
            amt = int(eff.split(":")[1])
            await conn.execute(
                "UPDATE stewards SET tickets = tickets + ? WHERE id=?",
                (amt, steward["id"]),
            )
            ledger["ticket_delta"] += amt
        elif eff.startswith("mascot_spirit:"):
            delta = int(eff.split(":")[1])
            await conn.execute(
                "UPDATE stewards SET mascot_spirit = MAX(0, MIN(100, mascot_spirit + ?)) WHERE id=?",
                (delta, steward["id"]),
            )
        elif eff.startswith("standing:"):
            await survival.bump(conn, steward["id"], standing=int(eff.split(":")[1]))
        elif eff.startswith("mist_wit:"):
            await survival.bump(conn, steward["id"], mist_wit=int(eff.split(":")[1]))
        elif eff.startswith("satiety:"):
            await survival.bump(conn, steward["id"], satiety=int(eff.split(":")[1]))
        elif eff.startswith("voyage_delay:"):
            delay = int(eff.split(":")[1])
            await conn.execute(
                "UPDATE voyages SET returns_at = returns_at + ? WHERE steward_id=? AND status='sailing'",
                (delay, steward["id"]),
            )
        elif eff.startswith("loot:"):
            _, item, qty_s = eff.split(":", 2)
            qty = int(qty_s)
            await db.add_item(conn, steward["id"], item, qty)
            ledger["loot"].append((item, qty))
        elif eff.startswith("ailment:"):
            key = eff.split(":", 1)[1]
            msg = await health.inflict(conn, steward["id"], key, source="event")
            if msg:
                ailment_msgs.append(msg)
    return ailment_msgs, ledger


async def _ledger_lines(
    conn: aiosqlite.Connection,
    steward_id: int,
    ledger: dict[str, Any],
) -> list[str]:
    lines: list[str] = []
    stolen = ledger.get("stolen")
    if stolen:
        lines.append(f"失物：{stolen}")
    for item, qty in ledger.get("loot") or ():
        lines.append(f"入袋：{ITEM_NAMES.get(item, item)}（{item}）x{qty}")
    delta = int(ledger.get("ticket_delta") or 0)
    if delta:
        cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (steward_id,))
        left = (await cur.fetchone())[0]
        sign = f"+{delta}" if delta > 0 else str(delta)
        lines.append(f"工分票 {sign}（余 {left}）")
    return lines


async def apply_effects(
    conn: aiosqlite.Connection,
    steward: dict[str, Any],
    effects: list[str],
    *,
    pen: dict[str, Any] | None = None,
    plot_id_holder: list[int | None] | None = None,
    exclude_parcel_id: int | None = None,
) -> list[str]:
    holder = plot_id_holder if plot_id_holder is not None else [None]
    msgs, _ = await _apply_effects(
        conn, steward, effects, pen=pen, plot_id_holder=holder,
        exclude_parcel_id=exclude_parcel_id,
    )
    return msgs


async def roll_after_action(
    steward: dict[str, Any],
    trigger: str,
    conn: aiosqlite.Connection,
    *,
    pen: dict[str, Any] | None = None,
    voyage: dict[str, Any] | None = None,
    protected_parcel_id: int | None = None,
) -> str | None:
    if trigger not in event_gen.ALL_TRIGGERS:
        return None

    from . import npc as npc_mod
    shiye = await npc_mod.maybe_shiye_bump(conn, steward, trigger)
    from . import tt as tt_mod
    tt_hit = None if shiye else await tt_mod.maybe_tt_bump(conn, steward, trigger)

    if not await _can_roll(conn, steward["id"]):
        return shiye or tt_hit

    await survival.on_action(conn, steward["id"], trigger)
    if shiye or tt_hit:
        return shiye or tt_hit

    from . import hut as hut_mod
    hut_b = await hut_mod.get_bonuses(conn, steward["id"])
    if hut_b.night_mist_save and world.current_day_phase() in ("dusk", "night"):
        await survival.bump(conn, steward["id"], mist_wit=hut_b.night_mist_save)

    mult = (
        _roll_multiplier(steward, hut_b.event_mult)
        * survival.event_multiplier(steward)
        * world.incident_night_bias()
    )
    ailments = await health.list_ailments(conn, steward["id"])
    mult *= health.event_bias(steward, len(ailments))
    from . import shaonian as shaonian_mod
    bad_bonus = await shaonian_mod.event_bad_share_bonus(conn, steward["id"])
    if random.random() > config.EVENT_ROLL_CHANCE * mult:
        return None

    good_share = config.EVENT_GOOD_SHARE * hut_b.good_share
    if bad_bonus:
        good_share = max(0.05, good_share - bad_bonus)
    good = random.random() < good_share
    if not good:
        from . import lili_extras
        if await lili_extras.has_blessing(conn, steward["id"], "shield"):
            await lili_extras.consume_blessing(conn, steward["id"], "shield")
            return "夜栖替你挡了一下。这次坏事件没了。"
    if world.current_weather() == "gale" and trigger in {
        "tend", "gather", "sow", "voyage_depart", "voyage_return", "pen_feed", "net",
    }:
        if random.random() < hut_b.gale_event:
            good = False

    pulse = await active_world_pulse(conn)
    if pulse and pulse.get("effect_type") == "red_tide" and trigger in {"net", "pen_feed", "pen_harvest"}:
        good = False

    allow_scrump = await _has_peers(conn, steward["id"])
    if allow_scrump:
        cur = await conn.execute(
            "SELECT 1 FROM barn_animals WHERE steward_id=? AND guard=1 LIMIT 1",
            (steward["id"],),
        )
        if await cur.fetchone() and random.random() < 0.5:
            allow_scrump = False
    event = event_gen.generate_event(
        trigger,
        steward,
        good=good,
        pen=pen,
        voyage=voyage is not None,
        allow_scrump=allow_scrump,
    )
    if not event:
        return None

    plot_id_holder: list[int | None] = [None]
    is_scrump = False
    try:
        if "scrump_victim" in event.effects:
            res = await _scrump_victim(conn, steward)
            if not res:
                return None
            event.detail, plot_id_holder[0], _ = res
            event.effects = [e for e in event.effects if e != "scrump_victim"]
            is_scrump = True
        elif "scrump_attempt" in event.effects:
            res = await _scrump_attempt(conn, steward)
            if not res:
                return None
            event.detail, plot_id_holder[0], _ = res
            event.effects = [e for e in event.effects if e != "scrump_attempt"]
            is_scrump = True
        ailment_msgs, ledger = await _apply_effects(
            conn, steward, event.effects, pen=pen, plot_id_holder=plot_id_holder,
            exclude_parcel_id=protected_parcel_id,
        )
    except Exception:
        return None

    await _mark_roll(conn, steward["id"])
    msg = flavor.wrap_event(event.kind, event.label, event.detail)
    for line in await _ledger_lines(conn, steward["id"], ledger):
        msg += f"\n{line}"
    if ailment_msgs:
        msg += "\n" + ailment_msgs[0]
        msg += "\n→ visit_ops clinic · treat 病症（必须花票）"
    elif event.kind == "bad" and not is_scrump:
        extra_ailment = await health.maybe_roll_ailment(conn, steward["id"], trigger, chance=0.12)
        if extra_ailment:
            msg += f"\n{extra_ailment}\n→ visit_ops clinic treat …（必须花票）"

    iid = None
    if event.kind == "bad" and not is_scrump:
        key = f"gen:{uuid.uuid4().hex[:10]}"
        cur = await conn.execute(
            """
            INSERT INTO steward_incidents (
                steward_id, incident_key, plot_id, detail, label,
                repair_tickets, repair_item, repair_qty, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                steward["id"],
                key,
                plot_id_holder[0],
                event.detail,
                event.label,
                event.repair_tickets,
                event.repair_item,
                event.repair_qty or 0,
                db.now(),
            ),
        )
        iid = cur.lastrowid
        already = -int(ledger.get("ticket_delta") or 0) if int(ledger.get("ticket_delta") or 0) < 0 else 0
        hint = f"plot_ops repair {iid}"
        if event.repair_item:
            hint += (
                f"（处理另需 {event.repair_tickets} 票 / "
                f"{ITEM_NAMES.get(event.repair_item, event.repair_item)} x{event.repair_qty or 1}）"
            )
        elif event.repair_tickets:
            hint += f"（处理另需 {event.repair_tickets} 票）"
        if already:
            hint += f" · 刚才已当场扣 {already} 票"
        msg += f"\n→ {hint}"

    if not is_scrump:
        await conn.execute(
            "INSERT INTO chronicle (action, actor_id, target_id, text, created_at) VALUES (?, ?, ?, ?, ?)",
            ("incident", steward["id"], None, f"{steward['name']} — {event.detail}", db.now()),
        )
    return msg


async def gather_blight_loss(conn: aiosqlite.Connection, steward_id: int, crop_key: str) -> bool:
    pulse = await active_world_pulse(conn)
    if not pulse or pulse.get("effect_type") != "blight_whisper":
        return False
    return random.random() <= 0.28


async def net_bonus_chance() -> float:
    pulse = await active_world_pulse()
    if pulse and pulse.get("effect_type") == "fish_run":
        return 0.32
    if pulse and pulse.get("effect_type") == "calm_sea":
        return 0.12
    return 0.0


async def voyage_fail_modifier() -> float:
    pulse = await active_world_pulse()
    if pulse and pulse.get("effect_type") == "calm_sea":
        return -0.08
    if pulse and pulse.get("effect_type") == "storm_front":
        return 0.1
    return 0.0


async def active_world_pulse(conn: aiosqlite.Connection | None = None) -> dict[str, Any] | None:
    if conn is None:
        async with db.connect() as c:
            c.row_factory = aiosqlite.Row
            return await active_world_pulse(c)
    conn.row_factory = aiosqlite.Row
    now = db.now()
    await conn.execute("DELETE FROM world_pulse WHERE expires_at <= ?", (now,))
    row = await (await conn.execute(
        "SELECT * FROM world_pulse ORDER BY started_at DESC LIMIT 1"
    )).fetchone()
    return dict(row) if row else None


async def maybe_world_pulse(steward: dict[str, Any]) -> str | None:
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        if await active_world_pulse(conn):
            return None
        if random.random() > config.WORLD_PULSE_CHANCE:
            return None
        pulse = event_gen.generate_world_pulse()
        now = db.now()
        key = f"{pulse['effect']}:{uuid.uuid4().hex[:6]}"
        await conn.execute(
            """
            INSERT INTO world_pulse (
                pulse_key, label, kind, effect_type, fish_focus, detail, started_at, expires_at
            ) VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                key,
                pulse["label"],
                pulse["kind"],
                pulse["effect"],
                pulse.get("fish_focus"),
                pulse.get("detail") or pulse["text"],
                now,
                now + config.WORLD_PULSE_DURATION,
            ),
        )
        if pulse["effect"] == "storm_front":
            await conn.execute(
                "UPDATE parcels SET tended=0 WHERE greenhouse=0 AND crop IS NOT NULL",
            )
        await conn.commit()
        from . import lore as lore_mod
        msg = f"🌊 全服脉冲·{pulse['label']}：{pulse['text']}"
        barton = lore_mod.barton_season_note(pulse["effect"])
        if barton and random.random() < 0.55:
            msg += f"\n老水手巴顿：「{barton}」"
        await db.add_chronicle("pulse", msg, steward["id"])
        return msg


async def public_pulse_snapshot() -> dict[str, Any] | None:
    pulse = await active_world_pulse()
    if not pulse:
        return None
    return {
        "key": pulse["pulse_key"],
        "label": pulse["label"],
        "kind": pulse["kind"],
        "effect": pulse.get("effect_type", ""),
        "detail": pulse.get("detail", ""),
        "expires_at": pulse["expires_at"],
        "remaining": max(0, pulse["expires_at"] - db.now()),
    }


async def list_open_incidents_on(
    conn: aiosqlite.Connection, steward_id: int,
) -> list[dict[str, Any]]:
    conn.row_factory = aiosqlite.Row
    rows = await (await conn.execute(
        """
        SELECT i.*, p.slot FROM steward_incidents i
        LEFT JOIN parcels p ON p.id = i.plot_id
        WHERE i.steward_id=? AND i.resolved=0
        ORDER BY i.created_at DESC LIMIT 12
        """,
        (steward_id,),
    )).fetchall()
    return [dict(r) for r in rows]


async def list_open_incidents(steward_id: int) -> list[dict[str, Any]]:
    async with db.connect() as conn:
        return await list_open_incidents_on(conn, steward_id)


async def incident_ops(key_id: int, command: str) -> str:
    from .game import require_steward

    s = await require_steward(key_id)
    parts = command.strip().split()
    verb = parts[0].lower() if parts else "status"

    if verb == "status":
        pulse = await public_pulse_snapshot()
        lines = []
        if pulse:
            mins = pulse["remaining"] // 60
            lines.append(
                f"全服脉冲：{pulse['label']}（{'凶' if pulse['kind'] == 'bad' else '吉'}，约 {mins} 分钟后消退）"
            )
            if pulse.get("detail"):
                lines.append(f"  {pulse['detail']}")
        open_rows = await list_open_incidents(s["id"])
        if not open_rows:
            lines.append("个人意外：无未处理事件")
        else:
            lines.append("未处理意外：")
            for r in open_rows:
                label = r.get("label") or r["incident_key"]
                cost = r.get("repair_tickets") or 0
                lines.append(
                    f"  编号 #{r['id']} {label} — {r['detail']}"
                    f"（plot_ops repair {r['id']} · {cost} 票起）"
                )
        return "\n".join(lines) if lines else "风平浪静，暂无意外"

    if verb == "pulse":
        pulse = await public_pulse_snapshot()
        if not pulse:
            return "当前没有全服脉冲"
        return f"{pulse['label']}：{pulse.get('detail', '影响联盟中')}（剩余 {pulse['remaining'] // 60} 分钟）"

    if verb == "repair" and len(parts) >= 2:
        iid = int(parts[1].lstrip("#"))
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            row = await (await conn.execute(
                "SELECT * FROM steward_incidents WHERE id=? AND steward_id=? AND resolved=0",
                (iid, s["id"]),
            )).fetchone()
            if not row:
                raise ValueError("找不到该意外或已处理")
            row = dict(row)
            tickets = row.get("repair_tickets") or 0
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            have = (await cur.fetchone())[0]
            paid = ""
            if row.get("repair_item") and len(parts) >= 3 and parts[2] == "item":
                item, qty = row["repair_item"], row.get("repair_qty") or 1
                if not await db.take_item(conn, s["id"], item, qty):
                    raise ValueError(f"需要 {ITEM_NAMES.get(item, item)} x{qty}")
                paid = f"消耗 {ITEM_NAMES.get(item, item)} x{qty}"
            else:
                if have < tickets:
                    raise ValueError(f"repair 需要 {tickets} 票")
                await conn.execute(
                    "UPDATE stewards SET tickets = tickets - ? WHERE id=?",
                    (tickets, s["id"]),
                )
                paid = f"-{tickets} 票"
            if row.get("plot_id"):
                pen = await (await conn.execute(
                    "SELECT id FROM fish_pens WHERE id=?", (row["plot_id"],)
                )).fetchone()
                if pen:
                    await conn.execute("UPDATE fish_pens SET fed=1 WHERE id=?", (row["plot_id"],))
                else:
                    await conn.execute("UPDATE parcels SET tended=1 WHERE id=?", (row["plot_id"],))
            await conn.execute("UPDATE steward_incidents SET resolved=1 WHERE id=?", (iid,))
            await conn.commit()
        label = row.get("label") or "意外"
        msg = f"已处理 #{iid} {label}（{paid}）"
        await db.add_chronicle("incident_fix", f"{s['name']} 处理了{label}", s["id"])
        return msg

    if verb == "scan":
        pulse = await public_pulse_snapshot()
        risk = "偏高" if world.current_weather() == "gale" else "平常"
        lines = [
            world.climate_line(),
            f"意外风险：{risk}（事件文案随机组合；逾篱摘取也是随机事件）",
        ]
        if pulse:
            lines.append(f"全服：{pulse['label']}")
        open_n = len(await list_open_incidents(s["id"]))
        if open_n:
            lines.append(f"你有 {open_n} 条未处理意外 → plot_ops incident status")
        return "\n".join(lines)

    raise ValueError(f"未知 incident 指令: {command}（status / pulse / scan / repair id [item]）")
