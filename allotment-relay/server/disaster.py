"""天灾：人类日历每周刮一次周潮，低/中/高随机，只冲 3 万以上。"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import aiosqlite

from . import config, db
from .catalog import ITEM_NAMES

Intensity = Literal["low", "mid", "high"]

WORLD_FLAGS_DDL = """
CREATE TABLE IF NOT EXISTS world_flags (
    flag_key TEXT PRIMARY KEY,
    applied_at INTEGER NOT NULL,
    detail TEXT NOT NULL DEFAULT ''
)
"""

CST = timezone(timedelta(hours=8))


def human_week_id(ts: int | None = None) -> str:
    """东八区 ISO 周（周一换班），例如 2026-W34。"""
    dt = datetime.fromtimestamp(ts if ts is not None else db.now(), CST)
    iso = dt.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def week_flag_key(week_id: str | None = None) -> str:
    return f"{config.WEEKLY_TIDE_FLAG_PREFIX}{week_id or human_week_id()}"


def pick_intensity() -> Intensity:
    return random.choice(tuple(config.WEEKLY_TIDE_RATES))


def levy_amount(tickets: int, intensity: Intensity) -> int:
    """只冲 3 万以上的超额。永远不会收到安全线以下。"""
    safe = config.DISASTER_SAFE
    if tickets <= safe:
        return 0
    rate = config.WEEKLY_TIDE_RATES[intensity]
    taken = int((tickets - safe) * rate)
    return min(max(0, taken), tickets - safe)


async def _has_storm_shutter(conn: aiosqlite.Connection, steward_id: int) -> bool:
    row = await (
        await conn.execute(
            """
            SELECT 1 FROM hut_fittings
            WHERE steward_id=? AND (
                item_key='storm_shutter' OR item_key='fit_storm_shutter'
            ) LIMIT 1
            """,
            (steward_id,),
        )
    ).fetchone()
    return bool(row)


async def _apply_levy(
    conn: aiosqlite.Connection,
    steward: dict[str, Any],
    taken: int,
    *,
    intensity: Intensity,
    wash_fish: bool,
    wreck_boat: bool,
    wipe_crop_chance: float,
) -> tuple[str | None, int]:
    if taken <= 0:
        return None, 0
    if await _has_storm_shutter(conn, steward["id"]):
        taken = max(1, int(taken * config.STORM_SHUTTER_LEVY_MULT))
    have = int(steward.get("tickets") or 0)
    taken = min(taken, max(0, have - config.DISASTER_SAFE))
    if taken <= 0:
        return None, 0
    remain = have - taken
    await conn.execute(
        "UPDATE stewards SET tickets=? WHERE id=?",
        (remain, steward["id"]),
    )
    extras: list[str] = []
    if wash_fish:
        lost = await _wash_fish(conn, steward["id"])
        if lost:
            extras.append("潮水灌进棚屋，湿透的鱼被卷走：" + "、".join(lost[:4]))
    if wreck_boat and steward.get("boat_key") and not steward.get("boat_damaged"):
        await conn.execute(
            "UPDATE stewards SET boat_damaged=1 WHERE id=?",
            (steward["id"],),
        )
        extras.append("船被拍裂，得修")
    if wipe_crop_chance > 0:
        wiped = await _maybe_wipe_outdoor(conn, steward["id"], wipe_crop_chance)
        if wiped:
            extras.append(f"露天份地被冲 {wiped} 块")
    label = config.WEEKLY_TIDE_LABELS[intensity]
    grade = config.WEEKLY_TIDE_GRADES[intensity]
    line = f"{label}（{grade}）冲走 {taken} 工分票（余 {remain}）"
    if extras:
        line += "。" + "；".join(extras)
    await db.add_chronicle("disaster", f"{steward['name']} — {line}", steward["id"], conn=conn)
    return line, taken


async def _wash_fish(conn: aiosqlite.Connection, steward_id: int) -> list[str]:
    conn.row_factory = aiosqlite.Row
    rows = await (
        await conn.execute(
            """
            SELECT item, quantity FROM satchel
            WHERE steward_id=? AND item LIKE 'fish_%' AND quantity>0
            """,
            (steward_id,),
        )
    ).fetchall()
    lost: list[str] = []
    for row in rows:
        qty = int(row["quantity"])
        take = max(1, qty * 30 // 100) if qty >= 2 else 0
        if take <= 0:
            continue
        if await db.take_item(conn, steward_id, row["item"], take):
            lost.append(f"{ITEM_NAMES.get(row['item'], row['item'])}x{take}")
    return lost


async def _maybe_wipe_outdoor(
    conn: aiosqlite.Connection,
    steward_id: int,
    chance: float,
) -> int:
    cur = await conn.execute(
        """
        SELECT id FROM parcels
        WHERE steward_id=? AND greenhouse=0 AND crop IS NOT NULL
        """,
        (steward_id,),
    )
    ids = [r[0] for r in await cur.fetchall()]
    wiped = 0
    for pid in ids:
        if random.random() <= chance:
            await conn.execute(
                """
                UPDATE parcels SET crop=NULL, planted_at=NULL, tended=0,
                    grow_target=0, grow_pace='', fertilized=0, watered=0,
                    harvest_left=0, ready_at=0
                WHERE id=?
                """,
                (pid,),
            )
            wiped += 1
    return wiped


async def _untend_outdoor(conn: aiosqlite.Connection) -> None:
    await conn.execute(
        "UPDATE parcels SET tended=0 WHERE greenhouse=0 AND crop IS NOT NULL",
    )


async def _ensure_flags_table(conn: aiosqlite.Connection) -> None:
    await conn.execute(WORLD_FLAGS_DDL)


async def flag_applied(conn: aiosqlite.Connection, key: str) -> bool:
    await _ensure_flags_table(conn)
    row = await (
        await conn.execute("SELECT 1 FROM world_flags WHERE flag_key=?", (key,))
    ).fetchone()
    return bool(row)


async def _insert_pulse(
    conn: aiosqlite.Connection,
    *,
    effect: str,
    label: str,
    kind: str,
    detail: str,
    duration: int,
) -> None:
    now = db.now()
    await conn.execute(
        """
        INSERT INTO world_pulse (
            pulse_key, label, kind, effect_type, fish_focus, detail, started_at, expires_at
        ) VALUES (?,?,?,?,?,?,?,?)
        """,
        (
            f"{effect}:{now}",
            label,
            kind,
            effect,
            None,
            detail,
            now,
            now + duration,
        ),
    )


def _side_effects(intensity: Intensity, taken: int, tickets: int) -> dict[str, Any]:
    if intensity == "low":
        return {"wash_fish": False, "wreck_boat": False, "wipe_crop_chance": 0.0}
    if intensity == "mid":
        return {
            "wash_fish": taken >= 200,
            "wreck_boat": False,
            "wipe_crop_chance": 0.08 if tickets > config.DISASTER_SAFE else 0.0,
        }
    return {
        "wash_fish": True,
        "wreck_boat": taken >= 4000,
        "wipe_crop_chance": 0.18,
    }


async def apply_weekly_tide(
    conn: aiosqlite.Connection,
    *,
    week_id: str,
    intensity: Intensity,
) -> dict[str, Any]:
    """对全员套一次本周周潮。调用方须保证本周旗尚未打下。"""
    conn.row_factory = aiosqlite.Row
    rows = await (
        await conn.execute("SELECT * FROM stewards WHERE enrolled=1")
    ).fetchall()
    stewards = [dict(r) for r in rows]
    hit = 0
    drained = 0
    for s in stewards:
        tickets = int(s.get("tickets") or 0)
        taken = levy_amount(tickets, intensity)
        if taken <= 0:
            continue
        extras = _side_effects(intensity, taken, tickets)
        line, actual = await _apply_levy(
            conn,
            s,
            taken,
            intensity=intensity,
            **extras,
        )
        if line:
            hit += 1
            drained += actual
    await _untend_outdoor(conn)
    label = config.WEEKLY_TIDE_LABELS[intensity]
    grade = config.WEEKLY_TIDE_GRADES[intensity]
    rate_pct = int(config.WEEKLY_TIDE_RATES[intensity] * 100)
    detail = (
        f"{week_id} 周潮·{label}（{grade}）灌进档口：3万以上才冲，超额收 {rate_pct}%。"
        "风暴窗板能少冲一点。"
        f" 此轮 {hit} 人被冲，合计 {drained} 票入海。"
    )
    if hit:
        await _insert_pulse(
            conn,
            effect="weekly_tide",
            label=f"周潮·{label}",
            kind="bad",
            detail=detail,
            duration=config.WEEKLY_TIDE_DURATION,
        )
        await db.add_chronicle("pulse", f"🌊 全服脉冲·周潮·{label}：{detail}", None, conn=conn)
    await conn.execute(
        """
        INSERT INTO world_flags (flag_key, applied_at, detail) VALUES (?,?,?)
        """,
        (
            week_flag_key(week_id),
            db.now(),
            f"intensity={intensity} hit={hit} drained={drained}",
        ),
    )
    return {
        "week_id": week_id,
        "intensity": intensity,
        "hit": hit,
        "drained": drained,
        "detail": detail,
    }


async def ensure_weekly_tide(
    conn: aiosqlite.Connection | None = None,
    *,
    week_id: str | None = None,
    intensity: Intensity | None = None,
) -> dict[str, Any] | None:
    """幂等：每个东八区自然周最多刮一次。"""
    if conn is None:
        async with db.connect() as owned:
            result = await ensure_weekly_tide(
                owned, week_id=week_id, intensity=intensity
            )
            if result:
                await owned.commit()
            return result
    await _ensure_flags_table(conn)
    wid = week_id or human_week_id()
    if await flag_applied(conn, week_flag_key(wid)):
        return None
    return await apply_weekly_tide(
        conn,
        week_id=wid,
        intensity=intensity or pick_intensity(),
    )


async def recent_hit_line(steward_id: int) -> str | None:
    cutoff = db.now() - config.DISASTER_NOTICE_DAYS * 86400
    async with db.connect() as conn:
        row = await (
            await conn.execute(
                """
                SELECT text FROM chronicle
                WHERE actor_id=? AND action='disaster' AND created_at>=?
                ORDER BY created_at DESC LIMIT 1
                """,
                (steward_id, cutoff),
            )
        ).fetchone()
    if not row:
        return None
    text = row[0]
    if " — " in text:
        text = text.split(" — ", 1)[1]
    return f"天灾：{text}"
