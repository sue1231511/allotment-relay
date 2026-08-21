"""岸畔小屋 — 硬装 / 软装 / 升级。装件加成在 catalog hint 里写了，这里真正生效。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import aiosqlite

from . import config, db, flavor
from .catalog import (
    HUT_HARD,
    HUT_LEVELS,
    HUT_SOFT,
    ITEM_NAMES,
    LILI_DECOR,
    LILI_JUNK_DECOR,
    dish_item,
    item_label,
    resolve_item_key,
    unknown_item_message,
)


def _slots(level: int) -> tuple[list[str], list[str]]:
    meta = HUT_LEVELS.get(level, HUT_LEVELS[1])
    hard = [f"hard_{i}" for i in range(1, meta["hard"] + 1)]
    soft = [f"soft_{i}" for i in range(1, meta["soft"] + 1)]
    return hard, soft


def _catalog_item(key: str) -> tuple[str, dict[str, Any]]:
    if key in HUT_HARD:
        return "hard", HUT_HARD[key]
    if key in HUT_SOFT:
        return "soft", HUT_SOFT[key]
    raise ValueError(f"未知装件: {key}（catalog 看 hard/soft 列表）")


async def _fittings(conn: aiosqlite.Connection, steward_id: int) -> dict[str, str]:
    conn.row_factory = aiosqlite.Row
    rows = await (await conn.execute(
        "SELECT slot, item_key FROM hut_fittings WHERE steward_id=?",
        (steward_id,),
    )).fetchall()
    return {r["slot"]: r["item_key"] for r in rows}


def _fit_name(item_key: str) -> str:
    if item_key.startswith("deco_"):
        return ITEM_NAMES.get(item_key, item_key)
    return ITEM_NAMES.get(f"fit_{item_key}", item_key)


def normalize_fitting_keys(raw: set[str] | list[str]) -> set[str]:
    """fridge / plank_floor / deco_coral_lamp / coral_lamp 都能对上。"""
    out: set[str] = set()
    for v in raw:
        if not v:
            continue
        out.add(v)
        if v.startswith("deco_"):
            out.add(v[5:])
        elif v.startswith("fit_"):
            out.add(v[4:])
    return out


@dataclass
class HutBonus:
    keys: set[str] = field(default_factory=set)
    event_mult: float = 1.0
    good_share: float = 1.0
    gale_grow: float = 1.0
    gale_event: float = 1.0
    brew_mist: int = 0
    night_mist_save: int = 0
    guild_standing: int = 0
    voyage_fail: float = 1.0
    commons_chance: float = 1.0
    beach_extra: float = 0.0
    bar_tip: int = 0
    wildlife_bad: float = 1.0
    dove_steal: float = 1.0

    def has(self, *names: str) -> bool:
        return any(n in self.keys for n in names)

    def summary(self) -> str | None:
        bits = []
        if self.event_mult < 1:
            bits.append("意外↓")
        if self.good_share > 1:
            bits.append("坏事件略少")
        if self.gale_grow < 1:
            bits.append("阵风份地稳些")
        if self.brew_mist:
            bits.append("brew 雾智+")
        if self.night_mist_save:
            bits.append("暮夜雾智少掉")
        if self.guild_standing:
            bits.append("档口更顺眼")
        if self.voyage_fail < 1:
            bits.append("出海略顺")
        if self.commons_chance > 1:
            bits.append("公共物资玄学↑")
        if self.beach_extra:
            bits.append("赶海铃响")
        if self.bar_tip:
            bits.append("酒吧小费+")
        if self.has("fridge"):
            bits.append("冰箱")
        if self.has("cabinet"):
            bits.append("潮柜")
        if not bits:
            return None
        return "装件生效：" + " · ".join(bits)


def bonuses_for(keys: set[str] | list[str]) -> HutBonus:
    b = HutBonus(keys=normalize_fitting_keys(keys))
    if b.has("plank_floor"):
        b.event_mult *= 0.90
    if b.has("storm_shutter", "net_dreamcatcher"):
        b.good_share *= 1.18
        b.wildlife_bad *= 0.82
        b.gale_event *= 0.85
        b.dove_steal *= 0.7
    if b.has("rain_gutter"):
        b.gale_grow *= 0.86
        b.gale_event *= 0.90
    if b.has("glass_window"):
        b.gale_grow *= 0.92
    if b.has("brick_hearth"):
        b.brew_mist += 4
    if b.has("tide_lamp", "coral_lamp"):
        b.night_mist_save += 1
    if b.has("mint_cushion"):
        b.guild_standing += 2
    if b.has("fog_curtain", "pearl_garland"):
        b.guild_standing += 1
    if b.has("sea_chart"):
        b.voyage_fail *= 0.86
    if b.has("glass_float"):
        b.commons_chance *= 1.22
    if b.has("tide_clock"):
        b.beach_extra += 0.14
    if b.has("star_crown", "herring_mobile"):
        b.bar_tip += 2
    if b.has("shell_windchime", "kelp_tassel"):
        b.bar_tip += 1
    from .catalog import LILI_FENG_SHUI_SETS
    if b.has(*LILI_FENG_SHUI_SETS["moon_tide"]["needs"]):
        b.night_mist_save += 1
    if b.has(*LILI_FENG_SHUI_SETS["sea_dream"]["needs"]):
        b.good_share *= 1.08
        b.wildlife_bad *= 0.95
    return b


async def installed_keys(conn: aiosqlite.Connection, steward_id: int) -> set[str]:
    fittings = await _fittings(conn, steward_id)
    return normalize_fitting_keys(fittings.values())


async def get_bonuses(conn: aiosqlite.Connection, steward_id: int) -> HutBonus:
    return bonuses_for(await installed_keys(conn, steward_id))


def _fitting_bare(key: str) -> str:
    if key.startswith("deco_junk_"):
        return key
    if key.startswith("deco_"):
        return key[5:]
    if key.startswith("fit_"):
        return key[4:]
    return key


async def has_cabinet(conn: aiosqlite.Connection, steward_id: int) -> bool:
    cur = await conn.execute(
        "SELECT 1 FROM hut_fittings WHERE steward_id=? AND item_key='cabinet'",
        (steward_id,),
    )
    return bool(await cur.fetchone())


async def _cabinet_rows(conn: aiosqlite.Connection, steward_id: int) -> list[tuple[str, int]]:
    prev = conn.row_factory
    conn.row_factory = aiosqlite.Row
    try:
        rows = await (await conn.execute(
            "SELECT item, quantity FROM hut_cabinet WHERE steward_id=? AND quantity>0 ORDER BY item",
            (steward_id,),
        )).fetchall()
        return [(r["item"], r["quantity"]) for r in rows]
    finally:
        conn.row_factory = prev


async def dump_cabinet(conn: aiosqlite.Connection, steward_id: int) -> int:
    rows = await _cabinet_rows(conn, steward_id)
    moved = 0
    for item, qty in rows:
        await db.add_item(conn, steward_id, item, qty)
        moved += qty
    await conn.execute("DELETE FROM hut_cabinet WHERE steward_id=?", (steward_id,))
    return moved


async def _maybe_dump_cabinet(
    conn: aiosqlite.Connection,
    steward_id: int,
    old_key: str | None,
    *,
    except_slot: str | None = None,
) -> int:
    if _fitting_bare(old_key or "") != "cabinet":
        return 0
    sql = "SELECT 1 FROM hut_fittings WHERE steward_id=? AND item_key='cabinet'"
    args: list[Any] = [steward_id]
    if except_slot:
        sql += " AND slot!=?"
        args.append(except_slot)
    still = await (await conn.execute(sql, args)).fetchone()
    if still:
        return 0
    return await dump_cabinet(conn, steward_id)


def _wear_text(seconds: int | None) -> str:
    if seconds is None:
        return "装上日不明"
    sec = max(0, int(seconds))
    if sec < 3600:
        mins = max(1, sec // 60)
        return f"装了 {mins} 分钟"
    if sec < 86400:
        return f"装了 {sec // 3600} 小时"
    days = sec / 86400
    if days < 10:
        return f"装了 {days:.1f} 天".replace(".0", "")
    return f"装了 {int(days)} 天"


def furniture_sell_quote(cost: int, installed_at: int | None, now: int | None = None) -> dict[str, Any]:
    """买价按折旧回收。刚装约 62%，随天数掉到 25%。"""
    now = db.now() if now is None else now
    cost = max(0, int(cost))
    installed = int(installed_at or 0)
    if installed <= 0:
        rate = (config.EATERY_SELL_RATE_START + config.EATERY_SELL_RATE_FLOOR) / 2
        age_s = None
        note = "没记下装上日，按中档折旧"
    else:
        age_s = max(0, now - installed)
        days = age_s / 86400
        rate = max(
            config.EATERY_SELL_RATE_FLOOR,
            config.EATERY_SELL_RATE_START - days * config.EATERY_SELL_DECAY_PER_DAY,
        )
        if days < 0.5:
            note = "刚装上，二手也要折一截"
        elif days < 2:
            note = "用了没几天，边还新"
        elif days < 7:
            note = "旧家具，按折旧收"
        else:
            note = "用旧了，残值见底"
    refund = max(1, int(round(cost * rate))) if cost else 1
    return {
        "cost": cost,
        "rate": rate,
        "refund": refund,
        "age_s": age_s,
        "note": note,
        "pct": int(round(rate * 100)),
    }


def _fitting_value(key: str) -> dict[str, Any]:
    raw = key or ""
    if raw.startswith("deco_junk_") or raw in LILI_JUNK_DECOR:
        jk = raw.replace("deco_junk_", "") if raw.startswith("deco_junk_") else raw
        meta = LILI_JUNK_DECOR.get(jk, {})
        return {"name": meta.get("name", key), "cost": 8, "junk": True}
    if raw.startswith("deco_"):
        dk = raw[5:]
        if dk in LILI_DECOR:
            meta = LILI_DECOR[dk]
            return {"name": meta["name"], "cost": meta["sell"], "junk": False}
    bare = _fitting_bare(raw)
    if bare in LILI_DECOR:
        meta = LILI_DECOR[bare]
        return {"name": meta["name"], "cost": meta["sell"], "junk": False}
    if bare in HUT_HARD:
        meta = HUT_HARD[bare]
        return {"name": meta["name"], "cost": meta["cost"], "junk": False}
    if bare in HUT_SOFT:
        meta = HUT_SOFT[bare]
        return {"name": meta["name"], "cost": meta["cost"], "junk": False}
    raise ValueError(f"这不是能卖的家具: {key}")


def _is_fridge_key(key: str) -> bool:
    return _fitting_bare(key) == "fridge"


def _is_cabinet_key(key: str) -> bool:
    return _fitting_bare(key) == "cabinet"


async def _fitting_rows(conn: aiosqlite.Connection, steward_id: int) -> list[dict[str, Any]]:
    prev = conn.row_factory
    conn.row_factory = aiosqlite.Row
    try:
        rows = await (await conn.execute(
            """
            SELECT slot, item_key, installed_at FROM hut_fittings
            WHERE steward_id=? ORDER BY slot
            """,
            (steward_id,),
        )).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.row_factory = prev


async def _dump_meals(conn: aiosqlite.Connection, steward_id: int) -> int:
    prev = conn.row_factory
    conn.row_factory = aiosqlite.Row
    try:
        rows = await (await conn.execute(
            "SELECT dish_key, stars, quantity FROM meal_storage WHERE steward_id=?",
            (steward_id,),
        )).fetchall()
    finally:
        conn.row_factory = prev
    moved = 0
    for r in rows:
        qty = int(r["quantity"] or 1)
        await db.add_item(conn, steward_id, dish_item(r["dish_key"], r["stars"]), qty)
        moved += qty
    if moved:
        await conn.execute("DELETE FROM meal_storage WHERE steward_id=?", (steward_id,))
    return moved


def _token_hits_fitting(token: str, key: str, name: str) -> bool:
    t = token.strip().lower()
    if not t:
        return False
    bare = _fitting_bare(key).lower()
    aliases = {
        key.lower(),
        bare,
        f"fit_{bare}",
        name.lower(),
        name,
    }
    return t in aliases or t == key.lower()


async def furniture_sell_command(s: dict[str, Any], rest: list[str]) -> str:
    confirm_words = {"确认", "ok", "yes", "confirm", "卖"}
    confirm = bool(rest) and rest[-1].lower() in confirm_words
    tokens = rest[:-1] if confirm else rest
    token = " ".join(tokens).strip()

    async with db.connect() as conn:
        rows = await _fitting_rows(conn, s["id"])
        prev = conn.row_factory
        conn.row_factory = aiosqlite.Row
        try:
            stock_rows = await (await conn.execute(
                "SELECT item, quantity FROM satchel WHERE steward_id=? AND quantity>0",
                (s["id"],),
            )).fetchall()
            bag_fits = [
                (r["item"], r["quantity"]) for r in stock_rows
                if r["item"].startswith("fit_") or r["item"].startswith("deco_")
            ]
        finally:
            conn.row_factory = prev

        if not token:
            lines = ["旧家具变卖（hut_ops 卖掉 槽位|装件名 确认）:"]
            if not rows and not bag_fits:
                lines.append("  小屋和行囊都没有装件")
                return "\n".join(lines)
            for r in rows:
                val = _fitting_value(r["item_key"])
                quote = furniture_sell_quote(val["cost"], r.get("installed_at"))
                lines.append(
                    f"  {r['slot']} {_fit_name(r['item_key'])} · "
                    f"{_wear_text(quote['age_s'])} · 回收 {quote['refund']} 票（{quote['pct']}%）"
                )
            for item, qty in bag_fits:
                val = _fitting_value(item)
                quote = furniture_sell_quote(val["cost"], 0)
                extra = f" x{qty}" if qty > 1 else ""
                lines.append(
                    f"  行囊 {item_label(item)}{extra} · 未上墙按中档 {quote['refund']} 票"
                )
            lines.append("确认：hut_ops 卖掉 soft_1 确认")
            return "\n".join(lines)

        target: dict[str, Any] | None = None
        for r in rows:
            val = _fitting_value(r["item_key"])
            if token.lower() == r["slot"] or _token_hits_fitting(token, r["item_key"], val["name"]):
                target = {"where": "slot", **r, "val": val}
                break
        if target is None:
            for item, qty in bag_fits:
                val = _fitting_value(item)
                if _token_hits_fitting(token, item, val["name"]):
                    target = {"where": "bag", "item": item, "qty": qty, "val": val}
                    break
        if target is None:
            raise ValueError("找不到这件家具。hut_ops 卖掉 看清单（槽位或名字）")

        val = target["val"]
        installed_at = target.get("installed_at") if target["where"] == "slot" else 0
        quote = furniture_sell_quote(val["cost"], installed_at)
        extras: list[str] = []
        if target["where"] == "slot":
            if _is_fridge_key(target["item_key"]) and s.get("eatery_open"):
                raise ValueError("冰箱还在给小馆用。先 kitchen_ops shop 卖掉 或 shop close")
            if _is_fridge_key(target["item_key"]):
                extras.append("冰箱里的熟菜退回行囊")
            if _is_cabinet_key(target["item_key"]):
                extras.append("潮柜里的货退回行囊")
        if not confirm:
            lines = [
                f"变卖{_fit_name(target['item_key']) if target['where']=='slot' else item_label(target['item'])}",
                f"买价 {quote['cost']} 票 · {_wear_text(quote['age_s'])} · "
                f"折旧回收 {quote['refund']} 票（{quote['pct']}%）",
                quote["note"],
                *extras,
                f"确认：hut_ops 卖掉 {token} 确认",
            ]
            return "\n".join(lines)

        notes: list[str] = []
        if target["where"] == "slot":
            key = target["item_key"]
            if _is_fridge_key(key) and s.get("eatery_open"):
                raise ValueError("冰箱还在给小馆用。先 kitchen_ops shop 卖掉 或 shop close")
            if _is_cabinet_key(key):
                dumped = await _maybe_dump_cabinet(
                    conn, s["id"], key, except_slot=target["slot"],
                )
                if dumped:
                    notes.append(f"潮柜货回行囊 x{dumped}")
            if _is_fridge_key(key):
                meals = await _dump_meals(conn, s["id"])
                if meals:
                    notes.append(f"熟菜退回行囊 x{meals}")
            await conn.execute(
                "DELETE FROM hut_fittings WHERE steward_id=? AND slot=?",
                (s["id"], target["slot"]),
            )
            label = _fit_name(key)
        else:
            if not await db.take_item(conn, s["id"], target["item"], 1):
                raise ValueError("行囊里已经没有这件了")
            label = item_label(target["item"])
        await conn.execute(
            "UPDATE stewards SET tickets=tickets+? WHERE id=?",
            (quote["refund"], s["id"]),
        )
        await conn.execute(
            "UPDATE stewards SET xp = MAX(0, COALESCE(xp, 0) - ?) WHERE id=?",
            (quote["refund"], s["id"]),
        )
        await conn.commit()
    await db.add_chronicle(
        "hut",
        f"{s['name']} 变卖{label}，折旧回收 {quote['refund']} 票",
        s["id"],
    )
    extra = "。".join(notes)
    if extra:
        extra = extra + "。"
    return (
        f"{label}卖掉了。{extra}"
        f"{quote['note']} 折旧回收 {quote['refund']} 票"
        f"（买价 {quote['cost']} 的 {quote['pct']}%）。"
    )


def _cabinet_forbid(item: str) -> str | None:
    if item.startswith("dish_") or item.startswith("meal_"):
        return "熟菜放冰箱 kitchen_ops store"
    if item.startswith("live_"):
        return "活物走畜栏 hut_ops barn"
    if item.startswith("fit_"):
        return "装件直接 install，不必进柜子"
    return None


async def cabinet_command(s: dict[str, Any], rest: list[str]) -> str:
    verb = rest[0].lower() if rest else "status"
    async with db.connect() as conn:
        if not await has_cabinet(conn, s["id"]):
            raise ValueError(
                "先 hut_ops buy cabinet → install soft_N cabinet。"
                "潮柜在小屋里，小偷和斑鸠翻不到。"
            )
        if verb in ("status", "list", "看", "柜子"):
            rows = await _cabinet_rows(conn, s["id"])
            if not rows:
                return (
                    f"潮柜空（{config.CABINET_SLOTS} 格，每格最多 {config.CABINET_STACK}）。"
                    "hut_ops 柜子 存 物品 [数量]"
                )
            lines = [f"潮柜 {len(rows)}/{config.CABINET_SLOTS}:"]
            for item, qty in rows:
                lines.append(f"  {item_label(item)}（{item}） x{qty}")
            lines.append("取：hut_ops 柜子 取 物品 [数量]")
            return "\n".join(lines)

        putting = verb in ("put", "store", "存", "放", "入")
        taking = verb in ("take", "取", "拿")
        if not (putting or taking) or len(rest) < 2:
            raise ValueError("用法: hut_ops 柜子 存|取 物品 [数量]")

        tokens = rest[1:]
        qty = 1
        name_tokens = tokens
        if tokens and tokens[-1].isdigit():
            qty = max(1, int(tokens[-1]))
            name_tokens = tokens[:-1]
        if not name_tokens:
            raise ValueError("要写物品名")
        item = resolve_item_key(" ".join(name_tokens))
        if not item:
            raise ValueError(unknown_item_message(" ".join(name_tokens)))
        blocked = _cabinet_forbid(item)
        if blocked:
            raise ValueError(blocked)

        if putting:
            rows = await _cabinet_rows(conn, s["id"])
            have = {k: v for k, v in rows}
            if item not in have and len(have) >= config.CABINET_SLOTS:
                raise ValueError(f"柜子满了（{config.CABINET_SLOTS} 种）")
            stacked = have.get(item, 0)
            if stacked + qty > config.CABINET_STACK:
                raise ValueError(
                    f"{item_label(item)} 这格最多 {config.CABINET_STACK}，已有 {stacked}"
                )
            if not await db.take_item(conn, s["id"], item, qty):
                raise ValueError("行囊没有这么多")
            await conn.execute(
                """
                INSERT INTO hut_cabinet (steward_id, item, quantity, stored_at)
                VALUES (?,?,?,?)
                ON CONFLICT(steward_id, item) DO UPDATE SET
                quantity = quantity + excluded.quantity
                """,
                (s["id"], item, qty, db.now()),
            )
            await conn.commit()
            return f"入柜 {item_label(item)} x{qty}（小偷翻不到）"

        cur = await conn.execute(
            "SELECT quantity FROM hut_cabinet WHERE steward_id=? AND item=?",
            (s["id"], item),
        )
        row = await cur.fetchone()
        have_n = row[0] if row else 0
        if have_n < qty:
            raise ValueError("柜子里没有这么多")
        new_n = have_n - qty
        if new_n <= 0:
            await conn.execute(
                "DELETE FROM hut_cabinet WHERE steward_id=? AND item=?",
                (s["id"], item),
            )
        else:
            await conn.execute(
                "UPDATE hut_cabinet SET quantity=? WHERE steward_id=? AND item=?",
                (new_n, s["id"], item),
            )
        await db.add_item(conn, s["id"], item, qty)
        await conn.commit()
        return f"取出 {item_label(item)} x{qty}，回行囊"


async def hut_ops(key_id: int, command: str) -> str:
    from .game import require_steward

    s = await require_steward(key_id)
    parts = command.strip().split(maxsplit=2)
    verb = parts[0].lower() if parts else "status"

    if verb in ("cabinet", "柜子", "chest", "locker", "柜"):
        return await cabinet_command(s, command.strip().split()[1:])

    if verb in ("卖掉", "sell", "变卖", "出售"):
        return await furniture_sell_command(s, command.strip().split()[1:])

    if verb == "status":
        async with db.connect() as conn:
            fittings = await _fittings(conn, s["id"])
        if not s.get("hut_built"):
            return (
                f"小屋: 未建 — hut_ops build（{config.HUT_BUILD_COST} 票）\n"
                "建好后可 buy 硬装/软装，install 到 hard_1 soft_1 等槽位"
            )
        lvl = s.get("hut_level") or 1
        meta = HUT_LEVELS[lvl]
        hard_slots, soft_slots = _slots(lvl)
        lines = [
            f"小屋: {s.get('hut_label') or meta['name']}（Lv{lvl} {meta['name']}）",
            "硬装:",
        ]
        for slot in hard_slots:
            key = fittings.get(slot)
            lines.append(f"  {slot}: {_fit_name(key) if key else '空'}")
        lines.append("软装:")
        for slot in soft_slots:
            key = fittings.get(slot)
            lines.append(f"  {slot}: {_fit_name(key) if key else '空'}")
        if lvl < 3:
            nxt = HUT_LEVELS[lvl + 1]
            lines.append(f"升级 Lv{lvl + 1} {nxt['name']}：{nxt['upgrade']} 票 → upgrade")
        active = bonuses_for(fittings.values()).summary()
        if active:
            lines.append(active)
        if bonuses_for(fittings.values()).has("cabinet"):
            async with db.connect() as conn:
                n = len(await _cabinet_rows(conn, s["id"]))
            lines.append(f"潮柜 {n}/{config.CABINET_SLOTS} 种 — hut_ops 柜子 存|取")
        if fittings:
            lines.append("旧家具按折旧卖：hut_ops 卖掉 槽位")
        return "\n".join(lines)

    if verb == "catalog":
        kind = parts[1].lower() if len(parts) > 1 else "all"
        lines = [
            f"小屋建造：{config.HUT_BUILD_COST} 票（hut_ops build）",
            "小屋装件 catalog（buy 后 install 到槽位；旧了 hut_ops 卖掉 槽位）:",
        ]
        if kind in ("all", "hard"):
            lines.append("【硬装】")
            for k, v in HUT_HARD.items():
                lines.append(f"  {k} — {v['emoji']}{v['name']} {v['cost']} 票 · {v['hint']}")
        if kind in ("all", "soft"):
            lines.append("【软装】")
            for k, v in HUT_SOFT.items():
                lines.append(f"  {k} — {v['emoji']}{v['name']} {v['cost']} 票 · {v['hint']}")
            lines.append("【栗栗稀有装饰】deco_* — visit_ops lili 换，install soft_N 键名")
            for k, v in LILI_DECOR.items():
                lines.append(f"  {k} — {v['emoji']}{v['name']} · {v['hint']}")
        return "\n".join(lines)

    if verb == "build":
        if s.get("hut_built"):
            return "已有小屋，用 upgrade 扩建"
        async with db.connect() as conn:
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < config.HUT_BUILD_COST:
                raise ValueError(f"建小屋需要 {config.HUT_BUILD_COST} 票")
            await conn.execute(
                """
                UPDATE stewards SET tickets=tickets-?, hut_built=1, hut_level=1
                WHERE id=?
                """,
                (config.HUT_BUILD_COST, s["id"]),
            )
            await conn.commit()
        await db.add_chronicle("hut", f"{s['name']} 搭了岸畔棚屋", s["id"])
        return (
            f"棚屋就绪（-{config.HUT_BUILD_COST} 票）。"
            f"hard_1 / soft_1~2 可装 → catalog / buy / install"
        )

    if verb == "upgrade":
        if not s.get("hut_built"):
            raise ValueError("先 build 小屋")
        lvl = s.get("hut_level") or 1
        if lvl >= 3:
            return "已是联盟小宅，没法再扩了——换软装吧"
        nxt = HUT_LEVELS[lvl + 1]
        cost = nxt["upgrade"]
        async with db.connect() as conn:
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < cost:
                raise ValueError(f"升级需要 {cost} 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-?, hut_level=? WHERE id=?",
                (cost, lvl + 1, s["id"]),
            )
            await conn.commit()
        await db.add_chronicle("hut", f"{s['name']} 扩建至 {nxt['name']}", s["id"])
        return f"升级至 Lv{lvl + 1} {nxt['name']}（-{cost} 票），新槽位已开"

    if verb == "label" and len(parts) >= 2:
        if not s.get("hut_built"):
            raise ValueError("先 build 小屋")
        label = " ".join(parts[1:])[:40]
        async with db.connect() as conn:
            await conn.execute("UPDATE stewards SET hut_label=? WHERE id=?", (label, s["id"]))
            await conn.commit()
        return f"小屋命名为「{label}」"

    if verb == "buy" and len(parts) >= 2:
        key = parts[1].split()[0].lower()
        kind, meta = _catalog_item(key)
        fit_item = f"fit_{key}"
        async with db.connect() as conn:
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < meta["cost"]:
                raise ValueError(f"购买需要 {meta['cost']} 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (meta["cost"], s["id"]),
            )
            await db.add_item(conn, s["id"], fit_item, 1)
            await conn.commit()
        return f"购入 {meta['emoji']}{meta['name']}（-{meta['cost']} 票）→ install {kind}_N {key}"

    if verb == "install" and len(parts) >= 3:
        if not s.get("hut_built"):
            raise ValueError("先 build 小屋")
        slot = parts[1].lower()
        key = parts[2].lower()
        lvl = s.get("hut_level") or 1
        hard_slots, soft_slots = _slots(lvl)
        if slot not in hard_slots + soft_slots:
            raise ValueError(f"无效槽位，可用: {', '.join(hard_slots + soft_slots)}")

        if key in LILI_DECOR:
            if not slot.startswith("soft"):
                raise ValueError("栗栗稀有装饰只能装 soft 槽")
            deco_meta = LILI_DECOR[key]
            deco_item = f"deco_{key}"
            async with db.connect() as conn:
                if not await db.take_item(conn, s["id"], deco_item, 1):
                    raise ValueError(f"行囊没有 {deco_meta['name']}，先 visit_ops lili trade")
                old = await _fittings(conn, s["id"])
                dumped = 0
                if slot in old:
                    old_key = old[slot]
                    dumped = await _maybe_dump_cabinet(
                        conn, s["id"], old_key, except_slot=slot,
                    )
                    if old_key.startswith("deco_"):
                        await db.add_item(conn, s["id"], old_key, 1)
                    else:
                        await db.add_item(conn, s["id"], f"fit_{old_key}", 1)
                await conn.execute(
                    """
                    INSERT INTO hut_fittings (steward_id, slot, item_key, installed_at)
                    VALUES (?,?,?,?)
                    ON CONFLICT(steward_id, slot) DO UPDATE SET item_key=excluded.item_key,
                    installed_at=excluded.installed_at
                    """,
                    (s["id"], slot, deco_item, db.now()),
                )
                await conn.commit()
            return flavor.fill(
                flavor.pick(flavor.HUT_INSTALL_LINES),
                slot=slot,
                item=deco_meta["name"],
                hint=deco_meta["hint"],
            )

        junk_key = key[5:] if key.startswith("junk_") else key
        if junk_key in LILI_JUNK_DECOR:
            if not slot.startswith("soft"):
                raise ValueError("铃鹿乱捡款只能装 soft 槽")
            deco_meta = LILI_JUNK_DECOR[junk_key]
            deco_item = f"deco_junk_{junk_key}"
            async with db.connect() as conn:
                if not await db.take_item(conn, s["id"], deco_item, 1):
                    raise ValueError(f"行囊没有 {deco_meta['name']}")
                old = await _fittings(conn, s["id"])
                dumped = 0
                if slot in old:
                    dumped = await _maybe_dump_cabinet(
                        conn, s["id"], old[slot], except_slot=slot,
                    )
                    old_key = old[slot]
                    if old_key.startswith("deco_"):
                        await db.add_item(conn, s["id"], old_key, 1)
                    else:
                        await db.add_item(conn, s["id"], f"fit_{old_key}", 1)
                await conn.execute(
                    """
                    INSERT INTO hut_fittings (steward_id, slot, item_key, installed_at)
                    VALUES (?,?,?,?)
                    ON CONFLICT(steward_id, slot) DO UPDATE SET item_key=excluded.item_key,
                    installed_at=excluded.installed_at
                    """,
                    (s["id"], slot, deco_item, db.now()),
                )
                await db.add_chronicle(
                    "lili",
                    f"{s['name']} 把铃鹿乱捡款「{deco_meta['name']}」挂上了",
                    s["id"],
                )
                await conn.commit()
            msg = f"#{slot} 挂上 {deco_meta['emoji']}{deco_meta['name']}。{deco_meta['hint']}"
            if dumped:
                msg += f" 潮柜货回行囊 x{dumped}"
            return msg

        kind, meta = _catalog_item(key)
        if slot.startswith("hard") and kind != "hard":
            raise ValueError("硬装槽只能装 hard 类")
        if slot.startswith("soft") and kind != "soft":
            raise ValueError("软装槽只能装 soft 类")
        fit_item = f"fit_{key}"
        dumped = 0
        async with db.connect() as conn:
            if not await db.take_item(conn, s["id"], fit_item, 1):
                raise ValueError(f"行囊没有 {meta['name']}，先 buy {key}")
            old = await _fittings(conn, s["id"])
            if slot in old:
                dumped = await _maybe_dump_cabinet(
                    conn, s["id"], old[slot], except_slot=slot,
                )
                await db.add_item(conn, s["id"], f"fit_{old[slot]}", 1)
            await conn.execute(
                """
                INSERT INTO hut_fittings (steward_id, slot, item_key, installed_at)
                VALUES (?,?,?,?)
                ON CONFLICT(steward_id, slot) DO UPDATE SET item_key=excluded.item_key,
                installed_at=excluded.installed_at
                """,
                (s["id"], slot, key, db.now()),
            )
            await conn.commit()
        msg = flavor.fill(
            flavor.pick(flavor.HUT_INSTALL_LINES),
            slot=slot,
            item=meta["name"],
            hint=meta["hint"],
        )
        if dumped:
            msg += f" 潮柜货回行囊 x{dumped}"
        return msg

    if verb == "remove" and len(parts) >= 2:
        slot = parts[1].lower()
        async with db.connect() as conn:
            fittings = await _fittings(conn, s["id"])
            if slot not in fittings:
                raise ValueError("该槽位是空的")
            key = fittings[slot]
            dumped = await _maybe_dump_cabinet(conn, s["id"], key, except_slot=slot)
            await conn.execute(
                "DELETE FROM hut_fittings WHERE steward_id=? AND slot=?",
                (s["id"], slot),
            )
            if key.startswith("deco_"):
                await db.add_item(conn, s["id"], key, 1)
            else:
                await db.add_item(conn, s["id"], f"fit_{key}", 1)
            await conn.commit()
        msg = f"已拆下 {slot} 的 {_fit_name(key)}，装件回行囊"
        if dumped:
            msg += f"；潮柜货回行囊 x{dumped}"
        msg += "。要按折旧卖掉：hut_ops 卖掉 槽位"
        return msg

    raise ValueError(
        f"未知 hut 指令: {command}（status/build/upgrade/label/catalog/buy/install/remove/柜子/卖掉）"
    )
