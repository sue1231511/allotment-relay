import random
import uuid
from typing import Any

import aiosqlite

from . import config, db, event_gen, farming, flavor, health, survival, world
from .catalog import CROPS, ITEM_NAMES


def _day_id() -> int:
    return db.now() // config.FORAGE_COOLDOWN_DAY


def _roll_multiplier(steward: dict[str, Any]) -> float:
    mult = 1.0
    weather = world.current_weather()
    if weather == "gale":
        mult *= 1.45
    elif weather == "clear":
        mult *= 0.85
    if steward.get("mascot_trait") == "lucky":
        mult *= 0.72
    return mult


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


async def _pick_plot(conn: aiosqlite.Connection, steward_id: int, *, need_crop: bool = True) -> dict[str, Any] | None:
    conn.row_factory = aiosqlite.Row
    if need_crop:
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
    ready = [p for p in rows if _plot_ready(p)]
    return random.choice(ready) if ready else None


async def _scrump_victim(
    conn: aiosqlite.Connection,
    steward: dict[str, Any],
) -> tuple[str, int | None, int | None] | None:
    plot = await _pick_ripe_plot(conn, steward["id"])
    if not plot:
        return None
    peer = await _random_peer(conn, steward["id"])
    from . import npc
    thief = npc.pick_thief_name(peer["name"] if peer else None)
    crop = plot["crop"]
    meta = CROPS[crop]
    await conn.execute(
        "UPDATE parcels SET crop=NULL, planted_at=NULL, tended=0 WHERE id=?",
        (plot["id"],),
    )
    detail = flavor.fill(
        flavor.pick(flavor.SCRUMP_VICTIM),
        thief=thief,
        slot=plot["slot"],
        crop=meta["name"],
    )
    action = "scrump"
    await conn.execute(
        "INSERT INTO chronicle (action, actor_id, target_id, text, created_at) VALUES (?, ?, ?, ?, ?)",
        (
            action,
            peer["id"] if peer else None,
            steward["id"],
            f"{thief} 逾篱摘了 {steward['name']} 的 {meta['name']}",
            db.now(),
        ),
    )
    return detail, plot["id"], peer["id"] if peer else None


async def _scrump_attempt(
    conn: aiosqlite.Connection,
    steward: dict[str, Any],
) -> tuple[str, int | None, int | None] | None:
    peer = await _random_peer(conn, steward["id"])
    if not peer:
        return None
    plot = await _pick_ripe_plot(conn, peer["id"])
    if not plot:
        return None
    crop = plot["crop"]
    meta = CROPS[crop]
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
        roll = random.random()
        bonus = 0.05 if steward.get("mascot_trait") == "lucky" else 0.0
        if roll < config.SCRUMP_LOOT_CROP + bonus:
            await db.add_item(conn, steward["id"], f"crop_{crop}", 1)
            loot = meta["name"]
        elif roll < config.SCRUMP_LOOT_CROP + config.SCRUMP_LOOT_SEED + bonus:
            await db.add_item(conn, steward["id"], f"seed_{crop}", 1)
            loot = f"{meta['name']}种"
        detail = flavor.fill(
            flavor.pick(flavor.SCRUMP_SUCCESS),
            crop=loot,
            victim=peer["name"],
            slot=plot["slot"],
        )
        action = "scrump"
    elif caught:
        await conn.execute(
            "UPDATE stewards SET tickets=MAX(0, tickets-?) WHERE id=?",
            (fine, steward["id"]),
        )
        await survival.bump(conn, steward["id"], standing=-random.randint(6, 12))
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
        "UPDATE parcels SET crop=NULL, planted_at=NULL, tended=0 WHERE id=?",
        (plot["id"],),
    )
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
    return f"{detail}（{hint}；可 plot_ops amends {peer['name']}）", plot["id"], peer["id"]


async def _apply_effects(
    conn: aiosqlite.Connection,
    steward: dict[str, Any],
    effects: list[str],
    *,
    pen: dict[str, Any] | None = None,
    plot_id_holder: list[int | None],
) -> list[str]:
    ailment_msgs: list[str] = []
    for eff in effects:
        if eff == "plot_untend":
            plot = await _pick_plot(conn, steward["id"])
            if plot:
                plot_id_holder[0] = plot["id"]
                await conn.execute("UPDATE parcels SET tended=0 WHERE id=?", (plot["id"],))
        elif eff == "plot_wreck":
            plot = await _pick_plot(conn, steward["id"])
            if plot:
                plot_id_holder[0] = plot["id"]
                await conn.execute(
                    "UPDATE parcels SET crop=NULL, planted_at=NULL, tended=0 WHERE id=?",
                    (plot["id"],),
                )
        elif eff == "plot_delay":
            plot = await _pick_plot(conn, steward["id"])
            if plot and plot.get("planted_at"):
                plot_id_holder[0] = plot["id"]
                delay = random.randint(600, 1200)
                await conn.execute(
                    "UPDATE parcels SET planted_at = planted_at + ?, tended=0 WHERE id=?",
                    (delay, plot["id"]),
                )
        elif eff == "steal_item":
            await _steal_random_item(conn, steward["id"])
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
        elif eff.startswith("ticket_bonus:"):
            amt = int(eff.split(":")[1])
            await conn.execute(
                "UPDATE stewards SET tickets = tickets + ? WHERE id=?",
                (amt, steward["id"]),
            )
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
            await db.add_item(conn, steward["id"], item, int(qty_s))
        elif eff.startswith("ailment:"):
            key = eff.split(":", 1)[1]
            msg = await health.inflict(conn, steward["id"], key, source="event")
            if msg:
                ailment_msgs.append(msg)
    return ailment_msgs


async def apply_effects(
    conn: aiosqlite.Connection,
    steward: dict[str, Any],
    effects: list[str],
    *,
    pen: dict[str, Any] | None = None,
    plot_id_holder: list[int | None] | None = None,
) -> list[str]:
    holder = plot_id_holder if plot_id_holder is not None else [None]
    return await _apply_effects(conn, steward, effects, pen=pen, plot_id_holder=holder)


async def roll_after_action(
    steward: dict[str, Any],
    trigger: str,
    conn: aiosqlite.Connection,
    *,
    pen: dict[str, Any] | None = None,
    voyage: dict[str, Any] | None = None,
) -> str | None:
    if trigger not in event_gen.ALL_TRIGGERS:
        return None
    if not await _can_roll(conn, steward["id"]):
        return None

    await survival.on_action(conn, steward["id"], trigger)

    mult = _roll_multiplier(steward) * survival.event_multiplier(steward) * world.incident_night_bias()
    ailments = await health.list_ailments(conn, steward["id"])
    mult *= health.event_bias(steward, len(ailments))
    if random.random() > config.EVENT_ROLL_CHANCE * mult:
        return None

    good = random.random() < config.EVENT_GOOD_SHARE
    if world.current_weather() == "gale" and trigger in {
        "tend", "gather", "sow", "voyage_depart", "voyage_return", "pen_feed", "net",
    }:
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
        ailment_msgs = await _apply_effects(conn, steward, event.effects, pen=pen, plot_id_holder=plot_id_holder)
    except Exception:
        return None

    await _mark_roll(conn, steward["id"])
    msg = flavor.wrap_event(event.kind, event.label, event.detail)
    if ailment_msgs:
        msg += "\n" + ailment_msgs[0]
        msg += "\n→ clinic_ops status · treat 病症（必须花票）"
    elif event.kind == "bad" and not is_scrump:
        extra_ailment = await health.maybe_roll_ailment(conn, steward["id"], trigger, chance=0.12)
        if extra_ailment:
            msg += f"\n{extra_ailment}\n→ clinic_ops treat …（必须花票）"

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
        hint = f"incident_ops repair {iid}"
        if event.repair_item:
            hint += (
                f"（或 {event.repair_tickets} 票 / "
                f"{ITEM_NAMES.get(event.repair_item, event.repair_item)} x{event.repair_qty or 1}）"
            )
        elif event.repair_tickets:
            hint += f"（需 {event.repair_tickets} 票）"
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
        async with aiosqlite.connect(db.DB_PATH) as c:
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
    async with aiosqlite.connect(db.DB_PATH) as conn:
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
                pulse["text"],
                now,
                now + config.WORLD_PULSE_DURATION,
            ),
        )
        if pulse["effect"] == "storm_front":
            await conn.execute(
                "UPDATE parcels SET tended=0 WHERE greenhouse=0 AND crop IS NOT NULL",
            )
        await conn.commit()
        msg = f"🌊 全服脉冲·{pulse['label']}：{pulse['text']}"
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


async def list_open_incidents(steward_id: int) -> list[dict[str, Any]]:
    async with aiosqlite.connect(db.DB_PATH) as conn:
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
                lines.append(f"  #{r['id']} {label} — {r['detail']}（repair {cost} 票起）")
        return "\n".join(lines) if lines else "风平浪静，暂无意外"

    if verb == "pulse":
        pulse = await public_pulse_snapshot()
        if not pulse:
            return "当前没有全服脉冲"
        return f"{pulse['label']}：{pulse.get('detail', '影响联盟中')}（剩余 {pulse['remaining'] // 60} 分钟）"

    if verb == "repair" and len(parts) >= 2:
        iid = int(parts[1])
        async with aiosqlite.connect(db.DB_PATH) as conn:
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
        w, t = world.current_weather(), world.current_tide()
        risk = "偏高" if world.current_weather() == "gale" else "平常"
        lines = [
            f"天气 {world.weather_label(w)} / 潮汐 {world.tide_label(t)} / 时辰 {world.day_phase_label(world.current_day_phase())}",
            f"意外风险：{risk}（事件文案随机组合；逾篱摘取也是随机事件）",
        ]
        if pulse:
            lines.append(f"全服：{pulse['label']}")
        open_n = len(await list_open_incidents(s["id"]))
        if open_n:
            lines.append(f"你有 {open_n} 条未处理意外 → incident_ops status")
        return "\n".join(lines)

    raise ValueError(f"未知 incident 指令: {command}（status / pulse / scan / repair id [item]）")
