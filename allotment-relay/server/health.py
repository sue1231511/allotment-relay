"""身体状况 — 随机事件致病，桥桥大夫诊所花钱治。"""

from __future__ import annotations

import random
from typing import Any

import aiosqlite

from . import config, db, flavor
from .catalog import AILMENTS

TRIGGER_AILMENTS: dict[str, list[str]] = {
    "tend": ["sprain", "backache", "blister", "cut", "allergy"],
    "gather": ["sprain", "backache", "blister", "allergy"],
    "sow": ["sprain", "backache", "cut"],
    "forage": ["allergy", "blister", "cut"],
    "net": ["jelly_sting", "cold", "shell_scratch"],
    "pen_feed": ["cut", "blister"],
    "pen_harvest": ["cut", "crab_pinch"],
    "pen_stock": ["cut"],
    "voyage_depart": ["cold", "food_poison", "backache"],
    "voyage_return": ["cold", "food_poison", "backache"],
    "guild": ["blister"],
    "brew": ["food_poison"],
    "beach": ["shell_scratch", "sunburn", "crab_pinch"],
    "bar_shift": ["hangover"],
    "naval_bad": ["cold", "food_poison", "backache"],
    "farm_wild": ["sprain", "allergy", "blister"],
}


async def list_ailments(conn: aiosqlite.Connection, steward_id: int) -> list[dict[str, Any]]:
    conn.row_factory = aiosqlite.Row
    rows = await (await conn.execute(
        """
        SELECT ailment_key, source, inflicted_at FROM steward_ailments
        WHERE steward_id=? ORDER BY inflicted_at
        """,
        (steward_id,),
    )).fetchall()
    out = []
    for r in rows:
        key = r["ailment_key"]
        meta = AILMENTS.get(key, {})
        out.append({
            "key": key,
            "name": meta.get("name", key),
            "emoji": meta.get("emoji", "🩹"),
            "cost": meta.get("cost", 0),
            "hint": meta.get("hint", ""),
            "source": r["source"],
            "inflicted_at": r["inflicted_at"],
        })
    return out


async def inflict(
    conn: aiosqlite.Connection,
    steward_id: int,
    ailment_key: str,
    *,
    source: str = "event",
) -> str | None:
    if ailment_key not in AILMENTS:
        return None
    cur = await conn.execute(
        "SELECT 1 FROM steward_ailments WHERE steward_id=? AND ailment_key=?",
        (steward_id, ailment_key),
    )
    if await cur.fetchone():
        return None
    meta = AILMENTS[ailment_key]
    loss = meta.get("health_loss", 8)
    await conn.execute(
        """
        UPDATE stewards SET health = MAX(0, health - ?) WHERE id=?
        """,
        (loss, steward_id),
    )
    await conn.execute(
        """
        INSERT INTO steward_ailments (steward_id, ailment_key, source, inflicted_at)
        VALUES (?,?,?,?)
        """,
        (steward_id, ailment_key, source, db.now()),
    )
    name = f"{meta['emoji']}{meta['name']}"
    return flavor.fill(
        flavor.pick(flavor.AILMENT_INFlict_LINES),
        name=name,
        hint=meta.get("hint", ""),
    )


async def maybe_roll_ailment(
    conn: aiosqlite.Connection,
    steward_id: int,
    trigger: str,
    *,
    pool: list[str] | None = None,
    chance: float | None = None,
    source: str = "event",
) -> str | None:
    keys = pool or TRIGGER_AILMENTS.get(trigger, [])
    if not keys:
        return None
    roll_chance = chance if chance is not None else config.AILMENT_ROLL_CHANCE
    if random.random() > roll_chance:
        return None
    key = random.choice(keys)
    return await inflict(conn, steward_id, key, source=source)


def energy_extra(ailments: list[dict[str, Any]]) -> int:
    total = 0
    for a in ailments:
        meta = AILMENTS.get(a["key"], {})
        total += meta.get("energy_extra", 1)
    return total


def max_energy_cap(ailments: list[dict[str, Any]]) -> int:
    cap = config.MAX_ENERGY
    for a in ailments:
        meta = AILMENTS.get(a["key"], {})
        cap -= meta.get("max_energy_cut", 0)
    return max(35, cap)


def event_bias(steward: dict[str, Any], ailment_count: int) -> float:
    mult = 1.0
    health = steward.get("health", config.START_HEALTH)
    if health < config.HEALTH_LOW:
        mult *= 1.10
    if ailment_count >= 2:
        mult *= 1.08
    if ailment_count >= 3:
        mult *= 1.06
    return mult


def meter_line(steward: dict[str, Any], ailments: list[dict[str, Any]]) -> str:
    h = steward.get("health", config.START_HEALTH)
    line = f"身体 {h}/100"
    if ailments:
        names = "、".join(f"{a['emoji']}{a['name']}" for a in ailments[:3])
        extra = f" 等{len(ailments)}项" if len(ailments) > 3 else ""
        line += f"（{names}{extra}）"
    hints = []
    if h < config.HEALTH_LOW:
        hints.append(flavor.HEALTH_HINT_LOW)
    if ailments:
        hints.append(flavor.HEALTH_HINT_CLINIC)
    if hints:
        line += f"（{'，'.join(hints)}）"
    return line


def clinic_hint(ailments: list[dict[str, Any]]) -> str | None:
    if not ailments:
        return None
    total = sum(a["cost"] for a in ailments)
    return flavor.fill(
        flavor.pick(flavor.CLINIC_NAG_LINES),
        n=len(ailments),
        total=total,
    )


async def treat_one(
    conn: aiosqlite.Connection,
    steward_id: int,
    ailment_key: str,
) -> str:
    if ailment_key not in AILMENTS:
        raise ValueError(f"未知病症，visit_ops clinic 查看")
    if ailment_key in ("pit_trauma", "ring_shock"):
        raise ValueError(
            "桥桥看了一眼伤势，又看了你一眼。\n"
            "「这不是摔的。哪儿弄的，回哪儿治。」\n"
            "「别把地下那套账算我头上。」\n"
            "（深坑专属重伤 — undertide_ops pit medic 处理）"
        )
    cur = await conn.execute(
        "SELECT 1 FROM steward_ailments WHERE steward_id=? AND ailment_key=?",
        (steward_id, ailment_key),
    )
    if not await cur.fetchone():
        raise ValueError(f"你没有 {AILMENTS[ailment_key]['name']}")
    meta = AILMENTS[ailment_key]
    cost = meta["cost"]
    cur = await conn.execute("SELECT tickets, health FROM stewards WHERE id=?", (steward_id,))
    row = await cur.fetchone()
    tickets, health = row[0], row[1]
    if tickets < cost:
        raise ValueError(f"诊费 {cost} 票，你只有 {tickets} 票——桥桥大夫不赊账")
    heal = meta.get("health_restore", 12)
    await conn.execute(
        "UPDATE stewards SET tickets=tickets-?, health=MIN(100, health+?) WHERE id=?",
        (cost, heal, steward_id),
    )
    await conn.execute(
        "DELETE FROM steward_ailments WHERE steward_id=? AND ailment_key=?",
        (steward_id, ailment_key),
    )
    return (
        f"桥桥大夫收 {cost} 票，治好 {meta['emoji']}{meta['name']} "
        f"（身体 +{heal}）"
    ) + flavor.maybe_suffix(flavor.CLINIC_TREAT_LINES)


async def treat_all(conn: aiosqlite.Connection, steward_id: int) -> str:
    ailments = await list_ailments(conn, steward_id)
    if not ailments:
        return "身体倍儿棒——没病别占桥桥大夫的号"
    total = sum(a["cost"] for a in ailments)
    cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (steward_id,))
    tickets = (await cur.fetchone())[0]
    if tickets < total:
        raise ValueError(
            f"全套治疗需 {total} 票（{len(ailments)} 项），你只有 {tickets} 票——必须花钱，不能赊"
        )
    names = []
    heal_total = 0
    for a in ailments:
        meta = AILMENTS[a["key"]]
        heal_total += meta.get("health_restore", 12)
        names.append(f"{meta['emoji']}{meta['name']}")
    await conn.execute(
        "UPDATE stewards SET tickets=tickets-?, health=MIN(100, health+?) WHERE id=?",
        (total, heal_total, steward_id),
    )
    await conn.execute("DELETE FROM steward_ailments WHERE steward_id=?", (steward_id,))
    return (
        f"桥桥大夫打包收 {total} 票，清掉 {len(ailments)} 项："
        f"{'、'.join(names)}（身体 +{min(100, heal_total)}）"
    )
