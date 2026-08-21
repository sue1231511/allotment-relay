"""Tt酱杂货店 — 种子/饲料/畜栏工具，送礼涨好感，进店可能塞东西。"""

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
BUMP_CHANCE = config.TT_BUMP_CHANCE
BUMP_DAILY_MAX = config.TT_BUMP_DAILY_MAX
BUMP_TRIGGERS = {"sow", "tend", "gather", "forage", "guild"}

FEED_ANIMAL = "feed_animal"
FEED_PET = "feed_pet"
TOOL_SHEARS = "tool_shears"
TOOL_MILKER = "tool_milker"

SHOP_EXTRAS: dict[str, dict[str, Any]] = {
    FEED_ANIMAL: {"name": "动物饲料", "emoji": "🌾", "price": 12, "kind": "feed"},
    FEED_PET: {"name": "宠物饲料", "emoji": "🦴", "price": 6, "kind": "feed"},
    TOOL_SHEARS: {"name": "剪毛剪刀", "emoji": "✂️", "price": 45, "kind": "tool"},
    TOOL_MILKER: {"name": "挤奶器", "emoji": "🥛", "price": 55, "kind": "tool"},
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
}

LOVED_CROPS = {"garlic", "chili", "ginger", "lemongrass", "mango", "durian", "coconut", "honey"}
LIKED_PREFIXES = ("crop_", "fish_", "egg", "duck_egg", "milk", "goat_milk", "wool", "honey")
DISLIKED_PREFIXES = ("manure_", "ticket_stub", "wet_note", "deco_junk_")

VISIT_LINES = [
    "杂货店不讲价。好感另算——自己人价写在脸上。",
    "种子、饲料、剪刀、挤奶器，货架上有的都能买。",
    "送礼可以。别送粪。粪我自己畜栏里有。",
    "心情好的时候会塞东西。别天天来蹲，概率就那一点。",
    "调味料种子在左边。大蒜辣椒姜香茅，厨房没这几样别来跟我哭。",
]


def day_id() -> int:
    return db.now() // config.FORAGE_COOLDOWN_DAY


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


def sku_base_price(item: str) -> int | None:
    for key, price, _kind in shop_skus():
        if key == item:
            return price
    return None


def resolve_shop_item(token: str) -> str | None:
    raw = (token or "").strip()
    if not raw:
        return None
    alias = SHOP_ALIASES.get(raw) or SHOP_ALIASES.get(raw.lower())
    if alias:
        return alias
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
    if item.startswith("dish_"):
        return 12
    if item in ("honey",) or item.replace("crop_", "") in LOVED_CROPS:
        return 10
    if item.startswith(DISLIKED_PREFIXES) or item in ("ticket_stub", "wet_note"):
        return 1
    if item.startswith(LIKED_PREFIXES) or item in ("egg", "duck_egg", "milk", "goat_milk", "wool"):
        return 6
    return 3


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
    return (
        f"{TT_NAME}杂货店\n"
        f"好感 {score}/{AFFINITY_MAX}  {heart_bar(score)}（{h} 心）\n"
        f"现价 {zhe_s}（每两心 -0.5 折，满心 7.5 折 / 75 折）"
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
    if kind == "sku" and item in (TOOL_SHEARS, TOOL_MILKER):
        if await _satchel_has(conn, steward["id"], item):
            item, _price, _k = random.choice(
                [row for row in shop_skus() if row[0] not in (TOOL_SHEARS, TOOL_MILKER)]
            )
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
    groups = {
        "seasoning": ["【调味料种子】"],
        "seed": ["【作物种子】"],
        "feed": ["【饲料】"],
        "tool": ["【工具】（各限购 1）"],
    }
    for item, base, kind in shop_skus():
        price = sale_price(base, score)
        tag = ""
        if price != base:
            tag = f"（原 {base}）"
        groups[kind].append(f"  {_item_label(item)} · {item} · {price}票{tag}")
    lines = [_status_block(score), ""]
    for key in ("seasoning", "seed", "feed", "tool"):
        lines.extend(groups[key])
        lines.append("")
    lines.append("buy 物品 [数量] · gift 物品 [数量] · 中文名或 id 都行")
    return "\n".join(lines).rstrip()


async def tt_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    parts = command.strip().split()
    verb = (parts[0].lower() if parts else "status") or "status"

    if verb in ("help", "?", "帮助"):
        return (
            "visit_ops tt — Tt酱杂货店\n"
            "  status / catalog — 货架与好感\n"
            "  buy 物品 [数量] — 种子/饲料/剪毛剪刀/挤奶器\n"
            "  gift 物品 [数量] — 送礼涨好感（100 满，十心，每两心 -0.5 折）\n"
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
            raise ValueError("货架上没有这件。catalog 看种子/饲料/剪刀/挤奶器")
        base = sku_base_price(item)
        if base is None:
            raise ValueError("货架上没有这件")
        async with db.connect() as conn:
            score = await _affinity(conn, s["id"])
            gift = await on_enter(conn, s)
            if item in (TOOL_SHEARS, TOOL_MILKER):
                if qty != 1:
                    raise ValueError("工具限购 1 把")
                if await _satchel_has(conn, s["id"], item):
                    raise ValueError(f"已经有{_item_label(item)}了")
            cost = sale_price(base, score) * qty
            left = await _pay(conn, s["id"], cost)
            await db.add_item(conn, s["id"], item, qty)
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
            f"{extra}"
        )

    if verb in ("gift", "送礼"):
        if len(parts) < 2:
            raise ValueError("用法: visit_ops tt gift 大蒜  或 gift 票 10")
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
    if qty < 1:
        raise ValueError("票数至少 1")
    gain = max(1, qty // 8) if qty >= 5 else 1
    async with db.connect() as conn:
        daily = await _daily(conn, steward["id"], day_id())
        gift_note = await _maybe_mood_gift(conn, steward, daily)
        used = int(daily.get("gifts") or 0)
        if used >= GIFT_DAILY_CAP:
            await conn.commit()
            return f"今日送礼已满 {GIFT_DAILY_CAP} 次。Tt酱挥手：账本要下班。"
        await _pay(conn, steward["id"], qty)
        score = await _affinity(conn, steward["id"])
        new = await _set_affinity(conn, steward["id"], score + gain)
        await conn.execute(
            "UPDATE tt_daily SET gifts=gifts+1 WHERE steward_id=? AND day=?",
            (steward["id"], daily["day"]),
        )
        await conn.commit()
    extra = f"\n{gift_note}" if gift_note else ""
    return (
        f"Tt酱把 {qty} 票收进抽屉。好感 {score}→{new} {heart_bar(new)}"
        f"{extra}"
    )


async def _gift_item(steward: dict[str, Any], token: str, qty: int) -> str:
    qty = max(1, qty)
    async with db.connect() as conn:
        item = await _resolve_owned_item(conn, steward["id"], token)
        if not item:
            raise ValueError("行囊里对不上这件。tote_ops list 看中文名")
        gain = gift_gain(item) * qty
        daily = await _daily(conn, steward["id"], day_id())
        gift_note = await _maybe_mood_gift(conn, steward, daily)
        used = int(daily.get("gifts") or 0)
        if used >= GIFT_DAILY_CAP:
            await conn.commit()
            return f"今日送礼已满 {GIFT_DAILY_CAP} 次。Tt酱：「明天再来烦我。」"
        if not await db.take_item(conn, steward["id"], item, qty):
            raise ValueError(f"行囊没有 {_item_label(item)} x{qty}")
        score = await _affinity(conn, steward["id"])
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
    if gift_gain(item) <= 1:
        reaction = "她接了，表情很复杂。"
    elif gift_gain(item) >= 10:
        reaction = "Tt酱眼睛亮了一下：「……行。」"
    else:
        reaction = "她点点头，收下了。"
    return (
        f"{reaction} {_item_label(item)} x{qty} → 好感 +{new - score}（{score}→{new}） "
        f"{heart_bar(new)}"
        f"{extra}"
    )


async def maybe_tt_bump(
    conn: aiosqlite.Connection,
    steward: dict[str, Any],
    trigger: str,
) -> str | None:
    """份地操作时可能撞见 Tt酱搬货 / 塞东西 / 讨食。不占意外次数。"""
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
    roll = random.random()
    score = await _affinity(conn, steward["id"])
    if roll < 0.40:
        _kind, item = pick_mood_gift()
        await db.add_item(conn, steward["id"], item, 1)
        label = _item_label(item)
        detail = flavor.pick([
            f"巷口撞见 Tt酱搬货。她把 {label} 塞你怀里就走了。",
            f"Tt酱从筐里捞出 {label}：「拿着。挡路。」",
        ])
        await db.add_chronicle(
            "tt",
            f"{steward['name']} 路上碰上 Tt酱，得了 {label}",
            steward["id"],
            conn=conn,
        )
        return flavor.wrap_event("good", "Tt酱路过", detail)
    if roll < 0.70:
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
        if crop_row:
            item = crop_row[0]
            await db.take_item(conn, steward["id"], item, 1)
            gain = gift_gain(item)
            new = await _set_affinity(conn, steward["id"], score + gain)
            label = _item_label(item)
            detail = (
                f"Tt酱盯上你行囊里的 {label}：「这筐我收下了。」"
                f"好感 {score}→{new} {heart_bar(new)}"
            )
            await db.add_chronicle(
                "tt",
                f"Tt酱向 {steward['name']} 讨走 {label}",
                steward["id"],
                conn=conn,
            )
            return flavor.wrap_event("good", "Tt酱讨食", detail)
        detail = "Tt酱翻你行囊：「连颗熟菜都没有？明天来店里。」"
        return flavor.wrap_event("neutral", "Tt酱路过", detail)
    new = await _set_affinity(conn, steward["id"], score + 1)
    detail = flavor.pick([
        "Tt酱来催账：你是不是该来店里转转。好感 +1。",
        "她把新到的调味料种子在你眼前晃了一下：「visit_ops tt catalog。」好感 +1。",
    ])
    return flavor.wrap_event("neutral", "Tt酱路过", detail + f" {heart_bar(new)}")


def shopfront_line() -> str:
    return "Tt酱杂货店营业中 · 种子/饲料/剪刀/挤奶器 · 送礼涨好感"
