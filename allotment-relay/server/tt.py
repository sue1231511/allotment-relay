"""Tt酱杂货店 — 种子/饲料/渔具/农具，送礼涨好感，进店可能塞东西。"""

from __future__ import annotations

import math
import random
from typing import Any

import aiosqlite

from . import config, db, flavor
from .catalog import (
    CROPS,
    ITEM_NAMES,
    KITCHEN_DISHES,
    dish_item,
    resolve_crop_key,
    resolve_item_key,
)
from .game import require_steward

TT_KEY = "tt"
TT_NAME = "Tt酱"
AFFINITY_MAX = config.TT_AFFINITY_MAX
HEARTS_MAX = 10  # 1 心 = 10 好感
ZHE_PER_PAIR = 0.5  # 每两心打 0.5 折（10 心 → 7.5 折 = 75 折）
MOOD_CHANCE = config.TT_MOOD_CHANCE
MOOD_DISH = 0.20
MOOD_CROP = 0.40  # 其余为货架商品
GIFT_DAILY_CAP = config.TT_GIFT_DAILY_CAP
GIFT_GAIN_CAP = config.TT_GIFT_GAIN_CAP
TICKET_GIFT_MIN = config.TT_TICKET_GIFT_MIN
TICKET_PER_POINT = config.TT_TICKET_PER_POINT
TICKET_GAIN_CAP = config.TT_TICKET_GAIN_CAP
BUMP_CHANCE = config.TT_BUMP_CHANCE
BUMP_DAILY_MAX = config.TT_BUMP_DAILY_MAX
BUMP_TRIGGERS = {"sow", "tend", "gather", "forage", "guild"}
SCALE_HALF_HEARTS = 4
SCALE_SLOW_HEARTS = 8

FEED_ANIMAL = "feed_animal"
FEED_PET = "feed_pet"
TOOL_SHEARS = "tool_shears"
TOOL_MILKER = "tool_milker"
TOOL_HOE = "tool_hoe"
TOOL_SHOVEL = "tool_shovel"
TOOL_NET_BASIC = "tool_net_basic"
TOOL_NET_FINE = "tool_net_fine"
TOOL_ROD = "tool_rod"
TOOL_PICK = "tool_pick"

SHOP_EXTRAS: dict[str, dict[str, Any]] = {
    FEED_ANIMAL: {"name": "动物饲料", "emoji": "🌾", "price": 12, "kind": "feed"},
    FEED_PET: {"name": "宠物饲料", "emoji": "🦴", "price": 6, "kind": "feed"},
    "bait_worm": {"name": "蚯蚓饵", "emoji": "🪱", "price": 10, "kind": "supply"},
    "drift_twine": {"name": "漂绳", "emoji": "🪢", "price": 12, "kind": "supply"},
    TOOL_NET_BASIC: {
        "name": "粗渔网", "emoji": "🕸️", "price": 28, "kind": "gear",
        "unique": True, "gear": ("net", 1),
    },
    TOOL_NET_FINE: {
        "name": "细渔网", "emoji": "🎣", "price": 75, "kind": "gear",
        "unique": True, "gear": ("net", 2),
    },
    TOOL_ROD: {
        "name": "竹钓竿", "emoji": "🎣", "price": 30, "kind": "gear",
        "unique": True, "gear": ("rod", 1),
    },
    TOOL_HOE: {"name": "锄头", "emoji": "⛏️", "price": 35, "kind": "tool", "unique": True},
    TOOL_SHOVEL: {"name": "铲子", "emoji": "🪏", "price": 42, "kind": "tool", "unique": True},
    TOOL_PICK: {
        "name": "盐风镐", "emoji": "⚒️", "price": config.QUARRY_PICK_T1_COST, "kind": "tool",
        "unique": True, "gear": ("pick", 1),
    },
    TOOL_SHEARS: {"name": "剪毛剪刀", "emoji": "✂️", "price": 45, "kind": "tool", "unique": True},
    TOOL_MILKER: {"name": "挤奶器", "emoji": "🥛", "price": 55, "kind": "tool", "unique": True},
}

SHOP_ALIASES = {
    "剪刀": TOOL_SHEARS,
    "剪毛剪刀": TOOL_SHEARS,
    "剪毛": TOOL_SHEARS,
    "shears": TOOL_SHEARS,
    "挤奶器": TOOL_MILKER,
    "挤奶": TOOL_MILKER,
    "milker": TOOL_MILKER,
    "动物饲料": FEED_ANIMAL,
    "饲料": FEED_ANIMAL,
    "畜栏饲料": FEED_ANIMAL,
    "宠物饲料": FEED_PET,
    "宠物粮": FEED_PET,
    "吉祥物饲料": FEED_PET,
    "蚯蚓饵": "bait_worm",
    "蚯蚓": "bait_worm",
    "鱼饵": "bait_worm",
    "饵": "bait_worm",
    "bait": "bait_worm",
    "worm": "bait_worm",
    "漂绳": "drift_twine",
    "绳子": "drift_twine",
    "麻绳": "drift_twine",
    "twine": "drift_twine",
    "渔网": TOOL_NET_BASIC,
    "网": TOOL_NET_BASIC,
    "粗渔网": TOOL_NET_BASIC,
    "粗网": TOOL_NET_BASIC,
    "net": TOOL_NET_BASIC,
    "net_basic": TOOL_NET_BASIC,
    "细渔网": TOOL_NET_FINE,
    "细网": TOOL_NET_FINE,
    "net_fine": TOOL_NET_FINE,
    "钓竿": TOOL_ROD,
    "鱼竿": TOOL_ROD,
    "竹钓竿": TOOL_ROD,
    "竹竿": TOOL_ROD,
    "rod": TOOL_ROD,
    "锄头": TOOL_HOE,
    "锄": TOOL_HOE,
    "hoe": TOOL_HOE,
    "铲子": TOOL_SHOVEL,
    "铲": TOOL_SHOVEL,
    "锹": TOOL_SHOVEL,
    "shovel": TOOL_SHOVEL,
    "盐风镐": TOOL_PICK,
    "镐": TOOL_PICK,
    "矿镐": TOOL_PICK,
    "pick": TOOL_PICK,
    "pickaxe": TOOL_PICK,
    "tool_pick": TOOL_PICK,
}

LOVED_CROPS = {"garlic", "chili", "ginger", "durian"}
LIKED_PREFIXES = ("crop_", "fish_", "egg", "duck_egg", "milk", "goat_milk", "wool", "honey")
DISLIKED_PREFIXES = ("manure_", "ticket_stub", "wet_note", "deco_junk_")

VISIT_LINES = [
    "杂货店不讲价。好感另算——自己人价写在脸上。",
    "种子、饲料、渔网、钓竿、蚯蚓饵、锄头铲子、盐风镐，货架上有的都能买。",
    "送礼可以。别送粪。粪我自己畜栏里有。",
    "75 折是自己人价。别想两天送熟菜刷满——心多了她懒得记账。",
    "心情好的时候会塞东西。别天天来蹲，概率就那一点。",
    "调味料种子在左边。大蒜辣椒姜香茅，厨房没这几样别来跟我哭。",
    "渔具入门在这儿买。更高档带着漂绳去 tide_ops gear upgrade。",
    "盐风镐是崖矿入门，比铲子和渔网贵。买了就能 quarry_ops 探脉 / 挖。更高档 quarry_ops 升镐。",
    "货架买的种、饲料、工具，系统回收进价九成。退货少亏一点，别当印钞反复倒卖。",
]


def day_id() -> int:
    return db.day_id()


def hearts(score: int) -> int:
    return max(0, min(HEARTS_MAX, int(score) // 10))


def zhe(heart_count: int) -> float:
    """10.0 = 原价，7.5 = 75 折。每两心 -0.5 折。"""
    pairs = max(0, min(HEARTS_MAX, heart_count)) // 2
    return 10.0 - ZHE_PER_PAIR * pairs


def price_mult(score: int) -> float:
    return zhe(hearts(score)) / 10.0


def sale_price(base: int, score: int) -> int:
    if base <= 0:
        return 0
    return max(1, math.ceil(base * price_mult(score)))


def heart_bar(score: int) -> str:
    h = hearts(score)
    return "♥" * h + "♡" * (HEARTS_MAX - h)


def shop_skus() -> list[tuple[str, int, str]]:
    rows: list[tuple[str, int, str]] = []
    for key, meta in CROPS.items():
        kind = "seasoning" if "seasoning" in meta.get("tags", ()) else "seed"
        rows.append((f"seed_{key}", meta["seed_price"], kind))
    for item, meta in SHOP_EXTRAS.items():
        rows.append((item, meta["price"], meta["kind"]))
    return rows


def unique_shop_items() -> set[str]:
    return {k for k, m in SHOP_EXTRAS.items() if m.get("unique")}


def sku_base_price(item: str) -> int | None:
    for key, price, _kind in shop_skus():
        if key == item:
            return price
    return None


def recycle_price(item: str) -> int | None:
    """系统回收价。货架货按进价九成，退货少亏一成。"""
    base = sku_base_price(item)
    if base is None:
        return None
    return max(1, int(base * config.TT_SHOP_VEND_RATE))


def resolve_shop_item(token: str) -> str | None:
    raw = (token or "").strip()
    if not raw:
        return None
    alias = SHOP_ALIASES.get(raw) or SHOP_ALIASES.get(raw.lower())
    if alias:
        return alias
    key = raw.lower().replace(" ", "_")
    if key in SHOP_EXTRAS:
        return key
    for sku, meta in SHOP_EXTRAS.items():
        if raw == meta.get("name"):
            return sku
    if raw in SHOP_EXTRAS or raw.lower() in SHOP_EXTRAS:
        return raw.lower()
    hit = resolve_item_key(raw, prefer="seed")
    if hit and sku_base_price(hit) is not None:
        return hit
    crop = resolve_crop_key(raw)
    if crop:
        seed = f"seed_{crop}"
        if sku_base_price(seed) is not None:
            return seed
    return None


async def _resolve_owned_item(
    conn: aiosqlite.Connection, steward_id: int, token: str
) -> str | None:
    """送礼认行囊里实际有的：大蒜种优先 seed_garlic，而不是作物。"""
    keys: list[str] = []
    for k in (
        resolve_shop_item(token),
        resolve_item_key(token, prefer="seed"),
        resolve_item_key(token, prefer="crop"),
        resolve_item_key(token),
    ):
        if k and k not in keys:
            keys.append(k)
    for k in keys:
        if await _satchel_has(conn, steward_id, k):
            return k
    return keys[0] if keys else None


def gift_gain(item: str) -> int:
    """未衰减的单笔基础分。件数不叠。"""
    if item.startswith("dish_"):
        return 6
    if item in ("honey",) or item.replace("crop_", "") in LOVED_CROPS:
        return 4
    if item.startswith(DISLIKED_PREFIXES) or item in ("ticket_stub", "wet_note"):
        return 0
    if item.startswith(LIKED_PREFIXES) or item in ("egg", "duck_egg", "milk", "goat_milk", "wool"):
        return 2
    return 1


def gift_scale(score: int) -> float:
    """7.5 折很难：4 心减半，8 心只剩 1/4。"""
    h = hearts(score)
    if h >= SCALE_SLOW_HEARTS:
        return 0.25
    if h >= SCALE_HALF_HEARTS:
        return 0.5
    return 1.0


def apply_gift_gain(base: int, score: int, *, cap: int | None = None) -> int:
    if base <= 0:
        return 0
    scaled = int(base * gift_scale(score))
    if scaled < 1:
        scaled = 1
    return min(cap if cap is not None else GIFT_GAIN_CAP, scaled)


def pick_mood_gift(*, rng: random.Random | None = None) -> tuple[str, str]:
    """返回 (kind, item)。kind: dish / crop / sku。权重 20 / 40 / 40。"""
    r = (rng or random).random()
    pick = (rng or random).choice
    if r < MOOD_DISH:
        key = pick(list(KITCHEN_DISHES))
        return "dish", dish_item(key, 3)
    if r < MOOD_DISH + MOOD_CROP:
        crop = pick(list(CROPS))
        return "crop", f"crop_{crop}"
    item, _price, _kind = pick(shop_skus())
    return "sku", item


def _item_label(item: str) -> str:
    return ITEM_NAMES.get(item, item)


async def _affinity(conn: aiosqlite.Connection, steward_id: int) -> int:
    cur = await conn.execute(
        "SELECT score FROM tt_affinity WHERE steward_id=?", (steward_id,)
    )
    row = await cur.fetchone()
    return int(row[0]) if row else 0


async def _set_affinity(conn: aiosqlite.Connection, steward_id: int, score: int) -> int:
    score = max(0, min(AFFINITY_MAX, score))
    await conn.execute(
        """
        INSERT INTO tt_affinity (steward_id, score, updated_at)
        VALUES (?,?,?)
        ON CONFLICT(steward_id) DO UPDATE SET score=excluded.score, updated_at=excluded.updated_at
        """,
        (steward_id, score, db.now()),
    )
    return score


async def _daily(
    conn: aiosqlite.Connection, steward_id: int, day: int
) -> dict[str, Any]:
    prev = conn.row_factory
    conn.row_factory = aiosqlite.Row
    try:
        row = await (
            await conn.execute(
                "SELECT * FROM tt_daily WHERE steward_id=? AND day=?",
                (steward_id, day),
            )
        ).fetchone()
        if row:
            return dict(row)
        await conn.execute(
            "INSERT INTO tt_daily (steward_id, day) VALUES (?,?)",
            (steward_id, day),
        )
        row = await (
            await conn.execute(
                "SELECT * FROM tt_daily WHERE steward_id=? AND day=?",
                (steward_id, day),
            )
        ).fetchone()
        return dict(row)
    finally:
        conn.row_factory = prev


async def _satchel_has(conn: aiosqlite.Connection, steward_id: int, item: str) -> bool:
    cur = await conn.execute(
        "SELECT quantity FROM satchel WHERE steward_id=? AND item=? AND quantity>0",
        (steward_id, item),
    )
    return await cur.fetchone() is not None


async def _unique_blocked(
    conn: aiosqlite.Connection, steward_id: int, item: str
) -> str | None:
    meta = SHOP_EXTRAS.get(item) or {}
    if not meta.get("unique"):
        return None
    if await _satchel_has(conn, steward_id, item):
        return f"已经有{_item_label(item)}了"
    grant = meta.get("gear")
    if grant:
        kind, tier = grant
        if kind == "pick":
            from . import quarry as quarry_mod
            prof = await quarry_mod.ensure_profile(conn, steward_id)
            if int(prof["pick_tier"]) >= int(tier):
                return (
                    f"{_item_label(item)}这档已经有了（镐 T{prof['pick_tier']}）。"
                    "更高档 `quarry_ops 升镐`"
                )
            return None
        from . import gear as gear_mod
        g = await gear_mod.get_gear(conn, steward_id)
        if g[kind] >= tier:
            return (
                f"{_item_label(item)}这档已经有了（{kind} T{g[kind]}）。"
                f"更高档 `tide_ops gear upgrade {kind}`"
            )
    return None


async def _grant_shop_gear(
    conn: aiosqlite.Connection, steward_id: int, item: str
) -> str:
    meta = SHOP_EXTRAS.get(item) or {}
    grant = meta.get("gear")
    if not grant:
        return ""
    kind, tier = grant
    if kind == "pick":
        from . import quarry as quarry_mod
        got = await quarry_mod.set_min_pick_tier(conn, steward_id, int(tier))
        return f" · 镐升至 T{got}（quarry_ops 探脉 / 挖）"
    if kind not in ("net", "rod", "bait"):
        return ""
    from . import gear as gear_mod
    g = await gear_mod.get_gear(conn, steward_id)
    if g[kind] >= tier:
        return ""
    await conn.execute(
        f"UPDATE steward_gear SET {kind}_tier=? WHERE steward_id=?",
        (tier, steward_id),
    )
    label = {"net": "渔网", "rod": "钓竿", "bait": "鱼饵"}.get(kind, kind)
    return f" · {label}升至 T{tier}"


async def _pay(conn: aiosqlite.Connection, steward_id: int, cost: int) -> int:
    cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (steward_id,))
    have = (await cur.fetchone())[0]
    if have < cost:
        raise ValueError(f"工分票不足，需要 {cost}（现 {have}）")
    await conn.execute(
        "UPDATE stewards SET tickets=tickets-? WHERE id=?",
        (cost, steward_id),
    )
    return have - cost


def _status_block(score: int) -> str:
    h = hearts(score)
    z = zhe(h)
    zhe_s = f"{z:g}折" if z != int(z) else f"{int(z)}折"
    if h >= SCALE_SLOW_HEARTS:
        pace = "送礼几乎只加 1 点"
    elif h >= SCALE_HALF_HEARTS:
        pace = "送礼收益减半"
    else:
        pace = "4 心起送礼减半，8 心起更慢"
    return (
        f"{TT_NAME}杂货店\n"
        f"好感 {score}/{AFFINITY_MAX}  {heart_bar(score)}（{h} 心）\n"
        f"现价 {zhe_s}（每两心 -0.5 折，满心 7.5 折 / 75 折）\n"
        f"涨好感难：每日 {GIFT_DAILY_CAP} 次 · {pace}"
    )


async def _maybe_mood_gift(
    conn: aiosqlite.Connection,
    steward: dict[str, Any],
    daily: dict[str, Any],
) -> str:
    if daily.get("visit_done"):
        return ""
    await conn.execute(
        "UPDATE tt_daily SET visit_done=1 WHERE steward_id=? AND day=?",
        (steward["id"], daily["day"]),
    )
    if random.random() > MOOD_CHANCE:
        return ""
    kind, item = pick_mood_gift()
    unique = unique_shop_items()
    if kind == "sku" and item in unique:
        pool = [row for row in shop_skus() if row[0] not in unique]
        if not pool:
            return ""
        item, _price, _k = random.choice(pool)
        kind = "sku"
    await db.add_item(conn, steward["id"], item, 1)
    await conn.execute(
        "UPDATE tt_daily SET mood_gift=1 WHERE steward_id=? AND day=?",
        (steward["id"], daily["day"]),
    )
    label = _item_label(item)
    if kind == "dish":
        line = flavor.pick([
            f"Tt酱把一盘还热的{label}推进你怀里：「账本顺眼，拿去。」",
            f"她从后厨端出{label}：「别问谁做的。吃。」",
        ])
    elif kind == "crop":
        line = flavor.pick([
            f"货架旁筐里滚出{label}：「熟的，别挑。」",
            f"Tt酱塞来{label}：「今早刚收的，放坏了算你的。」",
        ])
    else:
        line = flavor.pick([
            f"她随手从货架抽了{label}：「进店彩头，别指望天天有。」",
            f"Tt酱心情好：{label} x1 砸到你胸口。",
        ])
    await db.add_chronicle(
        "tt",
        f"{steward['name']} 进店碰上 Tt酱心情好，得了 {label}",
        steward["id"],
        conn=conn,
    )
    return flavor.wrap_event("good", "Tt酱心情好", line)


async def on_enter(
    conn: aiosqlite.Connection, steward: dict[str, Any]
) -> str:
    daily = await _daily(conn, steward["id"], day_id())
    return await _maybe_mood_gift(conn, steward, daily)


def _catalog_text(score: int) -> str:
    headers = {
        "seasoning": "【调味料种子】",
        "seed": "【作物种子】",
        "feed": "【饲料】",
        "supply": "【渔需】（可回购）",
        "gear": "【渔具】（限购；入门升档，更高走 tide_ops gear upgrade）",
        "tool": "【工具】（各限购 1）",
    }
    order = ("seasoning", "seed", "feed", "supply", "gear", "tool")
    groups = {k: [headers[k]] for k in order}
    for item, base, kind in shop_skus():
        price = sale_price(base, score)
        tag = ""
        if price != base:
            tag = f"（原 {base}）"
        season_mark = ""
        if item.startswith("seed_"):
            from . import season as season_mod
            season_mark = f" · {season_mod.season_tag(item[5:])}"
        groups.setdefault(kind, [f"【{kind}】"]).append(
            f"  {_item_label(item)} · {item} · {price}票{tag}{season_mark}"
        )
    from . import season as season_mod
    lines = [_status_block(score), season_mod.month_line(), "休市种子买不了；过季种子等到开窗，或 sow 棚1（温室种菜种树都不受季节）。", ""]
    for key in order:
        lines.extend(groups[key])
        lines.append("")
    lines.append("buy 物品 [数量] · gift 物品 [数量] · 中文名或 id 都行")
    lines.append("系统回收进价九成（退货少亏一成），别反复倒卖当正业")
    lines.append("行囊每种最多 24 份（和潮柜一样），买多了会拒")
    lines.append("送礼一次一笔，件数不叠；4 心起减半，8 心起更慢")
    return "\n".join(lines).rstrip()


async def tt_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    parts = command.strip().split()
    verb = (parts[0].lower() if parts else "status") or "status"

    if verb in ("help", "?", "帮助"):
        return (
            "visit_ops tt — Tt酱杂货店\n"
            "  status / catalog — 货架与好感\n"
            "  buy 物品 [数量] — 种子/饲料/渔网钓竿/蚯蚓饵/锄铲/剪刀挤奶器\n"
            "  种子看季节（一周一季）：catalog 标当季/休市；过季买不了，等到开窗或 sow 棚1\n"
            "  货架货系统回收进价九成，退货少亏一点，别买了再 tote_ops vend 当印钞\n"
            "    行囊每种最多 24 份，买多了会拒；满了先 vend 或 hut_ops 冰柜 存\n"
            "  gift 物品 [数量] — 送礼（一次一笔，每日最多 3 次；4 心减半，8 心更慢）\n"
            "  visit — 聊天；每日首次进店 10% 她心情好送礼"
        )

    if verb in ("status", "shop", "店"):
        async with db.connect() as conn:
            score = await _affinity(conn, s["id"])
            gift = await on_enter(conn, s)
            await conn.commit()
        extra = f"\n{gift}" if gift else ""
        return (
            f"{_status_block(score)}\n"
            f"{flavor.pick(VISIT_LINES)}\n"
            "catalog 看货架 · buy 物品 · gift 物品"
            f"{extra}"
        )

    if verb in ("catalog", "货架", "list"):
        async with db.connect() as conn:
            score = await _affinity(conn, s["id"])
            gift = await on_enter(conn, s)
            text = _catalog_text(score)
            await conn.commit()
        return f"{text}" + (f"\n{gift}" if gift else "")

    if verb in ("visit", "聊"):
        async with db.connect() as conn:
            score = await _affinity(conn, s["id"])
            gift = await on_enter(conn, s)
            await conn.commit()
        extra = f"\n{gift}" if gift else ""
        return f"{TT_NAME}：{flavor.pick(VISIT_LINES)}\n{_status_block(score)}{extra}"

    if verb in ("hearts", "affinity", "me", "好感"):
        async with db.connect() as conn:
            score = await _affinity(conn, s["id"])
        return _status_block(score)

    if verb == "buy":
        if len(parts) < 2:
            raise ValueError("用法: visit_ops tt buy 大蒜种 2")
        qty = 1
        name_toks = parts[1:]
        if name_toks[-1].isdigit():
            qty = max(1, int(name_toks[-1]))
            name_toks = name_toks[:-1]
        if len(name_toks) >= 2 and name_toks[0].isdigit():
            qty = max(1, int(name_toks[0]))
            name_toks = name_toks[1:]
        item = resolve_shop_item(" ".join(name_toks))
        if not item:
            raise ValueError("货架上没有这件。catalog 看种子/饲料/渔具/工具")
        if item.startswith("seed_"):
            from . import season as season_mod
            season_mod.assert_crop_in_season(item[5:])
        base = sku_base_price(item)
        if base is None:
            raise ValueError("货架上没有这件")
        async with db.connect() as conn:
            score = await _affinity(conn, s["id"])
            gift = await on_enter(conn, s)
            extra_meta = SHOP_EXTRAS.get(item) or {}
            if extra_meta.get("unique"):
                if qty != 1:
                    raise ValueError("工具/渔具限购 1")
                blocked = await _unique_blocked(conn, s["id"], item)
                if blocked:
                    raise ValueError(blocked)
            cost = sale_price(base, score) * qty
            left = await _pay(conn, s["id"], cost)
            await db.add_item(conn, s["id"], item, qty)
            gear_note = await _grant_shop_gear(conn, s["id"], item)
            await db.add_chronicle(
                "tt",
                f"{s['name']} 在 Tt酱店里买了 {_item_label(item)} x{qty}",
                s["id"],
                conn=conn,
            )
            await conn.commit()
        z = zhe(hearts(score))
        zhe_s = f"{z:g}折"
        extra = f"\n{gift}" if gift else ""
        note = ""
        if cost != base * qty:
            note = f"，原价 {base * qty}"
        return (
            f"购入 {_item_label(item)} x{qty}（-{cost} 票{note} · {zhe_s} · 余 {left}）"
            f"{gear_note}{extra}"
        )

    if verb in ("gift", "送礼"):
        if len(parts) < 2:
            raise ValueError("用法: visit_ops tt gift 大蒜  或 gift 票 12")
        qty = 1
        name_toks = parts[1:]
        if name_toks[-1].isdigit():
            qty = max(1, int(name_toks[-1]))
            name_toks = name_toks[:-1]
        token = " ".join(name_toks)
        if token in ("票", "工分票", "tickets", "ticket"):
            return await _gift_tickets(s, qty)
        return await _gift_item(s, token, qty)

    raise ValueError(
        f"未知 tt 指令: {command}（status/catalog/buy/gift/visit）"
    )


async def _gift_tickets(steward: dict[str, Any], qty: int) -> str:
    if qty < TICKET_GIFT_MIN:
        raise ValueError(f"塞票至少 {TICKET_GIFT_MIN} 张才入账。零钱她不收。")
    async with db.connect() as conn:
        daily = await _daily(conn, steward["id"], day_id())
        gift_note = await _maybe_mood_gift(conn, steward, daily)
        used = int(daily.get("gifts") or 0)
        if used >= GIFT_DAILY_CAP:
            await conn.commit()
            return f"今日送礼已满 {GIFT_DAILY_CAP} 次。Tt酱挥手：账本要下班。"
        await _pay(conn, steward["id"], qty)
        score = await _affinity(conn, steward["id"])
        raw = min(TICKET_GAIN_CAP, max(1, qty // TICKET_PER_POINT))
        gain = apply_gift_gain(raw, score, cap=TICKET_GAIN_CAP)
        new = await _set_affinity(conn, steward["id"], score + gain)
        await conn.execute(
            "UPDATE tt_daily SET gifts=gifts+1 WHERE steward_id=? AND day=?",
            (steward["id"], daily["day"]),
        )
        await conn.commit()
    extra = f"\n{gift_note}" if gift_note else ""
    return (
        f"Tt酱把 {qty} 票收进抽屉。好感 +{gain}（{score}→{new}） {heart_bar(new)}"
        f"{extra}"
    )


async def _gift_item(steward: dict[str, Any], token: str, qty: int) -> str:
    qty = max(1, qty)
    async with db.connect() as conn:
        item = await _resolve_owned_item(conn, steward["id"], token)
        if not item:
            raise ValueError("行囊里对不上这件。tote_ops list 看中文名")
        base = gift_gain(item)
        if base <= 0:
            raise ValueError("粪和废纸她自己有。换点能吃的或厨房做的。")
        daily = await _daily(conn, steward["id"], day_id())
        gift_note = await _maybe_mood_gift(conn, steward, daily)
        used = int(daily.get("gifts") or 0)
        if used >= GIFT_DAILY_CAP:
            await conn.commit()
            return f"今日送礼已满 {GIFT_DAILY_CAP} 次。Tt酱：「明天再来烦我。」"
        if not await db.take_item(conn, steward["id"], item, qty):
            raise ValueError(f"行囊没有 {_item_label(item)} x{qty}")
        score = await _affinity(conn, steward["id"])
        gain = apply_gift_gain(base, score)
        new = await _set_affinity(conn, steward["id"], score + gain)
        await conn.execute(
            "UPDATE tt_daily SET gifts=gifts+1 WHERE steward_id=? AND day=?",
            (steward["id"], daily["day"]),
        )
        await db.add_chronicle(
            "tt",
            f"{steward['name']} 给 Tt酱送了 {_item_label(item)} x{qty}",
            steward["id"],
            conn=conn,
        )
        await conn.commit()
    extra = f"\n{gift_note}" if gift_note else ""
    if base >= 4:
        reaction = "Tt酱眼睛亮了一下：「……行。」"
    elif base >= 2:
        reaction = "她点点头，收下了。"
    else:
        reaction = "她接了，表情很复杂。"
    pile = ""
    if qty > 1:
        pile = f" 一筐 {qty} 份她收下了，好感只记一笔。"
    slow = ""
    if gift_scale(score) < 1:
        slow = " 心多了，账记少。"
    return (
        f"{reaction}{pile}{slow} {_item_label(item)} x{qty} → 好感 +{gain}（{score}→{new}） "
        f"{heart_bar(new)}"
        f"{extra}"
    )


async def maybe_tt_bump(
    conn: aiosqlite.Connection,
    steward: dict[str, Any],
    trigger: str,
) -> str | None:
    """份地操作时可能撞见 Tt酱：催进店或讨一颗菜。不发货架礼，不占意外次数。"""
    if trigger not in BUMP_TRIGGERS:
        return None
    day = day_id()
    daily = await _daily(conn, steward["id"], day)
    if int(daily.get("bumps") or 0) >= BUMP_DAILY_MAX:
        return None
    if random.random() > BUMP_CHANCE:
        return None
    await conn.execute(
        "UPDATE tt_daily SET bumps=bumps+1 WHERE steward_id=? AND day=?",
        (steward["id"], day),
    )
    used = int(daily.get("gifts") or 0)
    score = await _affinity(conn, steward["id"])

    if random.random() < 0.5:
        return await _bump_ask_crop(conn, steward, daily, used, score)

    new = await _set_affinity(conn, steward["id"], score + 1)
    detail = flavor.pick([
        "Tt酱来催账：你是不是该来店里转转。好感 +1。",
        "她把新到的调味料种子在你眼前晃了一下：「visit_ops tt catalog。」好感 +1。",
    ])
    return flavor.wrap_event("neutral", "Tt酱路过", detail + f" {heart_bar(new)}")


async def _bump_ask_crop(
    conn: aiosqlite.Connection,
    steward: dict[str, Any],
    daily: dict[str, Any],
    used: int,
    score: int,
) -> str:
    if used >= GIFT_DAILY_CAP:
        detail = "Tt酱翻你行囊，又把东西放回去：「今日账本满了。进店再说。」"
        return flavor.wrap_event("neutral", "Tt酱路过", detail)
    crop_row = await (
        await conn.execute(
            """
            SELECT item FROM satchel
            WHERE steward_id=? AND quantity>0 AND item LIKE 'crop_%'
            ORDER BY RANDOM() LIMIT 1
            """,
            (steward["id"],),
        )
    ).fetchone()
    if not crop_row:
        detail = "Tt酱翻你行囊：「连颗熟菜都没有？visit_ops tt 来店里。」"
        return flavor.wrap_event("neutral", "Tt酱路过", detail)
    item = crop_row[0]
    await db.take_item(conn, steward["id"], item, 1)
    new = await _set_affinity(conn, steward["id"], score + 1)
    await conn.execute(
        "UPDATE tt_daily SET gifts=gifts+1 WHERE steward_id=? AND day=?",
        (steward["id"], daily["day"]),
    )
    label = _item_label(item)
    detail = (
        f"Tt酱盯上你行囊里的 {label}：「这筐我收下了。」"
        f"好感 +1（{score}→{new}，计入今日送礼） {heart_bar(new)}"
    )
    await db.add_chronicle(
        "tt",
        f"Tt酱向 {steward['name']} 讨走 {label}",
        steward["id"],
        conn=conn,
    )
    return flavor.wrap_event("neutral", "Tt酱讨食", detail)


def shopfront_line() -> str:
    return "Tt酱杂货店营业中 · 种子/饲料/渔网钓竿/蚯蚓饵/锄铲 · 送礼涨好感"
