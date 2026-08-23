"""买地 / 买园 — 起步各 3 块，露天无上限；付钱后要开垦一段时间才能种。"""

from __future__ import annotations

from typing import Any

import aiosqlite

from . import config, db, farming


def start_count(orchard: bool) -> int:
    return config.START_ORCHARDS if orchard else config.START_PARCELS


def count_of(steward: dict[str, Any], orchard: bool) -> int:
    if orchard:
        return int(steward.get("orchard_count") or config.START_ORCHARDS)
    return int(steward.get("parcel_count") or config.START_PARCELS)


def is_orchard(plot: dict[str, Any] | None) -> bool:
    return bool(plot and plot.get("orchard"))


def slot_label(plot: dict[str, Any] | int, orchard: int | bool = 0) -> str:
    if isinstance(plot, dict):
        slot = plot.get("slot", "?")
        if plot.get("greenhouse"):
            return f"#{slot}"
        if plot.get("orchard"):
            return f"园{slot}"
        return f"#{slot}"
    if orchard:
        return f"园{plot}"
    return f"#{plot}"


def parse_slot_ref(token: str, *, orchard_ctx: bool = False) -> tuple[int, int]:
    """解析地块记号。园3 / orchard3 / o3 → (3, 1)；纯数字在果园语境下也是树位。"""
    raw = (token or "").strip().rstrip(";,").lstrip("#")
    low = raw.lower()
    if low.startswith("园"):
        rest = raw[1:].strip() or "0"
        return _as_slot(rest, "树位"), 1
    if low.startswith("orchard"):
        rest = raw[7:].lstrip(" _-") or "0"
        return _as_slot(rest, "树位"), 1
    if low.startswith("grove"):
        rest = raw[5:].lstrip(" _-") or "0"
        return _as_slot(rest, "树位"), 1
    if len(low) >= 2 and low[0] == "o" and low[1:].isdigit():
        return int(low[1:]), 1
    return _as_slot(raw, "地块编号"), (1 if orchard_ctx else 0)


def _as_slot(token: str, label: str) -> int:
    cleaned = token.strip().lstrip("#")
    if cleaned.lower().startswith("x") and len(cleaned) > 1:
        cleaned = cleaned[1:]
    try:
        n = int(cleaned)
    except ValueError as exc:
        raise ValueError(f"{label}须为整数或园N，收到: {token!r}") from exc
    if n <= 0:
        raise ValueError(f"{label}须为正整数")
    return n


def missing_slot_msg(slot: int, orchard: int | bool) -> str:
    if orchard:
        return f"没有果园 {slot_label(slot, 1)}。plot_ops 买园 看价钱；买园 确认 开垦"
    return f"没有份地 #{slot}"


async def fetch_plot(
    conn: aiosqlite.Connection, steward_id: int, slot: int, orchard: int | bool
) -> dict[str, Any]:
    conn.row_factory = aiosqlite.Row
    row = await (await conn.execute(
        """
        SELECT * FROM parcels
        WHERE steward_id=? AND slot=? AND COALESCE(orchard,0)=?
        """,
        (steward_id, int(slot), 1 if orchard else 0),
    )).fetchone()
    return dict(row) if row else {}


def _offer_index(count: int, orchard: bool) -> int:
    idx = int(count) - start_count(orchard)
    return max(0, idx)


def next_slot(count: int, *, orchard: bool = False) -> int:
    n = int(count) + 1
    if not orchard and n >= config.GREENHOUSE_SLOT:
        return n + 1
    return n


def next_outdoor_slot(parcel_count: int) -> int:
    return next_slot(parcel_count, orchard=False)


def next_offer(count: int, *, orchard: bool = False) -> dict[str, int]:
    idx = _offer_index(count, orchard)
    return {
        "slot": next_slot(count, orchard=orchard),
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
        raise ValueError("没有这块地")
    left = clear_left(plot)
    if left <= 0:
        return
    raise ValueError(
        f"{slot_label(plot)} 还在开垦（{farming.format_grow_eta(left)}），开好才能动土"
    )


def price_table_lines(count: int | None = None, *, orchard: bool = False) -> list[str]:
    start = start_count(orchard)
    have = start if count is None else int(count)
    noun = "树位" if orchard else "块"
    mark = "园" if orchard else "#"
    lines = [
        f"价目（{'果园' if orchard else '露天份地'}无上限；第 {start + 1} {noun}起按表递推）：",
        f"  规律：{mark}{start + 1} 80票/30分 → {mark}{start + 2} 120/45 → "
        f"{mark}{start + 3} 180/60 → {mark}{start + 4} 260/90 → {mark}{start + 5} 360/120 → 之后以此类推",
    ]
    base = max(have, start)
    for i in range(6):
        offer = next_offer(base + i, orchard=orchard)
        lines.append(
            f"  {slot_label(offer['slot'], 1 if orchard else 0)}  "
            f"{offer['cost']}票 · 开垦 {fmt_clear(offer['clear_seconds'])}"
        )
    lines.append(
        "  再往后票价差额每次多 20（+40、+60、+80…）；开垦时间每两档多加 15 分钟。"
    )
    return lines


async def settle(conn: aiosqlite.Connection, steward_id: int) -> list[str]:
    now = db.now()
    conn.row_factory = aiosqlite.Row
    cur = await conn.execute(
        """
        SELECT slot, COALESCE(orchard,0) AS orchard FROM parcels
        WHERE steward_id=? AND ready_at>0 AND ready_at<=?
        ORDER BY orchard, slot
        """,
        (steward_id, now),
    )
    rows = [dict(r) for r in await cur.fetchall()]
    if not rows:
        return []
    await conn.execute(
        """
        UPDATE parcels SET ready_at=0
        WHERE steward_id=? AND ready_at>0 AND ready_at<=?
        """,
        (steward_id, now),
    )
    return [
        f"{slot_label(r['slot'], r['orchard'])} 开垦完成，可以 sow 了"
        for r in rows
    ]


async def clearing_slot(
    conn: aiosqlite.Connection, steward_id: int, *, orchard: bool = False
) -> dict[str, Any] | None:
    conn.row_factory = aiosqlite.Row
    row = await (await conn.execute(
        """
        SELECT * FROM parcels
        WHERE steward_id=? AND ready_at>? AND COALESCE(greenhouse,0)=0
          AND COALESCE(orchard,0)=?
        ORDER BY slot LIMIT 1
        """,
        (steward_id, db.now(), 1 if orchard else 0),
    )).fetchone()
    return dict(row) if row else None


def _kind_parcels(parcels: list[dict[str, Any]], orchard: bool) -> list[dict[str, Any]]:
    return [p for p in parcels if bool(p.get("orchard")) == orchard and not p.get("greenhouse")]


async def status_text(
    steward: dict[str, Any],
    parcels: list[dict[str, Any]] | None = None,
    *,
    orchard: bool = False,
) -> str:
    count = count_of(steward, orchard)
    start = start_count(orchard)
    if orchard:
        head = f"果园 {count} 个树位（起步 {start}，无上限；只种果树）"
        buy_cmd = "plot_ops 买园 确认"
        next_word = "下一树位"
    else:
        head = (
            f"份地 {count} 块（起步 {start} 块，露天无上限；温室 #{config.GREENHOUSE_SLOT} 另计；"
            "份地不种果树）"
        )
        buy_cmd = "plot_ops 买地 确认"
        next_word = "下一块"
    lines = [head]
    if parcels is None:
        parcels = await db.get_parcels(steward["id"], orchard=1 if orchard else 0)
    kind = _kind_parcels(parcels, orchard)
    clearing = [p for p in kind if clear_left(p) > 0]
    if clearing:
        for p in clearing:
            left = clear_left(p)
            lines.append(
                f"{slot_label(p)} 开垦中，还剩 {farming.format_grow_eta(left)}"
            )
        lines.append("上一块开好才能再买。")
    else:
        offer = next_offer(count, orchard=orchard)
        lines.append(
            f"{next_word} {slot_label(offer['slot'], 1 if orchard else 0)}："
            f"{offer['cost']} 票，开垦 {fmt_clear(offer['clear_seconds'])}"
        )
        lines.append(f"要买：{buy_cmd}")
    lines.extend(price_table_lines(count, orchard=orchard))
    if orchard:
        lines.append("种树：plot_ops 果园 sow 1 芒果 · 或 sow 园1 芒果。份地 sow 只收蔬菜。")
    else:
        lines.append("种菜：plot_ops sow 1 甘蓝。果树走果园。")
    return "\n".join(lines)


async def buy(conn: aiosqlite.Connection, steward: dict[str, Any], *, orchard: bool = False) -> str:
    count = count_of(steward, orchard)
    pending = await clearing_slot(conn, steward["id"], orchard=orchard)
    if pending:
        left = clear_left(pending)
        raise ValueError(
            f"{slot_label(pending)} 还在开垦（{farming.format_grow_eta(left)}）。"
            "开好再买下一块。"
        )
    offer = next_offer(count, orchard=orchard)
    cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (steward["id"],))
    tickets = (await cur.fetchone())[0]
    if tickets < offer["cost"]:
        raise ValueError(
            f"买 {slot_label(offer['slot'], 1 if orchard else 0)} 需要 {offer['cost']} 票，"
            f"你只有 {tickets} 票。开垦要 {fmt_clear(offer['clear_seconds'])}。"
        )
    new_count = count + 1
    ready_at = db.now() + offer["clear_seconds"]
    col = "orchard_count" if orchard else "parcel_count"
    await conn.execute(
        f"UPDATE stewards SET tickets=tickets-?, {col}=? WHERE id=?",
        (offer["cost"], new_count, steward["id"]),
    )
    await conn.execute(
        """
        INSERT INTO parcels (steward_id, slot, orchard, crop, planted_at, tended, ready_at)
        VALUES (?, ?, ?, NULL, NULL, 0, ?)
        ON CONFLICT(steward_id, slot, orchard) DO UPDATE SET ready_at=excluded.ready_at
        """,
        (steward["id"], offer["slot"], 1 if orchard else 0, ready_at),
    )
    steward[col] = new_count
    kind = "树位" if orchard else "块"
    sow_hint = "果园 sow" if orchard else "sow"
    return (
        f"买下 {slot_label(offer['slot'], 1 if orchard else 0)}（-{offer['cost']} 票）。"
        f"现 {new_count} {kind}（无上限）。"
        f"开垦 {fmt_clear(offer['clear_seconds'])}，开好才能 {sow_hint}。"
    )


def sheet_note(
    steward: dict[str, Any],
    parcels: list[dict[str, Any]],
    *,
    orchard: bool = False,
) -> str:
    count = count_of(steward, orchard)
    kind = _kind_parcels(parcels, orchard)
    if orchard:
        bits = [f"果园: {count} 树位（无上限）"]
        buy_cmd = "plot_ops 买园"
    else:
        bits = [f"份地: {count} 块（无上限）"]
        buy_cmd = "plot_ops 买地"
    clearing = [p for p in kind if clear_left(p) > 0]
    if clearing:
        p = clearing[0]
        bits.append(f"{slot_label(p)} 开垦中 {farming.format_grow_eta(clear_left(p))}")
    else:
        offer = next_offer(count, orchard=orchard)
        bits.append(
            f"下一块 {slot_label(offer['slot'], 1 if orchard else 0)} "
            f"{offer['cost']}票 · 开垦{fmt_clear(offer['clear_seconds'])}"
            f" → {buy_cmd}"
        )
    return " · ".join(bits)
