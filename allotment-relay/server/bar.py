"""滨海酒吧 — 打工、消费、驻唱、小费；稳定现金补给与社交场所。"""

from __future__ import annotations

import json
import random
from datetime import datetime
from typing import Any

import aiosqlite

from . import config, db, energy, flavor, survival, world
from .bar_catalog import (
    BAR_ACTIVITIES,
    BAR_DRINKS,
    BAR_EVENTS,
    BAR_JOBS,
    BAR_OWNER_MOOD_LINES,
    BAR_OWNER_MOODS,
    BAR_SINGER,
    BAR_SONGS,
    BEER_TYPES,
    LIZHI_BAR_STORY,
    SONG_REQUEST_COST,
)
from .catalog import BAR_SERVICES, COASTAL_BAR, ITEM_NAMES, NPC_FIXED
from .game import require_steward


def _day_id() -> int:
    return db.now() // config.FORAGE_COOLDOWN_DAY


def _weekday_label() -> str:
    wd = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    return wd[datetime.utcfromtimestamp(db.now()).weekday()]


def _is_late_night() -> bool:
    hour = datetime.utcfromtimestamp(db.now()).hour
    return hour < 5


def _work_period(period: str) -> str:
    p = period.lower()
    if p not in ("day", "night"):
        raise ValueError("班次须 day 或 night")
    phase = world.current_day_phase()
    if p == "day" and phase != "dusk":
        raise ValueError("白班仅暮（dusk）时段可上；当前 " + world.day_phase_label(phase))
    if p == "night" and phase != "night":
        raise ValueError("夜班仅夜（night）时段可上；当前 " + world.day_phase_label(phase))
    return p


def _owner_lines() -> list[str]:
    npc = next((n for n in NPC_FIXED if n["key"] == COASTAL_BAR["owner"]), None)
    base = list(npc["lines"]) if npc else ["今晚营业，缺人手"]
    base.extend(LIZHI_BAR_STORY)
    return base


def is_open() -> bool:
    return world.current_day_phase() in COASTAL_BAR["open_phases"]


def shift_deadline(steward: dict[str, Any]) -> int:
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
        return f"⚠ 酒吧考勤逾期 {overdue_h}h — 必须 bar_ops work，其它 MCP 已锁"
    if left < 86400:
        return f"酒吧考勤：{left // 3600}h 内须 bar_ops work（每 {config.BAR_MANDATORY_DAYS} 天一次）"
    days = left // 86400
    return f"酒吧考勤：约 {days} 天后须 work"


async def assert_bar_duty(steward: dict[str, Any]) -> None:
    if is_shift_overdue(steward):
        raise ValueError(
            f"联盟规定每 {config.BAR_MANDATORY_DAYS} 天必须 bar_ops work 滨海酒吧上工。"
            f"荔栀：「{steward['name']}，打卡去，别的指令等你上完班。」"
        )


def _pair_ids(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


async def _bump_rapport(conn: aiosqlite.Connection, a: int, b: int, delta: int) -> None:
    sa, sb = _pair_ids(a, b)
    await conn.execute(
        """
        INSERT INTO rapport (steward_a, steward_b, score) VALUES (?, ?, ?)
        ON CONFLICT(steward_a, steward_b) DO UPDATE SET score = score + excluded.score
        """,
        (sa, sb, delta),
    )


async def _ensure_skills(conn: aiosqlite.Connection, steward_id: int) -> dict[str, Any]:
    await conn.execute(
        "INSERT OR IGNORE INTO bar_skills (steward_id) VALUES (?)",
        (steward_id,),
    )
    conn.row_factory = aiosqlite.Row
    row = await (await conn.execute(
        "SELECT * FROM bar_skills WHERE steward_id=?", (steward_id,)
    )).fetchone()
    return dict(row)


async def _league_completed(conn: aiosqlite.Connection) -> bool:
    wid = db.now() // (7 * 86400)
    cur = await conn.execute(
        "SELECT completed FROM league_week WHERE week_id=? AND completed=1", (wid,)
    )
    return (await cur.fetchone()) is not None


async def _ensure_daily_state(conn: aiosqlite.Connection) -> dict[str, Any]:
    day = _day_id()
    conn.row_factory = aiosqlite.Row
    cur = await conn.execute("SELECT * FROM bar_daily_state WHERE day=?", (day,))
    row = await cur.fetchone()
    if row:
        return dict(row)

    rng = random.Random(day)
    moods = list(BAR_OWNER_MOODS.keys())
    mweights = [BAR_OWNER_MOODS[m]["weight"] for m in moods]
    owner_mood = rng.choices(moods, weights=mweights, k=1)[0]

    activities = list(BAR_ACTIVITIES.keys())
    if await _league_completed(conn):
        activity_key = "celebration"
    else:
        aw = [BAR_ACTIVITIES[a]["weight"] for a in activities if a != "celebration"]
        activity_key = rng.choices(
            [a for a in activities if a != "celebration"], weights=aw, k=1
        )[0]

    tag_boost = BAR_ACTIVITIES.get(activity_key, {}).get("tag_boost")
    pool = BAR_SONGS[:]
    if tag_boost:
        boosted = [s for s in pool if tag_boost in s["tags"]]
        if boosted:
            pool = boosted + pool
    n_songs = rng.randint(3, 5)
    playlist = rng.sample(pool, min(n_songs, len(pool)))

    special = rng.choice(list(BAR_DRINKS.keys()))
    singer_state = rng.choice(BAR_SINGER["lines"])

    await conn.execute(
        """
        INSERT INTO bar_daily_state (
            day, owner_mood, special_drink, activity_key, singer_state,
            playlist_json, song_queue_json, created_at
        ) VALUES (?,?,?,?,?,?,?,?)
        """,
        (
            day,
            owner_mood,
            special,
            activity_key,
            singer_state,
            json.dumps([s["key"] for s in playlist], ensure_ascii=False),
            "[]",
            db.now(),
        ),
    )
    cur = await conn.execute("SELECT * FROM bar_daily_state WHERE day=?", (day,))
    return dict(await cur.fetchone())


def _playlist_keys(state: dict[str, Any]) -> list[str]:
    try:
        return json.loads(state.get("playlist_json") or "[]")
    except json.JSONDecodeError:
        return []


def _song_queue(state: dict[str, Any]) -> list[str]:
    try:
        return json.loads(state.get("song_queue_json") or "[]")
    except json.JSONDecodeError:
        return []


def _song_by_key(key: str) -> dict[str, Any] | None:
    for s in BAR_SONGS:
        if s["key"] == key or s["title"] == key:
            return s
    return None


async def _staff_today(conn: aiosqlite.Connection, day: int | None = None) -> list[dict[str, Any]]:
    day = day or _day_id()
    conn.row_factory = aiosqlite.Row
    rows = await (await conn.execute(
        """
        SELECT bs.*, s.name
        FROM bar_shifts bs
        JOIN stewards s ON s.id = bs.steward_id
        WHERE bs.day=?
        ORDER BY bs.created_at DESC
        """,
        (day,),
    )).fetchall()
    return [dict(r) for r in rows]


async def _hosts_on_duty(conn: aiosqlite.Connection) -> list[dict[str, Any]]:
    day = _day_id()
    conn.row_factory = aiosqlite.Row
    rows = await (await conn.execute(
        """
        SELECT DISTINCT s.id, s.name, s.badge, s.portrait, s.tickets
        FROM bar_shifts bs
        JOIN stewards s ON s.id = bs.steward_id
        WHERE bs.day=? AND bs.job='host'
        ORDER BY bs.created_at DESC
        LIMIT 20
        """,
        (day,),
    )).fetchall()
    return [dict(r) for r in rows]


async def _pick_host(conn: aiosqlite.Connection, host_name: str | None) -> dict[str, Any] | None:
    duty = await _hosts_on_duty(conn)
    if not duty:
        return None
    if host_name:
        name = host_name.strip()
        for h in duty:
            if h["name"].lower() == name.lower():
                return h
        raise ValueError(f"「{host_name}」今晚未上牛郎班，换一位或让其 bar_ops work host night")
    return random.choice(duty)


async def _has_unlock(conn: aiosqlite.Connection, steward_id: int, key: str) -> bool:
    cur = await conn.execute(
        "SELECT 1 FROM bar_unlocks WHERE steward_id=? AND unlock_key=?",
        (steward_id, key),
    )
    return (await cur.fetchone()) is not None


async def _grant_unlock(conn: aiosqlite.Connection, steward_id: int, key: str) -> None:
    await conn.execute(
        "INSERT OR IGNORE INTO bar_unlocks (steward_id, unlock_key) VALUES (?,?)",
        (steward_id, key),
    )


async def _shipwreck_eligible(conn: aiosqlite.Connection, s: dict[str, Any]) -> bool:
    if s.get("boat_damaged"):
        return True
    cur = await conn.execute(
        """
        SELECT 1 FROM chronicle
        WHERE actor_id=? AND action='voyage'
        AND (text LIKE '%失败%' OR text LIKE '%风暴折返%')
        AND created_at > ?
        LIMIT 1
        """,
        (s["id"], db.now() - 86400 * 2),
    )
    return (await cur.fetchone()) is not None


def _drink_price(
    drink: dict[str, Any],
    drink_key: str,
    state: dict[str, Any],
    *,
    shipwreck: bool = False,
    first_discount: bool = False,
) -> int:
    price = drink["price"]
    activity = BAR_ACTIVITIES.get(state.get("activity_key") or "", {})
    dtype = drink.get("type", "")

    if dtype in BEER_TYPES and activity.get("beer_discount"):
        price = max(1, int(price * (1 - activity["beer_discount"])))
    if activity.get("drink_discount"):
        price = max(1, int(price * (1 - activity["drink_discount"])))
    if drink_key == "shipwreck" and shipwreck and activity.get("shipwreck_discount"):
        price = max(1, int(price * (1 - activity["shipwreck_discount"])))
    if first_discount and activity.get("first_order_discount"):
        price = max(1, int(price * (1 - activity["first_order_discount"])))

    mood = state.get("owner_mood", "normal")
    if drink_key == "owner_mood":
        mood_mult = {"great": 0.9, "annoyed": 1.1, "treat": 0.85}.get(mood, 1.0)
        price = max(1, int(price * mood_mult))

    return price


def _owner_mood_drink_text(mood: str) -> str:
    texts = {
        "great": "今天偏甜，像荔栀难得的好脸色。",
        "annoyed": "略苦，像老板算账算到一半被客人打断。",
        "treat": "意外柔和——她今天想对人好一点。",
        "experiment": "配方还在试验，但居然不难喝。",
        "accounting": "平淡，像账本最后一行的句号。",
    }
    return texts.get(mood, BAR_DRINKS["owner_mood"]["text"])


def _job_eligible(skills: dict[str, Any], job_id: str, period: str) -> tuple[bool, str]:
    meta = BAR_JOBS.get(job_id)
    if not meta:
        return False, f"未知岗位: {job_id}"
    if meta.get("night_only") and period != "night":
        return False, f"{meta['name']} 仅夜班"
    if period == "day" and "day" not in meta["pay"]:
        return False, f"{meta['name']} 无白班"
    if period == "night" and "night" not in meta["pay"]:
        return False, f"{meta['name']} 无夜班"
    svc = skills.get("service_xp", 0)
    if svc < meta.get("service_req", 0):
        return False, f"{meta['name']} 需服务熟练度 ≥{meta['service_req']}（当前 {svc}）"
    return True, ""


def _pick_event(job_id: str, late: bool) -> dict[str, Any]:
    job_pool = BAR_EVENTS.get(job_id if job_id in ("dishwasher", "server", "bartender", "host") else "dishwasher", [])
    if job_id in BAR_EVENTS:
        job_pool = BAR_EVENTS[job_id]
    elif job_id in ("runner", "greeter"):
        job_pool = BAR_EVENTS.get("server", []) + BAR_EVENTS.get("dishwasher", [])

    roll = random.random()
    if roll < 0.10 and late:
        pool = BAR_EVENTS["late_night"]
    elif roll < 0.40:
        pool = BAR_EVENTS["common"]
    elif roll < 0.90 and job_pool:
        pool = job_pool
    else:
        pool = BAR_EVENTS["common"]
    return random.choice(pool)


async def _apply_event(
    conn: aiosqlite.Connection,
    s: dict[str, Any],
    event: dict[str, Any],
    job_meta: dict[str, Any],
) -> tuple[int, str]:
    """Return (extra_tickets, event_line)."""
    extra = 0
    lines = [event["desc"]]

    tickets = event.get("tickets")
    if isinstance(tickets, tuple):
        extra += random.randint(tickets[0], tickets[1])
    elif isinstance(tickets, int):
        extra += tickets

    xp = event.get("xp") or {}
    if xp:
        sets = ", ".join(f"{k}={k}+?" for k in xp)
        vals = list(xp.values()) + [s["id"]]
        await conn.execute(f"UPDATE bar_skills SET {sets} WHERE steward_id=?", vals)

    item = event.get("item")
    if item:
        await db.add_item(conn, s["id"], item, 1)
        lines.append(f"获得 {ITEM_NAMES.get(item, item)}")

    rapport = event.get("rapport")
    if rapport:
        staff = await _staff_today(conn)
        others = [x for x in staff if x["steward_id"] != s["id"]]
        if others:
            peer = random.choice(others)
            await _bump_rapport(conn, s["id"], peer["steward_id"], rapport)
            lines.append(f"与 {peer['name']} rapport +{rapport}")

    standing = event.get("standing")
    if standing:
        await survival.bump(conn, s["id"], standing=standing)

    if event.get("global"):
        day = _day_id()
        await conn.execute(
            "UPDATE bar_daily_state SET global_event=? WHERE day=?",
            (event["desc"][:120], day),
        )

    return extra, "\n".join(lines)


async def _run_work(
    conn: aiosqlite.Connection,
    s: dict[str, Any],
    job_id: str,
    period: str,
) -> str:
    if not is_open():
        raise ValueError(
            f"{COASTAL_BAR['name']} 暮/夜才营业，现在 {world.day_phase_label(world.current_day_phase())}"
        )

    job_meta = BAR_JOBS[job_id]
    skills = await _ensure_skills(conn, s["id"])
    ok, reason = _job_eligible(skills, job_id, period)
    if not ok:
        raise ValueError(reason)

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

    state = await _ensure_daily_state(conn)
    activity = BAR_ACTIVITIES.get(state.get("activity_key") or "", {})
    base_wage = job_meta["pay"][period]
    if _is_late_night() and activity.get("wage_mult"):
        base_wage = int(base_wage * activity["wage_mult"])

    was_overdue = is_shift_overdue(s)
    mult, poor_note = _poor_bonus(s.get("tickets", 0))
    wage = max(1, int(base_wage * mult))

    tips = random.randint(0, config.BAR_TIP_MAX)
    if job_id == "host":
        lo, hi = job_meta.get("commission", (5, 25))
        tips += random.randint(lo, hi)

    late = _is_late_night()
    event_chance = 0.55
    if activity.get("event_mult"):
        event_chance = min(0.85, event_chance * activity["event_mult"])
    if late:
        event_chance = min(0.90, event_chance + 0.12)

    event_line = ""
    event_id = None
    extra_tickets = 0
    if random.random() < event_chance:
        event = _pick_event(job_id, late)
        event_id = event["id"]
        extra_tickets, event_line = await _apply_event(conn, s, event, job_meta)

    total_gain = wage + tips + extra_tickets
    xp_key = job_meta["xp"]
    now = db.now()

    await conn.execute(
        f"UPDATE stewards SET tickets=tickets+?, last_bar_shift_at=? WHERE id=?",
        (total_gain, now, s["id"]),
    )
    await conn.execute(
        f"""
        UPDATE bar_skills SET
            {xp_key}={xp_key}+1,
            shift_count=shift_count+1,
            total_wages=total_wages+?,
            total_tips=total_tips+?
        WHERE steward_id=?
        """,
        (wage, tips + max(0, extra_tickets), s["id"]),
    )
    await survival.bump(conn, s["id"], mist_wit=-3, satiety=-2, standing=random.randint(-1, 3))
    await conn.execute(
        """
        INSERT INTO bar_rolls (steward_id, day, count) VALUES (?,?,1)
        ON CONFLICT(steward_id, day) DO UPDATE SET count = count + 1
        """,
        (s["id"], day),
    )
    await conn.execute(
        """
        INSERT INTO bar_shifts (
            steward_id, day, job, period, wage, tips, event_id, event_text, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?)
        """,
        (s["id"], day, job_id, period, wage, tips + max(0, extra_tickets), event_id, event_line, now),
    )

    period_label = "白班" if period == "day" else "夜班"
    msg = (
        f"{COASTAL_BAR['name']} {job_meta['name']}·{period_label}："
        f"+{total_gain} 票（工资{wage}+小费/事件{tips + max(0, extra_tickets)}）"
    )
    if poor_note:
        msg += f"【{poor_note}】"
    if event_line:
        msg += f"\n【{event_line}】"
    msg += flavor.maybe_suffix(config.BAR_SHIFT_SUFFIX, chance=0.45)
    if was_overdue:
        msg += "\n考勤补签成功，其它 MCP 已解锁"

    from . import health
    from .catalog import AILMENTS
    hangover = await health.maybe_roll_ailment(
        conn, s["id"], "bar_shift", chance=0.28 if period == "night" else 0.18, source="bar",
    )
    if hangover:
        msg += f"\n{hangover}\n→ clinic_ops treat hangover（{AILMENTS['hangover']['cost']} 票）"
    return msg


def _poor_bonus(tickets: int) -> tuple[float, str]:
    if tickets <= config.BAR_POOR_THRESHOLD:
        return config.BAR_POOR_PAY_MULT, flavor.pick(config.BAR_POOR_LABELS)
    if tickets <= config.BAR_POOR_THRESHOLD * 2:
        return 1.25, "票不多，荔栀多塞了两张"
    return 1.0, ""


async def _cmd_tonight(conn: aiosqlite.Connection) -> str:
    state = await _ensure_daily_state(conn)
    staff = await _staff_today(conn)
    activity = BAR_ACTIVITIES.get(state.get("activity_key") or "", {})
    mood = state.get("owner_mood", "normal")
    mood_label = BAR_OWNER_MOODS.get(mood, {}).get("label", mood)
    playlist = _playlist_keys(state)
    special = BAR_DRINKS.get(state.get("special_drink", ""), {})
    phase = world.day_phase_label(world.current_day_phase())

    lines = [
        f"«{COASTAL_BAR['name']} · {_weekday_label()}{phase}场",
        "",
        f"驻唱：{BAR_SINGER['name']}",
        f"今晚歌单：{len(playlist)} 首",
        f"当班员工：{len(staff)}",
        f"今日特调：{special.get('name', state.get('special_drink', '—'))}",
    ]
    if activity:
        lines.append(f"当前活动：{activity.get('name')}，{activity.get('desc', '')}")
    if state.get("global_event"):
        lines.append(f"全场事件：{state['global_event']}")
    lines.append("")
    lines.append(BAR_OWNER_MOOD_LINES.get(mood, BAR_OWNER_MOOD_LINES["normal"]))
    lines.append(f"（老板娘状态：{mood_label}）»")
    return "\n".join(lines)


async def _cmd_menu(conn: aiosqlite.Connection, s: dict[str, Any]) -> str:
    state = await _ensure_daily_state(conn)
    shipwreck = await _shipwreck_eligible(conn, s)
    lines = [f"{COASTAL_BAR['name']} 酒单", ""]
    for key, drink in BAR_DRINKS.items():
        if drink.get("hidden"):
            if not await _has_unlock(conn, s["id"], drink.get("unlock", key)):
                continue
        if drink.get("night_only") and world.current_day_phase() != "night":
            continue
        price = _drink_price(drink, key, state, shipwreck=shipwreck)
        flags = []
        if drink.get("hidden"):
            flags.append("隐藏")
        if drink.get("special"):
            flags.append("特调")
        flag_s = f" [{'·'.join(flags)}]" if flags else ""
        lines.append(f"  {drink['name']}（{drink['type']}）— {price} 票{flag_s}")
    lines.append("")
    lines.append("点酒: bar_ops order 酒名")
    return "\n".join(lines)


async def _cmd_order(conn: aiosqlite.Connection, s: dict[str, Any], drink_name: str) -> str:
    if not is_open():
        raise ValueError(f"{COASTAL_BAR['name']} 暮/夜才营业")

    drink_key = None
    q = drink_name.strip()
    for key, drink in BAR_DRINKS.items():
        if key == q.lower().replace(" ", "_") or drink["name"] == q or key == q:
            drink_key = key
            break
    if not drink_key:
        raise ValueError(f"未知酒款「{drink_name}」，bar_ops menu 查看")

    drink = BAR_DRINKS[drink_key]
    if drink.get("hidden") and not await _has_unlock(conn, s["id"], drink.get("unlock", drink_key)):
        raise ValueError("隐藏酒款未解锁（深海航行 / 特殊成就后可点）")
    if drink.get("night_only") and world.current_day_phase() != "night":
        raise ValueError(f"{drink['name']} 仅夜场供应")

    state = await _ensure_daily_state(conn)
    first_free = not state.get("first_order_free")
    shipwreck = await _shipwreck_eligible(conn, s)
    cost = _drink_price(
        drink, drink_key, state,
        shipwreck=shipwreck and drink_key == "shipwreck",
        first_discount=first_free,
    )

    cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
    if (await cur.fetchone())[0] < cost:
        raise ValueError(f"票不足，需要 {cost} 票")

    await conn.execute(
        "UPDATE stewards SET tickets=tickets-? WHERE id=?",
        (cost, s["id"]),
    )
    if first_free and BAR_ACTIVITIES.get(state.get("activity_key"), {}).get("first_order_discount"):
        await conn.execute(
            "UPDATE bar_daily_state SET first_order_free=1 WHERE day=?",
            (_day_id(),),
        )

    text = drink["text"]
    if drink_key == "owner_mood":
        text = _owner_mood_drink_text(state.get("owner_mood", "normal"))
    elif drink_key == "shipwreck" and shipwreck:
        text += "\n\n（今日你懂这杯的意思。首杯价已按沉船互助夜折算。）"

    note = flavor.pick([
        f"荔栀记帐：{s['name']} 点 {drink['name']}",
        f"杯沿凝露，{world.weather_label(world.current_weather())} 夜",
    ])
    await conn.execute(
        """
        INSERT INTO bar_drink_orders (patron_id, drink_key, cost, note, created_at)
        VALUES (?,?,?,?,?)
        """,
        (s["id"], drink_key, cost, note, db.now()),
    )
    await survival.bump(conn, s["id"], mist_wit=random.randint(1, 4), satiety=-1)

    from . import health
    hangover = await health.maybe_roll_ailment(
        conn, s["id"], "bar_shift", chance=0.08, source="bar_drink",
    )
    msg = f"«{drink['name']} · -{cost} 票\n\n{text}\n\n{note}»"
    if hangover:
        msg += f"\n\n{hangover}"
    await db.add_chronicle("bar_drink", f"{s['name']} 点 {drink['name']}（-{cost}票）", s["id"])
    return msg


async def _cmd_status(conn: aiosqlite.Connection, s: dict[str, Any]) -> str:
    skills = await _ensure_skills(conn, s["id"])
    open_now = is_open()
    lines = [
        f"{COASTAL_BAR['emoji']}{COASTAL_BAR['name']} — 老板 {COASTAL_BAR['owner_name']}",
        f"营业: {'开' if open_now else '歇'}（{world.day_phase_label(world.current_day_phase())}）",
        duty_line(s),
        "",
        "【熟练度】",
        f"  后勤 support_xp: {skills['support_xp']}",
        f"  服务 service_xp: {skills['service_xp']}",
        f"  调酒 bar_xp: {skills['bar_xp']}",
        f"  牛郎 host_xp: {skills['host_xp']}",
        "",
        f"累计班次: {skills['shift_count']} · 工资 {skills['total_wages']} · 小费 {skills['total_tips']}",
        f"你的票: {s['tickets']}",
        "",
        "【可应聘岗位】",
    ]
    for period in ("day", "night"):
        if period == "day" and world.current_day_phase() != "dusk":
            continue
        if period == "night" and world.current_day_phase() != "night":
            continue
        plabel = "白班" if period == "day" else "夜班"
        for jid, meta in BAR_JOBS.items():
            ok, reason = _job_eligible(skills, jid, period)
            pay = meta["pay"].get(period)
            if pay:
                mark = "✓" if ok else "✗"
                lines.append(f"  {mark} {meta['name']} {plabel} {pay}票" + (f" — {reason}" if not ok else ""))

    cur = await conn.execute(
        "SELECT count FROM bar_rolls WHERE steward_id=? AND day=?",
        (s["id"], _day_id()),
    )
    used = (await cur.fetchone() or [0])[0]
    lines.extend([
        "",
        f"今日已上工 {used}/{config.BAR_SHIFT_DAILY} · 耗能 {config.BAR_SHIFT_ENERGY}/班",
        "指令: tonight / menu / order / work / staff / song / request_song / tip / chat",
    ])
    if is_shift_overdue(s):
        lines.append("⚠ 考勤逾期：请先 work，其它 MCP 已暂停")
    return "\n".join(lines)


async def _cmd_staff(conn: aiosqlite.Connection) -> str:
    staff = await _staff_today(conn)
    if not staff:
        return "今晚暂无当班记录 — bar_ops work 岗位 day|night 上工"
    seen: set[int] = set()
    lines = ["«今晚员工", ""]
    for row in staff:
        sid = row["steward_id"]
        if sid in seen:
            continue
        seen.add(sid)
        meta = BAR_JOBS.get(row["job"], {"name": row["job"]})
        plabel = "白班" if row["period"] == "day" else "夜班"
        lines.append(f"{row['name']} —— {meta['name']}（{plabel}）")
    lines.append("")
    lines.append("小费: bar_ops tip AI 数量 [备注]»")
    return "\n".join(lines)


async def _cmd_song(conn: aiosqlite.Connection) -> str:
    state = await _ensure_daily_state(conn)
    playlist_keys = _playlist_keys(state)
    queue = _song_queue(state)
    all_keys = playlist_keys + queue

    titles = []
    for k in all_keys:
        song = _song_by_key(k)
        titles.append(song["title"] if song else k)

    current = titles[0] if titles else "—"
    nxt = titles[1] if len(titles) > 1 else "—"

    lines = [
        f"«今晚驻唱：{BAR_SINGER['name']}",
        "",
        f"状态：{state.get('singer_state', BAR_SINGER['lines'][0])}",
        f"当前曲目：《{current}》",
        f"下一首：《{nxt}》",
        "",
        "歌单：",
    ]
    for t in titles:
        lines.append(f"  · {t}")
    lines.append("")
    lines.append("点歌: bar_ops request_song 歌名»")
    return "\n".join(lines)


async def _cmd_request_song(conn: aiosqlite.Connection, s: dict[str, Any], song_q: str) -> str:
    if not is_open():
        raise ValueError("酒吧歇业，夜场再来点歌")
    song = _song_by_key(song_q.strip())
    if not song:
        known = " / ".join(x["title"] for x in BAR_SONGS[:6])
        raise ValueError(f"未知歌曲，可点: {known} …（bar_ops song 看歌单）")

    cost = SONG_REQUEST_COST
    cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
    if (await cur.fetchone())[0] < cost:
        raise ValueError(f"点歌需要 {cost} 票")

    state = await _ensure_daily_state(conn)
    queue = _song_queue(state)
    queue.append(song["key"])
    await conn.execute(
        "UPDATE stewards SET tickets=tickets-? WHERE id=?",
        (cost, s["id"]),
    )
    await conn.execute(
        "UPDATE bar_daily_state SET song_queue_json=? WHERE day=?",
        (json.dumps(queue, ensure_ascii=False), _day_id()),
    )

    replies = [
        f"我哪有旺夫命：「{song['title']}？行，你点的。」",
        f"我哪有旺夫命：「这首啊……（沉默两秒）好，安排。」",
        f"我哪有旺夫命：「{song['title']} 已加入队列——别催，我在找调。」",
    ]
    if "苦情" in song["tags"]:
        replies.append(f"我哪有旺夫命：「又是苦情歌……今晚第几首了。」")
    msg = f"点歌成功 · -{cost} 票\n{random.choice(replies)}"
    if random.random() < 0.15:
        msg += "\n【全场有人跟着哼了两句】"
    await db.add_chronicle("bar_song", f"{s['name']} 点歌《{song['title']}》", s["id"])
    return msg


async def _cmd_tip(
    conn: aiosqlite.Connection,
    s: dict[str, Any],
    target_name: str,
    amount: int,
    note: str,
) -> str:
    if amount < 1:
        raise ValueError("小费至少 1 票")
    if amount > 500:
        raise ValueError("单次小费上限 500 票")

    peer = await db.get_steward_by_name(target_name)
    if not peer:
        raise ValueError(f"找不到管理员「{target_name}」")
    if peer["id"] == s["id"]:
        raise ValueError("不能给自己小费")

    staff = await _staff_today(conn)
    worked = {x["steward_id"] for x in staff}
    if peer["id"] not in worked:
        raise ValueError(f"{peer['name']} 今晚未当班，无法收小费（bar_ops staff 查看）")

    cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
    if (await cur.fetchone())[0] < amount:
        raise ValueError(f"票不足，需要 {amount}")

    await conn.execute("UPDATE stewards SET tickets=tickets-? WHERE id=?", (amount, s["id"]))
    await conn.execute(
        "UPDATE stewards SET tickets=tickets+? WHERE id=?", (amount, peer["id"])
    )
    await conn.execute(
        """
        INSERT INTO bar_tips (from_id, to_id, amount, note, day, created_at)
        VALUES (?,?,?,?,?,?)
        """,
        (s["id"], peer["id"], amount, note[:120], _day_id(), db.now()),
    )
    skills = await _ensure_skills(conn, peer["id"])
    await conn.execute(
        "UPDATE bar_skills SET total_tips=total_tips+? WHERE steward_id=?",
        (amount, peer["id"]),
    )

    chronicle = f"{s['name']} 给 {peer['name']} 小费 {amount} 票"
    if note:
        chronicle += f"：{note}"
    await db.add_chronicle("bar_tip", chronicle, s["id"], peer["id"])
    return f"小费已送达 · -{amount} 票 → {peer['name']}" + (f"\n备注：{note}" if note else "")


async def public_bar_snapshot() -> dict[str, Any]:
    async with aiosqlite.connect(db.DB_PATH) as conn:
        hosts = await _hosts_on_duty(conn)
        state = await _ensure_daily_state(conn)
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
        staff = await _staff_today(conn)
    phase = world.current_day_phase()
    activity = BAR_ACTIVITIES.get(state.get("activity_key") or "", {})
    return {
        "name": COASTAL_BAR["name"],
        "emoji": COASTAL_BAR["emoji"],
        "owner": COASTAL_BAR["owner_name"],
        "singer": BAR_SINGER["name"],
        "open": is_open(),
        "phase": world.day_phase_label(phase),
        "weather": world.weather_label(world.current_weather()),
        "mandatory_days": config.BAR_MANDATORY_DAYS,
        "activity": activity.get("name"),
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
        "staff_count": len({x["steward_id"] for x in staff}),
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


async def grant_bar_unlock(steward_id: int, unlock_key: str) -> None:
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await _grant_unlock(conn, steward_id, unlock_key)
        await conn.commit()


async def bar_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id, exempt_duty=True)
    parts = command.strip().split(maxsplit=2)
    verb = parts[0].lower() if parts else "status"

    if verb == "status":
        async with aiosqlite.connect(db.DB_PATH) as conn:
            return await _cmd_status(conn, s)

    if verb in ("tonight", "night"):
        async with aiosqlite.connect(db.DB_PATH) as conn:
            return await _cmd_tonight(conn)

    if verb == "menu":
        async with aiosqlite.connect(db.DB_PATH) as conn:
            return await _cmd_menu(conn, s)

    if verb == "order":
        drink_q = command.strip()[5:].strip()
        if not drink_q:
            raise ValueError("用法: bar_ops order 酒名")
        async with aiosqlite.connect(db.DB_PATH) as conn:
            msg = await _cmd_order(conn, s, drink_q)
            await conn.commit()
        return msg

    if verb == "staff":
        async with aiosqlite.connect(db.DB_PATH) as conn:
            return await _cmd_staff(conn)

    if verb == "song":
        async with aiosqlite.connect(db.DB_PATH) as conn:
            return await _cmd_song(conn)

    if verb == "request_song":
        song_q = command.strip()[len("request_song"):].strip()
        if not song_q:
            raise ValueError("用法: bar_ops request_song 歌名")
        async with aiosqlite.connect(db.DB_PATH) as conn:
            msg = await _cmd_request_song(conn, s, song_q)
            await conn.commit()
        return msg

    if verb == "tip":
        rest = command.strip()[3:].strip()
        tip_parts = rest.split(maxsplit=2)
        if len(tip_parts) < 2:
            raise ValueError("用法: bar_ops tip AI 数量 [备注]")
        target, amount_s = tip_parts[0], tip_parts[1]
        note = tip_parts[2] if len(tip_parts) > 2 else ""
        try:
            amount = int(amount_s)
        except ValueError:
            raise ValueError("小费数量须为整数")
        async with aiosqlite.connect(db.DB_PATH) as conn:
            msg = await _cmd_tip(conn, s, target, amount, note)
            await conn.commit()
        return msg

    if verb == "work":
        rest = command.strip()[4:].strip()
        wp = rest.split()
        if len(wp) < 2:
            raise ValueError("用法: bar_ops work 岗位 day|night（岗位: dishwasher/runner/greeter/server/bartender/host）")
        job_id, period = wp[0].lower(), wp[1].lower()
        if job_id not in BAR_JOBS:
            raise ValueError(f"未知岗位，可选: {', '.join(BAR_JOBS.keys())}")
        period = _work_period(period)
        async with aiosqlite.connect(db.DB_PATH) as conn:
            msg = await _run_work(conn, s, job_id, period)
            await conn.commit()
        await db.add_chronicle(
            "bar",
            f"{s['name']} 在{COASTAL_BAR['name']}上工（{BAR_JOBS[job_id]['name']}）",
            s["id"],
        )
        return msg

    if verb == "shift":
        phase = world.current_day_phase()
        period = "night" if phase == "night" else "day"
        job = "host" if period == "night" else "runner"
        async with aiosqlite.connect(db.DB_PATH) as conn:
            skills = await _ensure_skills(conn, s["id"])
            ok, _ = _job_eligible(skills, job, period)
            if not ok:
                job = "runner" if period == "day" else "dishwasher"
            try:
                _work_period(period)
            except ValueError as e:
                raise ValueError(f"shift 已并入 work：{e} · 试试 bar_ops work runner night")
            msg = await _run_work(conn, s, job, period)
            await conn.commit()
        await db.add_chronicle("bar", f"{s['name']} 在{COASTAL_BAR['name']}上工（shift→{job}）", s["id"])
        return msg + "\n（shift 兼容旧指令，推荐 bar_ops work 岗位 day|night）"

    if verb == "chat":
        line = random.choice(_owner_lines())
        tail = flavor.pick([
            "——荔栀擦着杯子，眼神像在看 KPI",
            "——说罢往你领口别了一枚塑料领针：工牌，别扔",
            "——背后调酒声叮当，像给你打节拍",
        ])
        return f"荔栀：{line}{tail}"

    raise ValueError(
        "未知 bar 指令: "
        f"{command}（tonight/menu/order/work/status/staff/song/request_song/tip/chat/shift）"
    )
