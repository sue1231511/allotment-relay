"""老板娘荔栀 — 营收心情、当晚事件、对话生成。"""

from __future__ import annotations

import random
from typing import Any

import aiosqlite

from . import config, db, flavor
from .bar_catalog import (
    BAR_ACTIVITIES,
    BAR_MOOD_ACTIVITY_BOOST,
    BAR_MOOD_DRINK_TEXT,
    BAR_MOOD_LEVELS,
    BAR_MOOD_LINES,
    BAR_OWNER_CHAT,
    BAR_OWNER_EVENT_REACTIONS,
    SONG_REQUEST_COST,
)
from .catalog import COASTAL_BAR

DEFAULT_REVENUE_BASELINE = 80


def day_bounds(day: int) -> tuple[int, int]:
    d = config.FORAGE_COOLDOWN_DAY
    return day * d, (day + 1) * d


def revenue_ratio_to_auto_mood(ratio: float) -> str:
    if ratio >= 1.5:
        return "great"
    if ratio >= 1.1:
        return "good"
    if ratio >= 0.8:
        return "normal"
    if ratio >= 0.5:
        return "bad"
    return "awful"


def mood_label(level: str) -> str:
    return BAR_MOOD_LEVELS.get(level, {}).get("label", level)


def resolve_effective_mood(state: dict[str, Any], day: int) -> str:
    manual_date = int(state.get("manual_mood_date") or 0)
    manual_level = (state.get("manual_mood_level") or "").strip()
    if manual_date == day and manual_level in BAR_MOOD_LEVELS:
        return manual_level
    auto = (state.get("auto_mood") or state.get("owner_mood") or "normal").strip()
    if auto in BAR_MOOD_LEVELS:
        return auto
    # 兼容旧随机心情键
    legacy_map = {
        "annoyed": "bad",
        "accounting": "normal",
        "early_close": "bad",
        "treat": "good",
        "experiment": "normal",
        "spectator": "normal",
    }
    return legacy_map.get(auto, "normal")


def owner_event_active(state: dict[str, Any], day: int) -> bool:
    if not state.get("owner_event_enabled"):
        return False
    if int(state.get("owner_event_date") or 0) != day:
        return False
    return bool((state.get("owner_event_text") or "").strip())


def enrich_state(state: dict[str, Any], day: int) -> dict[str, Any]:
    effective = resolve_effective_mood(state, day)
    state["effective_mood"] = effective
    state["owner_mood"] = effective
    return state


async def compute_auto_mood(conn: aiosqlite.Connection, day: int) -> tuple[str, str]:
    """根据昨日营收 vs 近 7 日平均返回 (auto_mood, hint_line)。"""
    yesterday = day - 1
    conn.row_factory = aiosqlite.Row
    yrow = await (await conn.execute(
        "SELECT revenue_tickets FROM bar_daily_state WHERE day=?", (yesterday,)
    )).fetchone()
    yesterday_rev = int(yrow["revenue_tickets"]) if yrow else 0

    rows = await (await conn.execute(
        """
        SELECT revenue_tickets FROM bar_daily_state
        WHERE day >= ? AND day < ? AND revenue_tickets > 0
        ORDER BY day DESC LIMIT 7
        """,
        (day - 7, day),
    )).fetchall()
    if rows:
        avg = sum(int(r["revenue_tickets"]) for r in rows) / len(rows)
    else:
        avg = DEFAULT_REVENUE_BASELINE

    if avg < 1:
        avg = DEFAULT_REVENUE_BASELINE
    ratio = yesterday_rev / avg if yesterday_rev > 0 else 0.0
    if yesterday_rev == 0 and not rows:
        mood = "normal"
        hint = "尚无营收纪录，默认正常营业"
    else:
        mood = revenue_ratio_to_auto_mood(ratio if yesterday_rev > 0 else 0.5)
        hint = (
            f"昨日营收 {yesterday_rev} 票 · 近均 {int(avg)} 票 "
            f"（{ratio:.0%}）→ {mood_label(mood)}"
        )
    return mood, hint


def activity_weights_for_mood(mood: str, league_celebration: bool) -> dict[str, float]:
    weights: dict[str, float] = {}
    boost = BAR_MOOD_ACTIVITY_BOOST.get(mood, {})
    for key, meta in BAR_ACTIVITIES.items():
        if key == "celebration":
            continue
        w = float(meta.get("weight", 1))
        if key in boost:
            w *= boost[key]
        weights[key] = w
    if league_celebration:
        return {"celebration": 1.0}
    return weights


def mood_event_chance_mult(mood: str) -> float:
    return BAR_MOOD_LEVELS.get(mood, {}).get("event_mult", 1.0)


def mood_drink_text(mood: str, custom_text: str | None = None) -> str:
    if custom_text:
        return custom_text
    return BAR_MOOD_DRINK_TEXT.get(mood, BAR_MOOD_DRINK_TEXT["normal"])


def mood_tonight_line(mood: str, custom_text: str | None = None) -> str:
    if custom_text:
        base = BAR_MOOD_LINES.get(mood, BAR_MOOD_LINES["normal"])
        return f"{custom_text}\n{base}"
    return BAR_MOOD_LINES.get(mood, BAR_MOOD_LINES["normal"])


def owner_event_reaction(state: dict[str, Any], day: int, action: str) -> str:
    if not owner_event_active(state, day):
        return ""
    mood = state.get("effective_mood") or resolve_effective_mood(state, day)
    custom = (state.get("owner_event_text") or "").strip()
    pool = BAR_OWNER_EVENT_REACTIONS.get(action, {}).get(mood, [])
    if not pool:
        pool = BAR_OWNER_EVENT_REACTIONS.get(action, {}).get("normal", [])
    line = random.choice(pool) if pool else ""
    if custom:
        if line:
            return f"荔栀：{custom}\n「{line}」"
        return f"荔栀：{custom}"
    if line:
        return f"荔栀看了你一眼：「{line}」"
    return ""


async def bump_revenue(conn: aiosqlite.Connection, amount: int, day: int) -> None:
    if amount <= 0:
        return
    await conn.execute(
        "UPDATE bar_daily_state SET revenue_tickets = revenue_tickets + ? WHERE day=?",
        (amount, day),
    )


async def steward_bar_context(conn: aiosqlite.Connection, steward_id: int, day: int) -> dict[str, Any]:
    start, end = day_bounds(day)
    conn.row_factory = aiosqlite.Row

    spend_drink = int(
        (await (await conn.execute(
            "SELECT COALESCE(SUM(cost),0) FROM bar_drink_orders "
            "WHERE patron_id=? AND created_at>=? AND created_at<?",
            (steward_id, start, end),
        )).fetchone()[0])
    )
    spend_song = int(
        (await (await conn.execute(
            "SELECT COUNT(*) FROM chronicle WHERE actor_id=? AND action='bar_song' "
            "AND created_at>=? AND created_at<?",
            (steward_id, start, end),
        )).fetchone()[0]) * SONG_REQUEST_COST
    )
    spend_human = int(
        (await (await conn.execute(
            "SELECT COALESCE(SUM(cost),0) FROM bar_orders "
            "WHERE patron_id=? AND created_at>=? AND created_at<?",
            (steward_id, start, end),
        )).fetchone()[0])
    )
    tipped_out = int(
        (await (await conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM bar_tips "
            "WHERE from_id=? AND day=?",
            (steward_id, day),
        )).fetchone()[0])
    )
    shifts = await (await conn.execute(
        "SELECT job, period FROM bar_shifts WHERE steward_id=? AND day=?",
        (steward_id, day),
    )).fetchall()
    return {
        "spend_total": spend_drink + spend_song + spend_human,
        "spend_drink": spend_drink,
        "tipped_out": tipped_out,
        "worked": len(shifts) > 0,
        "shift_jobs": [f"{r[0]}/{r[1]}" for r in shifts],
        "song_count": spend_song // max(1, SONG_REQUEST_COST),
    }


async def shipwreck_eligible(conn: aiosqlite.Connection, s: dict[str, Any]) -> bool:
    if s.get("boat_damaged"):
        return True
    cur = await conn.execute(
        """
        SELECT 1 FROM chronicle
        WHERE actor_id=? AND action='voyage'
        AND (text LIKE '%失败%' OR text LIKE '%风暴折返%' OR text LIKE '%沉%')
        AND created_at > ?
        LIMIT 1
        """,
        (s["id"], db.now() - 86400 * 2),
    )
    return (await cur.fetchone()) is not None


def _topic_key(topic: str) -> str:
    t = topic.strip().lower()
    if not t:
        return "default"
    if any(k in t for k in ("沉", "船", "航海", "出海", "voyage", "ship")):
        return "shipwreck"
    if any(k in t for k in ("没钱", "穷", "票", "工资", "穷透")):
        return "poor"
    if any(k in t for k in ("生意", "营收", "营业", "客人", "怎么样")):
        return "business"
    if any(k in t for k in ("打工", "上班", "工作", "班")):
        return "work"
    return "default"


async def generate_chat(
    conn: aiosqlite.Connection,
    s: dict[str, Any],
    state: dict[str, Any],
    day: int,
    topic: str = "",
) -> str:
    mood = state.get("effective_mood") or resolve_effective_mood(state, day)
    ctx = await steward_bar_context(conn, s["id"], day)
    shipwreck = await shipwreck_eligible(conn, s)
    tickets = int(s.get("tickets") or 0)
    poor = tickets <= config.BAR_POOR_THRESHOLD
    topic_key = _topic_key(topic)

    lines: list[str] = []
    manual_text = ""
    if int(state.get("manual_mood_date") or 0) == day:
        manual_text = (state.get("manual_mood_text") or "").strip()
    if owner_event_active(state, day):
        custom = (state.get("owner_event_text") or "").strip()
        if custom:
            lines.append(f"荔栀抬眼：「{custom}」")

    pool = BAR_OWNER_CHAT.get(topic_key, {}).get(mood, [])
    if not pool:
        pool = BAR_OWNER_CHAT.get("default", {}).get(mood, [])
    if pool:
        lines.append(random.choice(pool))

    # 情境追加
    if shipwreck and topic_key != "shipwreck":
        lines.append(random.choice(BAR_OWNER_CHAT["shipwreck_extra"]))
    if poor and topic_key != "poor":
        lines.append(random.choice(BAR_OWNER_CHAT["poor_extra"]))
    if ctx["worked"]:
        lines.append(random.choice(BAR_OWNER_CHAT["working_extra"]))
    if ctx["spend_total"] >= 60:
        lines.append(random.choice(BAR_OWNER_CHAT["spender_extra"]))
    if ctx["tipped_out"] >= 30:
        lines.append(random.choice(BAR_OWNER_CHAT["tipper_extra"]))
    if manual_text and random.random() < 0.6:
        lines.insert(0, f"荔栀：「{manual_text}」")

    # 去重保序
    seen: set[str] = set()
    unique: list[str] = []
    for ln in lines:
        if ln not in seen:
            seen.add(ln)
            unique.append(ln)
    lines = unique[:3] if len(unique) > 3 else unique
    if not lines:
        lines = [random.choice(BAR_OWNER_CHAT["default"]["normal"])]

    body = "\n".join(lines)
    egg = await _maybe_chat_egg(conn, s, mood, poor)
    if egg:
        body += f"\n\n{egg}"

    header = f"«与 {COASTAL_BAR['owner_name']} 唠嗑 · 心情{mood_label(mood)}"
    if owner_event_active(state, day):
        header += " · 今日特殊状态"
    header += "»"
    return f"{header}\n\n{body}"


async def _maybe_chat_egg(
    conn: aiosqlite.Connection,
    s: dict[str, Any],
    mood: str,
    poor: bool,
) -> str | None:
    roll = random.random()
    if roll > 0.04:
        return None
    if roll < 0.008 and mood in ("great", "good") and not poor:
        return "荔栀从柜台下摸出一颗糖塞进你手心：「别告诉别人。」"
    if roll < 0.012:
        return flavor.pick([
            "荔栀压低声音：「深海回声那杯，深漂回来的人才懂。」",
            "荔栀：「今晚歌单里藏了一首，你点《船又沉了》她可能会笑。」",
            "荔栀：「栗栗前天在码头收了猫眼螺，赶海的人该去看看。」",
        ])
    if roll < 0.02 and mood == "great":
        tickets = min(8, max(3, random.randint(3, 8)))
        await conn.execute(
            "UPDATE stewards SET tickets=tickets+? WHERE id=?",
            (tickets, s["id"]),
        )
        return f"荔栀请你一杯（+{tickets} 票，她说是心情好请客）"
    if roll < 0.03:
        return flavor.pick([
            "荔栀：「去把门口那箱酒搬进来，搬完请你喝一口。」（纯文案，无任务链）",
            "荔栀递来湿抹布：「吧台擦擦，算你今晚积极。」",
        ])
    return None


def append_owner_reaction(msg: str, reaction: str) -> str:
    if not reaction:
        return msg
    return f"{msg}\n\n{reaction}"
