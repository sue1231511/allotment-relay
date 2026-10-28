"""食材品质、鲜度（腐败）、鱼重 — 第一批玩法扩展。"""
from __future__ import annotations

import json
import logging
import random
from typing import Any

from . import db
from .catalog import CROPS, ITEM_PRICES, SEA_CATCH, item_label

_log = logging.getLogger(__name__)

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
    from . import world as world_mod
    w = world_mod.current_weather()
    if w in ("gale",):
        weights["twisted"] += 2
    if w in ("misty",):
        weights["tender"] += 2
    climate = world_mod.field_climate_effect()
    if climate in ("frost", "snowbound"):
        weights["twisted"] += 3
    if climate in ("drought", "heatwave"):
        weights["overripe"] += 3
        weights["tender"] -= 2
    last = plot.get("last_crop")
    if last and last == plot.get("crop"):
        weights["plain"] += 3
        weights["flavor"] = max(1, weights.get("flavor", 1) - 2)
    crop = plot.get("crop")
    seasons = (CROPS.get(crop) or {}).get("seasons") if crop else None
    if seasons:
        from . import season as season_mod
        now_s = season_mod.season_name()
        if now_s not in seasons and not plot.get("greenhouse"):
            weights["twisted"] += 3
            weights["plain"] += 2
    from . import seed_lineage as seed_lineage_mod
    seed_lineage_mod.apply_quality_bias(weights, plot)
    keys = list(weights.keys())
    w = [max(1, weights[k]) for k in keys]
    return random.choices(keys, weights=w)[0]


def roll_fish_state(species: str, *, layer: str = "", weather: str = "") -> str:
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
    if layer in ("shore",):
        weights["bruised"] += 3
        weights["fresh"] -= 1
    if layer in ("deep",):
        weights["parasite"] += 2
        weights["odd"] += 2
    if weather == "gale":
        weights["bruised"] += 4
        weights["fresh"] = max(1, weights["fresh"] - 2)
    if weather == "misty":
        weights["fresh"] += 3
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
    spoil_mult: float = 1.0,
) -> None:
    if qty <= 0:
        return
    await ensure_trait_tables(conn)
    spoil_at = 0
    sec = _spoil_seconds(item, loc)
    if sec > 0:
        mult = max(0.35, float(spoil_mult or 1.0))
        spoil_at = db.now() + int(sec * mult)
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


async def _satchel_qty(conn, steward_id: int, item: str) -> int:
    cur = await conn.execute(
        "SELECT quantity FROM satchel WHERE steward_id=? AND item=?", (steward_id, item),
    )
    row = await cur.fetchone()
    return int(row[0]) if row else 0


async def purge_spoiled(
    conn,
    steward_id: int,
    loc: str = "satchel",
    *,
    item: str | None = None,
) -> list[str]:
    """丢掉已经变质的批次，返回给玩家看的提示行（每一件丢弃都必须出现在回复里，调用方不许吞）。

    安全规则：
      * 先把这个物品的批次账对齐背包（丢掉幽灵批次），再按批次扣；
      * 每一批只扣 min(批次件数, 背包里此刻真有的件数)，背包不够就少扣，
        绝不会扣到别的（没过期的、没批次的）件头上；
      * item 不为空时只清这一种货，不顺带清别的物品。
    """
    await ensure_trait_tables(conn)
    now = db.now()
    sql = (
        "SELECT DISTINCT item FROM item_trait_batches "
        "WHERE steward_id=? AND loc=? AND spoil_at>0 AND spoil_at<=?"
    )
    args: list = [steward_id, loc, now]
    if item:
        sql += " AND item=?"
        args.append(item)
    items = [r[0] for r in await (await conn.execute(sql, args)).fetchall()]
    notes: list[str] = []
    for it in items:
        try:
            if loc == "satchel":
                await reconcile_batches(conn, steward_id, it)
            rows = await (await conn.execute(
                """
                SELECT id, qty, quality FROM item_trait_batches
                WHERE steward_id=? AND loc=? AND item=? AND spoil_at>0 AND spoil_at<=?
                ORDER BY id ASC
                """,
                (steward_id, loc, it, now),
            )).fetchall()
            for rid, qty, quality in rows:
                qty = int(qty)
                await conn.execute("DELETE FROM item_trait_batches WHERE id=?", (rid,))
                have = await _satchel_qty(conn, steward_id, it) if loc == "satchel" else qty
                take = min(qty, have)
                if take < qty:
                    _log.warning(
                        "purge_spoiled: 批次 %d 件 > 背包 %d 件，只丢 %d 件 steward=%s item=%s",
                        qty, have, take, steward_id, it,
                    )
                if take <= 0:
                    continue
                if not await db.take_item(conn, steward_id, it, take, settle_traits=False):
                    _log.warning(
                        "purge_spoiled: take_item 失败 steward=%s item=%s qty=%s", steward_id, it, take,
                    )
                    continue
                q = CROP_QUALITY_LABEL.get(quality) or FISH_STATE_LABEL.get(quality) or quality
                notes.append(f"{item_label(it)}×{take}{('·' + q) if q else ''} 已变质，只好丢掉")
                _log.info(
                    "purge_spoiled 丢弃变质 steward=%s item=%s qty=%s quality=%s", steward_id, it, take, quality,
                )
                await db.add_chronicle(
                    "spoil", f"变质丢弃 {item_label(it)}（{it}）x{take}", steward_id, conn=conn,
                )
        except Exception:
            _log.exception("purge_spoiled 失败 steward=%s item=%s loc=%s", steward_id, it, loc)
            raise
    return notes


async def pop_qualities(
    conn,
    steward_id: int,
    item: str,
    qty: int,
    *,
    loc: str = "satchel",
) -> list[str]:
    """按 FIFO 扣 trait 批次，返回每份品质（无 trait 则 plain/firm）。"""
    if qty <= 0:
        return []
    await ensure_trait_tables(conn)
    out: list[str] = []
    left = qty
    cur = await conn.execute(
        """
        SELECT id, qty, quality FROM item_trait_batches
        WHERE steward_id=? AND loc=? AND item=?
        ORDER BY id ASC
        """,
        (steward_id, loc, item),
    )
    rows = await cur.fetchall()
    for row in rows:
        if left <= 0:
            break
        bid, have, quality = int(row[0]), int(row[1]), (row[2] or "")
        take = min(have, left)
        left -= take
        q = quality or ("plain" if item.startswith("crop_") else "firm")
        out.extend([q] * take)
        if take >= have:
            await conn.execute("DELETE FROM item_trait_batches WHERE id=?", (bid,))
        else:
            await conn.execute(
                "UPDATE item_trait_batches SET qty=qty-? WHERE id=?",
                (take, bid),
            )
    if left > 0:
        default = "plain" if item.startswith("crop_") else "firm"
        out.extend([default] * left)
    return out


def cooking_star_bonus(qualities: list[str]) -> int:
    """食材品质 → 星级偏移（§四十七）。"""
    bonus = 0
    for q in qualities:
        if q in ("flavor", "plump", "fresh", "roe"):
            bonus += 1
        elif q in ("tender", "firm"):
            pass
        elif q in ("bugbit", "twisted", "overripe", "bruised", "old", "parasite"):
            bonus -= 1
        elif q == "odd":
            bonus += 1
    return max(-2, min(3, bonus))


async def consume_fifo(
    conn,
    steward_id: int,
    item: str,
    qty: int,
    *,
    loc: str = "satchel",
    purge: bool = True,
) -> list[str]:
    """按先进先出扣品质批次。purge=True 时顺带清这一种货剩下的变质批次，
    返回丢弃提示行——调用方必须把它写进回复。"""
    if qty <= 0:
        return []
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
    if left > 0 or not purge:
        return []
    return await purge_spoiled(conn, steward_id, loc, item=item)


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


async def vend_segments(
    conn,
    steward_id: int,
    item: str,
    qty: int,
) -> list[tuple[int, float, bool]]:
    """按 FIFO 把要卖的 qty 件拆成若干段：[(件数, 批次修正乘积, 是否已变质), ...]。

    批次修正 = 品质 × 重量（鱼）× 冰箱（生鱼）。没有批次记录的件（渔排收的、别人送的）修正为 1。
    每段只用自己那一批的系数——一次卖 N 件的总价 = 逐件卖 N 次的总价。
    """
    await ensure_trait_tables(conn)
    await reconcile_batches(conn, steward_id, item)
    cur = await conn.execute(
        """
        SELECT quality, weight_milli, spoil_at, qty FROM item_trait_batches
        WHERE steward_id=? AND loc='satchel' AND item=?
        ORDER BY id ASC
        """,
        (steward_id, item),
    )
    rows = await cur.fetchall()
    segments: list[tuple[int, float, bool]] = []
    left = int(qty)
    if rows and item.startswith("fish_"):
        from . import loop_couple as loop_mod

        fridge = await loop_mod.fridge_price_mult(conn, steward_id, item)
    else:
        fridge = 1.0
    now = db.now()
    for quality, wmilli, spoil_at, have in rows:
        if left <= 0:
            break
        take = min(int(have), left)
        left -= take
        if int(spoil_at or 0) and int(spoil_at) <= now:
            segments.append((take, 1.0, True))
            continue
        mult = price_multiplier(quality, fish=item.startswith("fish_"))
        if wmilli and item.startswith("fish_"):
            mult *= min(1.8, 0.85 + (int(wmilli) / 1000.0) * 0.04)
        segments.append((take, mult * fridge, False))
    if left > 0:
        segments.append((left, 1.0, False))
    return segments


async def reconcile_batches(conn, steward_id: int, item: str, *, loc: str = "satchel") -> int:
    """批次总量超过背包实际数量时，丢掉多出来的幽灵批次（已过期的优先，再从老到新）。返回丢掉的件数。"""
    await ensure_trait_tables(conn)
    cur = await conn.execute(
        "SELECT COALESCE(SUM(qty),0) FROM item_trait_batches WHERE steward_id=? AND loc=? AND item=?",
        (steward_id, loc, item),
    )
    batch_total = int((await cur.fetchone())[0] or 0)
    if batch_total <= 0 or loc != "satchel":
        return 0
    cur = await conn.execute(
        "SELECT quantity FROM satchel WHERE steward_id=? AND item=?", (steward_id, item)
    )
    row = await cur.fetchone()
    have = int(row[0]) if row else 0
    extra = batch_total - have
    if extra <= 0:
        return 0
    _log.warning(
        "reconcile_batches: 批次 %d 件 > 背包 %d 件，丢弃最老 %d 件幽灵批次 steward=%s item=%s",
        batch_total, have, extra, steward_id, item,
    )
    dropped = 0
    # 多出来的件一定是某些批次的「幽灵」。先削已经过期的批次（反正也要丢，新货最值钱要保住），再按编号从老到新
    cur = await conn.execute(
        """
        SELECT id, qty FROM item_trait_batches WHERE steward_id=? AND loc=? AND item=?
        ORDER BY (CASE WHEN spoil_at>0 AND spoil_at<=? THEN 0 ELSE 1 END), id ASC
        """,
        (steward_id, loc, item, db.now()),
    )
    for bid, bq in await cur.fetchall():
        if dropped >= extra:
            break
        cut = min(int(bq), extra - dropped)
        dropped += cut
        if cut >= int(bq):
            await conn.execute("DELETE FROM item_trait_batches WHERE id=?", (bid,))
        else:
            await conn.execute("UPDATE item_trait_batches SET qty=qty-? WHERE id=?", (cut, bid))
    return dropped


async def release_for_departure(conn, steward_id: int, item: str, qty: int) -> None:
    """物品离开背包（送礼、挂集市、捐赠、交付、交换台……）时，同步释放对应批次，
    不留「幽灵批次」。只处理会记批次的货（作物、鱼等）。"""
    if qty <= 0 or not is_trackable(item):
        return
    try:
        await consume_fifo(conn, steward_id, item, qty, purge=False)
    except Exception:
        _log.exception(
            "release_for_departure 失败 steward=%s item=%s qty=%s", steward_id, item, qty
        )
        raise


async def heal_ghost_batches(conn) -> int:
    """一次性（init_db 里跑，world_flags 防重复）：把旧版本留下的幽灵批次对齐背包。
    只改批次账，不动任何人的物品和票。返回丢掉的幽灵件数。"""
    flag = "trait_ghost_heal_v1"
    cur = await conn.execute("SELECT 1 FROM world_flags WHERE flag_key=?", (flag,))
    if await cur.fetchone():
        return 0
    await ensure_trait_tables(conn)
    dropped = 0
    try:
        pairs = await (await conn.execute(
            "SELECT DISTINCT steward_id, item FROM item_trait_batches WHERE loc='satchel'"
        )).fetchall()
        for sid, it in pairs:
            dropped += await reconcile_batches(conn, int(sid), it)
        await conn.execute(
            "INSERT OR IGNORE INTO world_flags (flag_key, applied_at, detail) VALUES (?,?,?)",
            (flag, db.now(), f"dropped={dropped}"),
        )
    except Exception:
        _log.exception("heal_ghost_batches 失败")
        raise
    _log.info("heal_ghost_batches 完成：对齐掉 %d 件幽灵批次", dropped)
    return dropped
