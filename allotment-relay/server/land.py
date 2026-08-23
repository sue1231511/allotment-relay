"""买地 — 起步 3 块，露天无上限；付钱后要开垦一段时间才能种。"""

from __future__ import annotations

from typing import Any

import aiosqlite

from . import config, db, farming


def _offer_index(parcel_count: int) -> int:
    idx = int(parcel_count) - config.START_PARCELS
    return max(0, idx)


def next_outdoor_slot(parcel_count: int) -> int:
    """下一块露天槽号。跳过温室 #99，避免和 shed 抢槽。"""
    n = int(parcel_count) + 1
    if n >= config.GREENHOUSE_SLOT:
        return n + 1
    return n


def next_offer(parcel_count: int) -> dict[str, int]:
    count = int(parcel_count)
    idx = _offer_index(count)
    return {
        "slot": next_outdoor_slot(count),
        "cost": int(config.parcel_expand_cost(idx)),
        "clear_seconds": int(config.parcel_clear_seconds(idx)),
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


def price_table_lines(parcel_count: int | None = None) -> list[str]:
    count = config.START_PARCELS if parcel_count is None else int(parcel_count)
    lines = [
        "价目（露天无上限；第 4 块起按表递推）：",
        "  规律：#4 80票/30分 → #5 120/45 → #6 180/60 → #7 260/90 → #8 360/120 → 之后以此类推",
    ]
    start = max(count, config.START_PARCELS)
    for i in range(6):
        offer = next_offer(start + i)
        lines.append(
            f"  #{offer['slot']}  {offer['cost']}票 · 开垦 {fmt_clear(offer['clear_seconds'])}"
        )
    lines.append(
        "  再往后票价差额每次多 20（+40、+60、+80…）；开垦时间每两档多加 15 分钟。"
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
        f"份地 {count} 块（起步 {config.START_PARCELS} 块，露天无上限；温室 #{config.GREENHOUSE_SLOT} 另计）",
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
    else:
        offer = next_offer(count)
        lines.append(
            f"下一块 #{offer['slot']}：{offer['cost']} 票，开垦 {fmt_clear(offer['clear_seconds'])}"
        )
        lines.append("要买：plot_ops 买地 确认")
    lines.extend(price_table_lines(count))
    return "\n".join(lines)


async def buy(conn: aiosqlite.Connection, steward: dict[str, Any]) -> str:
    count = int(steward.get("parcel_count") or config.START_PARCELS)
    pending = await clearing_slot(conn, steward["id"])
    if pending:
        left = clear_left(pending)
        raise ValueError(
            f"#{pending['slot']} 还在开垦（{farming.format_grow_eta(left)}）。"
            "开好再买下一块。"
        )
    offer = next_offer(count)
    cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (steward["id"],))
    tickets = (await cur.fetchone())[0]
    if tickets < offer["cost"]:
        raise ValueError(
            f"买 #{offer['slot']} 需要 {offer['cost']} 票，你只有 {tickets} 票。"
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
        f"现 {new_count} 块（露天无上限）。"
        f"开垦 {fmt_clear(offer['clear_seconds'])}，开好才能 sow。"
    )


def sheet_note(steward: dict[str, Any], parcels: list[dict[str, Any]]) -> str:
    count = int(steward.get("parcel_count") or config.START_PARCELS)
    bits = [f"份地: {count} 块（无上限）"]
    clearing = [p for p in parcels if clear_left(p) > 0]
    if clearing:
        p = clearing[0]
        bits.append(f"#{p['slot']} 开垦中 {farming.format_grow_eta(clear_left(p))}")
    else:
        offer = next_offer(count)
        bits.append(
            f"下一块 #{offer['slot']} {offer['cost']}票 · 开垦{fmt_clear(offer['clear_seconds'])}"
            " → plot_ops 买地"
        )
    return " · ".join(bits)
