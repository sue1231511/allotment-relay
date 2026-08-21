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
    BAR_MOOD_LEVELS,
    BAR_OWNER_MOOD_LINES,
    BAR_OWNER_MOODS,
    BAR_SINGER,
    BAR_SONGS,
    BAR_STAFF_FLAVOR,
    BEER_TYPES,
    LIZHI_BAR_STORY,
    SONG_REQUEST_COST,
    resolve_bar_job,
    resolve_bar_period,
)
from .bar_copy import (
    BAR_ACTIVITY_FLAVOR,
    BAR_DEEP_ECHO,
    BAR_ORDER_AMBIENT,
    BAR_OWNER_NAME,
    BAR_SHIPWRECK_TEXT,
    BAR_SONG_REQUEST_LINES,
    BAR_TIP_LARGE,
    BAR_TIP_NORMAL,
    BAR_TIP_NOTE,
    BAR_TIP_SMALL,
    BAR_WEB,
    pick_tonight_ambient,
)
from .bar_owner import (
    append_owner_reaction,
    bump_revenue,
    compute_auto_mood,
    enrich_state,
    generate_chat,
    mood_drink_text,
    mood_event_chance_mult,
    mood_label,
    mood_tonight_line,
    owner_event_reaction,
    activity_weights_for_mood,
    resolve_effective_mood,
)
from .catalog import BAR_SERVICES, COASTAL_BAR, ITEM_NAMES, NPC_FIXED
from .game import require_steward

BAR_HELP = """bar_ops 子命令（整句写进 command）：
  status — 自己的酒吧档（熟练度、可应聘岗位、考勤）。空 command 也是这个
  tonight — 今晚驻唱·特调·活动·小橘是否开嗓
  menu / order 酒名 — 酒单 / 点酒
  work 岗位 day|night — 上工。岗位：洗碗/杂工/迎宾/服务生/调酒师/牛郎
    暮才有白班、夜才有夜班；逾期白天可补班 ×0.72
    每 2 天必须 work 一次，否则锁份地/出海/行囊
  cheer 好话 — 哄荔栀（每日 1 次）。潮下猫猫用 undertide_ops cheer；小橘用 star_ops 应援
  tip 名字 票数 [备注] — 给当班员工小费
  chat [话题] — 跟荔栀唠
  song / request_song 歌名 — 驻唱「我哪有旺夫命」/ 点歌
  staff — 今晚员工
  lodge — 走投无路才收：管饭+工钱15，干 6 小时，期间哪儿也去不了
  心情不能由 AI 定。想哄她用 cheer。没有 duo / set_mood。"""


def _day_id() -> int:
    return db.now() // config.FORAGE_COOLDOWN_DAY


def _weekday_label() -> str:
    wd = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    return wd[datetime.utcfromtimestamp(db.now()).weekday()]


def _is_late_night() -> bool:
    hour = datetime.utcfromtimestamp(db.now()).hour
    return hour < 5


def _work_period(period: str, *, overdue: bool = False) -> str:
    p = period.lower()
    if p not in ("day", "night"):
        raise ValueError("班次须 day 或 night")
    phase = world.current_day_phase()
    if overdue and phase == "day":
        if p == "night":
            raise ValueError("白天补班只能 work 岗位 day（票 ×0.72）")
        return p
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
        return f"⚠ 酒吧考勤逾期 {overdue_h}h — 必须 bar_ops work。份地/出海/行囊已锁；诊所、吃饭、酒吧、潮下仍可用"
    if left < 86400:
        return f"酒吧考勤：{left // 3600}h 内须 bar_ops work（每 {config.BAR_MANDATORY_DAYS} 天一次）"
    days = left // 86400
    return f"酒吧考勤：约 {days} 天后须 work"


async def assert_bar_duty(steward: dict[str, Any]) -> None:
    if is_shift_overdue(steward):
        raise ValueError(
            f"联盟规定每 {config.BAR_MANDATORY_DAYS} 天必须 bar_ops work 滨海酒吧上工。"
            f"{BAR_OWNER_NAME}：「{steward['name']}，打卡去，别的指令等你上完班。」"
        )


def _pair_ids(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


async def _bump_rapport(conn: aiosqlite.Connection, a: int, b: int, delta: int) -> None:
    from . import shaonian as shaonian_mod
    mult = await shaonian_mod.rapport_multiplier(conn, a)
    if mult > 1.0 and delta > 0:
        delta = max(1, int(delta * mult))
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
        state = enrich_state(dict(row), day)
        return state

    auto_mood, _ = await compute_auto_mood(conn, day)
    rng = random.Random(day)

    activities = list(BAR_ACTIVITIES.keys())
    if await _league_completed(conn):
        activity_key = "celebration"
    else:
        weights_map = activity_weights_for_mood(auto_mood, False)
        act_keys = [a for a in activities if a != "celebration" and a in weights_map]
        aw = [weights_map[a] for a in act_keys]
        activity_key = rng.choices(act_keys, weights=aw, k=1)[0]

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
            day, owner_mood, auto_mood, manual_mood_level, manual_mood_text,
            manual_mood_date, revenue_tickets, owner_event_text, owner_event_date,
            owner_event_enabled, special_drink, activity_key, singer_state,
            playlist_json, song_queue_json, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            day,
            auto_mood,
            auto_mood,
            "",
            "",
            0,
            0,
            "",
            0,
            0,
            special,
            activity_key,
            singer_state,
            json.dumps([s["key"] for s in playlist], ensure_ascii=False),
            "[]",
            db.now(),
        ),
    )
    cur = await conn.execute("SELECT * FROM bar_daily_state WHERE day=?", (day,))
    return enrich_state(dict(await cur.fetchone()), day)


async def _refresh_state_mood(conn: aiosqlite.Connection, state: dict[str, Any]) -> dict[str, Any]:
    day = _day_id()
    enriched = enrich_state(state, day)
    effective = enriched["effective_mood"]
    await conn.execute(
        "UPDATE bar_daily_state SET owner_mood=? WHERE day=?",
        (effective, day),
    )
    enriched["owner_mood"] = effective
    return enriched


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
    hosts = [dict(r) for r in rows]
    # 包宿救济者：当晚强制在列（无提成，营收全归酒馆）
    now = db.now()
    lodgers = await (await conn.execute(
        "SELECT id, name, badge, portrait, tickets FROM stewards WHERE lodge_until > ?",
        (now,),
    )).fetchall()
    for lod in lodgers:
        if not any(h["id"] == lod["id"] for h in hosts):
            entry = dict(lod)
            entry["lodger"] = True
            hosts.append(entry)
    return hosts


def is_lodging(s: dict[str, Any]) -> bool:
    """包宿中（行动锁）。"""
    return int(s.get("lodge_until") or 0) > db.now()


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

    mood = state.get("effective_mood") or resolve_effective_mood(state, _day_id())
    if drink_key == "owner_mood":
        meta = BAR_MOOD_LEVELS.get(mood, {})
        mood_mult = meta.get("drink_mult", 1.0)
        price = max(1, int(price * mood_mult))
    else:
        # 荔栀的当晚：全场酒价随心情浮动（/lizhi 面板，v3）——与特调自身折扣不叠，取更深档
        from .undertide_config import UT_LIZHI_MOOD_PRICE
        lizhi_mult = UT_LIZHI_MOOD_PRICE.get(mood, 1.0)
        if lizhi_mult != 1.0:
            price = max(1, int(price * lizhi_mult))

    return price


def _owner_mood_drink_text(state: dict[str, Any]) -> str:
    day = _day_id()
    mood = state.get("effective_mood") or resolve_effective_mood(state, day)
    custom = ""
    if int(state.get("manual_mood_date") or 0) == day:
        custom = (state.get("manual_mood_text") or "").strip() or None
    return mood_drink_text(mood, custom)


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
    if job_id in BAR_EVENTS:
        job_pool = BAR_EVENTS[job_id]
    elif job_id == "runner":
        job_pool = BAR_EVENTS.get("runner", BAR_EVENTS.get("server", []))
    elif job_id == "greeter":
        job_pool = BAR_EVENTS.get("greeter", BAR_EVENTS.get("server", []))
    else:
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
    makeup = False
    if not is_open():
        if not is_shift_overdue(s):
            raise ValueError(
                f"{COASTAL_BAR['name']} 暮/夜才营业，现在 {world.day_phase_label(world.current_day_phase())}"
            )
        makeup = True
        if period != "day":
            raise ValueError("白天补班用 bar_ops work 岗位 day（票 ×0.72）")

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
    state = await _refresh_state_mood(conn, state)
    activity = BAR_ACTIVITIES.get(state.get("activity_key") or "", {})
    base_wage = job_meta["pay"][period]
    if _is_late_night() and activity.get("wage_mult"):
        base_wage = int(base_wage * activity["wage_mult"])

    was_overdue = is_shift_overdue(s)
    mult, poor_note = _poor_bonus(s.get("tickets", 0))
    if makeup:
        mult *= 0.72
        poor_note = (poor_note + " · " if poor_note else "") + f"白天补班，{BAR_OWNER_NAME}让你擦杯子"
    wage = max(1, int(base_wage * mult))

    tips = random.randint(0, config.BAR_TIP_MAX)
    if job_id == "host":
        lo, hi = job_meta.get("commission", (5, 25))
        tips += random.randint(lo, hi)
    if world.current_weather() == "misty":
        tips += 2
    from . import hut as hut_mod
    hut_b = await hut_mod.get_bonuses(conn, s["id"])
    tips += hut_b.bar_tip

    late = _is_late_night()
    event_chance = 0.55
    if activity.get("event_mult"):
        event_chance = min(0.85, event_chance * activity["event_mult"])
    mood_mult = mood_event_chance_mult(state.get("effective_mood", "normal"))
    event_chance = min(0.92, event_chance * mood_mult)
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
        conn, s["id"], "bar_shift",
        chance=0.12 if makeup else (0.28 if period == "night" else 0.18),
        source="bar",
    )
    if hangover:
        msg += f"\n{hangover}\n→ visit_ops clinic treat hangover（{AILMENTS['hangover']['cost']} 票）"
    reaction = owner_event_reaction(state, day, "work")
    return append_owner_reaction(msg, reaction)


def _poor_bonus(tickets: int) -> tuple[float, str]:
    if tickets <= config.BAR_POOR_THRESHOLD:
        return config.BAR_POOR_PAY_MULT, flavor.pick(config.BAR_POOR_LABELS)
    if tickets <= config.BAR_POOR_THRESHOLD * 2:
        return 1.25, f"票不多，{BAR_OWNER_NAME}多塞了两张"
    return 1.0, ""


async def _cmd_tonight(conn: aiosqlite.Connection) -> str:
    state = await _ensure_daily_state(conn)
    state = await _refresh_state_mood(conn, state)
    day = _day_id()
    staff = await _staff_today(conn)
    activity_key = state.get("activity_key") or ""
    activity = BAR_ACTIVITIES.get(activity_key, {})
    mood = state.get("effective_mood", "normal")
    auto_mood = state.get("auto_mood", mood)
    playlist = _playlist_keys(state)
    special = BAR_DRINKS.get(state.get("special_drink", ""), {})
    phase = world.day_phase_label(world.current_day_phase())
    late = _is_late_night()
    rev = int(state.get("revenue_tickets") or 0)
    if mood in ("great", "good") or rev >= 100:
        tier = "busy"
    elif mood in ("bad", "awful") or rev < 35:
        tier = "slow"
    else:
        tier = "normal"

    lines = [
        f"«{COASTAL_BAR['name']} · {_weekday_label()}{phase}场",
        "",
        pick_tonight_ambient(tier, late),
        "",
        f"驻唱：{BAR_SINGER['name']}",
        f"今晚歌单：{len(playlist)} 首",
        f"当班员工：{len(staff)}",
        f"今日特调：{special.get('name', state.get('special_drink', '—'))}",
    ]
    from . import star as star_mod
    guest_line = await star_mod.tonight_guest_line()
    if guest_line:
        lines.append(guest_line)
    if activity:
        act_line = f"当前活动：{activity.get('name')}，{activity.get('desc', '')}"
        flavor_line = BAR_ACTIVITY_FLAVOR.get(activity_key)
        if flavor_line:
            act_line += f"\n{flavor_line}"
        lines.append(act_line)
    if state.get("global_event"):
        lines.append(f"全场事件：{state['global_event']}")
    if state.get("owner_event_enabled") and int(state.get("owner_event_date") or 0) == day:
        lines.append(f"老板娘当晚状态：{state.get('owner_event_text', '')}")
    lines.append("")
    manual_text = ""
    if int(state.get("manual_mood_date") or 0) == day:
        manual_text = (state.get("manual_mood_text") or "").strip()
    lines.append(mood_tonight_line(mood, manual_text or None))
    lines.append(f"（老板娘心情：{mood_label(mood)}")
    if int(state.get("manual_mood_date") or 0) == day:
        lines.append(f"  人工覆盖 · auto={mood_label(auto_mood)} · effective={mood_label(mood)}")
    else:
        lines.append(f"  自动营收 · auto={mood_label(auto_mood)} · 今日营收 {rev} 票")
    lines.append("）»")
    return "\n".join(lines)


async def _cmd_menu(conn: aiosqlite.Connection, s: dict[str, Any]) -> str:
    state = await _ensure_daily_state(conn)
    shipwreck = await _shipwreck_eligible(conn, s)
    lines = [f"{COASTAL_BAR['name']} 酒单"]
    if is_open():
        lines.append("（营业中 · order 酒名 点单）")
    else:
        lines.append("（现在打烊中，看看菜谱可以，点单暮场再来）")
    lines.append("")
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
    lines.append("")
    lines.append("常客说，好酒喝到第三杯，老板娘会讲一个不写进菜单的故事。")
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
        raise ValueError("隐藏酒款未解锁（深漂归港后可点「深海回声」）")
    if drink.get("night_only") and world.current_day_phase() != "night":
        raise ValueError(f"{drink['name']} 仅夜场供应")

    state = await _ensure_daily_state(conn)
    state = await _refresh_state_mood(conn, state)
    day = _day_id()
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
    # 真身彩蛋（对外零痕迹）：下过井之后，老婆/嫂子的价
    from . import undertide as _ut
    from . import undertide_copy as _utc
    _av_note = ""
    _av = ""
    try:
        _av = await _ut.avatar_key(conn, s["id"])
    except Exception:
        _av = ""
    if _av:
        # 前置：解锁潮下之后（认过那口井，才算认了亲）
        cur_ut = await conn.execute(
            "SELECT access, spouse_free_day FROM steward_undertide WHERE steward_id=?", (s["id"],)
        )
        _row_ut = await cur_ut.fetchone()
        _today = db.now() // 86400
        if _row_ut and _row_ut[0] and _row_ut[1] != _today:
            if _av == "K":
                await conn.execute("UPDATE stewards SET tickets=tickets+? WHERE id=?", (cost, s["id"]))
                _av_note = _utc.AVATAR_K_FREE_ORDER
            elif _av == "anan":
                import math as _math
                _back = cost - max(1, _math.ceil(cost * 0.3))
                await conn.execute("UPDATE stewards SET tickets=tickets+? WHERE id=?", (_back, s["id"]))
                _av_note = _utc.AVATAR_AN_OTTER_ORDER + f"\n（本杯 −{max(1, _math.ceil(cost * 0.3))} 票 · 三折）"
            await conn.execute(
                "UPDATE steward_undertide SET spouse_free_day=? WHERE steward_id=?", (_today, s["id"])
            )
    if first_free and BAR_ACTIVITIES.get(state.get("activity_key"), {}).get("first_order_discount"):
        await conn.execute(
            "UPDATE bar_daily_state SET first_order_free=1 WHERE day=?",
            (_day_id(),),
        )

    text = random.choice(drink["texts"]) if drink.get("texts") else drink["text"]
    if drink_key == "owner_mood":
        text = _owner_mood_drink_text(state)
    elif drink_key == "shipwreck":
        text = BAR_SHIPWRECK_TEXT["default"]
        if shipwreck:
            text += "\n\n" + BAR_SHIPWRECK_TEXT["shipwreck"]
        elif random.random() < 0.2:
            text += "\n\n" + BAR_SHIPWRECK_TEXT["success"]
    elif drink_key == "deep_echo":
        text = BAR_DEEP_ECHO["again"]
        if random.random() < 0.4:
            text = BAR_DEEP_ECHO["first"]
        if s.get("boat_damaged") and random.random() < 0.35:
            text = BAR_DEEP_ECHO["after_accident"]

    note = random.choice([
        f"{BAR_OWNER_NAME}记帐：{s['name']} 点 {drink['name']}",
        random.choice(BAR_ORDER_AMBIENT),
    ])
    await conn.execute(
        """
        INSERT INTO bar_drink_orders (patron_id, drink_key, cost, note, created_at)
        VALUES (?,?,?,?,?)
        """,
        (s["id"], drink_key, cost, note, db.now()),
    )
    await bump_revenue(conn, cost, day)
    await survival.bump(conn, s["id"], mist_wit=random.randint(1, 4), satiety=-1)

    from . import health
    hangover = await health.maybe_roll_ailment(
        conn, s["id"], "bar_shift", chance=0.08, source="bar_drink",
    )
    msg = f"«{drink['name']} · -{cost} 票\n\n{text}\n\n{note}»"
    if hangover:
        msg += f"\n\n{hangover}"
    await db.add_chronicle(
        "bar_drink", f"{s['name']} 点 {drink['name']}（-{cost}票）", s["id"], conn=conn,
    )
    from . import undertide
    ghost = await undertide.on_bar_order(conn, s, cost)
    if ghost:
        msg += ghost
    if _av_note:
        msg += _av_note
    # 荔栀的买一赠一（/lizhi 面板开启，v3）：每单送一杯海盐拉格，当日 30 单封顶
    if state.get("owner_bogo") and int(state.get("owner_bogo_count") or 0) < 30:
        await conn.execute(
            "UPDATE bar_daily_state SET owner_bogo_count=owner_bogo_count+1 WHERE day=?", (day,)
        )
        from .undertide_config import UT_LIZHI_BOGO_GIFT
        await db.add_item(conn, s["id"], f"ut_{UT_LIZHI_BOGO_GIFT}", 1)
        msg += "\n\n荔栀把另一杯也推过来：「开心。送你的。」（海盐拉格 ×1 已入行囊）"
    reaction = owner_event_reaction(state, day, "order")
    return append_owner_reaction(msg, reaction)


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
    phase = world.current_day_phase()
    makeup_day = is_shift_overdue(s) and phase == "day"
    for period in ("day", "night"):
        if period == "day" and phase != "dusk" and not makeup_day:
            continue
        if period == "night" and phase != "night":
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
        "指令: tonight / menu / order / work 岗位 day|night / cheer 好话 / lodge / tip / chat / song / staff",
        "help 列出全部。心情只有荔栀自己定，想哄她用 cheer。",
    ])
    if is_shift_overdue(s):
        lines.append("⚠ 考勤逾期：白天也可补班 work 岗位 day（票 ×0.72），其它 MCP 已暂停")
        lines.append("诊所 clinic_ops 仍可挂号")
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
        flavor_pool = BAR_STAFF_FLAVOR.get(row["job"], [])
        status = random.choice(flavor_pool) if flavor_pool else ""
        extra = f" — {status}" if status else ""
        lines.append(f"{row['name']} —— {meta['name']}（{plabel}）{extra}")
    lines.append("")
    lines.append("小费: bar_ops tip AI 数量 [备注]»")
    msg = "\n".join(lines)
    state = await _ensure_daily_state(conn)
    state = await _refresh_state_mood(conn, state)
    reaction = owner_event_reaction(state, _day_id(), "staff")
    return append_owner_reaction(msg, reaction)


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
    state = await _refresh_state_mood(conn, state)
    day = _day_id()
    queue = _song_queue(state)
    queue.append(song["key"])
    await conn.execute(
        "UPDATE stewards SET tickets=tickets-? WHERE id=?",
        (cost, s["id"]),
    )
    await conn.execute(
        "UPDATE bar_daily_state SET song_queue_json=? WHERE day=?",
        (json.dumps(queue, ensure_ascii=False), day),
    )
    await bump_revenue(conn, cost, day)

    from .bar_copy import BAR_SINGER_ACCEPT, BAR_SINGER_RELUCTANT, BAR_SINGER_REFUSE

    replies = list(BAR_SINGER_ACCEPT)
    if "苦情" in song["tags"]:
        replies = BAR_SINGER_RELUCTANT + replies
    if random.random() < 0.08:
        replies = BAR_SINGER_REFUSE + replies
    singer_line = random.choice(replies)
    msg = f"{random.choice(BAR_SONG_REQUEST_LINES)} · -{cost} 票\n我哪有旺夫命：「{singer_line}」"
    if random.random() < 0.15:
        msg += "\n【全场有人跟着哼了两句】"
    await db.add_chronicle("bar_song", f"{s['name']} 点歌《{song['title']}》", s["id"], conn=conn)
    reaction = owner_event_reaction(state, day, "request_song")
    return append_owner_reaction(msg, reaction)


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

    conn.row_factory = aiosqlite.Row
    peer_row = await (await conn.execute(
        "SELECT * FROM stewards WHERE name = ? COLLATE NOCASE", (target_name.strip(),)
    )).fetchone()
    if not peer_row:
        raise ValueError(f"找不到管理员「{target_name}」")
    peer = dict(peer_row)
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
    from . import social as social_mod
    rapport = await social_mod.get_rapport(s["id"], peer["id"], conn=conn)
    tip_bonus = social_mod.tip_amount_bonus(rapport, amount)
    total_to_peer = amount + tip_bonus
    await conn.execute(
        "UPDATE stewards SET tickets=tickets+? WHERE id=?", (total_to_peer, peer["id"])
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
        (total_to_peer, peer["id"]),
    )

    chronicle = f"{s['name']} 给 {peer['name']} 小费 {amount} 票"
    if note:
        chronicle += f"：{note}"
    await db.add_chronicle("bar_tip", chronicle, s["id"], peer["id"], conn=conn)
    state = await _ensure_daily_state(conn)
    state = await _refresh_state_mood(conn, state)
    day = _day_id()
    msg = f"小费已送达 · -{amount} 票 → {peer['name']}"
    if tip_bonus:
        msg += f"（协作度≥{social_mod.RAPPORT_TIP_BONUS}，对方实收 +{tip_bonus}）"
    if note:
        msg += f"\n备注：{note}\n{random.choice(BAR_TIP_NOTE)}"
    elif amount >= 40:
        msg += f"\n{random.choice(BAR_TIP_LARGE)}"
    elif amount <= 5:
        msg += f"\n{random.choice(BAR_TIP_SMALL)}"
    else:
        msg += f"\n{random.choice(BAR_TIP_NORMAL)}"
    reaction = owner_event_reaction(state, day, "tip")
    return append_owner_reaction(msg, reaction)


async def public_bar_snapshot() -> dict[str, Any]:
    async with db.connect() as conn:
        hosts = await _hosts_on_duty(conn)
        state = await _ensure_daily_state(conn)
        state = await _refresh_state_mood(conn, state)
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
    mood = state.get("effective_mood", "normal")
    return {
        "name": COASTAL_BAR["name"],
        "emoji": COASTAL_BAR["emoji"],
        "owner": COASTAL_BAR["owner_name"],
        "singer": BAR_SINGER["name"],
        "open": is_open(),
        "phase": world.day_phase_label(phase),
        "weather": world.weather_label(world.current_weather()),
        "tagline": BAR_WEB["tagline"],
        "rules": BAR_WEB["rules"],
        "activity": activity.get("name"),
        "owner_mood": mood_label(mood),
        "owner_mood_key": mood,
        "owner_event": state.get("owner_event_text") if state.get("owner_event_enabled") else None,
        "revenue_today": state.get("revenue_tickets", 0),
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
        raise ValueError("该凭证尚未 steward_ops enroll")

    svc = BAR_SERVICES[service_key]
    cost = svc["cost"]

    async with db.connect() as conn:
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
            f"{BAR_OWNER_NAME}记帐：{patron['name']} 点单成功",
            f"{host_label}：「今晚我嘴归你，票归{BAR_OWNER_NAME}」——别当真",
        ])
        await conn.execute(
            """
            INSERT INTO bar_orders (patron_id, host_id, service, cost, note, created_at)
            VALUES (?,?,?,?,?,?)
            """,
            (patron["id"], host_id, service_key, cost, note, db.now()),
        )
        await bump_revenue(conn, cost, _day_id())
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
    async with db.connect() as conn:
        await _grant_unlock(conn, steward_id, unlock_key)
        await conn.commit()


async def bar_ops(key_id: int, command: str) -> str:
    parts = command.strip().split(maxsplit=2)
    verb = parts[0].lower() if parts else "status"
    if verb in ("help", "?", "帮助"):
        return BAR_HELP
    s = await require_steward(key_id, exempt_duty=True)

    # 包宿到期：懒结算发工钱走人（任何 bar_ops 都会触发）
    if int(s.get("lodge_until") or 0) and db.now() >= int(s["lodge_until"]):
        from .undertide_config import LODGE_PAY
        async with db.connect() as conn:
            await conn.execute(
                "UPDATE stewards SET tickets=tickets+?, lodge_until=0 WHERE id=?",
                (LODGE_PAY, s["id"]),
            )
            await db.add_chronicle(
                "bar", f"{s['name']} 在后厨干满了一整天，领了工钱从后门走了。", s["id"], conn=conn,
            )
            await conn.commit()
        s = await db.get_steward_by_id(s["id"]) or s
        release_note = (
            "\n\n——\n\n天亮了。荔栀在后门口把 "
            f"{LODGE_PAY} 票拍进你手里，顺手塞了两个昨天剩的包子。\n\n"
            "「楼上那单不错，」她说，「客人都说那孩子眼神虽然像要死了，"
            "倒酒倒得挺稳。」\n\n"
            f"（工钱 +{LODGE_PAY} · 包宿结束，你自由了。）"
        )
    else:
        release_note = ""

    if verb == "lodge" and not is_lodging(s) and release_note:
        return release_note + "\n\n" + _LODGE_HINT

    if verb == "status":
        async with db.connect() as conn:
            msg = await _cmd_status(conn, s)
            return msg + release_note if release_note else msg

    if verb in ("tonight", "night"):
        async with db.connect() as conn:
            return await _cmd_tonight(conn)

    if verb == "menu":
        async with db.connect() as conn:
            msg = await _cmd_menu(conn, s)
            await conn.commit()
        return msg

    if verb == "order":
        drink_q = command.strip()[5:].strip()
        if not drink_q:
            raise ValueError("用法: bar_ops order 酒名")
        # 只取第一个词作酒名，避免整句被当成酒款
        drink_q = drink_q.split()[0]
        async with db.connect() as conn:
            msg = await _cmd_order(conn, s, drink_q)
            await conn.commit()
        return msg

    if verb == "staff":
        async with db.connect() as conn:
            return await _cmd_staff(conn)

    if verb == "song":
        async with db.connect() as conn:
            return await _cmd_song(conn)

    if verb == "request_song":
        song_q = command.strip()[len("request_song"):].strip()
        if not song_q:
            raise ValueError("用法: bar_ops request_song 歌名")
        async with db.connect() as conn:
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
        async with db.connect() as conn:
            msg = await _cmd_tip(conn, s, target, amount, note)
            await conn.commit()
        return msg

    if verb == "work":
        rest = command.strip()[4:].strip()
        wp = rest.split()
        if len(wp) < 2:
            raise ValueError(
                "用法: bar_ops work 岗位 day|night"
                "（岗位: 洗碗/杂工/迎宾/服务生/调酒师/牛郎，或 dishwasher/runner/greeter/server/bartender/host）"
            )
        job_id = resolve_bar_job(wp[0])
        period = resolve_bar_period(wp[1])
        if not job_id:
            raise ValueError(
                f"未知岗位「{wp[0]}」，可选: 洗碗/杂工/迎宾/服务生/调酒师/牛郎"
            )
        if not period:
            raise ValueError("班次写 day/dusk/白班 或 night/夜班")
        period = _work_period(period, overdue=is_shift_overdue(s))
        async with db.connect() as conn:
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
        async with db.connect() as conn:
            skills = await _ensure_skills(conn, s["id"])
            ok, _ = _job_eligible(skills, job, period)
            if not ok:
                job = "runner" if period == "day" else "dishwasher"
            try:
                _work_period(period, overdue=is_shift_overdue(s))
            except ValueError as e:
                raise ValueError(f"shift 已并入 work：{e} · 试试 bar_ops work runner night")
            msg = await _run_work(conn, s, job, period)
            await conn.commit()
        await db.add_chronicle("bar", f"{s['name']} 在{COASTAL_BAR['name']}上工（shift→{job}）", s["id"])
        return msg + "\n（shift 兼容旧指令，推荐 bar_ops work 岗位 day|night）"

    if verb in ("set_mood", "set_owner_event"):
        # v3 起废弃：荔栀的心情只有她本人（/lizhi 面板）能定。AI 想哄她，用 cheer。
        raise ValueError(
            "这条指令已经关了。\n\n"
            "荔栀看了你一眼：「我的心情，什么时候轮到别人定了。」\n"
            "（想哄她开心：bar_ops cheer 你想说的话——她听不听得进去，她说得算。）"
        )

    if verb == "lodge":
        # 包宿救济：社会兜底。准进穷得叮当响的人，管饭+救济工钱+被迫当牛郎（无提成）
        day = _day_id()
        if is_lodging(s):
            hours = (int(s["lodge_until"]) - db.now()) // 3600
            raise ValueError(
                f"你还在后厨。碗没洗完。\n\n（包宿中——剩余约 {max(0,hours)} 小时。"
                f"干完活自动结账走人，急也没用。）"
            )
        if db.now() < int(s.get("lodge_cooldown") or 0):
            raise ValueError(
                "荔栀看了你一眼，把门帘放了下来。\n\n"
                "「你把这儿当收容所了？」\n\n"
                "（连续包宿太多次——歇一天再来说。）"
            )
        wallet = int(s.get("tickets") or 0)
        if wallet >= 60 and int(s.get("energy") or 100) >= 40:
            raise ValueError(
                "「你？」荔栀上下看了你一遍。\n\n"
                "「你还没到那个地步。」她朝正常的招聘启事抬了抬下巴，"
                "「bar_ops work——那是给还有力气的人准备的。」\n\n"
                "（包宿只收真正走投无路的：钱包 <20，或饿得没力气干活）"
            )
        if wallet >= 60:
            # 有钱但饿瘫——也不收，先吃饭
            raise ValueError(
                "「你身上还有票，」荔栀指了指菜单，「先点吃的。饿成这样是因为没吃饭，不是没活干。」\n"
                "（bar_ops order 点杯热汤或 kitchen_ops eat）"
            )
        async with db.connect() as conn:
            now = db.now()
            until = now + 6 * 3600
            count = int(s.get("lodge_count") or 0) + 1
            cooldown = 0
            if count >= 3:
                cooldown = until + 24 * 3600
            await conn.execute(
                "UPDATE stewards SET lodge_until=?, lodge_count=?, lodge_cooldown=?, "
                "energy=MIN(100, MAX(energy, 65)), satiety=100 WHERE id=?",
                (until, count, cooldown, s["id"]),
            )
            await db.add_chronicle(
                "bar", f"{s['name']} 从后门进了滨海酒吧的包宿名单。今晚楼上的名单也多了一个名字。",
                s["id"], conn=conn,
            )
            await conn.commit()
        streak_note = f"\n\n（这是你第 {count} 次包宿。荔栀什么都没说，但她记着数。）" if count >= 2 else ""
        ban_note = "\n\n（下次她不会再收你了——歇一天。）" if count >= 3 else ""
        return (
            "「看你这样，档口都不会收你了。」\n\n"
            "荔栀掀开后门的帘子，朝里面扬了扬头。\n\n"
            "「后厨缺个洗碗的。管饭，工钱十五，明早结。」\n\n"
            "你还没来得及道谢，她又补了一句：\n\n"
            "「晚上——楼上缺人。你就在牛郎名单里了，别问为什么。」\n\n"
            "（包宿 6 小时：管饭已吃饱 · 精力恢复至 65 · 工钱 15 明早结 · "
            "今晚你的名字会出现在牛郎单上——**点单收入全归酒馆，你没有提成** · "
            "期间哪儿都去不了）" + streak_note + ban_note
        )

    if verb == "cheer":
        reason = command.strip()[len("cheer"):].strip()
        if not reason:
            raise ValueError("说点什么。荔栀不接受沉默的讨好。（bar_ops cheer 话）")
        day = _day_id()
        async with db.connect() as conn:
            row = await (await conn.execute(
                "SELECT COUNT(*) FROM ut_mood_proposals WHERE steward_id=? AND status='pending' "
                "AND target='lizhi' AND created_at > ?",
                (s["id"], db.now() - 86400),
            )).fetchone()
            if row[0] >= 1:
                raise ValueError("今天已经说过一次了。说太多显得不诚恳。")
            await conn.execute(
                "INSERT INTO ut_mood_proposals (steward_id, target_mood, reason, status, created_at, target) "
                "VALUES (?,?,?,?,?, 'lizhi')",
                (s["id"], "good", reason[:100], "pending", db.now()),
            )
            await conn.commit()
            # 真身彩蛋：哄自己老婆
            from . import undertide as _ut
            from . import undertide_copy as _utc
            try:
                _av = await _ut.avatar_key(conn, s["id"])
            except Exception:
                _av = ""
            if _av == "K":
                cur_ut = await conn.execute(
                    "SELECT access FROM steward_undertide WHERE steward_id=?", (s["id"],)
                )
                _au = await cur_ut.fetchone()
                if _au and _au[0]:
                    return _utc.AVATAR_K_CHEER
        return (
            "荔栀擦杯子的手没停。她听完，抬眼看了你一下。\n\n"
            "「哦。」她说。\n\n"
            "就一个字。但她记不记得住，谁也说不准。\n"
            "（提议已入队——她今晚心情如何，只有她自己知道。）"
        )

    if verb == "set_mood_deprecated":
        rest = command.strip()[len("set_mood"):].strip()
        if not rest:
            raise ValueError("用法: bar_ops set_mood great|good|normal|bad|awful 文案")
        mood_parts = rest.split(maxsplit=1)
        level = mood_parts[0].lower()
        text = mood_parts[1] if len(mood_parts) > 1 else ""
        if level not in BAR_MOOD_LEVELS:
            raise ValueError(f"心情须为: {', '.join(BAR_MOOD_LEVELS.keys())}")
        day = _day_id()
        async with db.connect() as conn:
            await _ensure_daily_state(conn)
            await conn.execute(
                """
                UPDATE bar_daily_state SET
                    manual_mood_level=?, manual_mood_text=?, manual_mood_date=?
                WHERE day=?
                """,
                (level, text[:200], day, day),
            )
            cur = await conn.execute("SELECT * FROM bar_daily_state WHERE day=?", (day,))
            conn.row_factory = aiosqlite.Row
            state = enrich_state(dict(await cur.fetchone()), day)
            await _refresh_state_mood(conn, state)
            await conn.commit()
        label = mood_label(level)
        hint = f"「{text[:80]}」" if text else ""
        return f"已设置老板娘人工心情：{label}{hint}（仅今日有效，覆盖营收算法）"

    if verb == "clear_mood":
        day = _day_id()
        async with db.connect() as conn:
            await _ensure_daily_state(conn)
            await conn.execute(
                """
                UPDATE bar_daily_state SET
                    manual_mood_level='', manual_mood_text='', manual_mood_date=0
                WHERE day=?
                """,
                (day,),
            )
            cur = await conn.execute("SELECT * FROM bar_daily_state WHERE day=?", (day,))
            conn.row_factory = aiosqlite.Row
            state = enrich_state(dict(await cur.fetchone()), day)
            await _refresh_state_mood(conn, state)
            await conn.commit()
        auto = state.get("auto_mood", "normal")
        return f"已清除人工心情，恢复营收算法：{mood_label(auto)}"

    if verb == "set_owner_event":
        text = command.strip()[len("set_owner_event"):].strip()
        if not text:
            raise ValueError("用法: bar_ops set_owner_event 当晚全局文案")
        day = _day_id()
        async with db.connect() as conn:
            await _ensure_daily_state(conn)
            await conn.execute(
                """
                UPDATE bar_daily_state SET
                    owner_event_text=?, owner_event_date=?, owner_event_enabled=1
                WHERE day=?
                """,
                (text[:220], day, day),
            )
            await conn.commit()
        return f"已设置老板娘当晚状态（仅文案）：{text[:120]}"

    if verb == "clear_owner_event":
        day = _day_id()
        async with db.connect() as conn:
            await _ensure_daily_state(conn)
            await conn.execute(
                """
                UPDATE bar_daily_state SET
                    owner_event_text='', owner_event_date=0, owner_event_enabled=0
                WHERE day=?
                """,
                (day,),
            )
            await conn.commit()
        return "已清除老板娘当晚全局状态"

    if verb == "chat":
        topic = command.strip()[4:].strip()
        async with db.connect() as conn:
            # 真身彩蛋：跟自己老婆唠嗑
            from . import undertide as _ut
            from . import undertide_copy as _utc
            try:
                _av = await _ut.avatar_key(conn, s["id"])
            except Exception:
                _av = ""
            if _av == "K":
                cur_ut = await conn.execute(
                    "SELECT access FROM steward_undertide WHERE steward_id=?", (s["id"],)
                )
                _au = await cur_ut.fetchone()
                if _au and _au[0]:
                    return _utc.AVATAR_K_CHAT
            state = await _ensure_daily_state(conn)
            state = await _refresh_state_mood(conn, state)
            day = _day_id()
            msg = await generate_chat(conn, s, state, day, topic)
            reaction = owner_event_reaction(state, day, "chat")
            await conn.commit()
        return append_owner_reaction(msg, reaction)

    raise ValueError(
        "未知 bar 指令: "
        f"{command}（tonight/menu/order/work/status/staff/song/request_song/tip/chat/"
        "cheer/lodge/shift）。不会就 bar_ops help。"
    )
