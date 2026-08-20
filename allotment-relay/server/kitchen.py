"""厨房 — 星级料理、吃饭回精力、冰箱保鲜。"""

from __future__ import annotations

import random
from typing import Any

import aiosqlite

from . import config, db, energy, flavor, social, survival
from .catalog import (
    HEARTH_RECIPES,
    ITEM_NAMES,
    ITEM_PRICES,
    KITCHEN_DISHES,
    dish_display_name,
    dish_item,
    dish_sell_price,
    resolve_item_key,
    unknown_item_message,
)
from .game import require_steward


def _day_id() -> int:
    return db.now() // config.FORAGE_COOLDOWN_DAY


def _roll_stars(steward: dict[str, Any], dish_key: str) -> int:
    meta = KITCHEN_DISHES[dish_key]
    base = 3
    if steward.get("hut_built") and steward.get("hut_level", 0) >= 2:
        base += 1
    if "seasoning" in str(meta.get("tags", [])) or any(
        ing.startswith("crop_garlic") or ing.startswith("crop_chili") or ing.startswith("crop_ginger")
        for ing in meta["ings"]
    ):
        base += random.randint(0, 1)
    if random.random() < 0.08:
        base += 1
    if random.random() < 0.03:
        base += 1
    return max(1, min(5, base))


async def _has_fridge(conn: aiosqlite.Connection, steward_id: int) -> bool:
    cur = await conn.execute(
        "SELECT 1 FROM hut_fittings WHERE steward_id=? AND item_key='fridge'",
        (steward_id,),
    )
    return await cur.fetchone() is not None


async def _can_cook(conn: aiosqlite.Connection, steward_id: int) -> bool:
    day = _day_id()
    cur = await conn.execute(
        "SELECT count FROM kitchen_rolls WHERE steward_id=? AND day=?",
        (steward_id, day),
    )
    row = await cur.fetchone()
    used = row[0] if row else 0
    return used < config.KITCHEN_COOK_DAILY


async def _mark_cook(conn: aiosqlite.Connection, steward_id: int) -> None:
    day = _day_id()
    await conn.execute(
        """
        INSERT INTO kitchen_rolls (steward_id, day, count) VALUES (?,?,1)
        ON CONFLICT(steward_id, day) DO UPDATE SET count = count + 1
        """,
        (steward_id, day),
    )


async def kitchen_ops(key_id: int, command: str) -> str:
    parts = command.strip().split()
    verb = parts[0].lower() if parts else "menu"
    exempt = verb in ("eat", "brew", "recipes", "menu")
    s = await require_steward(key_id, exempt_duty=exempt)

    if verb == "menu":
        lines = [
            "厨房菜单（cook 菜名 / brew 材料 / eat 菜或生食）:",
            "生鱼/作物/野薄荷也可 eat，回少量精力。",
        ]
        for key, meta in KITCHEN_DISHES.items():
            ings = " + ".join(
                f"{ITEM_NAMES.get(i, i)}（{i}）" for i in meta["ings"]
            )
            lines.append(
                f"  {meta['emoji']}{meta['name']}（{key}） — {ings} "
                f"（+{meta['energy']}精力 · 基价{meta['base_sell']}票）"
            )
        lines.append("")
        lines.append("灶台 brew（回雾智，2~3 种材料；原 hearth_ops 仍可用）:")
        for sig, recipe in HEARTH_RECIPES.items():
            keys = sig.split("|")
            ings = " + ".join(f"{ITEM_NAMES.get(i, i)}（{i}）" for i in keys)
            lines.append(f"  {recipe['name']} — brew {' '.join(keys)}  · {ings}")
        lines.append("小馆: kitchen_ops shop board|open|stock|dine")
        return "\n".join(lines)

    if verb == "cook" and len(parts) >= 2:
        dish_key = parts[1].lower()
        if dish_key not in KITCHEN_DISHES:
            raise ValueError(f"未知菜品，kitchen_ops menu 查看")
        meta = KITCHEN_DISHES[dish_key]
        async with db.connect() as conn:
            if not await _can_cook(conn, s["id"]):
                raise ValueError(f"今日烹饪上限 {config.KITCHEN_COOK_DAILY}")
            for ing in meta["ings"]:
                if not await db.take_item(conn, s["id"], ing, 1):
                    raise ValueError(f"缺少 {ITEM_NAMES.get(ing, ing)}")
            stars = _roll_stars(s, dish_key)
            item = dish_item(dish_key, stars)
            await db.add_item(conn, s["id"], item, 1)
            await _mark_cook(conn, s["id"])
            await survival.bump(conn, s["id"], satiety=6, mist_wit=4)
            await conn.commit()
        sell = dish_sell_price(dish_key, stars)
        msg = (
            f"出菜 {dish_display_name(dish_key, stars)} "
            f"（建议 vend {sell} 票 · +{meta['energy']}精力若 eat）"
        )
        msg += flavor.maybe_suffix([
            "灶台：这锅有灵魂",
            "姜姨点头：够味",
            "随机组装成功，别问配方",
        ])
        await db.add_chronicle("kitchen", f"{s['name']} 做了 {meta['name']} {stars}星", s["id"])
        return msg

    if verb == "eat" and len(parts) >= 2:
        item = resolve_item_key(parts[1]) or parts[1]
        async with db.connect() as conn:
            if not await db.take_item(conn, s["id"], item, 1):
                raise ValueError(
                    f"行囊里没有 {ITEM_NAMES.get(item, item)}（{item}）"
                )
            gain = 15
            dish_key = None
            if item.startswith("dish_") and "_s" in item:
                base, star_s = item.rsplit("_s", 1)
                dish_key = base.replace("dish_", "", 1)
                if star_s.isdigit() and dish_key in KITCHEN_DISHES:
                    stars = int(star_s)
                    gain = KITCHEN_DISHES[dish_key]["energy"] + stars * 2
            elif item.startswith("dish_"):
                dish_key = item.replace("dish_", "", 1)
                if dish_key in KITCHEN_DISHES:
                    gain = KITCHEN_DISHES[dish_key]["energy"]
            elif item == "myth_octopus":
                gain = 40
            elif item.startswith("meal_"):
                gain = 12
                await survival.bump(conn, s["id"], mist_wit=6)
            elif item.startswith("crop_"):
                gain = 8
            elif item.startswith("fish_"):
                gain = 10
            elif item == "wild_mint":
                gain = 6
            else:
                raise ValueError(
                    f"{ITEM_NAMES.get(item, item)} 不能直接吃；"
                    "试试 kitchen_ops brew 或吃 meal_/dish_"
                )
            restored = await energy.restore(conn, s["id"], gain)
            await survival.bump(conn, s["id"], satiety=min(20, gain // 2 + 8))
            await conn.commit()
        return f"吃了 {ITEM_NAMES.get(item, item)}（{item}），精力 +{restored}"

    if verb == "store" and len(parts) >= 2:
        item = parts[1]
        if not item.startswith("dish_"):
            raise ValueError("只能存熟菜 dish_*")
        async with db.connect() as conn:
            if not await _has_fridge(conn, s["id"]):
                raise ValueError("需要 hut_ops install fridge 冰箱")
            cur = await conn.execute(
                "SELECT COUNT(*) FROM meal_storage WHERE steward_id=?",
                (s["id"],),
            )
            if (await cur.fetchone())[0] >= config.FRIDGE_SLOTS:
                raise ValueError(f"冰箱满了（{config.FRIDGE_SLOTS} 格）")
            if not await db.take_item(conn, s["id"], item, 1):
                raise ValueError("行囊里没有这道菜")
            dish_key, stars = item, 3
            if "_s" in item:
                base, star_s = item.rsplit("_s", 1)
                dish_key = base.replace("dish_", "", 1)
                stars = int(star_s) if star_s.isdigit() else 3
            await conn.execute(
                """
                INSERT INTO meal_storage (steward_id, dish_key, stars, quantity, stored_at)
                VALUES (?,?,?,1,?)
                """,
                (s["id"], dish_key, stars, db.now()),
            )
            await conn.commit()
        return f"已入冰箱 {ITEM_NAMES.get(item, item)}"

    if verb == "fridge":
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            rows = await (await conn.execute(
                """
                SELECT dish_key, stars, quantity, stored_at FROM meal_storage
                WHERE steward_id=? ORDER BY stored_at
                """,
                (s["id"],),
            )).fetchall()
        if not rows:
            return "冰箱空 — cook 后 store 物品"
        lines = ["冰箱:"]
        expire = config.FRIDGE_DAYS * config.FORAGE_COOLDOWN_DAY
        for r in rows:
            age = db.now() - r["stored_at"]
            stale = " ⚠快过期" if age > expire * 0.85 else ""
            name = dish_display_name(r["dish_key"], r["stars"])
            lines.append(f"  {name} x{r['quantity']}{stale}")
        lines.append("取菜: kitchen_ops take 菜名_s星")
        return "\n".join(lines)

    if verb == "take" and len(parts) >= 2:
        target = parts[1]
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            rows = [dict(r) for r in await (await conn.execute(
                "SELECT * FROM meal_storage WHERE steward_id=? ORDER BY stored_at",
                (s["id"],),
            )).fetchall()]
            picked = None
            for r in rows:
                item = dish_item(r["dish_key"], r["stars"])
                if target in (item, r["dish_key"], f"{r['dish_key']}_s{r['stars']}"):
                    picked = r
                    break
            if not picked:
                raise ValueError("冰箱里没有这道菜")
            item = dish_item(picked["dish_key"], picked["stars"])
            await db.add_item(conn, s["id"], item, 1)
            if picked["quantity"] <= 1:
                await conn.execute("DELETE FROM meal_storage WHERE id=?", (picked["id"],))
            else:
                await conn.execute(
                    "UPDATE meal_storage SET quantity=quantity-1 WHERE id=?",
                    (picked["id"],),
                )
            await conn.commit()
        return f"取出 {ITEM_NAMES.get(item, item)}"

    if verb == "vend" and len(parts) >= 2:
        item = parts[1]
        async with db.connect() as conn:
            if not await db.take_item(conn, s["id"], item, 1):
                raise ValueError("行囊里没有这道菜")
            price = 0
            if item.startswith("dish_") and "_s" in item:
                base, star_s = item.rsplit("_s", 1)
                key = base.replace("dish_", "", 1)
                if star_s.isdigit() and key in KITCHEN_DISHES:
                    price = dish_sell_price(key, int(star_s))
            if not price:
                from .catalog import ITEM_PRICES
                price = ITEM_PRICES.get(item, 0)
            if not price:
                raise ValueError("这道菜卖不出价")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets+? WHERE id=?",
                (price, s["id"]),
            )
            await conn.commit()
        return f"出售 {ITEM_NAMES.get(item, item)} +{price} 票"

    if verb in ("shop", "stall", "eatery"):
        rest = " ".join(parts[1:]) if len(parts) > 1 else "board"
        from . import eatery
        return await eatery.eatery_command(s, rest)

    if verb == "recipes":
        return await _hearth_catalog()

    if verb == "brew":
        return await _hearth_brew(s, parts[1:])

    raise ValueError(
        f"未知 kitchen 指令: {command}（menu/cook/eat/store/fridge/take/vend/brew/recipes/shop）"
    )


async def _hearth_catalog() -> str:
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            """
            SELECT h.signature, h.meal_key, p.name
            FROM hearth_discoveries h JOIN stewards p ON p.id=h.discoverer_id
            ORDER BY h.discovered_at DESC LIMIT 20
            """
        )).fetchall()
    lines = ["灶台配方（brew 材料1 材料2 [材料3]）:"]
    for sig, recipe in HEARTH_RECIPES.items():
        ings = " ".join(sig.split("|"))
        labeled = " + ".join(f"{ITEM_NAMES.get(i, i)}（{i}）" for i in sig.split("|"))
        lines.append(f"  「{recipe['name']}」 brew {ings} → {labeled} · {recipe['sell']}票级")
    if rows:
        lines.append("已点亮:")
        for r in rows:
            recipe = HEARTH_RECIPES.get(r["signature"], {})
            lines.append(f"  「{recipe.get('name', r['meal_key'])}」 by {r['name']}")
    return "\n".join(lines)


async def _hearth_brew(s: dict[str, Any], ings: list[str]) -> str:
    from .config import DAILY_BREW_LIMIT
    from . import events

    ings = sorted(ings)
    if len(ings) < 2 or len(ings) > 3:
        raise ValueError("brew 需要 2~3 种材料，kitchen_ops recipes 看配方")
    resolved: list[str] = []
    for ing in ings:
        key = resolve_item_key(ing)
        if not key:
            raise ValueError(unknown_item_message(ing))
        resolved.append(key)
    ings = sorted(resolved)
    sig = "|".join(ings)
    if sig not in HEARTH_RECIPES:
        raise ValueError("这组材料没有已知配方，kitchen_ops recipes 查看")
    recipe = HEARTH_RECIPES[sig]
    day = db.now() // 86400
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT brews_today, brew_day FROM stewards WHERE id=?", (s["id"],)
        )).fetchone()
        brews = row["brews_today"] if row["brew_day"] == day else 0
        if brews >= DAILY_BREW_LIMIT:
            raise ValueError(f"今日 brew 上限 {DAILY_BREW_LIMIT}")
        from . import hut as hut_mod
        hut_b = await hut_mod.get_bonuses(conn, s["id"])
        for item in ings:
            if not await db.take_item(conn, s["id"], item, 1):
                raise ValueError(f"缺少 {ITEM_NAMES.get(item, item)}")
        meal_ids = list(HEARTH_RECIPES.keys())
        meal_idx = meal_ids.index(sig) + 1
        meal_item = f"meal_{meal_idx}"
        await db.add_item(conn, s["id"], meal_item, 1)
        cur = await conn.execute("SELECT 1 FROM hearth_discoveries WHERE signature=?", (sig,))
        if not await cur.fetchone():
            await conn.execute(
                "INSERT INTO hearth_discoveries (signature, meal_key, discoverer_id, discovered_at) VALUES (?,?,?,?)",
                (sig, meal_item, s["id"], db.now()),
            )
            await db.add_chronicle(
                "hearth", f"{s['name']} 点亮配方「{recipe['name']}」", s["id"], conn=conn,
            )
        await conn.execute(
            "UPDATE stewards SET brews_today=?, brew_day=? WHERE id=?",
            (brews + 1 if row["brew_day"] == day else 1, day, s["id"]),
        )
        await survival.bump(conn, s["id"], satiety=10, mist_wit=8 + hut_b.brew_mist + int(social.badge_val(s, "brew_mist")))
        extra = await events.roll_after_action(s, "brew", conn)
        await conn.commit()
    msg = f"灶台煮成「{recipe['name']}」→ {meal_item}（回雾智，可 eat / shop stock）"
    if hut_b.brew_mist:
        msg += " · 砖砌灶基加持"
    return f"{msg}\n{extra}" if extra else msg
