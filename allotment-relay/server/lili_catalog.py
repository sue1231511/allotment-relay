"""栗栗流动摊 — 按日种子生成货单，四域（种地/钓鱼/捕捞/赶海）等级影响票附加。"""

from __future__ import annotations

import json
import random
from typing import Any

import aiosqlite

from . import config, db
from .catalog import BEACH_LOOT, CROPS, ITEM_PRICES, LILI_DECOR, LILI_JUNK_DECOR, RARE_CURIO, SEA_CATCH
from .config import BOATS
from .gear import get_gear

DOMAINS = ("farm", "fish", "sea", "beach")
DOMAIN_LABELS = {
    "farm": "种地",
    "fish": "钓鱼",
    "sea": "捕捞",
    "beach": "赶海",
}

DECO_TIER: dict[str, int] = {}
for key, meta in LILI_DECOR.items():
    sell = meta["sell"]
    if sell <= 40:
        DECO_TIER[key] = 1
    elif sell <= 48:
        DECO_TIER[key] = 2
    elif sell <= 55:
        DECO_TIER[key] = 3
    elif sell <= 62:
        DECO_TIER[key] = 4
    else:
        DECO_TIER[key] = 5

DECO_DOMAINS: dict[str, list[str]] = {
    "coral_lamp": ["beach", "sea"],
    "shell_windchime": ["beach"],
    "pearl_garland": ["beach", "sea"],
    "tide_clock": ["beach", "fish"],
    "drift_bonsai": ["farm", "beach"],
    "moon_mirror": ["beach", "sea"],
    "net_dreamcatcher": ["sea", "beach"],
    "star_crown": ["beach", "fish"],
    "amber_frame": ["beach", "sea"],
    "kelp_tassel": ["farm", "beach"],
}

SKIP_PREFIXES = ("deco_", "fit_", "tool_", "live_", "meal_", "dish_", "seed_")


def day_id() -> int:
    return db.now() // config.FORAGE_COOLDOWN_DAY


def _price_tier(price: int) -> int:
    if price <= 12:
        return 1
    if price <= 20:
        return 2
    if price <= 30:
        return 3
    if price <= 45:
        return 4
    return 5


def _fish_domain(species: str, meta: dict[str, Any]) -> str:
    zones = meta.get("zones") or []
    rarity = meta.get("rarity") or 1
    if any(z in zones for z in ("far", "deep")):
        return "sea"
    if meta.get("pen") and rarity >= 3:
        return "sea"
    if any(z in zones for z in ("shore", "near")):
        return "fish"
    return "sea"


def _build_domain_pools() -> dict[str, list[tuple[str, int, int]]]:
    pools: dict[str, list[tuple[str, int, int]]] = {d: [] for d in DOMAINS}

    farm_extra = {
        "compost", "wild_mint", "egg", "duck_egg", "milk", "goat_milk",
        "honey", "wool", "goat_cheese", "scarecrow",
    }
    beach_extra = {"sea_glass", "drift_twine", "bait_worm"}
    beach_keys = {row[0] for row in BEACH_LOOT}
    beach_keys.update(RARE_CURIO.keys())

    for item, price in ITEM_PRICES.items():
        if price <= 0:
            continue
        if any(item.startswith(p) for p in SKIP_PREFIXES):
            continue
        tier = _price_tier(price)
        if item.startswith("crop_"):
            pools["farm"].append((item, price, tier))
            continue
        if item.startswith("fish_"):
            species = item.removeprefix("fish_")
            meta = SEA_CATCH.get(species)
            if not meta:
                continue
            domain = _fish_domain(species, meta)
            pools[domain].append((item, price, tier))
            continue
        if item.startswith("shell_") or item.startswith("beach_") or item in beach_extra:
            pools["beach"].append((item, price, tier))
            continue
        if item in beach_keys or item in RARE_CURIO:
            pools["beach"].append((item, price, tier))
            continue
        if item.startswith("manure_") or item in farm_extra:
            pools["farm"].append((item, price, tier))
            continue
        if item == "bait_worm":
            pools["fish"].append((item, price, tier))
            pools["beach"].append((item, price, tier))

    for d in DOMAINS:
        pools[d].sort(key=lambda x: x[1])
    return pools


DOMAIN_POOLS = _build_domain_pools()


def _deco_target_value(deco_key: str, rng: random.Random) -> int:
    sell = LILI_DECOR[deco_key]["sell"]
    tier = DECO_TIER.get(deco_key, 2)
    mult = 0.88 + rng.uniform(0, 0.28) + tier * 0.04
    return max(20, int(sell * mult))


def _pick_domains(deco_key: str, rng: random.Random) -> list[str]:
    base = list(DECO_DOMAINS.get(deco_key, ["beach", "farm"]))
    rng.shuffle(base)
    if rng.random() < 0.35 and len(base) < 3:
        extra = rng.choice([d for d in DOMAINS if d not in base])
        base.append(extra)
    return base[: rng.randint(1, min(3, len(base) or 1))] or ["beach"]


def _assemble_give(
    rng: random.Random,
    domains: list[str],
    target: int,
    tier: int,
) -> tuple[dict[str, int], int]:
    give: dict[str, int] = {}
    total = 0
    pool: list[tuple[str, int, int]] = []
    for d in domains:
        pool.extend(DOMAIN_POOLS.get(d, []))
    if not pool:
        pool = list(DOMAIN_POOLS["beach"])
    rng.shuffle(pool)

    min_items = 2 if tier >= 3 else 1
    max_items = 4 if tier >= 4 else 3
    picks = min(max_items, max(min_items, len(domains) + 1))

    chosen: list[tuple[str, int, int]] = []
    seen: set[str] = set()
    for row in pool:
        if row[0] in seen:
            continue
        if tier >= 4 and row[2] < 2 and rng.random() < 0.5:
            continue
        chosen.append(row)
        seen.add(row[0])
        if len(chosen) >= picks:
            break
    if not chosen:
        chosen = pool[:2]

    for item, price, _ in chosen:
        if total >= target:
            break
        need = max(1, (target - total + price - 1) // max(1, price))
        qty = min(8, max(1, need))
        if tier >= 5 and price >= 35:
            qty = min(qty, 2)
        give[item] = give.get(item, 0) + qty
        total += price * qty

    guard = 0
    while total < int(target * 0.82) and guard < 24:
        guard += 1
        item, price, _ = rng.choice(chosen)
        give[item] = give.get(item, 0) + 1
        total += price

    return give, total


def _base_ticket_cost(tier: int, value_total: int, rng: random.Random) -> int:
    if tier <= 2:
        if rng.random() < 0.12:
            return rng.randint(2, 5)
        return 0
    if tier == 3:
        if rng.random() < 0.45:
            return rng.randint(4, 10)
        return 0
    if tier == 4:
        return rng.randint(6, 14) if rng.random() < 0.65 else rng.randint(0, 6)
    return rng.randint(10, 22)


def _offer_note(domains: list[str], tier: int, rng: random.Random) -> str:
    labels = "·".join(DOMAIN_LABELS.get(d, d) for d in domains)
    vibes = [
        f"今日价签偏{labels}",
        f"栗栗说：{labels}货今日紧俏",
        f"配方锁在{labels}线",
        "全服今日仅此配方",
    ]
    if tier >= 4:
        vibes.append("高档软装，可能要搭点票")
    return rng.choice(vibes)


def generate_daily_offers(day: int, count: int | None = None) -> list[dict[str, Any]]:
    rng = random.Random(day * 982451653 + 1567)
    n = count or rng.randint(config.LILI_OFFERS_MIN, config.LILI_OFFERS_MAX)
    decos = list(LILI_DECOR.keys())
    rng.shuffle(decos)
    decos = decos[:n]

    offers: list[dict[str, Any]] = []
    junk_slot = rng.random() < 0.14 and decos
    for i, deco_key in enumerate(decos):
        if junk_slot and i == len(decos) - 1:
            junk_key = rng.choice(list(LILI_JUNK_DECOR.keys()))
            sub = random.Random(day * 100003 + i * 9176)
            give = {"shell_rough_scallop": sub.randint(6, 10)}
            if sub.random() < 0.4:
                give["shell_rough_conch"] = sub.randint(2, 4)
            offers.append({
                "trade_key": f"d{day}_junk_{junk_key}_{sub.randint(100, 999)}",
                "give": give,
                "get": f"deco_junk_{junk_key}",
                "get_qty": 1,
                "ticket_cost": 0,
                "stock": 1,
                "day_id": day,
                "domains_json": json.dumps(["beach"], ensure_ascii=False),
                "offer_tier": 1,
                "value_total": sub.randint(18, 28),
                "note": "铃鹿乱捡款·不退不换",
            })
            continue
        sub = random.Random(day * 100003 + i * 9176)
        tier = DECO_TIER.get(deco_key, 2)
        domains = _pick_domains(deco_key, sub)
        target = _deco_target_value(deco_key, sub)
        give, value_total = _assemble_give(sub, domains, target, tier)
        tickets = _base_ticket_cost(tier, value_total, sub)
        trade_key = f"d{day}_{deco_key}_{sub.randint(100, 999)}"
        offers.append({
            "trade_key": trade_key,
            "give": give,
            "get": f"deco_{deco_key}",
            "get_qty": 1,
            "ticket_cost": tickets,
            "stock": 1 if tier >= 4 else sub.randint(1, 2),
            "day_id": day,
            "domains_json": json.dumps(domains, ensure_ascii=False),
            "offer_tier": tier,
            "value_total": value_total,
            "note": _offer_note(domains, tier, sub),
        })
    return offers


async def ensure_daily_offers(conn: aiosqlite.Connection, day: int, visit_id: int) -> list[dict[str, Any]]:
    conn.row_factory = aiosqlite.Row
    rows = await (await conn.execute(
        "SELECT * FROM lili_offers WHERE day_id=? ORDER BY id",
        (day,),
    )).fetchall()
    if rows:
        return [dict(r) for r in rows]

    offers = generate_daily_offers(day)
    for tmpl in offers:
        await conn.execute(
            """
            INSERT INTO lili_offers (
                visit_id, trade_key, give_json, get_item, get_qty, ticket_cost, stock,
                day_id, domains_json, offer_tier, value_total, note
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                visit_id,
                tmpl["trade_key"],
                json.dumps(tmpl["give"], ensure_ascii=False),
                tmpl["get"],
                tmpl["get_qty"],
                tmpl["ticket_cost"],
                tmpl["stock"],
                day,
                tmpl["domains_json"],
                tmpl["offer_tier"],
                tmpl["value_total"],
                tmpl["note"],
            ),
        )
    rows = await (await conn.execute(
        "SELECT * FROM lili_offers WHERE day_id=? ORDER BY id",
        (day,),
    )).fetchall()
    return [dict(r) for r in rows]


async def daily_offers(conn: aiosqlite.Connection, day: int) -> list[dict[str, Any]]:
    conn.row_factory = aiosqlite.Row
    rows = await (await conn.execute(
        "SELECT * FROM lili_offers WHERE day_id=? ORDER BY id",
        (day,),
    )).fetchall()
    return [dict(r) for r in rows]


async def steward_domain_levels(conn: aiosqlite.Connection, steward_id: int) -> dict[str, int]:
    conn.row_factory = aiosqlite.Row
    steward = dict(await (await conn.execute(
        "SELECT parcel_count, hut_level, boat_key FROM stewards WHERE id=?",
        (steward_id,),
    )).fetchone())

    parcels = int(steward.get("parcel_count") or 3)
    hut = int(steward.get("hut_level") or 0)
    farm = min(5, max(1, 1 + max(0, parcels - 3) + (1 if hut >= 2 else 0) + (1 if hut >= 3 else 0)))

    gear = await get_gear(conn, steward_id)
    fish_score = gear["bait"] + gear["rod"] + gear["net"]
    fish = min(5, max(1, 1 + fish_score // 2))

    boat_key = steward.get("boat_key") or ""
    boat_rank = BOATS.get(boat_key, {}).get("rank", 0)
    pen_rows = await (await conn.execute(
        "SELECT COUNT(*) FROM fish_pens WHERE steward_id=? AND species IS NOT NULL AND species != ''",
        (steward_id,),
    )).fetchone()
    pen_count = pen_rows[0] if pen_rows else 0
    sea = min(5, max(1, 1 + boat_rank + pen_count))

    beach_keys = sorted({row[0] for row in BEACH_LOOT})
    catch_rows = await (await conn.execute(
        """
        SELECT catch_key FROM steward_catches
        WHERE steward_id=? AND catch_key IN ({})
        """.format(",".join("?" * len(beach_keys))),
        (steward_id, *beach_keys),
    )).fetchall()
    got = len(catch_rows)
    ratio = got / max(1, len(beach_keys))
    beach = min(5, max(1, 1 + int(ratio * 4)))

    crop_tags = set()
    for ck in CROPS:
        crop_tags.add(f"crop_{ck}")
    crop_rows = await (await conn.execute(
        "SELECT COUNT(DISTINCT item) FROM satchel WHERE steward_id=? AND quantity>0 AND item LIKE 'crop_%'",
        (steward_id,),
    )).fetchone()
    if crop_rows and crop_rows[0] >= 6:
        farm = min(5, farm + 1)

    return {"farm": farm, "fish": fish, "sea": sea, "beach": beach}


def ticket_cost_for_steward(base: int, domains: list[str], levels: dict[str, int]) -> int:
    if base <= 0:
        return 0
    bonus = sum(max(0, levels.get(d, 1) - 1) for d in domains)
    discount = (bonus * 2) // max(1, len(domains))
    return max(0, base - discount)


def domain_level_line(levels: dict[str, int]) -> str:
    parts = [f"{DOMAIN_LABELS[d]}{levels[d]}" for d in DOMAINS]
    return "四域等级 " + " · ".join(parts) + "（高等级减票附加）"
