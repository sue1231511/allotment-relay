"""畜栏 — 牛羊猪狗兔鸡鸭山羊蜂箱，喂食产出与日常收奶。"""

from __future__ import annotations

import random

import aiosqlite

from . import config, db, flavor
from .catalog import ITEM_NAMES, LIVESTOCK, MANURE
from .game import require_steward


def _day_id() -> int:
    return db.now() // config.FORAGE_COOLDOWN_DAY


async def has_guard_dog(conn: aiosqlite.Connection, steward_id: int) -> bool:
    cur = await conn.execute(
        "SELECT 1 FROM barn_animals WHERE steward_id=? AND species='dog' AND guard=1 LIMIT 1",
        (steward_id,),
    )
    return await cur.fetchone() is not None


def _ready(animal: dict, species: str) -> bool:
    meta = LIVESTOCK[species]
    if meta.get("guard") or meta.get("hive"):
        return False
    if not animal.get("stocked_at"):
        return False
    grow = meta["grow"]
    if animal.get("fed"):
        grow = int(grow * 0.85)
    return db.now() - animal["stocked_at"] >= grow


def _line(animal: dict | None, slot: int) -> str:
    if not animal or not animal.get("species"):
        return f"  #{slot}: 空栏"
    spec = LIVESTOCK[animal["species"]]
    if spec.get("guard"):
        state = "守夜中" if animal.get("guard") else "幼犬"
    elif spec.get("hive"):
        state = "采蜜中" if animal.get("fed") else "待喂"
    elif _ready(animal, animal["species"]):
        state = "可收"
    elif animal.get("fed"):
        extra = "·可 collect" if spec.get("daily") or spec.get("hive") else ""
        state = f"放养{extra}"
    else:
        state = "待喂"
    return f"  #{slot}: {spec['emoji']}{spec['name']}（{state}）"


async def barn_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    parts = command.strip().split(maxsplit=2)
    verb = parts[0].lower() if parts else "status"

    if verb == "status":
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            rows = await (await conn.execute(
                "SELECT * FROM barn_animals WHERE steward_id=? ORDER BY slot",
                (s["id"],),
            )).fetchall()
        built = s.get("barn_built")
        lines = [
            f"畜栏: {'已建' if built else '未建'}（erect {config.BARN_ERECT_COST} 票）",
            f"槽位 {config.BARN_SLOTS}",
        ]
        by_slot = {r["slot"]: dict(r) for r in rows}
        for slot in range(1, config.BARN_SLOTS + 1):
            lines.append(_line(by_slot.get(slot), slot))
        lines.append(f"可购: {', '.join(LIVESTOCK.keys())}")
        lines.append("catalog 看详情 · collect 日常收奶/蛋/蜜 · shear 剪羊毛（要剪刀） · churn 山羊奶→奶酪")
        return "\n".join(lines)

    if verb == "catalog":
        lines = ["畜栏图鉴（buy 物种 槽位 / feed 槽位 / harvest|collect 槽位）:"]
        for key, meta in LIVESTOCK.items():
            feed = ITEM_NAMES.get(meta["feed"], meta["feed"])
            if meta.get("guard"):
                lines.append(
                    f"  {meta['emoji']}{meta['name']} {meta['buy']}票 — 喂{feed}守夜："
                    f"野兽总掷×0.78、兔/鹿/猪权重×0.45、斑鸠偷包×0.35、拾叶小偷拆穿+0.22"
                )
            elif meta.get("hive"):
                lines.append(
                    f"  {meta['emoji']}{meta['name']} {meta['buy']}票 — "
                    f"喂{feed} x{meta['feed_qty']} · collect 采{ITEM_NAMES.get(meta['product'], meta['product'])}"
                )
            elif meta.get("daily"):
                prod = ITEM_NAMES.get(meta["product"], meta["product"])
                extra = " · 挤奶器（Tt酱）多收 1" if key in ("cow", "goat") else ""
                lines.append(
                    f"  {meta['emoji']}{meta['name']} {meta['buy']}票 — "
                    f"feed 后 collect 日常{prod} · harvest 满周期大收{extra}"
                )
            else:
                prod = ITEM_NAMES.get(meta["product"], meta["product"])
                manure = ""
                if meta.get("manure"):
                    manure = f" · 产{MANURE[meta['manure']]['name']}"
                shear = " · shear 剪毛（要剪刀，不杀羊）" if key == "sheep" else ""
                lines.append(
                    f"  {meta['emoji']}{meta['name']} {meta['buy']}票 — "
                    f"喂{feed} x{meta['feed_qty']} → {prod} x{meta['product_qty']}{manure}{shear}"
                )
        return "\n".join(lines)

    if verb == "erect":
        if s.get("barn_built"):
            return "已有畜栏"
        async with db.connect() as conn:
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < config.BARN_ERECT_COST:
                raise ValueError(f"搭建畜栏需要 {config.BARN_ERECT_COST} 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-?, barn_built=1 WHERE id=?",
                (config.BARN_ERECT_COST, s["id"]),
            )
            for slot in range(1, config.BARN_SLOTS + 1):
                await conn.execute(
                    "INSERT OR IGNORE INTO barn_animals (steward_id, slot, species, fed) VALUES (?,?,NULL,0)",
                    (s["id"], slot),
                )
            await conn.commit()
        return f"畜栏就绪（-{config.BARN_ERECT_COST} 票，{config.BARN_SLOTS} 槽）"

    if verb == "buy" and len(parts) >= 2:
        if not s.get("barn_built"):
            raise ValueError("先 barn_ops erect")
        species = parts[1].lower()
        slot = int(parts[2]) if len(parts) > 2 else 1
        if species not in LIVESTOCK:
            raise ValueError(f"可购: {', '.join(LIVESTOCK.keys())}")
        if slot < 1 or slot > config.BARN_SLOTS:
            raise ValueError(f"槽位 1~{config.BARN_SLOTS}")
        meta = LIVESTOCK[species]
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                "SELECT * FROM barn_animals WHERE steward_id=? AND slot=?",
                (s["id"], slot),
            )
            row = await cur.fetchone()
            if not row:
                await conn.execute(
                    "INSERT INTO barn_animals (steward_id, slot, species, fed) VALUES (?,?,NULL,0)",
                    (s["id"], slot),
                )
            elif row["species"]:
                raise ValueError(f"#{slot} 已有动物")
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < meta["buy"]:
                raise ValueError(f"需要 {meta['buy']} 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (meta["buy"], s["id"]),
            )
            guard = 1 if meta.get("guard") else 0
            stocked = db.now() if not meta.get("hive") else db.now()
            await conn.execute(
                """
                UPDATE barn_animals SET species=?, stocked_at=?, fed=0, guard=?
                WHERE steward_id=? AND slot=?
                """,
                (species, stocked, guard, s["id"], slot),
            )
            await conn.commit()
        if meta.get("guard"):
            return f"#{slot} 入驻 {meta['name']} — 守夜减偷菜概率"
        if meta.get("hive"):
            return f"#{slot} 安置 {meta['emoji']}{meta['name']} — feed 后 collect 采蜜"
        return f"#{slot} 购入 {meta['emoji']}{meta['name']}（-{meta['buy']} 票）"

    if verb == "feed":
        slot = int(parts[1]) if len(parts) > 1 else 1
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            row = dict(await (await conn.execute(
                "SELECT * FROM barn_animals WHERE steward_id=? AND slot=?",
                (s["id"], slot),
            )).fetchone() or {})
            if not row.get("species"):
                raise ValueError("空栏")
            meta = LIVESTOCK[row["species"]]
            if meta.get("guard"):
                if not await db.take_item(conn, s["id"], meta["feed"], meta["feed_qty"]):
                    if not await db.take_item(conn, s["id"], "feed_animal", 1):
                        raise ValueError(
                            f"喂狗需要 {ITEM_NAMES.get(meta['feed'], meta['feed'])}"
                            "（或 Tt酱店里的动物饲料）"
                        )
                await conn.execute(
                    "UPDATE barn_animals SET guard=1, fed=1 WHERE steward_id=? AND slot=?",
                    (s["id"], slot),
                )
            else:
                if row.get("fed"):
                    return f"#{slot} 今日已喂"
                if not await db.take_item(conn, s["id"], meta["feed"], meta["feed_qty"]):
                    if not await db.take_item(conn, s["id"], "feed_animal", 1):
                        raise ValueError(
                            f"需要 {ITEM_NAMES.get(meta['feed'], meta['feed'])} x{meta['feed_qty']}"
                            "（或 visit_ops tt buy 动物饲料）"
                        )
                await conn.execute(
                    "UPDATE barn_animals SET fed=1 WHERE steward_id=? AND slot=?",
                    (s["id"], slot),
                )
            manure_msg = ""
            if meta.get("manure"):
                qty = meta.get("manure_feed", 1)
                await db.add_item(conn, s["id"], meta["manure"], qty)
                manure_msg = f"，顺手收 {MANURE[meta['manure']]['name']} x{qty}"
            await conn.commit()
        return f"#{slot} 已喂食{manure_msg}"

    if verb == "collect":
        slot = int(parts[1]) if len(parts) > 1 else 1
        day = _day_id()
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            row = dict(await (await conn.execute(
                "SELECT * FROM barn_animals WHERE steward_id=? AND slot=?",
                (s["id"], slot),
            )).fetchone() or {})
            if not row.get("species"):
                raise ValueError("空栏")
            meta = LIVESTOCK[row["species"]]
            if not (meta.get("daily") or meta.get("hive")):
                raise ValueError("该动物不支持 collect，用 harvest")
            if not row.get("fed"):
                raise ValueError("先 feed 再 collect")
            cur = await conn.execute(
                "SELECT 1 FROM barn_daily_collect WHERE steward_id=? AND slot=? AND day=?",
                (s["id"], slot, day),
            )
            if await cur.fetchone():
                raise ValueError("今日已收过")
            product = meta["product"]
            qty = meta["product_qty"]
            extra = ""
            if meta.get("hive") and random.random() < 0.2:
                qty += 1
            if row["species"] in ("cow", "goat"):
                cur = await conn.execute(
                    "SELECT 1 FROM satchel WHERE steward_id=? AND item='tool_milker' AND quantity>0",
                    (s["id"],),
                )
                if await cur.fetchone():
                    qty += 1
                    extra = " · 挤奶器+1"
                else:
                    extra = " · 没挤奶器（Tt酱店有卖，装上多收 1）"
            await db.add_item(conn, s["id"], product, qty)
            await conn.execute(
                "INSERT INTO barn_daily_collect (steward_id, slot, day) VALUES (?,?,?)",
                (s["id"], slot, day),
            )
            await conn.commit()
        msg = f"#{slot} 收取 {ITEM_NAMES.get(product, product)} x{qty}{extra}"
        tail = flavor.maybe_suffix(["日常小收，积少成多", "栏里忙，票里稳"])
        if tail:
            msg += f" · {tail}"
        return msg

    if verb == "harvest":
        slot = int(parts[1]) if len(parts) > 1 else 1
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            row = dict(await (await conn.execute(
                "SELECT * FROM barn_animals WHERE steward_id=? AND slot=?",
                (s["id"], slot),
            )).fetchone() or {})
            if not row.get("species"):
                raise ValueError("空栏")
            species = row["species"]
            meta = LIVESTOCK[species]
            if meta.get("guard"):
                raise ValueError("狗不产肉，它产安全感")
            if meta.get("hive"):
                raise ValueError("蜂箱用 collect 采蜜，别连箱端走")
            if not _ready(row, species):
                raise ValueError("还没长成，继续 feed（或 daily 动物先 collect）")
            product = meta["product"]
            qty = meta["product_qty"]
            if not row.get("fed"):
                qty = max(1, qty // 2)
            await db.add_item(conn, s["id"], product, qty)
            bonus_msg = ""
            if species == "goat":
                await db.add_item(conn, s["id"], "goat_cheese", 1)
                bonus_msg = "，山羊奶酪 x1"
            manure_msg = ""
            if meta.get("manure"):
                mqty = meta.get("manure_harvest", 1)
                await db.add_item(conn, s["id"], meta["manure"], mqty)
                manure_msg = f"，{MANURE[meta['manure']]['name']} x{mqty}"
            await conn.execute(
                """
                UPDATE barn_animals SET species=NULL, stocked_at=NULL, fed=0, guard=0
                WHERE steward_id=? AND slot=?
                """,
                (s["id"], slot),
            )
            await conn.commit()
        msg = f"#{slot} 收获 {ITEM_NAMES.get(product, product)} x{qty}{bonus_msg}{manure_msg}"
        msg += flavor.maybe_suffix(["栏里忙，票里稳", "牲畜：今天也努力了"])
        await db.add_chronicle("barn", f"{s['name']} 畜栏收 {product}", s["id"])
        return msg

    if verb == "shear":
        slot = int(parts[1]) if len(parts) > 1 else 1
        day = _day_id()
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            row = dict(await (await conn.execute(
                "SELECT * FROM barn_animals WHERE steward_id=? AND slot=?",
                (s["id"], slot),
            )).fetchone() or {})
            if not row.get("species"):
                raise ValueError("空栏")
            if row["species"] != "sheep":
                raise ValueError("只有羊能剪毛")
            cur = await conn.execute(
                "SELECT 1 FROM satchel WHERE steward_id=? AND item='tool_shears' AND quantity>0",
                (s["id"],),
            )
            if not await cur.fetchone():
                raise ValueError("剪毛需要剪毛剪刀 — visit_ops tt buy 剪毛剪刀")
            if not row.get("fed"):
                raise ValueError("先 feed 再 shear")
            cur = await conn.execute(
                "SELECT 1 FROM barn_daily_collect WHERE steward_id=? AND slot=? AND day=?",
                (s["id"], slot, day),
            )
            if await cur.fetchone():
                raise ValueError("今日已剪过")
            qty = LIVESTOCK["sheep"]["product_qty"]
            await db.add_item(conn, s["id"], "wool", qty)
            await conn.execute(
                "INSERT INTO barn_daily_collect (steward_id, slot, day) VALUES (?,?,?)",
                (s["id"], slot, day),
            )
            await conn.commit()
        return (
            f"#{slot} 剪下羊毛 x{qty}（羊还在）"
            + flavor.maybe_suffix(["剪刀咔嚓，羊：还行", "不杀羊也能出毛，文明"])
        )

    if verb == "compost" and len(parts) >= 2:
        item = parts[1]
        qty = int(parts[2]) if len(parts) > 2 else 1
        if item not in MANURE:
            raise ValueError(f"可堆肥: {', '.join(MANURE.keys())}")
        yield_each = MANURE[item]["compost_yield"]
        async with db.connect() as conn:
            if not await db.take_item(conn, s["id"], item, qty):
                raise ValueError(f"缺少 {MANURE[item]['name']} x{qty}")
            total = yield_each * qty
            if s.get("mascot_trait") == "compost":
                total += qty
            await db.add_item(conn, s["id"], "compost", total)
            extra = f"+吉祥物堆肥" if s.get("mascot_trait") == "compost" else ""
            await conn.commit()
        return (
            f"{MANURE[item]['name']} x{qty} → 堆肥 x{total} "
            f"（每份{yield_each}{extra}）"
        ) + flavor.maybe_suffix(["粪肥到位，土力拉满", "大型动物回馈，堆肥桶笑纳"])

    if verb == "churn":
        qty = int(parts[1]) if len(parts) > 1 else 2
        if qty < 2:
            raise ValueError("churn 至少山羊奶 x2 → 奶酪 x1")
        milk = qty - (qty % 2)
        cheese = milk // 2
        async with db.connect() as conn:
            if not await db.take_item(conn, s["id"], "goat_milk", milk):
                raise ValueError(f"需要山羊奶 x{milk}（goat collect）")
            await db.add_item(conn, s["id"], "goat_cheese", cheese)
            await conn.commit()
        return (
            f"山羊奶 x{milk} → 山羊奶酪 x{cheese}"
        ) + flavor.maybe_suffix(["姜姨：这才叫奶制品", "厨房 goat_cheese_salad 等着"])

    raise ValueError(
        f"未知 barn 指令: {command}（status/catalog/erect/buy/feed/collect/shear/harvest/compost/churn）"
    )
