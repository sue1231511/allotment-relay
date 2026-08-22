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
    dish_energy,
    dish_ingredient_cost,
    dish_item,
    dish_sell_price,
    is_fruit_item,
    is_vegetable_item,
    item_label,
    parse_mix_item,
    register_mix_item,
    resolve_item_key,
    suggested_price,
    unknown_item_message,
    is_raw_meat,
)
from .game import require_steward

EAT_RULES = (
    "eat 可吃：熟菜 dish_/meal_（回精力大头）；水果可生吃但只回一点、连吃会营养不良；"
    "生鱼/野薄荷生吃安全；蔬菜不能生吃（cook/brew 下锅）；只有生肉 meat_* 可能感染。"
)


def _day_id() -> int:
    return db.now() // config.FORAGE_COOLDOWN_DAY


async def _ate_raw_fruit(conn: aiosqlite.Connection, steward_id: int) -> str | None:
    """生吃一口水果：连击 +1；攒够阈值落营养不良，连击清零重新数。"""
    cur = await conn.execute(
        "SELECT fruit_streak FROM stewards WHERE id=?", (steward_id,)
    )
    row = await cur.fetchone()
    streak = int(row[0] if row else 0) + 1
    await conn.execute(
        "UPDATE stewards SET fruit_streak=? WHERE id=?", (streak, steward_id)
    )
    if streak < config.FRUIT_EAT_STREAK_LIMIT:
        left = config.FRUIT_EAT_STREAK_LIMIT - streak
        return (
            f"水果当零嘴（连吃第 {streak} 口）。再连吃 {left} 口要营养不良——"
            "吃顿熟菜就清零。"
        )
    await conn.execute(
        "UPDATE stewards SET fruit_streak=0 WHERE id=?", (steward_id,)
    )
    from . import health as health_mod
    line = await health_mod.inflict(conn, steward_id, "malnutrition", source="fruit")
    tip = "吃熟菜（dish_/meal_）能压下去，visit_ops clinic treat 营养不良 也能治。"
    return f"{line}\n{tip}" if line else tip


async def ate_cooked_meal(conn: aiosqlite.Connection, steward_id: int) -> str | None:
    """熟菜下肚：水果连击清零；营养不良吃熟菜压一档，一档一档吃好。"""
    await conn.execute(
        "UPDATE stewards SET fruit_streak=0 WHERE id=?", (steward_id,)
    )
    cur = await conn.execute(
        "SELECT stage FROM steward_ailments WHERE steward_id=? AND ailment_key='malnutrition'",
        (steward_id,),
    )
    row = await cur.fetchone()
    if not row:
        return None
    stage = int(row[0] or 2)
    if stage <= 1:
        await conn.execute(
            "DELETE FROM steward_ailments WHERE steward_id=? AND ailment_key='malnutrition'",
            (steward_id,),
        )
        await conn.execute(
            "UPDATE stewards SET health=MIN(100, health+6) WHERE id=?",
            (steward_id,),
        )
        return "热乎饭下肚，🥗营养不良好利索了（身体 +6）。别再拿水果当饭。"
    await conn.execute(
        """
        UPDATE steward_ailments SET stage=1, last_treat_at=0
        WHERE steward_id=? AND ailment_key='malnutrition'
        """,
        (steward_id,),
    )
    return "热乎饭把营养不良压下一档。再吃一顿熟菜就利索了（或 visit_ops clinic treat 营养不良）。"


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


def is_cooked_item(item: str) -> bool:
    return item.startswith("dish_") or item.startswith("meal_")


def _has_star_suffix(item: str) -> bool:
    if "_s" not in item:
        return False
    _, star = item.rsplit("_s", 1)
    return star.isdigit() and 1 <= int(star) <= 5


def _resolve_cooked_token(token: str) -> str | None:
    raw = (token or "").strip()
    if not raw:
        return None
    if is_cooked_item(raw):
        return raw
    resolved = resolve_item_key(raw)
    if resolved and is_cooked_item(resolved):
        return resolved
    from . import cook_mix
    dish = cook_mix.resolve_dish_key(raw.rstrip("★☆*"))
    if dish:
        return f"dish_{dish}"
    return resolved


def _fridge_parts(item: str) -> tuple[str, int]:
    mix = parse_mix_item(item)
    if mix:
        grade, tier, sig, stars = mix
        return f"mix_{grade}{tier}_{sig}", stars
    if item.startswith("meal_"):
        return item, 3
    if item.startswith("dish_"):
        if _has_star_suffix(item):
            base, star_s = item.rsplit("_s", 1)
            return base.replace("dish_", "", 1), int(star_s)
        return item.replace("dish_", "", 1), 3
    raise ValueError("冰箱只收熟菜")


def _fridge_satchel_item(dish_key: str, stars: int) -> str:
    if dish_key.startswith("meal_"):
        return dish_key
    return dish_item(dish_key, stars)


def _fridge_label(dish_key: str, stars: int) -> str:
    if dish_key.startswith("meal_"):
        return item_label(dish_key)
    try:
        return dish_display_name(dish_key, stars)
    except KeyError:
        return item_label(_fridge_satchel_item(dish_key, stars))


async def _pick_cooked_satchel(
    conn: aiosqlite.Connection, steward_id: int, resolved: str
) -> str:
    cur = await conn.execute(
        "SELECT quantity FROM satchel WHERE steward_id=? AND item=? AND quantity>0",
        (steward_id, resolved),
    )
    if await cur.fetchone():
        return resolved
    if resolved.startswith("dish_") and not _has_star_suffix(resolved):
        cur = await conn.execute(
            """
            SELECT item FROM satchel
            WHERE steward_id=? AND quantity>0 AND item LIKE ?
            ORDER BY item DESC
            """,
            (steward_id, resolved + "_s%"),
        )
        for (item,) in await cur.fetchall():
            if item.startswith(resolved + "_s") and _has_star_suffix(item):
                return item
    raise ValueError("行囊里没有这道菜")


def _fridge_need_msg() -> str:
    return (
        "熟菜放冰箱。先 hut_ops buy fridge → install soft_N fridge，"
        "再 hut_ops 冰柜 存 菜名。kitchen_ops store 也能存。"
    )


async def fridge_status_text(s: dict[str, Any]) -> str:
    async with db.connect() as conn:
        installed = await _has_fridge(conn, s["id"])
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            """
            SELECT dish_key, stars, quantity, stored_at FROM meal_storage
            WHERE steward_id=? ORDER BY stored_at
            """,
            (s["id"],),
        )).fetchall()
    if not installed:
        return (
            "冰箱：未装 — hut_ops buy fridge → install soft_N fridge。"
            "熟菜用 hut_ops 冰柜 存 盐焗沙蟹"
        )
    if not rows:
        return (
            f"冰箱空（{config.FRIDGE_SLOTS} 格）。"
            "hut_ops 冰柜 存 盐焗沙蟹 · kitchen_ops store 菜名"
        )
    lines = [f"冰箱 {len(rows)}/{config.FRIDGE_SLOTS}:"]
    expire = config.FRIDGE_DAYS * config.FORAGE_COOLDOWN_DAY
    for r in rows:
        age = db.now() - r["stored_at"]
        stale = " ⚠快过期" if age > expire * 0.85 else ""
        lines.append(f"  {_fridge_label(r['dish_key'], r['stars'])} x{r['quantity']}{stale}")
    lines.append("取：hut_ops 冰柜 取 菜名 · kitchen_ops take 菜名")
    return "\n".join(lines)


async def fridge_put(s: dict[str, Any], token: str, qty: int = 1) -> str:
    qty = max(1, int(qty))
    resolved = _resolve_cooked_token(token)
    if not resolved or not is_cooked_item(resolved):
        raise ValueError(
            f"{token} 不是熟菜。生鲜请 hut_ops 冰柜 存（进潮柜）；熟菜才进冰箱。"
        )
    async with db.connect() as conn:
        if not await _has_fridge(conn, s["id"]):
            raise ValueError(_fridge_need_msg())
        item = await _pick_cooked_satchel(conn, s["id"], resolved)
        cur = await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item=?",
            (s["id"], item),
        )
        row = await cur.fetchone()
        have = row[0] if row else 0
        if have < qty:
            raise ValueError("行囊里没有这么多熟菜")
        dish_key, stars = _fridge_parts(item)
        cur = await conn.execute(
            """
            SELECT id, quantity FROM meal_storage
            WHERE steward_id=? AND dish_key=? AND stars=?
            ORDER BY id LIMIT 1
            """,
            (s["id"], dish_key, stars),
        )
        existing = await cur.fetchone()
        if not existing:
            cur = await conn.execute(
                "SELECT COUNT(*) FROM meal_storage WHERE steward_id=?",
                (s["id"],),
            )
            if (await cur.fetchone())[0] >= config.FRIDGE_SLOTS:
                raise ValueError(f"冰箱满了（{config.FRIDGE_SLOTS} 格）")
        if not await db.take_item(conn, s["id"], item, qty):
            raise ValueError("行囊里没有这么多熟菜")
        if existing:
            await conn.execute(
                "UPDATE meal_storage SET quantity=quantity+? WHERE id=?",
                (qty, existing[0]),
            )
        else:
            await conn.execute(
                """
                INSERT INTO meal_storage (steward_id, dish_key, stars, quantity, stored_at)
                VALUES (?,?,?,?,?)
                """,
                (s["id"], dish_key, stars, qty, db.now()),
            )
        await conn.commit()
    return f"入冰箱 {_fridge_label(dish_key, stars)} x{qty}"


def _fridge_row_matches(row: dict[str, Any], token: str) -> bool:
    dish_key = row["dish_key"]
    stars = int(row["stars"])
    item = _fridge_satchel_item(dish_key, stars)
    raw = (token or "").strip()
    bare = raw.rstrip("★☆*")
    needles: set[str] = {raw, bare}
    resolved = _resolve_cooked_token(raw)
    if resolved:
        needles.add(resolved)
        if resolved.startswith("dish_"):
            needles.add(resolved.replace("dish_", "", 1))
            if _has_star_suffix(resolved):
                needles.add(resolved.rsplit("_s", 1)[0].replace("dish_", "", 1))
    from . import cook_mix
    dish = cook_mix.resolve_dish_key(bare)
    if dish:
        needles.add(dish)
        needles.add(f"dish_{dish}")
        if dish == dish_key:
            return True
    haystack = {
        item,
        dish_key,
        f"{dish_key}_s{stars}",
        f"dish_{dish_key}",
        f"dish_{dish_key}_s{stars}",
    }
    return bool(needles & haystack)


async def fridge_take(s: dict[str, Any], token: str, qty: int = 1) -> str:
    qty = max(1, int(qty))
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        rows = [dict(r) for r in await (await conn.execute(
            "SELECT * FROM meal_storage WHERE steward_id=? ORDER BY stored_at",
            (s["id"],),
        )).fetchall()]
        picked = None
        for r in rows:
            if _fridge_row_matches(r, token):
                picked = r
                break
        if not picked:
            raise ValueError("冰箱里没有这道菜")
        have = int(picked["quantity"] or 1)
        if have < qty:
            raise ValueError("冰箱里没有这么多")
        item = _fridge_satchel_item(picked["dish_key"], picked["stars"])
        await db.add_item(conn, s["id"], item, qty)
        left = have - qty
        if left <= 0:
            await conn.execute("DELETE FROM meal_storage WHERE id=?", (picked["id"],))
        else:
            await conn.execute(
                "UPDATE meal_storage SET quantity=? WHERE id=?",
                (left, picked["id"]),
            )
        await conn.commit()
    return f"从冰箱取出 {_fridge_label(picked['dish_key'], picked['stars'])} x{qty}，回行囊"


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


async def _cook_named(s: dict[str, Any], dish_key: str) -> str:
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
    cost = dish_ingredient_cost(dish_key)
    msg = (
        f"出菜 {dish_display_name(dish_key, stars)} "
        f"（建议 vend {sell} 票 · 材料回收 {cost} · +{meta['energy']}精力若 eat）"
    )
    msg += flavor.maybe_suffix([
        "灶台：这锅有灵魂",
        "姜姨点头：够味",
        "这是定点菜谱，星级照旧。",
    ])
    await db.add_chronicle("kitchen", f"{s['name']} 做了 {meta['name']} {stars}星", s["id"])
    return msg


async def _cook_mix(s: dict[str, Any], ings: list[str]) -> str:
    from . import cook_mix
    for ing in ings:
        if cook_mix.classify(ing) == "refuse":
            raise ValueError("活物、工具、装饰、熟菜不能下锅")
    async with db.connect() as conn:
        if not await _can_cook(conn, s["id"]):
            raise ValueError(f"今日烹饪上限 {config.KITCHEN_COOK_DAILY}")
        for ing in ings:
            if not await db.take_item(conn, s["id"], ing, 1):
                raise ValueError(f"缺少 {ITEM_NAMES.get(ing, ing)}")
        result = cook_mix.score_mix(ings, s)
        await db.add_item(conn, s["id"], result.item, 1)
        await _mark_cook(conn, s["id"])
        sat = 3 if result.grade == "j" else 6
        await survival.bump(conn, s["id"], satiety=sat, mist_wit=2)
        await conn.commit()
    used = " + ".join(ITEM_NAMES.get(i, i) for i in ings)
    junk_note = "乱炖按材料身价兜底 45%，好料不至于白扔。" if result.grade == "j" else f"按星级可卖。"
    msg = (
        f"出菜 {result.display}（{result.item}）\n"
        f"材料 {used}\n"
        f"{result.comment}\n"
        f"建议 vend {result.sell} 票 · eat +{result.energy}精力。{junk_note}"
    )
    await db.add_chronicle(
        "kitchen",
        f"{s['name']} 即兴做了 {result.display}（{result.stars}星）",
        s["id"],
    )
    return msg


async def kitchen_ops(key_id: int, command: str) -> str:
    parts = command.strip().split()
    verb = parts[0].lower() if parts else "menu"
    exempt = verb in ("eat", "brew", "recipes", "menu", "help", "?", "帮助", "status")
    s = await require_steward(key_id, exempt_duty=exempt)

    if verb in ("help", "?", "帮助"):
        return (
            "kitchen_ops 子命令（整句写进 command）：\n"
            "  menu — 菜谱与定价\n"
            "  cook 菜名 — 定点菜，例如 cook 蒜蓉生蚝\n"
            "  cook 材料1 材料2 … — 自由组合 2~5 样，例如 cook 甘蓝 鲭鱼\n"
            "  eat 物品 — 回精力。熟菜回得最多；水果可生吃但只回一点、连吃会营养不良；\n"
            "             生鱼/野薄荷安全；蔬菜不能生吃；只有生肉可能感染\n"
            "             例子：eat 鲭鱼 · eat 芒果 · eat 兔肉 · eat 蒜蓉生蚝\n"
            "  vend 菜名 — 卖掉行囊里的熟菜（中文名也行；家具请 hut_ops 卖掉）\n"
            "  store 菜名 [数量] / fridge / take 菜名 — 冰箱熟菜（小屋要先装 fridge）\n"
            "             也可 hut_ops 冰柜 存|取，生鲜进潮柜、熟菜进冰箱\n"
            "  brew 材料 — 灶台（回雾智）\n"
            "  shop board — 全服谁在营业的小馆名单（店名和几道菜），不是流水也不是评价\n"
            "  shop open|stock|dine|卖掉 — 开馆 / 上菜 / 去别人家吃 / 关张回收\n"
            f"{EAT_RULES}"
        )

    if verb in ("menu", "status"):
        lines = [
            "厨房菜单（command 例子：cook 蒜蓉生蚝 / cook 甘蓝 鲭鱼 / brew 材料 / eat 鲭鱼）:",
            EAT_RULES,
            "定点菜谱如下。也可以 cook 材料自由组合（2~5 样），按星级可卖；乱搭也按材料身价兜底 45%。",
            "定点菜 3★ 起至少 1.25 倍材料回收价（直接 vend 生鲜）。小屋 Lv2 更容易出 4★。熟菜回精力 22 起，比生吃划算得多。",
        ]
        for key, meta in KITCHEN_DISHES.items():
            ings = " + ".join(
                f"{ITEM_NAMES.get(i, i)}（{i}）" for i in meta["ings"]
            )
            lines.append(
                f"  {meta['emoji']}{meta['name']}（{key}） — {ings} "
                f"（材料回收 {dish_ingredient_cost(key)} · "
                f"3★可卖 {dish_sell_price(key, 3)} · "
                f"+{meta['energy']}精力）"
            )
        lines.append("")
        lines.append("灶台 brew（回雾智，2~3 种材料）：")
        for sig, recipe in HEARTH_RECIPES.items():
            keys = sig.split("|")
            ings = " + ".join(f"{ITEM_NAMES.get(i, i)}（{i}）" for i in keys)
            lines.append(f"  {recipe['name']} — brew {' '.join(keys)}  · {ings}")
        lines.append("小馆: kitchen_ops shop board|open|stock|dine|卖掉")
        lines.append("冰箱: hut_ops 冰柜 存|取 熟菜（先装 fridge）· kitchen_ops store/fridge/take")
        return "\n".join(lines)

    if verb == "cook" and len(parts) >= 2:
        tokens = parts[1:]
        from . import cook_mix
        named = cook_mix.resolve_dish_key(tokens[0]) if len(tokens) == 1 else None
        if named:
            return await _cook_named(s, named)
        ings: list[str] = []
        for tok in tokens:
            key = resolve_item_key(tok) or cook_mix.resolve_dish_key(tok)
            if key and key in KITCHEN_DISHES and len(tokens) == 1:
                return await _cook_named(s, key)
            item = resolve_item_key(tok)
            if not item:
                raise ValueError(unknown_item_message(tok))
            ings.append(item)
        if len(ings) < 2:
            raise ValueError(
                "自由组合至少 2 样材料。定点菜：kitchen_ops cook 菜名；"
                "乱搭：cook 材料1 材料2"
            )
        matched = cook_mix.match_named_recipe(ings)
        if matched:
            return await _cook_named(s, matched)
        return await _cook_mix(s, ings)

    if verb == "eat" and len(parts) >= 2:
        token = " ".join(parts[1:])
        item = resolve_item_key(token) or token
        if not is_cooked_item(item):
            cooked = _resolve_cooked_token(token)
            if cooked and is_cooked_item(cooked):
                item = cooked
        if is_vegetable_item(item):
            raise ValueError(
                f"{item_label(item)} 是蔬菜，不能生吃——先 kitchen_ops cook 下锅"
                f"（例如 cook {ITEM_NAMES.get(item, item)} 鲭鱼）或 brew。"
                "能生吃的：水果（回得少）、生鱼、野薄荷；熟菜回得最多。"
            )
        async with db.connect() as conn:
            satchel_item = item
            if is_cooked_item(item):
                try:
                    satchel_item = await _pick_cooked_satchel(conn, s["id"], item)
                except ValueError:
                    satchel_item = item
            if not await db.take_item(conn, s["id"], satchel_item, 1):
                raise ValueError(
                    f"行囊里没有 {ITEM_NAMES.get(item, item)}（{item}）。"
                    "tote_ops list 看有什么；中文名或英文 id 都行。"
                )
            item = satchel_item
            gain = 15
            mix_e = dish_energy(item)
            if mix_e is not None:
                gain = mix_e
            elif item.startswith("dish_") and "_s" in item:
                base, star_s = item.rsplit("_s", 1)
                dish_key = base.replace("dish_", "", 1)
                if star_s.isdigit() and dish_key in KITCHEN_DISHES:
                    stars = int(star_s)
                    gain = KITCHEN_DISHES[dish_key]["energy"] + stars * 3
            elif item.startswith("dish_"):
                dish_key = item.replace("dish_", "", 1)
                if dish_key in KITCHEN_DISHES:
                    gain = KITCHEN_DISHES[dish_key]["energy"]
            elif item == "myth_octopus":
                gain = 40
            elif item.startswith("meal_"):
                gain = 18
                await survival.bump(conn, s["id"], mist_wit=6)
            elif is_fruit_item(item):
                gain = config.FRUIT_RAW_ENERGY
            elif item.startswith("fish_"):
                gain = 10
            elif item == "wild_mint":
                gain = 6
            elif is_raw_meat(item):
                gain = 12
            else:
                raise ValueError(
                    f"{ITEM_NAMES.get(item, item)} 不能直接吃。"
                    f"{EAT_RULES}"
                    "或 kitchen_ops brew 下锅。"
                )
            infect_line = None
            if is_raw_meat(item):
                from . import health as health_mod
                infect_line = await health_mod.maybe_infect_raw_meat(conn, s["id"])
            fruit_line = None
            cured_line = None
            if is_cooked_item(item) or item.startswith("meal_"):
                cured_line = await ate_cooked_meal(conn, s["id"])
            elif is_fruit_item(item):
                fruit_line = await _ate_raw_fruit(conn, s["id"])
            else:
                # 生鱼/野薄荷/生肉：不算拿水果当饭，连击清零
                await conn.execute(
                    "UPDATE stewards SET fruit_streak=0 WHERE id=?", (s["id"],)
                )
            restored = await energy.restore(conn, s["id"], gain)
            await survival.bump(conn, s["id"], satiety=min(20, gain // 2 + 8))
            await conn.commit()
        msg = f"吃了 {item_label(item)}（{item}），精力 +{restored}"
        if item.startswith("fish_") or item == "wild_mint":
            msg += "（生吃安全，不会感染）"
        if fruit_line:
            msg += f"\n{fruit_line}"
        if cured_line:
            msg += f"\n{cured_line}"
        if infect_line:
            msg += (
                f"\n{infect_line}\n"
                "→ visit_ops clinic treat infection（约三次、间隔 6 小时；第一次可以马上挂）"
            )
        return msg

    if verb == "store" and len(parts) >= 2:
        tokens = parts[1:]
        qty = 1
        if tokens[-1].isdigit():
            qty = max(1, int(tokens[-1]))
            tokens = tokens[:-1]
        if not tokens:
            raise ValueError("用法: kitchen_ops store 菜名 [数量]（或 hut_ops 冰柜 存 菜名）")
        return await fridge_put(s, " ".join(tokens), qty)

    if verb in ("fridge", "冰箱", "冰柜"):
        rest = parts[1:]
        if rest:
            sub = rest[0].lower()
            tokens = rest[1:]
            qty = 1
            if tokens and tokens[-1].isdigit():
                qty = max(1, int(tokens[-1]))
                tokens = tokens[:-1]
            if sub in ("put", "store", "存", "放", "入") and tokens:
                return await fridge_put(s, " ".join(tokens), qty)
            if sub in ("take", "取", "拿") and tokens:
                return await fridge_take(s, " ".join(tokens), qty)
        return await fridge_status_text(s)

    if verb == "take" and len(parts) >= 2:
        tokens = parts[1:]
        qty = 1
        if tokens[-1].isdigit():
            qty = max(1, int(tokens[-1]))
            tokens = tokens[:-1]
        if not tokens:
            raise ValueError("用法: kitchen_ops take 菜名 [数量]（或 hut_ops 冰柜 取 菜名）")
        return await fridge_take(s, " ".join(tokens), qty)

    if verb == "vend" and len(parts) >= 2:
        token = " ".join(parts[1:])
        resolved = _resolve_cooked_token(token) or resolve_item_key(token)
        if not resolved:
            raise ValueError(unknown_item_message(token))
        async with db.connect() as conn:
            item = resolved
            if is_cooked_item(resolved):
                try:
                    item = await _pick_cooked_satchel(conn, s["id"], resolved)
                except ValueError:
                    item = resolved
            if not await db.take_item(conn, s["id"], item, 1):
                raise ValueError("行囊里没有这道菜")
            price = suggested_price(item)
            if parse_mix_item(item):
                register_mix_item(item)
                price = suggested_price(item)
            if not price:
                price = ITEM_PRICES.get(item, 0)
            if not price:
                raise ValueError("这道菜卖不出价")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets+? WHERE id=?",
                (price, s["id"]),
            )
            await conn.commit()
        return f"出售 {item_label(item)} +{price} 票"

    if verb in ("shop", "stall", "eatery"):
        rest = " ".join(parts[1:]) if len(parts) > 1 else "board"
        from . import eatery
        return await eatery.eatery_command(s, rest)

    if verb == "recipes":
        return await _hearth_catalog()

    if verb == "brew":
        return await _hearth_brew(s, parts[1:])

    raise ValueError(
        f"未知 kitchen 指令: {command}。先 kitchen_ops help 或 menu。"
        "常用：cook 菜名 · cook 材料1 材料2 · eat 鲭鱼 · eat 芒果 · shop"
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
