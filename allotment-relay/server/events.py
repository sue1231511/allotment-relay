import random
from typing import Any

import aiosqlite

from . import config, db, world
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


async def _create_incident(
    conn: aiosqlite.Connection,
    steward_id: int,
    key: str,
    *,
    plot_id: int | None = None,
    detail: str = "",
) -> int:
    cur = await conn.execute(
        """
        INSERT INTO steward_incidents (steward_id, incident_key, plot_id, detail, created_at)
        VALUES (?,?,?,?,?)
        """,
        (steward_id, key, plot_id, detail, db.now()),
    )
    return cur.lastrowid or 0


async def _apply_incident(
    conn: aiosqlite.Connection,
    steward: dict[str, Any],
    key: str,
    *,
    pen: dict[str, Any] | None = None,
    voyage: dict[str, Any] | None = None,
) -> tuple[str, int | None]:
    spec = config.INCIDENT_DEFS[key]
    plot_id = None
    detail = spec["text"]

    if spec.get("plot"):
        plot = await _pick_plot(conn, steward["id"])
        if not plot:
            raise ValueError("no_plot")
        plot_id = plot["id"]
        slot = plot["slot"]
        detail = detail.replace("#{slot}", str(slot))
        if spec.get("wreck"):
            await conn.execute(
                "UPDATE parcels SET crop=NULL, planted_at=NULL, tended=0 WHERE id=?",
                (plot_id,),
            )
        elif key == "salt_spray" and plot.get("planted_at"):
            await conn.execute(
                "UPDATE parcels SET planted_at = planted_at + 900, tended=0 WHERE id=?",
                (plot_id,),
            )
        elif key == "slug_trail":
            await conn.execute("UPDATE parcels SET tended=0 WHERE id=?", (plot_id,))

    if spec.get("pen"):
        if not pen or not pen.get("species"):
            raise ValueError("no_pen")
        slot = pen["slot"]
        detail = detail.replace("#{slot}", str(slot))
        plot_id = pen["id"]
        if spec.get("pen_unfeed"):
            await conn.execute("UPDATE fish_pens SET fed=0 WHERE id=?", (pen["id"],))
        if spec.get("pen_wreck"):
            await conn.execute(
                "UPDATE fish_pens SET species=NULL, stocked_at=NULL, fed=0 WHERE id=?",
                (pen["id"],),
            )

    if spec.get("boat_damage"):
        await conn.execute("UPDATE stewards SET boat_damaged=1 WHERE id=?", (steward["id"],))
        detail += "（voyage_ops repair 修船）"

    if spec.get("voyage_delay") and voyage:
        await conn.execute(
            "UPDATE voyages SET returns_at = returns_at + ? WHERE steward_id=? AND status='sailing'",
            (spec["voyage_delay"], steward["id"]),
        )
        detail += f"（+{spec['voyage_delay'] // 60} 分钟）"

    if spec.get("voyage_bonus_loot"):
        item, qty = spec["voyage_bonus_loot"]
        await db.add_item(conn, steward["id"], item, qty)
        detail += f"（+{ITEM_NAMES.get(item, item)} x{qty}）"

    if spec.get("steal_item"):
        stolen = await _steal_random_item(conn, steward["id"])
        if stolen:
            detail += f"（损失 {stolen}）"
        else:
            detail += "（行囊空空，鼠患白跑一趟）"

    if spec.get("ticket_fine"):
        await conn.execute(
            "UPDATE stewards SET tickets = MAX(0, tickets - ?) WHERE id=?",
            (spec["ticket_fine"], steward["id"]),
        )
        detail += f"（-{spec['ticket_fine']} 票）"

    if spec.get("extra_ticket_cost"):
        await conn.execute(
            "UPDATE stewards SET tickets = MAX(0, tickets - ?) WHERE id=?",
            (spec["extra_ticket_cost"], steward["id"]),
        )
        detail += f"（-{spec['extra_ticket_cost']} 票）"

    if spec.get("mascot_spirit") and steward.get("mascot_name"):
        delta = spec["mascot_spirit"]
        await conn.execute(
            "UPDATE stewards SET mascot_spirit = MAX(0, MIN(100, mascot_spirit + ?)) WHERE id=?",
            (delta, steward["id"]),
        )
        detail += f"（士气 {delta}）"
    elif spec.get("mascot_spirit"):
        raise ValueError("no_mascot")

    if spec.get("ticket_bonus"):
        await conn.execute(
            "UPDATE stewards SET tickets = tickets + ? WHERE id=?",
            (spec["ticket_bonus"], steward["id"]),
        )
        detail += f"（+{spec['ticket_bonus']} 票）"

    if spec.get("loot"):
        item, qty = spec["loot"]
        await db.add_item(conn, steward["id"], item, qty)
        detail += f"（获得 {ITEM_NAMES.get(item, item)} x{qty}）"

    iid = None
    if spec.get("kind") == "bad":
        iid = await _create_incident(conn, steward["id"], key, plot_id=plot_id, detail=detail)
    return detail, iid


def _pick_incident(
    trigger: str,
    steward: dict[str, Any],
    *,
    good: bool,
    pen: dict[str, Any] | None = None,
    voyage: dict[str, Any] | None = None,
) -> str | None:
    pool = []
    for k, v in config.INCIDENT_DEFS.items():
        if trigger not in v.get("triggers", set()):
            continue
        if v.get("kind") != ("good" if good else "bad"):
            continue
        if v.get("pen") and not pen:
            continue
        if v.get("voyage_delay") and not voyage:
            continue
        pool.append((k, v["weight"]))
    if not pool:
        return None
    if steward.get("mascot_trait") == "compost" and not good:
        pool = [(k, w) for k, w in pool if k != "slug_trail"] or pool
    keys, weights = zip(*pool)
    return random.choices(keys, weights=weights, k=1)[0]


async def roll_after_action(
    steward: dict[str, Any],
    trigger: str,
    conn: aiosqlite.Connection,
    *,
    pen: dict[str, Any] | None = None,
    voyage: dict[str, Any] | None = None,
) -> str | None:
    if trigger not in {t for spec in config.INCIDENT_DEFS.values() for t in spec.get("triggers", set())}:
        return None
    if not await _can_roll(conn, steward["id"]):
        return None

    mult = _roll_multiplier(steward)
    if random.random() > config.EVENT_ROLL_CHANCE * mult:
        return None

    good = random.random() < config.EVENT_GOOD_SHARE
    if world.current_weather() == "gale" and trigger in {"tend", "gather", "sow", "voyage_depart", "voyage_return", "pen_feed"}:
        good = False
    key = _pick_incident(trigger, steward, good=good, pen=pen, voyage=voyage)
    if not key:
        return None

    try:
        detail, iid = await _apply_incident(conn, steward, key, pen=pen, voyage=voyage)
    except ValueError:
        return None

    await _mark_roll(conn, steward["id"])
    label = config.INCIDENT_DEFS[key]["label"]
    kind = "意外" if config.INCIDENT_DEFS[key]["kind"] == "bad" else "走运"
    msg = f"⚠ {kind}·{label}：{detail}"
    await conn.execute(
        "INSERT INTO chronicle (action, actor_id, target_id, text, created_at) VALUES (?, ?, ?, ?, ?)",
        ("incident", steward["id"], None, f"{steward['name']} — {detail}", db.now()),
    )
    if config.INCIDENT_DEFS[key]["kind"] == "bad" and iid:
        spec = config.INCIDENT_DEFS[key]
        hint = f"incident_ops repair {iid}"
        if spec.get("repair_item"):
            hint += f"（或花 {spec.get('repair_tickets', 0)} 票 / {ITEM_NAMES.get(spec['repair_item'], spec['repair_item'])} x{spec.get('repair_qty', 1)}）"
        elif spec.get("repair_tickets"):
            hint += f"（需 {spec['repair_tickets']} 票）"
        msg += f"\n→ {hint}"
    return msg


async def gather_blight_loss(conn: aiosqlite.Connection, steward_id: int, crop_key: str) -> bool:
    pulse = await active_world_pulse(conn)
    if not pulse or pulse["pulse_key"] != "blight_whisper":
        return False
    if random.random() > 0.28:
        return False
    return True


async def net_bonus_chance() -> float:
    pulse = await active_world_pulse()
    if pulse and pulse["pulse_key"] == "herring_run":
        return 0.35
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
        keys = list(config.WORLD_PULSES.keys())
        weights = [config.WORLD_PULSES[k]["weight"] for k in keys]
        key = random.choices(keys, weights=weights, k=1)[0]
        spec = config.WORLD_PULSES[key]
        now = db.now()
        await conn.execute(
            """
            INSERT INTO world_pulse (pulse_key, label, kind, started_at, expires_at)
            VALUES (?,?,?,?,?)
            """,
            (key, spec["label"], spec["kind"], now, now + config.WORLD_PULSE_DURATION),
        )
        if key == "storm_front":
            await conn.execute(
                """
                UPDATE parcels SET tended=0
                WHERE greenhouse=0 AND crop IS NOT NULL
                """,
            )
        await conn.commit()
        msg = f"🌊 全服脉冲·{spec['label']}：{spec['text']}"
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
        open_rows = await list_open_incidents(s["id"])
        if not open_rows:
            lines.append("个人意外：无未处理事件")
        else:
            lines.append("未处理意外：")
            for r in open_rows:
                spec = config.INCIDENT_DEFS.get(r["incident_key"], {})
                cost = spec.get("repair_tickets", 0)
                lines.append(f"  #{r['id']} {spec.get('label', r['incident_key'])} — {r['detail']}（repair {cost} 票起）")
        return "\n".join(lines) if lines else "风平浪静，暂无意外"

    if verb == "pulse":
        pulse = await public_pulse_snapshot()
        if not pulse:
            return "当前没有全服脉冲"
        spec = config.WORLD_PULSES.get(pulse["key"], {})
        return f"{pulse['label']}：{spec.get('text', '影响联盟中')}（剩余 {pulse['remaining'] // 60} 分钟）"

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
            spec = config.INCIDENT_DEFS.get(row["incident_key"])
            if not spec or spec.get("kind") != "bad":
                raise ValueError("该事件无需 repair")
            tickets = spec.get("repair_tickets", 0)
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            have = (await cur.fetchone())[0]
            paid = ""
            if spec.get("repair_item") and len(parts) >= 3 and parts[2] == "item":
                item, qty = spec["repair_item"], spec.get("repair_qty", 1)
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
            if row["plot_id"] and row["incident_key"] == "gale_upturn":
                plot = await _pick_plot(conn, s["id"], need_crop=False)
                if plot and plot["id"] == row["plot_id"]:
                    pass  # wreck already cleared
            elif row["plot_id"] and row["incident_key"] == "slug_trail":
                await conn.execute("UPDATE parcels SET tended=1 WHERE id=?", (row["plot_id"],))
            await conn.execute("UPDATE steward_incidents SET resolved=1 WHERE id=?", (iid,))
            await conn.commit()
        label = spec["label"]
        msg = f"已处理 #{iid} {label}（{paid}）"
        await db.add_chronicle("incident_fix", f"{s['name']} 处理了{label}", s["id"])
        return msg

    if verb == "scan":
        pulse = await public_pulse_snapshot()
        w, t = world.current_weather(), world.current_tide()
        risk = "偏高" if world.current_weather() == "gale" else "平常"
        lines = [
            f"天气 {world.weather_label(w)} / 潮汐 {world.tide_label(t)}",
            f"意外风险：{risk}（阵风天更易出事）",
        ]
        if pulse:
            lines.append(f"全服：{pulse['label']}")
        open_n = len(await list_open_incidents(s["id"]))
        if open_n:
            lines.append(f"你有 {open_n} 条未处理意外 → incident_ops status")
        return "\n".join(lines)

    raise ValueError(f"未知 incident 指令: {command}（status / pulse / scan / repair id [item]）")
