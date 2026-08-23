"""天灾：黑潮一次性削超额工分，暴潮脉冲继续冲口袋太鼓的人。"""

from __future__ import annotations

from typing import Any

import aiosqlite

from . import config, db
from .catalog import ITEM_NAMES


WORLD_FLAGS_DDL = """
CREATE TABLE IF NOT EXISTS world_flags (
    flag_key TEXT PRIMARY KEY,
    applied_at INTEGER NOT NULL,
    detail TEXT NOT NULL DEFAULT ''
)
"""


def levy_amount(tickets: int, *, bands: tuple[tuple[int, int | None, float], ...] | None = None) -> int:
    """分段征收。永远不会把人收到安全线以下。"""
    safe = int(bands[0][0]) if bands else config.WEALTH_SAFE
    if tickets <= safe:
        return 0
    taken = 0
    for lo, hi, rate in (bands or config.WEALTH_LEVY_BANDS):
        if tickets <= lo:
            break
        slice_hi = tickets if hi is None else min(tickets, hi)
        if slice_hi > lo:
            taken += int((slice_hi - lo) * rate)
    return min(max(0, taken), max(0, tickets - safe))


def surge_levy_amount(tickets: int) -> int:
    if tickets <= config.SURGE_SAFE:
        return 0
    taken = int((tickets - config.SURGE_SAFE) * config.SURGE_RATE)
    return min(taken, tickets - config.SURGE_SAFE)


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
    kind: str,
    wash_fish: bool,
    wreck_boat: bool,
    wipe_crop_chance: float,
) -> tuple[str | None, int]:
    if taken <= 0:
        return None, 0
    if await _has_storm_shutter(conn, steward["id"]):
        taken = max(1, int(taken * config.STORM_SHUTTER_LEVY_MULT))
    have = int(steward.get("tickets") or 0)
    floor = config.WEALTH_SAFE if kind == "black_tide" else config.SURGE_SAFE
    taken = min(taken, max(0, have - floor))
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
    if kind == "black_tide":
        line = f"秋分黑潮冲走 {taken} 工分票（余 {remain}）"
    else:
        line = f"暴潮又卷走超额 {taken} 票（余 {remain}）"
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
    import random

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


async def apply_black_tide(conn: aiosqlite.Connection) -> dict[str, Any]:
    """对全员套一次秋分黑潮。调用方须保证尚未打过旗。"""
    conn.row_factory = aiosqlite.Row
    rows = await (
        await conn.execute("SELECT * FROM stewards WHERE enrolled=1")
    ).fetchall()
    stewards = [dict(r) for r in rows]
    hit = 0
    drained = 0
    for s in stewards:
        taken = levy_amount(int(s.get("tickets") or 0))
        if taken <= 0:
            continue
        line, actual = await _apply_levy(
            conn,
            s,
            taken,
            kind="black_tide",
            wash_fish=taken >= 80,
            wreck_boat=taken >= 2500,
            wipe_crop_chance=0.18 if int(s.get("tickets") or 0) > 8000 else 0.0,
        )
        if line:
            hit += 1
            drained += actual
    await _untend_outdoor(conn)
    detail = (
        "秋分黑潮灌进档口：2000 票以下没事；口袋越鼓冲得越狠。"
        "风暴窗板能少冲一点。之后若再来暴潮脉冲，8000 以上还会被卷。"
        f" 此轮 {hit} 人被冲，合计 {drained} 票入海。"
    )
    if hit:
        await _insert_pulse(
            conn,
            effect="black_tide",
            label="秋分黑潮",
            kind="bad",
            detail=detail,
            duration=config.BLACK_TIDE_DURATION,
        )
        await db.add_chronicle("pulse", f"🌊 全服脉冲·秋分黑潮：{detail}", None, conn=conn)
    await conn.execute(
        """
        INSERT INTO world_flags (flag_key, applied_at, detail) VALUES (?,?,?)
        """,
        (config.BLACK_TIDE_FLAG, db.now(), f"hit={hit} drained={drained}"),
    )
    return {"hit": hit, "drained": drained, "detail": detail}


async def ensure_black_tide(conn: aiosqlite.Connection | None = None) -> dict[str, Any] | None:
    """幂等：部署后只刮一次。"""
    if conn is None:
        async with db.connect() as owned:
            result = await ensure_black_tide(owned)
            if result:
                await owned.commit()
            return result
    await _ensure_flags_table(conn)
    if await flag_applied(conn, config.BLACK_TIDE_FLAG):
        return None
    return await apply_black_tide(conn)


async def apply_surge_levy(conn: aiosqlite.Connection) -> dict[str, Any]:
    """暴潮脉冲：只冲 8000 以上的超额。"""
    conn.row_factory = aiosqlite.Row
    rows = await (
        await conn.execute("SELECT * FROM stewards WHERE enrolled=1")
    ).fetchall()
    hit = 0
    drained = 0
    for raw in rows:
        s = dict(raw)
        taken = surge_levy_amount(int(s.get("tickets") or 0))
        if taken <= 0:
            continue
        line, actual = await _apply_levy(
            conn,
            s,
            taken,
            kind="surge",
            wash_fish=False,
            wreck_boat=False,
            wipe_crop_chance=0.0,
        )
        if line:
            hit += 1
            drained += actual
    await _untend_outdoor(conn)
    return {"hit": hit, "drained": drained}


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
