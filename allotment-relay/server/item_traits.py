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
    """一次性（init_db 里跑）：把旧版本留下的幽灵批次对齐背包。
    只改批次账，不动任何人的物品和票。返回丢掉的幽灵件数。补数据和标记在同一个保存点里。"""
    return await db.run_flagged_migration(conn, "trait_ghost_heal_v1", "幽灵批次对齐", _heal_work)


async def _heal_work(conn, stats: dict[str, int]) -> int:
    await ensure_trait_tables(conn)
    dropped = 0
    pairs = await (await conn.execute(
        "SELECT DISTINCT steward_id, item FROM item_trait_batches WHERE loc='satchel'"
    )).fetchall()
    for sid, it in pairs:
        dropped += await reconcile_batches(conn, int(sid), it)
        stats["processed"] += 1
    return dropped


# ═══ 变质时间跟着货走：转手、存柜/取柜都不重置保鲜期 ═══════════════════════
#
# 批次 = (件数, 品质, 重量毫克, 变质时刻)。转手时批次原样带给收货人（挂单期间按真实时间照常变质）；
# 存潮柜/冰箱时，剩余寿命按位置倍率放慢（柜 ×1.8，冰箱 ×3.5），取出来再按倍率折回去：
# 保鲜只是变慢，不是不坏，也不会因为存取一下就重新计时。
TraitSlice = tuple[int, str, int, int]


def escrow_loc(kind: str, ref: int) -> str:
    return f"{kind}:{int(ref)}"


def scale_slices(slices: list[TraitSlice], factor: float) -> list[TraitSlice]:
    """把每一批「剩余寿命」乘 factor。不会变质的批次（spoil_at=0）和已经过期的批次不动。"""
    now = db.now()
    out: list[TraitSlice] = []
    for qty, quality, wmilli, spoil_at in slices:
        if spoil_at and spoil_at > now and factor > 0:
            spoil_at = now + max(1, int((spoil_at - now) * factor))
        out.append((qty, quality, wmilli, spoil_at))
    return out


def loc_factor(from_loc: str, to_loc: str) -> float:
    return SPOIL_LOC_MULT.get(to_loc, 1.0) / SPOIL_LOC_MULT.get(from_loc, 1.0)


async def _pop_trait_fifo(
    conn, owner: int, loc: str, item: str, qty: int,
) -> list[TraitSlice]:
    if qty <= 0:
        return []
    rows = await (await conn.execute(
        """
        SELECT id, qty, quality, weight_milli, spoil_at FROM item_trait_batches
        WHERE steward_id=? AND loc=? AND item=? ORDER BY id ASC
        """,
        (owner, loc, item),
    )).fetchall()
    left = qty
    out: list[TraitSlice] = []
    for bid, have, quality, wmilli, spoil_at in rows:
        if left <= 0:
            break
        have = int(have)
        take = min(have, left)
        left -= take
        out.append((take, quality or "", int(wmilli or 0), int(spoil_at or 0)))
        if take >= have:
            await conn.execute("DELETE FROM item_trait_batches WHERE id=?", (bid,))
        else:
            await conn.execute("UPDATE item_trait_batches SET qty=qty-? WHERE id=?", (take, bid))
    return out


async def _insert_trait_rows(
    conn, owner: int, loc: str, item: str, slices: list[TraitSlice],
) -> None:
    for qty, quality, wmilli, spoil_at in slices:
        if qty <= 0:
            continue
        await conn.execute(
            """
            INSERT INTO item_trait_batches
            (steward_id, loc, item, qty, quality, weight_milli, spoil_at)
            VALUES (?,?,?,?,?,?,?)
            """,
            (owner, loc, item, qty, quality or "", wmilli, spoil_at),
        )


async def carry_out(
    conn, steward_id: int, item: str, qty: int, *, loc: str = "satchel",
) -> list[TraitSlice]:
    """取走 qty 件的品质批次（先进先出）并带出；不会变质/没记批次的货返回空。"""
    if qty <= 0 or not is_trackable(item):
        return []
    try:
        await ensure_trait_tables(conn)
        return await _pop_trait_fifo(conn, steward_id, loc, item, qty)
    except Exception:
        _log.exception("carry_out 失败 steward=%s item=%s qty=%s loc=%s", steward_id, item, qty, loc)
        raise


async def deposit(
    conn, steward_id: int, item: str, slices: list[TraitSlice] | None,
    *, loc: str = "satchel",
) -> None:
    """收货/入柜落账。调用方已经把物品放进对应位置；背包批次总量不会超过背包数量。"""
    if not slices or not is_trackable(item):
        return
    try:
        await ensure_trait_tables(conn)
        await _insert_trait_rows(conn, steward_id, loc, item, slices)
        if loc == "satchel":
            await reconcile_batches(conn, steward_id, item)
    except Exception:
        _log.exception("deposit 失败 steward=%s item=%s loc=%s", steward_id, item, loc)
        raise


async def stash_traits(
    conn, kind: str, ref: int, item: str, slices: list[TraitSlice] | None,
) -> None:
    """挂单暂存（集市/交换台/公仓/台阶交接）；挂单期间照常按真实时间变质。"""
    if not slices or not is_trackable(item):
        return
    try:
        await ensure_trait_tables(conn)
        await _insert_trait_rows(conn, 0, escrow_loc(kind, ref), item, slices)
    except Exception:
        _log.exception("stash_traits 失败 kind=%s ref=%s item=%s", kind, ref, item)
        raise


async def unstash_traits(conn, kind: str, ref: int, item: str, qty: int) -> list[TraitSlice]:
    if qty <= 0 or not is_trackable(item):
        return []
    try:
        await ensure_trait_tables(conn)
        return await _pop_trait_fifo(conn, 0, escrow_loc(kind, ref), item, qty)
    except Exception:
        _log.exception("unstash_traits 失败 kind=%s ref=%s item=%s", kind, ref, item)
        raise


async def discard_traits(conn, kind: str, ref: int) -> None:
    try:
        await ensure_trait_tables(conn)
        await conn.execute(
            "DELETE FROM item_trait_batches WHERE steward_id=0 AND loc=?", (escrow_loc(kind, ref),),
        )
    except Exception:
        _log.exception("discard_traits 失败 kind=%s ref=%s", kind, ref)
        raise


async def store_into(
    conn, steward_id: int, item: str, qty: int, to_loc: str,
) -> None:
    """物品已经从背包取走、放进柜子：把背包里对应的批次搬进柜子，剩余寿命放慢。"""
    slices = await carry_out(conn, steward_id, item, qty, loc="satchel")
    await deposit(conn, steward_id, item, scale_slices(slices, loc_factor("satchel", to_loc)), loc=to_loc)


async def take_out_of(
    conn, steward_id: int, item: str, qty: int, from_loc: str,
) -> None:
    """物品已经放回背包：把柜子里对应的批次搬回背包，剩余寿命折回背包时间。"""
    slices = await carry_out(conn, steward_id, item, qty, loc=from_loc)
    await deposit(conn, steward_id, item, scale_slices(slices, loc_factor(from_loc, "satchel")), loc="satchel")


async def _storage_qty_and_take(
    conn, steward_id: int, kind: str, item: str, qty: int | None,
) -> int:
    """读（qty=None）或扣（qty>0）柜子里的件数，返回柜子里原有（读）/实际扣掉（扣）的件数。"""
    if kind == "cabinet":
        row = await (await conn.execute(
            "SELECT quantity FROM hut_cabinet WHERE steward_id=? AND item=?", (steward_id, item),
        )).fetchone()
        have = int(row[0]) if row else 0
        if qty is None:
            return have
        cut = min(have, qty)
        if cut <= 0:
            return 0
        if have - cut <= 0:
            await conn.execute("DELETE FROM hut_cabinet WHERE steward_id=? AND item=?", (steward_id, item))
        else:
            await conn.execute(
                "UPDATE hut_cabinet SET quantity=? WHERE steward_id=? AND item=?", (have - cut, steward_id, item),
            )
        return cut
    # fridge：熟菜按 (dish_key, stars) 分行
    from . import kitchen

    dish_key, stars = kitchen._fridge_parts(item)  # noqa: SLF001
    rows = await (await conn.execute(
        "SELECT id, quantity FROM meal_storage WHERE steward_id=? AND dish_key=? AND stars=? ORDER BY id",
        (steward_id, dish_key, stars),
    )).fetchall()
    have = sum(int(r[1] or 0) for r in rows)
    if qty is None:
        return have
    left = min(have, qty)
    cut_total = left
    for rid, rq in rows:
        if left <= 0:
            break
        rq = int(rq or 0)
        cut = min(rq, left)
        left -= cut
        if rq - cut <= 0:
            await conn.execute("DELETE FROM meal_storage WHERE id=?", (rid,))
        else:
            await conn.execute("UPDATE meal_storage SET quantity=? WHERE id=?", (rq - cut, rid))
    return cut_total


async def purge_storage(
    conn, steward_id: int, kind: str, *, item: str | None = None,
) -> list[str]:
    """潮柜(cabinet)/冰箱(fridge) 里已经变质的批次：按真实件数从柜子里扣掉，返回提示行。
    保鲜只是变慢，放久了照样坏。每一批只扣 min(批次件数, 柜子里真有的件数)。"""
    await ensure_trait_tables(conn)
    now = db.now()
    sql = (
        "SELECT DISTINCT item FROM item_trait_batches "
        "WHERE steward_id=? AND loc=? AND spoil_at>0 AND spoil_at<=?"
    )
    args: list = [steward_id, kind, now]
    if item:
        sql += " AND item=?"
        args.append(item)
    items = [r[0] for r in await (await conn.execute(sql, args)).fetchall()]
    where = "潮柜" if kind == "cabinet" else "冰箱"
    notes: list[str] = []
    for it in items:
        try:
            rows = await (await conn.execute(
                """
                SELECT id, qty, quality FROM item_trait_batches
                WHERE steward_id=? AND loc=? AND item=? AND spoil_at>0 AND spoil_at<=? ORDER BY id
                """,
                (steward_id, kind, it, now),
            )).fetchall()
            for rid, qty, quality in rows:
                await conn.execute("DELETE FROM item_trait_batches WHERE id=?", (rid,))
                cut = await _storage_qty_and_take(conn, steward_id, kind, it, int(qty))
                if cut < int(qty):
                    _log.warning(
                        "purge_storage: 批次 %d 件 > %s 里 %d 件，只丢 %d 件 steward=%s item=%s",
                        int(qty), where, cut, cut, steward_id, it,
                    )
                if cut <= 0:
                    continue
                q = CROP_QUALITY_LABEL.get(quality) or FISH_STATE_LABEL.get(quality) or quality
                notes.append(f"{where}里的{item_label(it)}×{cut}{('·' + q) if q else ''} 放坏了，只好丢掉")
                _log.info("purge_storage 丢弃变质 steward=%s %s item=%s qty=%s", steward_id, kind, it, cut)
                await db.add_chronicle(
                    "spoil", f"{where}变质丢弃 {item_label(it)}（{it}）x{cut}", steward_id, conn=conn,
                )
        except Exception:
            _log.exception("purge_storage 失败 steward=%s kind=%s item=%s", steward_id, kind, it)
            raise
    return notes


# ═══ 老存货补变质起点（一次性）══════════════════════════════════════════
SPOIL_CLOCK_FLAG = "spoil_clock_backfill_v1"

SPOIL_NOTICE = (
    "【柜子和冰箱现在会变质】潮柜让货变质慢 1.8 倍、冰箱慢 3.5 倍，但不是不坏：存进去、取出来不重新计时，"
    "放太久照样坏，丢了什么会写在回复里；送人、挂集市、换给别人，货的新鲜程度也跟着走。"
    "已经放在柜子、冰箱里的老存货，以及没有新鲜记录的老货，从今天起各给一整段保质期重新起算："
    "潮柜里作物约 5.4 天、鱼约 2.7 天；冰箱里熟菜约 2.6 天；行囊里作物 3 天、鱼 1.5 天、熟菜 18 小时。"
    "到期前取出来用掉或卖掉就好。"
)


async def _unbatched(conn, owner: int, loc: str, item: str, have: int) -> int:
    row = await (await conn.execute(
        "SELECT COALESCE(SUM(qty),0) FROM item_trait_batches WHERE steward_id=? AND loc=? AND item=?",
        (owner, loc, item),
    )).fetchone()
    return max(0, int(have) - int((row[0] if row else 0) or 0))


async def backfill_spoil_clock(conn) -> int:
    """一次性（init_db 里跑）：旧版本里没有变质记录的存货，从上线这一刻起
    各给一整段完整保质期——行囊 ×1、潮柜 ×1.8、冰箱 ×3.5（不按已存放多久折算）。

    范围：背包、潮柜、冰箱，以及还挂在集市/交换台/公仓/台阶交接里的货（按行囊算）。
    已经有批次的件不动；新批次品质留空，价格和做菜星级都和没有批次时一样。
    只加批次行，不动任何人的物品和票。补完写一条全岛纪事和一条潮生会告示。返回补了多少件。
    补批次、写纪事/告示和「已补」标记在同一个保存点里（db.run_flagged_migration）：
    中途失败整体回滚，下次启动重试。
    """
    return await db.run_flagged_migration(conn, SPOIL_CLOCK_FLAG, "老存货补变质起点", _spoil_clock_work)


async def _spoil_clock_work(conn, stats: dict[str, int]) -> int:
    await ensure_trait_tables(conn)
    from . import kitchen

    now = db.now()
    added = 0

    async def fill(owner: int, loc: str, item: str, have: int, clock_loc: str) -> int:
        if not is_trackable(item):
            return 0
        missing = await _unbatched(conn, owner, loc, item, have)
        if missing <= 0:
            return 0
        sec = _spoil_seconds(item, clock_loc)
        if sec <= 0:
            return 0
        await conn.execute(
            """
            INSERT INTO item_trait_batches (steward_id, loc, item, qty, quality, weight_milli, spoil_at)
            VALUES (?,?,?,?,'',0,?)
            """,
            (owner, loc, item, missing, now + sec),
        )
        stats["processed"] += 1
        return missing

    for sid, item, qty in await (await conn.execute(
        "SELECT steward_id, item, quantity FROM satchel WHERE quantity>0"
    )).fetchall():
        added += await fill(int(sid), "satchel", item, int(qty), "satchel")
    for sid, item, qty in await (await conn.execute(
        "SELECT steward_id, item, quantity FROM hut_cabinet WHERE quantity>0"
    )).fetchall():
        added += await fill(int(sid), "cabinet", item, int(qty), "cabinet")
    fridge: dict[tuple[int, str], int] = {}
    for sid, dish_key, stars, qty in await (await conn.execute(
        "SELECT steward_id, dish_key, stars, quantity FROM meal_storage WHERE quantity>0"
    )).fetchall():
        key = (int(sid), kitchen._fridge_satchel_item(dish_key, int(stars)))  # noqa: SLF001
        fridge[key] = fridge.get(key, 0) + int(qty)
    for (sid, item), qty in fridge.items():
        added += await fill(sid, "fridge", item, qty, "fridge")
    for kind, sql in (
        ("market", "SELECT id, item, quantity FROM market_listings WHERE buyer_id IS NULL AND quantity>0"),
        ("swap", "SELECT id, item, quantity FROM swap_lots WHERE claimed_by IS NULL AND quantity>0"),
        ("handoff", "SELECT id, item, quantity FROM handoffs WHERE picked_up=0 AND quantity>0"),
    ):
        for ref, item, qty in await (await conn.execute(sql)).fetchall():
            added += await fill(0, escrow_loc(kind, int(ref)), item, int(qty), "satchel")
    for item, qty in await (await conn.execute(
        "SELECT item, quantity FROM larder WHERE quantity>0"
    )).fetchall():
        added += await fill(0, escrow_loc("larder", 0), item, int(qty), "satchel")

    row = await (await conn.execute("SELECT COUNT(*) FROM stewards")).fetchone()
    if int((row[0] if row else 0) or 0) > 0:
        await db.add_chronicle("spoil_notice", SPOIL_NOTICE, None, conn=conn)
        await conn.execute(
            "INSERT INTO hui_notices (tag, body, created_at, retracted) VALUES ('厅示', ?, ?, 0)",
            (SPOIL_NOTICE, now),
        )
    return added


async def sweep_escrow(conn, kind: str, ref: int, item: str, listed_qty: int) -> int:
    """挂单（集市/交换台/公仓）里已经变质的批次：删掉这些批次，返回变质的件数（不超过挂单件数）。
    调用方负责从挂单/储藏室里扣掉同样件数、清理实付批次、写纪事——变质的货不能成交。"""
    if listed_qty <= 0 or not is_trackable(item):
        return 0
    try:
        await ensure_trait_tables(conn)
        rows = await (await conn.execute(
            """
            SELECT id, qty FROM item_trait_batches
            WHERE steward_id=0 AND loc=? AND item=? AND spoil_at>0 AND spoil_at<=? ORDER BY id
            """,
            (escrow_loc(kind, ref), item, db.now()),
        )).fetchall()
        cut = 0
        for bid, qty in rows:
            await conn.execute("DELETE FROM item_trait_batches WHERE id=?", (bid,))
            cut += int(qty)
        return min(cut, int(listed_qty))
    except Exception:
        _log.exception("sweep_escrow 失败 kind=%s ref=%s item=%s", kind, ref, item)
        raise
