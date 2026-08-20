import random
import uuid
from typing import Any

import aiosqlite

from . import config, db, event_gen, world
from .catalog import ITEM_NAMES


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
    pulse = None  # filled by caller when needed
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


async def _apply_effects(
    conn: aiosqlite.Connection,
    steward: dict[str, Any],
    effects: list[str],
    *,
    pen: dict[str, Any] | None = None,
    plot_id_holder: list[int | None],
) -> None:
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
        elif eff.startswith("voyage_delay:"):
            delay = int(eff.split(":")[1])
            await conn.execute(
                "UPDATE voyages SET returns_at = returns_at + ? WHERE steward_id=? AND status='sailing'",
                (delay, steward["id"]),
            )
        elif eff.startswith("loot:"):
            _, item, qty_s = eff.split(":", 2)
            await db.add_item(conn, steward["id"], item, int(qty_s))


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

    mult = _roll_multiplier(steward)
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

    event = event_gen.generate_event(
        trigger,
        steward,
        good=good,
        pen=pen,
        voyage=voyage is not None,
    )
    if not event:
        return None

    plot_id_holder: list[int | None] = [None]
    try:
        await _apply_effects(conn, steward, event.effects, pen=pen, plot_id_holder=plot_id_holder)
    except Exception:
        return None

    await _mark_roll(conn, steward["id"])
    kind = "走运" if event.kind == "good" else "意外"
    msg = f"⚠ {kind}·{event.label}：{event.detail}"

    iid = None
    if event.kind == "bad":
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
            f"天气 {world.weather_label(w)} / 潮汐 {world.tide_label(t)}",
            f"意外风险：{risk}（事件每次随机组合，非固定剧本）",
        ]
        if pulse:
            lines.append(f"全服：{pulse['label']}")
        open_n = len(await list_open_incidents(s["id"]))
        if open_n:
            lines.append(f"你有 {open_n} 条未处理意外 → incident_ops status")
        return "\n".join(lines)

    raise ValueError(f"未知 incident 指令: {command}（status / pulse / scan / repair id [item]）")
