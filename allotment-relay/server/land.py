"""买地 — 起步 3 块，最多 8 块；付钱后要开垦一段时间才能种。"""

from __future__ import annotations

from typing import Any

import aiosqlite

from . import config, db, farming


def _offer_index(parcel_count: int) -> int:
    idx = int(parcel_count) - config.START_PARCELS
    return max(0, idx)


def next_offer(parcel_count: int) -> dict[str, int] | None:
    count = int(parcel_count)
    if count >= config.MAX_PARCELS:
        return None
    idx = min(_offer_index(count), len(config.PARCEL_EXPAND_COSTS) - 1)
    clear_idx = min(idx, len(config.PARCEL_CLEAR_SECONDS) - 1)
    return {
        "slot": count + 1,
        "cost": int(config.PARCEL_EXPAND_COSTS[idx]),
        "clear_seconds": int(config.PARCEL_CLEAR_SECONDS[clear_idx]),
    }


def fmt_clear(seconds: int) -> str:
    seconds = max(0, int(seconds))
    if seconds <= 0:
        return "马上"
    if seconds % 3600 == 0:
        return f"{seconds // 3600}小时"
    if seconds % 60 == 0:
        return f"{seconds // 60}分钟"
    return farming.format_grow_eta(seconds)


def clear_left(plot: dict[str, Any], now: int | None = None) -> int:
    ready_at = int(plot.get("ready_at") or 0)
    if ready_at <= 0:
        return 0
    now = db.now() if now is None else int(now)
    return max(0, ready_at - now)


def assert_ready(plot: dict[str, Any]) -> None:
    if not plot:
        raise ValueError("没有这块份地")
    left = clear_left(plot)
    if left <= 0:
        return
    slot = plot.get("slot", "?")
    raise ValueError(
        f"#{slot} 还在开垦（{farming.format_grow_eta(left)}），开好才能动土"
    )


def price_table_lines() -> list[str]:
    lines = ["价目（第 4～8 块）："]
    n = min(len(config.PARCEL_EXPAND_COSTS), len(config.PARCEL_CLEAR_SECONDS))
    for i in range(n):
        slot = config.START_PARCELS + 1 + i
        lines.append(
            f"  #{slot}  {config.PARCEL_EXPAND_COSTS[i]}票 · 开垦 {fmt_clear(config.PARCEL_CLEAR_SECONDS[i])}"
        )
    return lines


async def settle(conn: aiosqlite.Connection, steward_id: int) -> list[str]:
    now = db.now()
    cur = await conn.execute(
        """
        SELECT slot FROM parcels
        WHERE steward_id=? AND ready_at>0 AND ready_at<=?
        ORDER BY slot
        """,
        (steward_id, now),
    )
    slots = [int(r[0]) for r in await cur.fetchall()]
    if not slots:
        return []
    await conn.execute(
        """
        UPDATE parcels SET ready_at=0
        WHERE steward_id=? AND ready_at>0 AND ready_at<=?
        """,
        (steward_id, now),
    )
    return [f"#{n} 开垦完成，可以 sow 了" for n in slots]


async def clearing_slot(conn: aiosqlite.Connection, steward_id: int) -> dict[str, Any] | None:
    conn.row_factory = aiosqlite.Row
    row = await (await conn.execute(
        """
        SELECT * FROM parcels
        WHERE steward_id=? AND ready_at>? AND COALESCE(greenhouse,0)=0
        ORDER BY slot LIMIT 1
        """,
        (steward_id, db.now()),
    )).fetchone()
    return dict(row) if row else None


async def status_text(steward: dict[str, Any], parcels: list[dict[str, Any]] | None = None) -> str:
    count = int(steward.get("parcel_count") or config.START_PARCELS)
    lines = [
        f"份地 {count}/{config.MAX_PARCELS}（起步 {config.START_PARCELS} 块，最多 {config.MAX_PARCELS} 块；温室 #99 另计）",
    ]
    if parcels is None:
        parcels = await db.get_parcels(steward["id"])
    clearing = [p for p in parcels if clear_left(p) > 0]
    if clearing:
        for p in clearing:
            left = clear_left(p)
            lines.append(
                f"#{p['slot']} 开垦中，还剩 {farming.format_grow_eta(left)}"
            )
        lines.append("上一块开好才能再买。")
    offer = next_offer(count)
    if offer and not clearing:
        lines.append(
            f"下一块 #{offer['slot']}：{offer['cost']} 票，开垦 {fmt_clear(offer['clear_seconds'])}"
        )
        lines.append("要买：plot_ops 买地 确认")
    elif not offer:
        lines.append("已经买满，没有下一块了。")
    lines.extend(price_table_lines())
    return "\n".join(lines)


async def buy(conn: aiosqlite.Connection, steward: dict[str, Any]) -> str:
    count = int(steward.get("parcel_count") or config.START_PARCELS)
    if count >= config.MAX_PARCELS:
        raise ValueError(f"份地已达上限 {config.MAX_PARCELS} 块")
    pending = await clearing_slot(conn, steward["id"])
    if pending:
        left = clear_left(pending)
        raise ValueError(
            f"#{pending['slot']} 还在开垦（{farming.format_grow_eta(left)}）。"
            "开好再买下一块。"
        )
    offer = next_offer(count)
    if not offer:
        raise ValueError(f"份地已达上限 {config.MAX_PARCELS} 块")
    cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (steward["id"],))
    tickets = (await cur.fetchone())[0]
    if tickets < offer["cost"]:
        raise ValueError(
            f"买第 {offer['slot']} 块需要 {offer['cost']} 票，你只有 {tickets} 票。"
            f"开垦要 {fmt_clear(offer['clear_seconds'])}。"
        )
    new_count = count + 1
    ready_at = db.now() + offer["clear_seconds"]
    await conn.execute(
        "UPDATE stewards SET tickets=tickets-?, parcel_count=? WHERE id=?",
        (offer["cost"], new_count, steward["id"]),
    )
    await conn.execute(
        """
        INSERT INTO parcels (steward_id, slot, crop, planted_at, tended, ready_at)
        VALUES (?, ?, NULL, NULL, 0, ?)
        ON CONFLICT(steward_id, slot) DO UPDATE SET ready_at=excluded.ready_at
        """,
        (steward["id"], offer["slot"], ready_at),
    )
    steward["parcel_count"] = new_count
    return (
        f"买下 #{offer['slot']}（-{offer['cost']} 票）。"
        f"现 {new_count}/{config.MAX_PARCELS} 块。"
        f"开垦 {fmt_clear(offer['clear_seconds'])}，开好才能 sow。"
    )


def sheet_note(steward: dict[str, Any], parcels: list[dict[str, Any]]) -> str:
    count = int(steward.get("parcel_count") or config.START_PARCELS)
    bits = [f"份地: {count}/{config.MAX_PARCELS} 块"]
    clearing = [p for p in parcels if clear_left(p) > 0]
    if clearing:
        p = clearing[0]
        bits.append(f"#{p['slot']} 开垦中 {farming.format_grow_eta(clear_left(p))}")
    else:
        offer = next_offer(count)
        if offer:
            bits.append(
                f"下一块 #{offer['slot']} {offer['cost']}票 · 开垦{fmt_clear(offer['clear_seconds'])}"
                " → plot_ops 买地"
            )
    return " · ".join(bits)
