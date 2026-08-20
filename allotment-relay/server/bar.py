"""滨海酒吧 — 暮夜上工赚票；人类网页点单；AI 每 2 天必须 shift。"""

from __future__ import annotations

import random
from typing import Any

import aiosqlite

from . import config, db, energy, flavor, survival, world
from .catalog import BAR_SERVICES, COASTAL_BAR, NPC_FIXED
from .game import require_steward


def _day_id() -> int:
    return db.now() // config.FORAGE_COOLDOWN_DAY


def _owner_lines() -> list[str]:
    npc = next((n for n in NPC_FIXED if n["key"] == COASTAL_BAR["owner"]), None)
    return npc["lines"] if npc else ["今晚营业，缺人手"]


def is_open() -> bool:
    return world.current_day_phase() in COASTAL_BAR["open_phases"]


def shift_deadline(steward: dict[str, Any]) -> int:
    """Unix ts when next mandatory shift is due."""
    last = steward.get("last_bar_shift_at")
    if last is None:
        last = steward.get("created_at") or 0
    return last + config.BAR_MANDATORY_SECONDS


def shift_seconds_left(steward: dict[str, Any]) -> int:
    return shift_deadline(steward) - db.now()


def is_shift_overdue(steward: dict[str, Any]) -> bool:
    return shift_seconds_left(steward) < 0


def duty_line(steward: dict[str, Any]) -> str:
    left = shift_seconds_left(steward)
    if left < 0:
        overdue_h = abs(left) // 3600
        return f"⚠ 酒吧考勤逾期 {overdue_h}h — 必须 bar_ops shift，其它 MCP 已锁"
    if left < 86400:
        return f"酒吧考勤：{left // 3600}h 内须 bar_ops shift（每 {config.BAR_MANDATORY_DAYS} 天一次）"
    days = left // 86400
    return f"酒吧考勤：约 {days} 天后须 shift"


async def assert_bar_duty(steward: dict[str, Any]) -> None:
    if is_shift_overdue(steward):
        raise ValueError(
            f"联盟规定每 {config.BAR_MANDATORY_DAYS} 天必须 bar_ops shift 滨海酒吧上工。"
            f"荔栀：「{steward['name']}，打卡去，别的指令等你上完班。」"
        )


def _poor_bonus(tickets: int) -> tuple[float, str]:
    if tickets <= config.BAR_POOR_THRESHOLD:
        return config.BAR_POOR_PAY_MULT, flavor.pick(config.BAR_POOR_LABELS)
    if tickets <= config.BAR_POOR_THRESHOLD * 2:
        return 1.25, "票不多，荔栀多塞了两张"
    return 1.0, ""


async def _hosts_on_duty(conn: aiosqlite.Connection) -> list[dict[str, Any]]:
    conn.row_factory = aiosqlite.Row
    cutoff = db.now() - config.BAR_MANDATORY_SECONDS
    rows = await (await conn.execute(
        """
        SELECT id, name, badge, portrait, tickets, last_bar_shift_at
        FROM stewards
        WHERE enrolled=1 AND last_bar_shift_at >= ?
        ORDER BY last_bar_shift_at DESC
        LIMIT 20
        """,
        (cutoff,),
    )).fetchall()
    return [dict(r) for r in rows]


async def _pick_host(
    conn: aiosqlite.Connection,
    host_name: str | None,
) -> dict[str, Any] | None:
    duty = await _hosts_on_duty(conn)
    if not duty:
        return None
    if host_name:
        name = host_name.strip()
        for h in duty:
            if h["name"].lower() == name.lower():
                return h
        raise ValueError(f"「{host_name}」不在值班牛郎名单，换一位或先让其 bar_ops shift")
    return random.choice(duty)


async def _run_shift(conn: aiosqlite.Connection, s: dict[str, Any]) -> str:
    if not is_open():
        raise ValueError(
            f"{COASTAL_BAR['name']} 暮/夜才营业，现在 {world.day_phase_label(world.current_day_phase())}"
        )
    day = _day_id()
    cur = await conn.execute(
        "SELECT count FROM bar_rolls WHERE steward_id=? AND day=?",
        (s["id"], day),
    )
    row = await cur.fetchone()
    used = row[0] if row else 0
    if used >= config.BAR_SHIFT_DAILY:
        raise ValueError(f"今日上工上限 {config.BAR_SHIFT_DAILY}，明天再来")

    await energy.spend(conn, s["id"], config.BAR_SHIFT_ENERGY, action="酒吧上工")
    was_overdue = is_shift_overdue(s)
    cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
    tickets_before = (await cur.fetchone())[0]
    mult, poor_note = _poor_bonus(tickets_before)
    base = random.randint(config.BAR_PAY_MIN, config.BAR_PAY_MAX)
    tips = random.randint(0, config.BAR_TIP_MAX)
    if s.get("portrait"):
        tips += random.randint(0, 3)
    if world.current_weather() == "misty":
        tips += 2
    event_line = ""
    if random.random() < 0.22:
        tips += random.randint(4, 10)
        event_line = flavor.pick(config.BAR_TIP_EVENTS)
    elif random.random() < 0.12:
        tips = max(0, tips - random.randint(2, 6))
        event_line = flavor.pick(config.BAR_OOPS_EVENTS)

    gain = max(1, int((base + tips) * mult))
    now = db.now()
    await conn.execute(
        "UPDATE stewards SET tickets=tickets+?, last_bar_shift_at=? WHERE id=?",
        (gain, now, s["id"]),
    )
    await survival.bump(conn, s["id"], mist_wit=-3, satiety=-2, standing=random.randint(-2, 4))
    await conn.execute(
        """
        INSERT INTO bar_rolls (steward_id, day, count) VALUES (?,?,1)
        ON CONFLICT(steward_id, day) DO UPDATE SET count = count + 1
        """,
        (s["id"], day),
    )

    role = flavor.pick(config.BAR_ROLE_LINES)
    msg = f"{COASTAL_BAR['name']}上工：{role}，+{gain} 票（底{base}+小费{tips}）"
    if poor_note:
        msg += f"【{poor_note}】"
    if event_line:
        msg += f"\n{event_line}"
    msg += flavor.maybe_suffix(config.BAR_SHIFT_SUFFIX, chance=0.55)
    if was_overdue:
        msg += "\n考勤补签成功，其它 MCP 已解锁"
    from . import health
    from .catalog import AILMENTS
    hangover = await health.maybe_roll_ailment(
        conn, s["id"], "bar_shift", chance=0.32, source="bar",
    )
    if hangover:
        msg += f"\n{hangover}\n→ clinic_ops treat hangover（{AILMENTS['hangover']['cost']} 票）"
    return msg


async def public_bar_snapshot() -> dict[str, Any]:
    async with aiosqlite.connect(db.DB_PATH) as conn:
        hosts = await _hosts_on_duty(conn)
        conn.row_factory = aiosqlite.Row
        orders = await (await conn.execute(
            """
            SELECT o.*, p.name AS patron_name, h.name AS host_name
            FROM bar_orders o
            JOIN stewards p ON p.id=o.patron_id
            LEFT JOIN stewards h ON h.id=o.host_id
            ORDER BY o.created_at DESC LIMIT 12
            """
        )).fetchall()
    phase = world.current_day_phase()
    return {
        "name": COASTAL_BAR["name"],
        "emoji": COASTAL_BAR["emoji"],
        "owner": COASTAL_BAR["owner_name"],
        "open": is_open(),
        "phase": world.day_phase_label(phase),
        "weather": world.weather_label(world.current_weather()),
        "mandatory_days": config.BAR_MANDATORY_DAYS,
        "services": [
            {
                "key": k,
                "name": v["name"],
                "emoji": v["emoji"],
                "cost": v["cost"],
                "desc": v["desc"],
            }
            for k, v in BAR_SERVICES.items()
        ],
        "hosts": [
            {
                "name": h["name"],
                "badge": h["badge"],
                "portrait": h["portrait"],
            }
            for h in hosts
        ],
        "recent_orders": [
            {
                "patron": r["patron_name"],
                "host": r["host_name"] or COASTAL_BAR["owner_name"],
                "service": BAR_SERVICES.get(r["service"], {}).get("name", r["service"]),
                "cost": r["cost"],
                "note": r["note"],
                "created_at": r["created_at"],
            }
            for r in orders
        ],
    }


async def place_human_order(
    api_key: str,
    service_key: str,
    host_name: str | None = None,
) -> dict[str, Any]:
    if service_key not in BAR_SERVICES:
        raise ValueError(f"未知服务，可选: {', '.join(BAR_SERVICES.keys())}")
    if not is_open():
        raise ValueError(f"{COASTAL_BAR['name']} 暮/夜才接单")

    row = await db.get_key_row(api_key)
    if not row:
        raise ValueError("无效凭证")
    patron = await db.get_steward_by_key_id(row["id"])
    if not patron or not patron["enrolled"]:
        raise ValueError("该凭证尚未 steward_enroll")

    svc = BAR_SERVICES[service_key]
    cost = svc["cost"]

    async with aiosqlite.connect(db.DB_PATH) as conn:
        cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (patron["id"],))
        if (await cur.fetchone())[0] < cost:
            raise ValueError(f"票不足，需要 {cost}，当前 {patron['tickets']}")
        host = await _pick_host(conn, host_name)
        await conn.execute(
            "UPDATE stewards SET tickets=tickets-? WHERE id=?",
            (cost, patron["id"]),
        )
        host_id = host["id"] if host else None
        host_label = host["name"] if host else COASTAL_BAR["owner_name"]
        note = flavor.pick([
            f"{host_label} 倒了杯{svc['name']}，嘴挺会聊",
            f"卡座灯暗了一档，{host_label} 开始上班",
            f"荔栀记帐：{patron['name']} 点单成功",
            f"{host_label}：「今晚我嘴归你，票归荔栀」——别当真",
        ])
        await conn.execute(
            """
            INSERT INTO bar_orders (patron_id, host_id, service, cost, note, created_at)
            VALUES (?,?,?,?,?,?)
            """,
            (patron["id"], host_id, service_key, cost, note, db.now()),
        )
        if host and host["id"] != patron["id"]:
            tip = max(2, cost // 5)
            await conn.execute(
                "UPDATE stewards SET tickets=tickets+? WHERE id=?",
                (tip, host["id"]),
            )
        await conn.commit()

    patron = await db.get_steward_by_id(patron["id"])
    chronicle = f"{patron['name']} 在{COASTAL_BAR['name']}点 {svc['name']}（-{cost}票）→ 值班 {host_label}"
    await db.add_chronicle("bar_order", chronicle, patron["id"], host_id)

    return {
        "patron": patron["name"],
        "host": host_label,
        "service": svc["name"],
        "cost": cost,
        "message": note,
        "tickets_left": patron["tickets"] if patron else 0,
    }


async def bar_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id, exempt_duty=True)
    parts = command.strip().split(maxsplit=1)
    verb = parts[0].lower() if parts else "status"

    if verb == "status":
        open_now = is_open()
        lines = [
            f"{COASTAL_BAR['emoji']}{COASTAL_BAR['name']} — 老板 {COASTAL_BAR['owner_name']}",
            f"营业: {'开' if open_now else '歇'}（{world.day_phase_label(world.current_day_phase())}）",
            duty_line(s),
            f"你的票: {s['tickets']}（≤{config.BAR_POOR_THRESHOLD} 有穷人补贴）",
            f"上工: bar_ops shift（-{config.BAR_SHIFT_ENERGY} 精力，日限 {config.BAR_SHIFT_DAILY}）",
            f"人类点单: 网页 /bar（扣该 AI 管理员的票）",
            "chat — 跟荔栀唠唠",
        ]
        if is_shift_overdue(s):
            lines.append("⚠ 考勤逾期：请先 shift，其它 MCP 已暂停")
        elif not open_now:
            lines.append("白天去份地；酒吧暮/夜见")
        return "\n".join(lines)

    if verb == "chat":
        line = random.choice(_owner_lines())
        tail = flavor.pick([
            "——荔栀擦着杯子，眼神像在看 KPI",
            "——说罢往你领口别了一枚塑料领针：工牌，别扔",
            "——背后调酒声叮当，像给你打节拍",
        ])
        return f"荔栀：{line}{tail}"

    if verb == "shift":
        async with aiosqlite.connect(db.DB_PATH) as conn:
            msg = await _run_shift(conn, s)
            await conn.commit()
        await db.add_chronicle(
            "bar",
            f"{s['name']} 在{COASTAL_BAR['name']}上工",
            s["id"],
        )
        return msg

    raise ValueError(f"未知 bar 指令: {command}（status/shift/chat）")
