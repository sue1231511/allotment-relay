"""食材品质、鲜度（腐败）、鱼重 — 第一批玩法扩展。"""
from __future__ import annotations

import json
import random
from typing import Any

from . import db
from .catalog import CROPS, ITEM_PRICES, SEA_CATCH, item_label

# ── 作物品质 ──
CROP_QUALITY_KEYS = (
    "plain",
    "tender",
    "plump",
    "flavor",
    "bugbit",
    "twisted",
    "overripe",
)
CROP_QUALITY_LABEL = {
    "plain": "普通",
    "tender": "鲜嫩",
    "plump": "饱满",
    "flavor": "风味",
    "bugbit": "虫咬",
    "twisted": "畸形",
    "overripe": "过熟",
}
CROP_QUALITY_MULT = {
    "plain": 1.0,
    "tender": 1.08,
    "plump": 1.12,
    "flavor": 1.18,
    "bugbit": 0.82,
    "twisted": 0.75,
    "overripe": 0.65,
}

# ── 鱼状态 + 重量 ──
FISH_STATE_KEYS = ("fresh", "firm", "bruised", "old", "roe", "parasite", "odd")
FISH_STATE_LABEL = {
    "fresh": "极鲜",
    "firm": "完整",
    "bruised": "擦伤",
    "old": "老鱼",
    "roe": "带卵",
    "parasite": "寄生虫",
    "odd": "异常色",
}
FISH_STATE_MULT = {
    "fresh": 1.15,
    "firm": 1.05,
    "bruised": 0.92,
    "old": 0.78,
    "roe": 1.22,
    "parasite": 0.55,
    "odd": 1.08,
}

SPOIL_HOURS_SATCHEL = {
    "fish": 36,
    "crop": 72,
    "meat": 28,
    "dairy": 24,
    "egg": 48,
    "meal": 18,
    "dish": 20,
}
SPOIL_LOC_MULT = {
    "satchel": 1.0,
    "cabinet": 1.8,
    "fridge": 3.5,
}

def _item_spoil_class(item: str) -> str | None:
    if not item:
        return None
    if item.startswith("dried_") or item == "pickles" or item.startswith("proc_"):
        return None
    if item.startswith("fish_"):
        return "fish"
    if item.startswith("crop_"):
        ck = item[5:]
        if ck in CROPS and ("fiber" in CROPS[ck].get("tags", ()) or ck in ("cotton", "hemp")):
            return None
        return "crop"
    if item in ("meat_rabbit", "meat_pork"):
        return "meat"
    if item in ("egg", "duck_egg"):
        return "egg"
    if item in ("milk", "goat_milk"):
        return "dairy"
    if item.startswith("meal_") or item.startswith("dish_"):
        return "meal"
    return None


def is_trackable(item: str) -> bool:
    return _item_spoil_class(item) is not None or item.startswith("fish_")


def roll_crop_quality(plot: dict[str, Any]) -> str:
    weights = {
        "plain": 42,
        "tender": 18,
        "plump": 14,
        "flavor": 8,
        "bugbit": 10,
        "twisted": 5,
        "overripe": 3,
    }
    if plot.get("watered"):
        weights["tender"] += 4
        weights["plump"] += 3
    if plot.get("tended"):
        weights["flavor"] += 3
        weights["bugbit"] -= 2
    if plot.get("fertilized"):
        weights["plump"] += 4
    if plot.get("greenhouse"):
        weights["overripe"] -= 2
    fert = int(plot.get("soil_fertility") or 70)
    if fert >= 85:
        weights["plump"] += 3
        weights["twisted"] -= 1
    elif fert < 40:
        weights["twisted"] += 4
        weights["bugbit"] += 3
    if plot.get("pest_key"):
        weights["bugbit"] += 5
        weights["plain"] += 2
    from . import seed_lineage as seed_lineage_mod
    seed_lineage_mod.apply_quality_bias(weights, plot)
    keys = list(weights.keys())
    w = [max(1, weights[k]) for k in keys]
    return random.choices(keys, weights=w)[0]


def roll_fish_state(species: str) -> str:
    meta = SEA_CATCH.get(species) or {}
    rarity = int(meta.get("rarity") or 1)
    weights = {
        "fresh": 22 + rarity,
        "firm": 35,
        "bruised": 18,
        "old": 10,
        "roe": 4 + max(0, 3 - rarity),
        "parasite": 3,
        "odd": 2 + rarity // 2,
    }
    keys = list(weights.keys())
    w = [max(1, weights[k]) for k in keys]
    return random.choices(keys, weights=w)[0]


def roll_fish_weight_kg(species: str) -> float:
    meta = SEA_CATCH.get(species) or {}
    base = 0.35 + 0.12 * int(meta.get("rarity") or 1)
    spread = 0.25 + 0.08 * int(meta.get("rarity") or 1)
    kg = max(0.05, random.gauss(base, spread))
    if species in ("tuna", "swordfish", "oarfish", "kingcrab"):
        kg = max(kg, random.uniform(3.0, 22.0))
    elif species in ("lobster", "grouper", "wolfeel"):
        kg = max(kg, random.uniform(0.8, 6.5))
    return round(kg, 1)


def _spoil_seconds(item: str, loc: str) -> int:
    kind = _item_spoil_class(item)
    if not kind:
        return 0
    hours = SPOIL_HOURS_SATCHEL.get(kind, 48)
    mult = SPOIL_LOC_MULT.get(loc, 1.0)
    return int(hours * 3600 * mult)


async def ensure_trait_tables(conn) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS item_trait_batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            steward_id INTEGER NOT NULL,
            loc TEXT NOT NULL DEFAULT 'satchel',
            item TEXT NOT NULL,
            qty INTEGER NOT NULL,
            quality TEXT NOT NULL DEFAULT '',
            weight_milli INTEGER NOT NULL DEFAULT 0,
            spoil_at INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_trait_batches_steward "
        "ON item_trait_batches(steward_id, loc, item, id)"
    )


async def register_gain(
    conn,
    steward_id: int,
    item: str,
    qty: int,
    *,
    loc: str = "satchel",
    quality: str = "",
    weight_kg: float = 0.0,
) -> None:
    if qty <= 0:
        return
    await ensure_trait_tables(conn)
    spoil_at = 0
    sec = _spoil_seconds(item, loc)
    if sec > 0:
        spoil_at = db.now() + sec
    wmilli = int(round(weight_kg * 1000)) if weight_kg else 0
    await conn.execute(
        """
        INSERT INTO item_trait_batches
        (steward_id, loc, item, qty, quality, weight_milli, spoil_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (steward_id, loc, item, qty, quality or "", wmilli, spoil_at),
    )


async def grant_satchel(
    conn,
    steward_id: int,
    item: str,
    qty: int,
    *,
    quality: str = "",
    weight_kg: float = 0.0,
) -> None:
    await db.add_item(conn, steward_id, item, qty)
    if quality or weight_kg or is_trackable(item):
        if item.startswith("fish_") and not quality:
            quality = roll_fish_state(item[5:])
        if item.startswith("crop_") and not quality:
            quality = "plain"
        if item.startswith("fish_") and weight_kg <= 0:
            weight_kg = roll_fish_weight_kg(item[5:])
        await register_gain(
            conn, steward_id, item, qty,
            loc="satchel", quality=quality, weight_kg=weight_kg,
        )


async def purge_spoiled(conn, steward_id: int, loc: str = "satchel") -> list[str]:
    await ensure_trait_tables(conn)
    now = db.now()
    cur = await conn.execute(
        """
        SELECT id, item, qty, quality FROM item_trait_batches
        WHERE steward_id=? AND loc=? AND spoil_at>0 AND spoil_at<=?
        """,
        (steward_id, loc, now),
    )
    rows = await cur.fetchall()
    notes: list[str] = []
    for row in rows:
        rid, item, qty, quality = row[0], row[1], int(row[2]), row[3]
        await conn.execute("DELETE FROM item_trait_batches WHERE id=?", (rid,))
        took = await db.take_item(conn, steward_id, item, qty)
        if took:
            q = CROP_QUALITY_LABEL.get(quality) or FISH_STATE_LABEL.get(quality) or quality
            label = item_label(item)
            notes.append(f"{label}×{qty}{('·'+q) if q else ''} 已变质，只好丢掉")
    return notes


async def consume_fifo(
    conn,
    steward_id: int,
    item: str,
    qty: int,
    *,
    loc: str = "satchel",
) -> None:
    if qty <= 0:
        return
    await ensure_trait_tables(conn)
    left = qty
    cur = await conn.execute(
        """
        SELECT id, qty FROM item_trait_batches
        WHERE steward_id=? AND loc=? AND item=?
        ORDER BY id ASC
        """,
        (steward_id, loc, item),
    )
    for row in await cur.fetchall():
        if left <= 0:
            break
        bid, have = int(row[0]), int(row[1])
        take = min(have, left)
        left -= take
        if take >= have:
            await conn.execute("DELETE FROM item_trait_batches WHERE id=?", (bid,))
        else:
            await conn.execute(
                "UPDATE item_trait_batches SET qty=qty-? WHERE id=?",
                (take, bid),
            )
    if left > 0:
        return
    await purge_spoiled(conn, steward_id, loc)


def price_multiplier(quality: str, *, fish: bool = False) -> float:
    if fish:
        return FISH_STATE_MULT.get(quality, 1.0)
    return CROP_QUALITY_MULT.get(quality, 1.0)


async def summary_for_item(
    conn,
    steward_id: int,
    item: str,
    *,
    loc: str = "satchel",
) -> str:
    await ensure_trait_tables(conn)
    cur = await conn.execute(
        """
        SELECT quality, weight_milli, spoil_at, SUM(qty) FROM item_trait_batches
        WHERE steward_id=? AND loc=? AND item=?
        GROUP BY quality, weight_milli, spoil_at
        ORDER BY id ASC
        LIMIT 4
        """,
        (steward_id, loc, item),
    )
    rows = await cur.fetchall()
    if not rows:
        return ""
    bits: list[str] = []
    now = db.now()
    for q, wmilli, spoil_at, qty in rows:
        q = q or ""
        label = FISH_STATE_LABEL.get(q) or CROP_QUALITY_LABEL.get(q) or q
        part = f"{label}×{int(qty)}"
        if wmilli and item.startswith("fish_"):
            part = f"{wmilli/1000:.1f}kg·{part}"
        if spoil_at and spoil_at <= now:
            part += "·已坏"
        elif spoil_at and spoil_at - now < 6 * 3600:
            part += "·快坏"
        bits.append(part)
    return "｜".join(bits)


async def vend_unit_price(
    conn,
    steward_id: int,
    item: str,
    base: int,
) -> int:
    await ensure_trait_tables(conn)
    cur = await conn.execute(
        """
        SELECT quality, weight_milli, spoil_at FROM item_trait_batches
        WHERE steward_id=? AND loc='satchel' AND item=?
        ORDER BY id ASC LIMIT 1
        """,
        (steward_id, item),
    )
    row = await cur.fetchone()
    if not row:
        return base
    quality, wmilli, spoil_at = row[0], int(row[1] or 0), int(row[2] or 0)
    if spoil_at and spoil_at <= db.now():
        return max(1, base // 5)
    mult = price_multiplier(quality, fish=item.startswith("fish_"))
    if wmilli and item.startswith("fish_"):
        kg = wmilli / 1000.0
        mult *= min(1.8, 0.85 + kg * 0.04)
    return max(1, int(base * mult))


async def format_list_extra(conn, steward_id: int, item: str) -> str:
    spoiled = await purge_spoiled(conn, steward_id)
    extra = await summary_for_item(conn, steward_id, item)
    return extra
