"""渔具 tier 数值升级 — 鱼饵 / 鱼竿 / 渔网。"""

from __future__ import annotations

from typing import Any

import aiosqlite

from . import db, flavor
from .catalog import GEAR_TIERS, ITEM_NAMES
from .game import require_steward


def _tier_meta(kind: str, tier: int) -> dict[str, Any]:
    rows = GEAR_TIERS[kind]
    for row in rows:
        if row["tier"] == tier:
            return row
    return rows[-1]


def _next_tier(kind: str, current: int) -> dict[str, Any] | None:
    rows = GEAR_TIERS[kind]
    for row in rows:
        if row["tier"] == current + 1:
            return row
    return None


async def get_gear(conn: aiosqlite.Connection, steward_id: int) -> dict[str, int]:
    conn.row_factory = aiosqlite.Row
    row = await (await conn.execute(
        "SELECT bait_tier, rod_tier, net_tier FROM steward_gear WHERE steward_id=?",
        (steward_id,),
    )).fetchone()
    if row:
        return {"bait": row["bait_tier"], "rod": row["rod_tier"], "net": row["net_tier"]}

    # 兼容旧版 tool_net_* 道具
    stock = await (await conn.execute(
        "SELECT item FROM satchel WHERE steward_id=? AND quantity>0 AND item LIKE 'tool_net_%'",
        (steward_id,),
    )).fetchall()
    items = {r[0] for r in stock}
    net_tier = 0
    if "tool_net_fine" in items:
        net_tier = 2
    elif "tool_net_basic" in items:
        net_tier = 1
    gear = {"bait": 1, "rod": 0, "net": net_tier}
    await conn.execute(
        "INSERT INTO steward_gear (steward_id, bait_tier, rod_tier, net_tier) VALUES (?,?,?,?)",
        (steward_id, gear["bait"], gear["rod"], gear["net"]),
    )
    return gear


async def get_stats(conn: aiosqlite.Connection, steward_id: int) -> dict[str, dict[str, Any]]:
    gear = await get_gear(conn, steward_id)
    return {
        kind: _tier_meta(kind, gear[kind])
        for kind in ("bait", "rod", "net")
    }


def combined_fish_bonus(
    *,
    bait: dict[str, Any],
    rod: dict[str, Any] | None = None,
    net: dict[str, Any] | None = None,
) -> tuple[float, int, float, int]:
    """Return (catch_bonus, rarity_cap_bonus, empty_reduce, energy)."""
    catch = bait["catch"]
    rarity = bait["rarity"]
    empty = bait["empty"]
    energy = 0
    if rod:
        catch += rod["catch"]
        rarity += rod["rarity"]
        empty += rod["empty"]
        energy = rod["energy"]
    if net:
        catch += net["catch"]
        rarity += net["rarity"]
        empty += net["empty"]
        energy = net["energy"]
    return catch, rarity, empty, energy


def fish_catch_payout(stats: dict[str, dict[str, Any]], *, mode: str) -> tuple[float, int]:
    """Return (sell value multiplier, flat ticket bonus) for a catch."""
    if mode == "cast":
        bait, rod = stats["bait"], stats["rod"]
        mult = 1.0 + bait["catch"] * 0.65 + rod["catch"] * 1.05
        bonus = bait["tier"] + rod["tier"] * 2
        return mult, bonus
    net = stats["net"]
    mult = 1.0 + net["catch"] * 1.25 + net["tier"] * 0.05
    bonus = net["tier"] * 2
    return mult, bonus


def _format_tier(kind: str, tier: int) -> str:
    meta = _tier_meta(kind, tier)
    nxt = _next_tier(kind, tier)
    line = (
        f"  {kind} T{tier} {meta['name']} — "
        f"渔获+{int(meta['catch']*100)}% 空杆-{int(meta['empty']*100)}% "
        f"稀有+{meta['rarity']}"
    )
    if kind in ("rod", "net") and meta.get("energy"):
        line += f" 精力{meta['energy']}"
    if kind == "net" and meta.get("tier"):
        line += f" 网到+{meta['tier']}票（不按鱼价抽成）"
    elif meta.get("catch"):
        line += f" 鱼价增幅"
    if nxt:
        need = ", ".join(
            f"{ITEM_NAMES.get(k, k)}x{v}" for k, v in nxt.get("need", {}).items()
        )
        extra = f" 下一级T{nxt['tier']} {nxt['name']}（{nxt['tickets']}票"
        if need:
            extra += f" + {need}"
        extra += "）"
        line += extra
    else:
        line += " [满级]"
    return line


async def gear_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    parts = command.strip().split()
    verb = parts[0].lower() if parts else "status"

    if verb == "status":
        async with db.connect() as conn:
            gear = await get_gear(conn, s["id"])
            await conn.commit()
        lines = [
            "渔具 tier（数值）：",
            _format_tier("bait", gear["bait"]),
            _format_tier("rod", gear["rod"]),
            _format_tier("net", gear["net"]),
            "upgrade bait|rod|net — 升一级",
            "钓鱼: tide_ops cast（竿+饵） / tide_ops net（网 tier）",
        ]
        return "\n".join(lines)

    if verb == "upgrade" and len(parts) >= 2:
        kind = parts[1].lower()
        if kind not in GEAR_TIERS:
            raise ValueError("可升级: bait, rod, net")
        async with db.connect() as conn:
            gear = await get_gear(conn, s["id"])
            current = gear[kind]
            nxt = _next_tier(kind, current)
            if not nxt:
                return f"{kind} 已满级 T{current}"
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < nxt["tickets"]:
                raise ValueError(f"需要 {nxt['tickets']} 票")
            for item, qty in nxt.get("need", {}).items():
                if not await db.take_item(conn, s["id"], item, qty):
                    raise ValueError(f"缺少 {ITEM_NAMES.get(item, item)} x{qty}")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (nxt["tickets"], s["id"]),
            )
            col = f"{kind}_tier"
            await conn.execute(
                f"UPDATE steward_gear SET {col}=? WHERE steward_id=?",
                (nxt["tier"], s["id"]),
            )
            await conn.commit()
        msg = (
            f"{kind} 升至 T{nxt['tier']} {nxt['name']} — "
            f"渔获+{int(nxt['catch']*100)}% 空杆-{int(nxt['empty']*100)}%"
        )
        return msg + flavor.maybe_suffix(["渔具升级，潮线都客气三分", "数值到位，鱼自己上岸"])

    raise ValueError(f"未知 gear 指令: {command}（status/upgrade）")
