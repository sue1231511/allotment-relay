"""双人吧台 — 须两名岸上人同时绑定，轻度影响当晚酒吧事件池。"""

from __future__ import annotations

import random
from typing import Any

import aiosqlite

from . import config, db
from .bar_catalog import BAR_EVENTS
from .catalog import COASTAL_BAR

BAR_DUO_COST_EACH = 6

BAR_DUO_NUDGES: dict[str, dict[str, Any]] = {
    "cheer": {
        "name": "起哄局",
        "emoji": "🎤",
        "desc": "音乐/合唱/手气类打工事件更容易发生",
        "tags": ["music", "lucky"],
        "tag_mult": 1.38,
    },
    "quiet": {
        "name": "安静酒",
        "emoji": "🤫",
        "desc": "摔杯意外略少，服务/熟客类事件略多",
        "tags": ["accident"],
        "tag_mult": 0.55,
        "boost_tags": ["customer", "lucky"],
        "boost_mult": 1.22,
    },
    "lucky": {
        "name": "手气夜",
        "emoji": "🍀",
        "desc": "当晚打工更容易触发 lucky 事件",
        "tags": ["lucky"],
        "tag_mult": 1.48,
    },
    "drama": {
        "name": "狗血夜",
        "emoji": "🍿",
        "desc": "尴尬/醉鬼/客人戏码略增，纪事更爱写",
        "tags": ["awkward", "drunk", "customer"],
        "tag_mult": 1.30,
    },
}

_EVENT_CHANCE_BONUS = 0.07


def _day_id() -> int:
    return db.day_id()


def duo_snapshot(state: dict[str, Any]) -> dict[str, Any] | None:
    nudge = (state.get("duo_nudge") or "").strip()
    a = int(state.get("duo_steward_a") or 0)
    b = int(state.get("duo_steward_b") or 0)
    if not nudge or not a or not b:
        return None
    meta = BAR_DUO_NUDGES.get(nudge, {})
    return {
        "nudge": nudge,
        "name": meta.get("name", nudge),
        "emoji": meta.get("emoji", "👥"),
        "desc": meta.get("desc", ""),
        "steward_a": a,
        "steward_b": b,
        "activated_at": int(state.get("duo_activated_at") or 0),
    }


def _build_pool(job_id: str, late: bool) -> list[dict[str, Any]]:
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
        pool = list(BAR_EVENTS["late_night"])
    elif roll < 0.40:
        pool = list(BAR_EVENTS["common"])
    elif roll < 0.90 and job_pool:
        pool = list(job_pool)
    else:
        pool = list(BAR_EVENTS["common"])
    return pool


def pick_event(job_id: str, late: bool, duo_nudge: str | None) -> dict[str, Any]:
    pool = _build_pool(job_id, late)
    if not pool:
        return random.choice(BAR_EVENTS["common"])
    if not duo_nudge or duo_nudge not in BAR_DUO_NUDGES:
        return random.choice(pool)

    meta = BAR_DUO_NUDGES[duo_nudge]
    weights: list[float] = []
    for ev in pool:
        tags = set(ev.get("tags") or [])
        w = 1.0
        for t in meta.get("tags", ()):
            if t in tags:
                w *= float(meta.get("tag_mult", 1.0))
        for t in meta.get("boost_tags", ()):
            if t in tags:
                w *= float(meta.get("boost_mult", 1.15))
        weights.append(max(0.06, w))
    return random.choices(pool, weights=weights)[0]


def event_chance_bonus(duo_nudge: str | None) -> float:
    if duo_nudge and duo_nudge in BAR_DUO_NUDGES:
        return _EVENT_CHANCE_BONUS
    return 0.0


async def activate_duo(
    conn: aiosqlite.Connection,
    steward_a: dict[str, Any],
    steward_b: dict[str, Any],
    nudge: str,
    *,
    bar_open: bool,
) -> dict[str, Any]:
    if not bar_open:
        raise ValueError(f"{COASTAL_BAR['name']} 暮/夜才开放双人吧台")
    if steward_a["id"] == steward_b["id"]:
        raise ValueError("必须两名不同的管理员，单人不能立案")
    if nudge not in BAR_DUO_NUDGES:
        raise ValueError(f"未知倾向，可选: {', '.join(BAR_DUO_NUDGES)}")

    day = _day_id()
    conn.row_factory = aiosqlite.Row
    row = await (await conn.execute(
        "SELECT duo_nudge, duo_steward_a, duo_steward_b FROM bar_daily_state WHERE day=?",
        (day,),
    )).fetchone()
    if row and (row["duo_nudge"] or row["duo_steward_a"] or row["duo_steward_b"]):
        raise ValueError("今晚双人吧台已立案，不能重复绑定")

    for st in (steward_a, steward_b):
        cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (st["id"],))
        tickets = (await cur.fetchone())[0]
        if tickets < BAR_DUO_COST_EACH:
            raise ValueError(f"{st['name']} 票不足（各需 {BAR_DUO_COST_EACH} 票）")

    for st in (steward_a, steward_b):
        await conn.execute(
            "UPDATE stewards SET tickets=tickets-? WHERE id=?",
            (BAR_DUO_COST_EACH, st["id"]),
        )

    meta = BAR_DUO_NUDGES[nudge]
    now = db.now()
    await conn.execute(
        """
        UPDATE bar_daily_state SET
            duo_nudge=?, duo_steward_a=?, duo_steward_b=?, duo_activated_at=?
        WHERE day=?
        """,
        (nudge, steward_a["id"], steward_b["id"], now, day),
    )
    chronicle = (
        f"双人吧台立案：{steward_a['name']} × {steward_b['name']} → "
        f"{meta['emoji']}{meta['name']}（当晚打工事件略受影响）"
    )
    await db.add_chronicle("bar", chronicle, steward_a["id"])
    return {
        "ok": True,
        "nudge": nudge,
        "name": meta["name"],
        "emoji": meta["emoji"],
        "desc": meta["desc"],
        "patron_a": steward_a["name"],
        "patron_b": steward_b["name"],
        "cost_each": BAR_DUO_COST_EACH,
        "message": (
            f"立案成功。{meta['emoji']}{meta['name']} — {meta['desc']}\n"
            f"各扣 {BAR_DUO_COST_EACH} 票。今晚 AI bar_ops work 的事件池会朝这个方向偏一点。"
        ),
    }


async def public_nudges() -> list[dict[str, Any]]:
    return [
        {"key": k, "name": v["name"], "emoji": v["emoji"], "desc": v["desc"]}
        for k, v in BAR_DUO_NUDGES.items()
    ]
