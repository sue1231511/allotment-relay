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
    MANURE,
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


FIT_ALIASES = {
    "冰柜": "fridge",
    "冰箱": "fridge",
    "icebox": "fridge",
    "freezer": "fridge",
    "潮柜": "cabinet",
    "柜子": "cabinet",
    "柜": "cabinet",
    "locker": "cabinet",
    "chest": "cabinet",
    "堆肥桶": "compost_bin",
    "肥桶": "compost_bin",
    "堆肥箱": "compost_bin",
    "composter": "compost_bin",
}

STORAGE_ALIASES = {
    "cabinet", "柜子", "chest", "locker", "柜", "潮柜",
    "冰柜", "冰箱", "icebox", "fridge", "freezer",
}

STORAGE_USAGE = (
    "用法：hut_ops 冰柜 存 甘蓝 3｜冰柜 取 甘蓝 2"
    "（柜子/潮柜/冰箱同义）。生鲜进潮柜，熟菜进冰箱。"
    "买潮柜：hut_ops buy cabinet → install soft_N cabinet；"
    "买冰箱：hut_ops buy fridge → install soft_N fridge（也可 buy 冰柜）。"
    "冰箱列出中文名+英文 id；自由组合用中文名或 dish_mix_ id 取。"
    f"潮柜基础 {config.CABINET_SLOTS} 格，满了 hut_ops 潮柜 扩（{config.CABINET_SLOT_COST}票/格，顶 {config.CABINET_SLOTS_MAX}）。"
    "粪便不能进潮柜，走 hut_ops 堆肥桶。"
)

COMPOST_BIN_ALIASES = {
    "堆肥桶", "肥桶", "堆肥箱", "compost_bin", "composter", "compostbin",
}

COMPOST_BIN_USAGE = (
    "用法：hut_ops 堆肥桶 存 羊粪 3｜堆肥桶 取 堆肥 2"
    "（肥桶/compost_bin 同义）。买：hut_ops buy compost_bin → install soft_N compost_bin。"
    "粪便不能进潮柜。丢进桶按层沤，满 7 层结 1 份堆肥（羊粪+2 / 猪粪+3 / 牛粪+4）。"
    f"桶里结好的堆肥最多囤 {config.COMPOST_BIN_READY_MAX}，先取再丢。"
)


def _resolve_fitting_key(token: str) -> str:
    raw = (token or "").strip()
    low = raw.lower()
    if raw in FIT_ALIASES:
        return FIT_ALIASES[raw]
    if low in FIT_ALIASES:
        return FIT_ALIASES[low]
    if raw in HUT_HARD or raw in HUT_SOFT:
        return raw
    if low in HUT_HARD or low in HUT_SOFT:
        return low
    for k, v in {**HUT_HARD, **HUT_SOFT}.items():
        if v["name"] == raw:
            return k
    return low


def _catalog_item(key: str) -> tuple[str, dict[str, Any]]:
    key = _resolve_fitting_key(key)
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
    quarry_energy_save: int = 0
    bar_tip: int = 0
    wildlife_bad: float = 1.0
    dove_steal: float = 1.0
    salvage_empty: float = 1.0

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
        if self.quarry_energy_save:
            bits.append("崖矿省力")
        if self.has("boat_rib"):
            bits.append("铁肋护船")
        if self.bar_tip:
            bits.append("酒吧小费+")
        if self.salvage_empty < 1:
            bits.append("打捞少空")
        if self.has("iron_edge"):
            bits.append("铁锄刃松土")
        if self.has("tide_crest"):
            bits.append("潮冠压舱")
        if self.has("fridge"):
            bits.append("冰箱")
        if self.has("cabinet"):
            bits.append("潮柜")
        if self.has("compost_bin"):
            bits.append("堆肥桶")
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
    if b.has("miner_lamp"):
        b.quarry_energy_save += 1
    if b.has("lamp_wick"):
        b.quarry_energy_save += 1
    if b.has("copper_chime"):
        b.bar_tip += 1
    if b.has("boat_rib"):
        b.voyage_fail *= 0.90
    if b.has("salt_stool"):
        b.guild_standing += 1
    if b.has("tide_weight"):
        b.commons_chance *= 1.22
        b.beach_extra += 0.10
    if b.has("marrow_sieve"):
        b.salvage_empty *= 0.70
    if b.has("anvil_plaque"):
        b.brew_mist += 2
    if b.has("tide_crest"):
        b.event_mult *= 0.92
        b.guild_standing += 2
    if b.has("marrow_jar"):
        b.night_mist_save += 1
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


def cabinet_capacity(extra: int | None) -> int:
    extra_n = max(0, int(extra or 0))
    return min(config.CABINET_SLOTS_MAX, config.CABINET_SLOTS + extra_n)


async def _cabinet_extra(conn: aiosqlite.Connection, steward_id: int) -> int:
    cur = await conn.execute(
        "SELECT cabinet_extra FROM stewards WHERE id=?", (steward_id,)
    )
    row = await cur.fetchone()
    return int((row[0] if row else 0) or 0)


async def has_cabinet(conn: aiosqlite.Connection, steward_id: int) -> bool:
    cur = await conn.execute(
        "SELECT 1 FROM hut_fittings WHERE steward_id=? AND item_key='cabinet'",
        (steward_id,),
    )
    return bool(await cur.fetchone())


async def has_fridge(conn: aiosqlite.Connection, steward_id: int) -> bool:
    cur = await conn.execute(
        "SELECT 1 FROM hut_fittings WHERE steward_id=? AND item_key='fridge'",
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
        await db.add_item(conn, steward_id, item, qty, over_cap=True)
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


def _is_compost_bin_key(key: str) -> bool:
    return _fitting_bare(key) == "compost_bin"


async def has_compost_bin(conn: aiosqlite.Connection, steward_id: int) -> bool:
    cur = await conn.execute(
        "SELECT 1 FROM hut_fittings WHERE steward_id=? AND item_key='compost_bin'",
        (steward_id,),
    )
    return bool(await cur.fetchone())


async def _compost_bin_row(conn: aiosqlite.Connection, steward_id: int) -> tuple[int, int]:
    cur = await conn.execute(
        "SELECT fill, ready FROM hut_compost_bin WHERE steward_id=?",
        (steward_id,),
    )
    row = await cur.fetchone()
    if not row:
        return 0, 0
    return int(row[0] or 0), int(row[1] or 0)


async def _compost_bin_save(
    conn: aiosqlite.Connection, steward_id: int, fill: int, ready: int,
) -> None:
    await conn.execute(
        """
        INSERT INTO hut_compost_bin (steward_id, fill, ready)
        VALUES (?,?,?)
        ON CONFLICT(steward_id) DO UPDATE SET fill=excluded.fill, ready=excluded.ready
        """,
        (steward_id, fill, ready),
    )


async def dump_compost_bin(conn: aiosqlite.Connection, steward_id: int) -> int:
    _fill, ready = await _compost_bin_row(conn, steward_id)
    if ready:
        await db.add_item(conn, steward_id, "compost", ready, over_cap=True)
    await conn.execute("DELETE FROM hut_compost_bin WHERE steward_id=?", (steward_id,))
    return ready


async def _maybe_dump_compost_bin(
    conn: aiosqlite.Connection,
    steward_id: int,
    old_key: str | None,
    *,
    except_slot: str | None = None,
) -> int:
    if _fitting_bare(old_key or "") != "compost_bin":
        return 0
    sql = "SELECT 1 FROM hut_fittings WHERE steward_id=? AND item_key='compost_bin'"
    args: list[Any] = [steward_id]
    if except_slot:
        sql += " AND slot!=?"
        args.append(except_slot)
    still = await (await conn.execute(sql, args)).fetchone()
    if still:
        return 0
    return await dump_compost_bin(conn, steward_id)


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
        await db.add_item(
            conn, steward_id, dish_item(r["dish_key"], r["stars"]), qty, over_cap=True,
        )
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
            if _is_compost_bin_key(target["item_key"]):
                extras.append("桶里结好的堆肥退回行囊（未满的层数会散掉）")
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
            if _is_compost_bin_key(key):
                ready = await _maybe_dump_compost_bin(
                    conn, s["id"], key, except_slot=target["slot"],
                )
                if ready:
                    notes.append(f"堆肥桶结肥回行囊 x{ready}")
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
    if item.startswith("manure_"):
        return (
            "粪便别进潮柜，恶心。装堆肥桶：hut_ops buy compost_bin → install soft_N compost_bin，"
            "再 hut_ops 堆肥桶 存 羊粪 3"
        )
    if item.startswith("dish_") or item.startswith("meal_"):
        return "熟菜放冰箱 — hut_ops 冰柜 存 菜名（先 buy fridge → install）"
    if item.startswith("live_"):
        return "活物走畜栏 hut_ops barn"
    if item.startswith("fit_"):
        return "装件直接 install，不必进柜子"
    return None


def _split_storage_item_qty(tokens: list[str]) -> tuple[str, int]:
    qty = 1
    name_tokens = list(tokens)
    if name_tokens and name_tokens[-1].isdigit():
        qty = max(1, int(name_tokens[-1]))
        name_tokens = name_tokens[:-1]
    if not name_tokens:
        raise ValueError("要写物品名")
    return " ".join(name_tokens), qty


def _resolve_storage_item(raw: str) -> str | None:
    item = resolve_item_key(raw)
    if item:
        return item
    from . import cook_mix
    dish = cook_mix.resolve_dish_key(raw.rstrip("★☆*"))
    if dish:
        return f"dish_{dish}"
    if raw.startswith("dish_") or raw.startswith("meal_"):
        return raw
    return None


def _parse_storage_item_qty(tokens: list[str]) -> tuple[str, int]:
    raw, qty = _split_storage_item_qty(tokens)
    item = _resolve_storage_item(raw)
    if not item:
        raise ValueError(unknown_item_message(raw))
    return item, qty


def _is_cooked_item(item: str) -> bool:
    return item.startswith("dish_") or item.startswith("meal_")


async def _cabinet_status_text(s: dict[str, Any]) -> str:
    async with db.connect() as conn:
        installed = await has_cabinet(conn, s["id"])
        extra = await _cabinet_extra(conn, s["id"]) if installed else 0
        rows = await _cabinet_rows(conn, s["id"]) if installed else []
    if not installed:
        return (
            "潮柜：未装 — hut_ops buy cabinet → install soft_N cabinet。"
            "生鲜用 hut_ops 冰柜 存 甘蓝 3（小偷翻不到）"
        )
    cap = cabinet_capacity(extra)
    expand_hint = (
        f"满了 hut_ops 潮柜 扩（{config.CABINET_SLOT_COST}票/格，顶 {config.CABINET_SLOTS_MAX}）"
    )
    if not rows:
        return (
            f"潮柜空（{cap} 格，每格最多 {config.CABINET_STACK}）。"
            f"hut_ops 冰柜 存 甘蓝 3。{expand_hint}"
        )
    lines = [f"潮柜 {len(rows)}/{cap}:"]
    for item, qty in rows:
        lines.append(f"  {item_label(item)}（{item}） x{qty}")
    lines.append("取：hut_ops 冰柜 取 物品 [数量]")
    if cap < config.CABINET_SLOTS_MAX:
        lines.append(expand_hint)
    return "\n".join(lines)


async def storage_status(s: dict[str, Any]) -> str:
    from . import kitchen
    cab = await _cabinet_status_text(s)
    fridge = await kitchen.fridge_status_text(s)
    return "\n".join([
        "小屋存菜（生鲜进潮柜，熟菜进冰箱）",
        STORAGE_USAGE,
        cab,
        fridge,
    ])


async def cabinet_put(s: dict[str, Any], item: str, qty: int) -> str:
    async with db.connect() as conn:
        if not await has_cabinet(conn, s["id"]):
            raise ValueError(
                "生鲜放潮柜。先 hut_ops buy cabinet → install soft_N cabinet，"
                "再 hut_ops 冰柜 存 甘蓝 3。潮柜在小屋里，小偷和斑鸠翻不到。"
            )
        blocked = _cabinet_forbid(item)
        if blocked:
            raise ValueError(blocked)
        rows = await _cabinet_rows(conn, s["id"])
        have = {k: v for k, v in rows}
        cap = cabinet_capacity(await _cabinet_extra(conn, s["id"]))
        if item not in have and len(have) >= cap:
            raise ValueError(
                f"柜子满了（{cap} 种）。hut_ops 潮柜 扩 再买一格"
                f"（{config.CABINET_SLOT_COST}票，顶 {config.CABINET_SLOTS_MAX}）"
            )
        stacked = have.get(item, 0)
        if stacked + qty > config.CABINET_STACK:
            raise ValueError(
                f"{item_label(item)} 这格最多叠 {config.CABINET_STACK} 份（同种货栈上限，防单格囤货），"
                f"已有 {stacked}。多出来的先 vend 或 cook，或换另一种货占新格。"
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


async def cabinet_take(s: dict[str, Any], item: str, qty: int) -> str:
    async with db.connect() as conn:
        if not await has_cabinet(conn, s["id"]):
            raise ValueError(
                "还没装潮柜。hut_ops buy cabinet → install soft_N cabinet。"
                "熟菜走冰箱：hut_ops 冰柜 取 菜名"
            )
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


async def cabinet_expand(s: dict[str, Any], n: int = 1) -> str:
    n = max(1, int(n))
    async with db.connect() as conn:
        if not await has_cabinet(conn, s["id"]):
            raise ValueError(
                "先装潮柜再扩格。hut_ops buy cabinet → install soft_N cabinet"
            )
        extra = await _cabinet_extra(conn, s["id"])
        cap = cabinet_capacity(extra)
        room = config.CABINET_SLOTS_MAX - cap
        if room <= 0:
            raise ValueError(f"潮柜已经扩到顶了（{config.CABINET_SLOTS_MAX} 格）")
        n = min(n, room)
        cost = n * config.CABINET_SLOT_COST
        cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
        have = (await cur.fetchone())[0]
        if have < cost:
            raise ValueError(
                f"加 {n} 格需要 {cost} 票（每格 {config.CABINET_SLOT_COST}）"
            )
        await conn.execute(
            "UPDATE stewards SET tickets=tickets-?, cabinet_extra=cabinet_extra+? WHERE id=?",
            (cost, n, s["id"]),
        )
        await conn.commit()
        new_cap = cabinet_capacity(extra + n)
    return (
        f"潮柜加了 {n} 格（-{cost} 票）。现在 {new_cap}/{config.CABINET_SLOTS_MAX} 格，"
        f"每格最多 {config.CABINET_STACK}。格子跟着人走，卸了柜子再装还在。"
    )


async def cabinet_command(s: dict[str, Any], rest: list[str]) -> str:
    verb = rest[0].lower() if rest else "status"
    if verb in ("status", "list", "看", "柜子", "潮柜", "冰柜", "冰箱"):
        return await storage_status(s)

    if verb in ("扩", "扩容", "加格", "买格", "expand"):
        n = 1
        if len(rest) > 1 and rest[1].isdigit():
            n = max(1, int(rest[1]))
        return await cabinet_expand(s, n)

    putting = verb in ("put", "store", "存", "放", "入")
    taking = verb in ("take", "取", "拿")
    if not (putting or taking) or len(rest) < 2:
        raise ValueError(STORAGE_USAGE)

    raw, qty = _split_storage_item_qty(rest[1:])
    item = _resolve_storage_item(raw)
    from . import kitchen
    if putting:
        if item and _is_cooked_item(item):
            return await kitchen.fridge_put(s, item, qty)
        if item:
            return await cabinet_put(s, item, qty)
        try:
            return await kitchen.fridge_put(s, raw, qty)
        except ValueError as exc:
            msg = str(exc)
            if "不是熟菜" in msg or "行囊里没有这道菜" in msg:
                raise ValueError(unknown_item_message(raw)) from exc
            raise
    if item and not _is_cooked_item(item):
        return await cabinet_take(s, item, qty)
    try:
        return await kitchen.fridge_take(s, item or raw, qty)
    except ValueError as exc:
        if item and _is_cooked_item(item):
            raise
        if item:
            return await cabinet_take(s, item, qty)
        raise


def _compost_bin_need_msg() -> str:
    return (
        "还没装堆肥桶。粪便别进潮柜。"
        "hut_ops buy compost_bin → install soft_N compost_bin，"
        "再 hut_ops 堆肥桶 存 羊粪 3"
    )


async def compost_bin_status_text(s: dict[str, Any]) -> str:
    async with db.connect() as conn:
        installed = await has_compost_bin(conn, s["id"])
        fill, ready = await _compost_bin_row(conn, s["id"]) if installed else (0, 0)
    layers = config.COMPOST_BIN_LAYERS
    if not installed:
        return _compost_bin_need_msg()
    return "\n".join([
        f"堆肥桶 {fill}/{layers} 层，可取堆肥 x{ready}（桶里最多囤 {config.COMPOST_BIN_READY_MAX}）",
        COMPOST_BIN_USAGE,
        "搅一搅不会涨层——跟 MC 一样，丢粪便才沤，满了再取。",
    ])


async def compost_bin_put(s: dict[str, Any], item: str, qty: int) -> str:
    qty = max(1, int(qty))
    if item not in MANURE:
        raise ValueError(f"堆肥桶只收粪便：羊粪 / 猪粪 / 牛粪。{COMPOST_BIN_USAGE}")
    meta = MANURE[item]
    layers = config.COMPOST_BIN_LAYERS
    add = int(meta["compost_yield"]) * qty
    mascot = ""
    if s.get("mascot_trait") == "compost":
        add += qty
        mascot = "，吉祥物多沤一层"
    async with db.connect() as conn:
        if not await has_compost_bin(conn, s["id"]):
            raise ValueError(_compost_bin_need_msg())
        fill, ready = await _compost_bin_row(conn, s["id"])
        produced = (fill + add) // layers
        leftover = (fill + add) % layers
        new_ready = ready + produced
        if new_ready > config.COMPOST_BIN_READY_MAX:
            raise ValueError(
                f"桶里堆肥已结 {ready}/{config.COMPOST_BIN_READY_MAX}，再沤会溢出来。"
                "先 hut_ops 堆肥桶 取 堆肥"
            )
        if not await db.take_item(conn, s["id"], item, qty):
            raise ValueError(f"行囊没有 {meta['name']} x{qty}")
        await _compost_bin_save(conn, s["id"], leftover, new_ready)
        await conn.commit()
    made = f"，结出堆肥 x{produced}" if produced else ""
    return (
        f"{meta['name']} x{qty} 丢进堆肥桶（+{add} 层{mascot}）。"
        f"现在 {leftover}/{layers} 层，可取堆肥 x{new_ready}{made}"
    ) + flavor.maybe_suffix([
        "木盖一扣，味儿留给桶",
        "跟 MC 那只绿桶一个道理：丢进去，满了再取",
        "粪进桶，柜里干净",
    ])


async def compost_bin_take(s: dict[str, Any], qty: int | None) -> str:
    layers = config.COMPOST_BIN_LAYERS
    async with db.connect() as conn:
        if not await has_compost_bin(conn, s["id"]):
            raise ValueError(_compost_bin_need_msg())
        fill, ready = await _compost_bin_row(conn, s["id"])
        if ready <= 0:
            raise ValueError(
                f"桶里还没结出堆肥（{fill}/{layers} 层）。再 hut_ops 堆肥桶 存 羊粪"
            )
        n = ready if qty is None else max(1, int(qty))
        if n > ready:
            raise ValueError(f"桶里只有堆肥 x{ready}")
        await db.add_item(conn, s["id"], "compost", n)
        await _compost_bin_save(conn, s["id"], fill, ready - n)
        await conn.commit()
    return f"从堆肥桶取出堆肥 x{n}，回行囊"


async def compost_bin_command(s: dict[str, Any], rest: list[str]) -> str:
    verb = rest[0].lower() if rest else "status"
    if verb in ("status", "list", "看", "搅", "stir", "compost"):
        text = await compost_bin_status_text(s)
        if verb in ("搅", "stir"):
            return text + "\n木棍搅了搅。层数没变：丢粪便才涨。"
        return text

    putting = verb in ("put", "store", "存", "放", "入", "丢", "扔", "add")
    taking = verb in ("take", "取", "拿", "收", "harvest")
    if putting:
        if len(rest) < 2:
            raise ValueError(COMPOST_BIN_USAGE)
        item, qty = _parse_storage_item_qty(rest[1:])
        return await compost_bin_put(s, item, qty)
    if taking:
        qty = None
        tokens = list(rest[1:])
        if tokens and tokens[-1].isdigit():
            qty = max(1, int(tokens[-1]))
            tokens = tokens[:-1]
        if tokens:
            raw = " ".join(tokens)
            item = resolve_item_key(raw) or raw
            if item != "compost":
                raise ValueError("堆肥桶只能取堆肥：hut_ops 堆肥桶 取 堆肥 2")
        return await compost_bin_take(s, qty)
    raise ValueError(COMPOST_BIN_USAGE)


async def _has_fitting(conn: aiosqlite.Connection, steward_id: int, key: str) -> bool:
    cur = await conn.execute(
        "SELECT 1 FROM hut_fittings WHERE steward_id=? AND item_key=?",
        (steward_id, key),
    )
    return await cur.fetchone() is not None


async def _vanity_note(conn: aiosqlite.Connection, steward_id: int) -> str | None:
    if not await _has_fitting(conn, steward_id, "vanity"):
        return None
    from . import survival
    await survival.bump(conn, steward_id, standing=config.VANITY_STANDING)
    return f"梳妆台前捯饬了一下，档信 +{config.VANITY_STANDING}。"


async def bath_soak(s: dict[str, Any]) -> str:
    from . import survival
    if not s.get("hut_built"):
        raise ValueError("先 hut_ops build 小屋，再 buy bath_tub → install hard_N bath_tub")
    async with db.connect() as conn:
        if not await _has_fitting(conn, s["id"], "bath_tub"):
            raise ValueError("小屋里还没有浴桶 — hut_ops buy bath_tub → install hard_N bath_tub")
        row = await (await conn.execute(
            "SELECT bath_soak_at FROM stewards WHERE id=?", (s["id"],)
        )).fetchone()
        last = int(row[0] if row else 0)
        wait = last + config.BATH_COOLDOWN - db.now()
        if wait > 0:
            raise ValueError(f"刚泡过没多久，约 {wait // 3600 + 1} 小时后再来")
        await conn.execute("UPDATE stewards SET bath_soak_at=? WHERE id=?", (db.now(), s["id"]))
        await survival.bump(conn, s["id"], mist_wit=config.BATH_MIST_WIT, satiety=4)
        vanity = await _vanity_note(conn, s["id"])
        await conn.commit()
    msg = f"泡在雪松浴桶里听潮（雾智 +{config.BATH_MIST_WIT}，饱食 +4）。"
    if vanity:
        msg += vanity
    return msg


async def pickle_crops(s: dict[str, Any], rest: list[str]) -> str:
    if not rest:
        raise ValueError("用法：hut_ops 腌 甘蓝 4")
    from .catalog import is_fruit_item, is_vegetable_item, resolve_crop_key, unknown_crop_message
    crop = resolve_crop_key(rest[0])
    if not crop:
        raise ValueError(unknown_crop_message(rest[0]))
    item = f"crop_{crop}"
    if is_fruit_item(item):
        raise ValueError("水果不用腌，直接吃或做甜品")
    if not is_vegetable_item(item):
        raise ValueError("只能腌蔬菜")
    qty = max(1, int(rest[1])) if len(rest) > 1 and rest[1].isdigit() else 1
    async with db.connect() as conn:
        if not await _has_fitting(conn, s["id"], "pickle_crock"):
            raise ValueError("小屋里还没有腌菜坛 — buy pickle_crock → install hard_N pickle_crock")
        row = await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item=?", (s["id"], item)
        )).fetchone()
        have = int(row[0] if row else 0)
        made = min(qty, have // config.PICKLE_VEG_PER_JAR)
        if made <= 0:
            raise ValueError(f"腌一坛要 {config.PICKLE_VEG_PER_JAR} 份蔬菜")
        used = made * config.PICKLE_VEG_PER_JAR
        if not await db.take_item(conn, s["id"], item, used):
            raise ValueError("蔬菜数量不足")
        await db.add_item(conn, s["id"], "pickles", made)
        await conn.commit()
    return f"腌好 🫙腌菜 x{made}（用掉 {item_label(item)} x{used}）"


async def dry_fish(s: dict[str, Any], rest: list[str]) -> str:
    if not rest:
        raise ValueError("用法：hut_ops 晾 鲭鱼 4")
    from .catalog import SEA_CATCH
    token = rest[0]
    item = resolve_item_key(token) or token
    fish_key = item[5:] if item.startswith("fish_") and item[5:] in SEA_CATCH else None
    if not fish_key:
        raise ValueError("晾鱼架只收生鱼")
    qty = max(1, int(rest[1])) if len(rest) > 1 and rest[1].isdigit() else 1
    async with db.connect() as conn:
        if not await _has_fitting(conn, s["id"], "fish_rack"):
            raise ValueError("小屋里还没有晾鱼架 — buy fish_rack → install soft_N fish_rack")
        row = await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item=?", (s["id"], item)
        )).fetchone()
        have = int(row[0] if row else 0)
        made = min(qty, have // config.DRY_FISH_PER)
        if made <= 0:
            raise ValueError(f"晾一条要 {config.DRY_FISH_PER} 条同种生鱼")
        used = made * config.DRY_FISH_PER
        if not await db.take_item(conn, s["id"], item, used):
            raise ValueError("生鱼数量不足")
        await db.add_item(conn, s["id"], f"dried_{fish_key}", made)
        await conn.commit()
    return f"晾好 🥓鱼干·{SEA_CATCH[fish_key]['name']} x{made}（用掉 {used} 条）"


async def bookshelf_read(s: dict[str, Any]) -> str:
    from . import survival
    from .lore import LORE_TOPIC_LABELS, LORE_TOPICS
    import random as _random
    async with db.connect() as conn:
        if not await _has_fitting(conn, s["id"], "bookshelf"):
            raise ValueError("小屋里还没有书架 — buy bookshelf → install soft_N bookshelf")
        day = db.day_id()
        row = await (await conn.execute(
            "SELECT book_read_day FROM stewards WHERE id=?", (s["id"],)
        )).fetchone()
        if row and int(row[0] or 0) == day:
            raise ValueError("今天翻过书了，明日再读")
        await conn.execute("UPDATE stewards SET book_read_day=? WHERE id=?", (day, s["id"]))
        await survival.bump(conn, s["id"], mist_wit=config.BOOKSHELF_MIST_WIT)
        await conn.commit()
    topic = _random.choice(list(LORE_TOPICS.keys()))
    text = _random.choice(LORE_TOPICS[topic])
    return f"在航海书架前翻了半晌（雾智 +{config.BOOKSHELF_MIST_WIT}）。\n【{LORE_TOPIC_LABELS.get(topic, '沿海旧史')}】{text}"


async def bed_rest(s: dict[str, Any]) -> str:
    """板床/升级床：一觉回精力（床越好略多，主要是好看）。每天一次换班刷新。"""
    from . import energy as energy_mod
    from . import survival
    from .catalog import bed_sleep_energy, is_bed_key

    if not s.get("hut_built"):
        raise ValueError(
            "先 hut_ops build 小屋，再 buy bed → install hard_N bed（岸柏板床）"
        )
    async with db.connect() as conn:
        cur = await conn.execute(
            "SELECT item_key FROM hut_fittings WHERE steward_id=?", (s["id"],)
        )
        bed_key = None
        has_hammock = False
        for (key,) in await cur.fetchall():
            if is_bed_key(key):
                bed_key = key
                break
            if key == "hammock":
                has_hammock = True
        if not bed_key and not has_hammock:
            raise ValueError(
                "小屋里还没有床 — buy bed → install hard_N bed，"
                "或 buy hammock → install soft_N hammock"
            )
        sleep_energy = bed_sleep_energy(bed_key) if bed_key else config.HAMMOCK_ENERGY
        row = await (await conn.execute(
            "SELECT bed_rest_at FROM stewards WHERE id=?", (s["id"],)
        )).fetchone()
        last = int(row[0] if row else 0)
        if last and db.day_id(last) >= db.day_id():
            wait = db.seconds_until_next_day()
            hours = wait // 3600 + (1 if wait % 3600 else 0)
            raise ValueError(
                f"今天睡过了，潮声换班后再来（约 {hours} 小时后）"
                f"（一觉回 {sleep_energy} 精力，每天一次）"
            )
        restored = await energy_mod.restore(conn, s["id"], sleep_energy)
        if restored <= 0:
            raise ValueError("精力是满的，不困。先干活去")
        await conn.execute(
            "UPDATE stewards SET bed_rest_at=? WHERE id=?", (db.now(), s["id"])
        )
        await survival.bump(conn, s["id"], satiety=8)
        vanity = await _vanity_note(conn, s["id"])
        await conn.commit()
    bed_name = HUT_HARD.get(bed_key, {}).get("name", "麻绳吊床" if not bed_key else "床")
    msg = (
        f"在{bed_name}上睡到潮声换班（精力 +{restored}，饱食 +8）。"
        "今天先这样；明天换班后还能再睡。饿醒不算病，记得正经吃饭。"
    )
    if vanity:
        msg += vanity
    return msg


async def hut_ops(key_id: int, command: str) -> str:
    from .game import require_steward

    s = await require_steward(key_id)
    parts = command.strip().split(maxsplit=2)
    verb = parts[0].lower() if parts else "status"

    if verb in STORAGE_ALIASES:
        return await cabinet_command(s, command.strip().split()[1:])

    if verb in COMPOST_BIN_ALIASES:
        return await compost_bin_command(s, command.strip().split()[1:])

    if verb in ("扩柜", "加格"):
        n = 1
        if len(parts) > 1 and parts[1].isdigit():
            n = max(1, int(parts[1]))
        return await cabinet_expand(s, n)

    if verb in ("睡", "睡觉", "sleep", "休息", "rest"):
        return await bed_rest(s)

    if verb in ("泡澡", "泡", "沐浴", "bath", "soak"):
        return await bath_soak(s)

    if verb in ("腌", "泡菜", "pickle"):
        return await pickle_crops(s, command.strip().split()[1:])

    if verb in ("晾", "晒", "dry"):
        return await dry_fish(s, command.strip().split()[1:])

    if verb in ("读", "读书", "翻书", "read"):
        return await bookshelf_read(s)

    if verb in ("卖掉", "sell", "变卖", "出售"):
        return await furniture_sell_command(s, command.strip().split()[1:])

    if verb == "status":
        async with db.connect() as conn:
            fittings = await _fittings(conn, s["id"])
        if not s.get("hut_built"):
            return (
                f"小屋: 未建 — hut_ops build（{config.HUT_BUILD_COST} 票）\n"
                "建好后可 buy 硬装/软装，install 到 hard_1 soft_1 等槽位\n"
                "存菜：buy cabinet（潮柜·生鲜）或 buy fridge（冰箱·熟菜），"
                "装好后 hut_ops 冰柜 存 甘蓝 3。"
                "粪便走 buy compost_bin → install → 堆肥桶 存"
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
        bonus = bonuses_for(fittings.values())
        if bonus.has("cabinet"):
            async with db.connect() as conn:
                n = len(await _cabinet_rows(conn, s["id"]))
                cap = cabinet_capacity(await _cabinet_extra(conn, s["id"]))
            lines.append(
                f"潮柜 {n}/{cap} 种 — hut_ops 冰柜 存|取（生鲜）；"
                f"满了 hut_ops 潮柜 扩（{config.CABINET_SLOT_COST}票/格）"
            )
        if bonus.has("fridge"):
            lines.append("冰箱 — hut_ops 冰柜 存|取（熟菜）· kitchen_ops fridge")
        if bonus.has("compost_bin"):
            async with db.connect() as conn:
                fill, ready = await _compost_bin_row(conn, s["id"])
            lines.append(
                f"堆肥桶 {fill}/{config.COMPOST_BIN_LAYERS} 层，可取堆肥 x{ready}"
                " — hut_ops 堆肥桶 存 羊粪 3｜取 堆肥"
            )
        if bonus.has("bed"):
            async with db.connect() as conn:
                row = await (await conn.execute(
                    "SELECT bed_rest_at FROM stewards WHERE id=?", (s["id"],)
                )).fetchone()
            last = int(row[0] if row else 0)
            if last and db.day_id(last) >= db.day_id():
                wait = db.seconds_until_next_day()
                lines.append(
                    f"床 — 今天睡过了，换班后约 {wait // 3600 + 1} 小时能再睡"
                    f"（回 {config.BED_REST_ENERGY} 精力）"
                )
            else:
                lines.append(f"床 — 现在能睡：hut_ops 睡（回 {config.BED_REST_ENERGY} 精力）")
        if not bonus.has("cabinet") and not bonus.has("fridge"):
            lines.append(
                "存菜：hut_ops buy cabinet（潮柜·生鲜）或 buy fridge（冰箱·熟菜），"
                "装好后 hut_ops 冰柜 存 甘蓝 3"
            )
        if not bonus.has("compost_bin"):
            lines.append(
                "粪便：hut_ops buy compost_bin → install soft_N compost_bin，"
                "再 hut_ops 堆肥桶 存 羊粪 3（别进潮柜）"
            )
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
                if k == "tide_crest":
                    lines.append(f"  {k} — {v['emoji']}{v['name']} 满级礼 · {v['hint']}")
                elif v.get("craft_only"):
                    lines.append(f"  {k} — {v['emoji']}{v['name']} 工坊打 · {v['hint']}")
                else:
                    lines.append(f"  {k} — {v['emoji']}{v['name']} {v['cost']} 票 · {v['hint']}")
            lines.append(
                "存菜：buy cabinet（潮柜·生鲜）或 buy fridge（冰箱·熟菜，也可 buy 冰柜）；"
                f"装好后 hut_ops 冰柜 存|取。潮柜基础 {config.CABINET_SLOTS} 格，"
                f"hut_ops 潮柜 扩 加格（{config.CABINET_SLOT_COST}票/格，顶 {config.CABINET_SLOTS_MAX}）。"
                "粪便：buy compost_bin → install soft_N compost_bin → 堆肥桶 存 羊粪 3"
            )
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
            f"hard_1 / soft_1~2 可装 → catalog / buy / install。"
            "存菜：buy cabinet 潮柜（生鲜）或 buy fridge 冰箱（熟菜），"
            "装好后 hut_ops 冰柜 存 甘蓝 3。"
            "粪便：buy compost_bin → install soft_N compost_bin → 堆肥桶 存"
        )

    if verb == "upgrade":
        if not s.get("hut_built"):
            raise ValueError("先 build 小屋")
        lvl = s.get("hut_level") or 1
        if lvl >= max(HUT_LEVELS):
            return "已是最高档小屋了——换软装或升级床吧"
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
        key = _resolve_fitting_key(parts[1].split()[0])
        kind, meta = _catalog_item(key)
        if meta.get("craft_only"):
            raise ValueError(
                f"{meta['name']}是岸工坊出品，craft_ops 打 {meta['name']}，不能 hut_ops buy"
            )
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
        extra = ""
        if key == "cabinet":
            extra = (
                f"。生鲜：install 后 hut_ops 冰柜 存 甘蓝 3；"
                f"基础 {config.CABINET_SLOTS} 格，满了 hut_ops 潮柜 扩"
                f"（{config.CABINET_SLOT_COST}票/格）"
            )
        elif key == "fridge":
            extra = "。熟菜：install 后 hut_ops 冰柜 存 盐焗沙蟹"
        elif key == "compost_bin":
            extra = "。粪便：install 后 hut_ops 堆肥桶 存 羊粪 3｜取 堆肥 2（别进潮柜）"
        return (
            f"购入 {meta['emoji']}{meta['name']}（-{meta['cost']} 票）"
            f"→ install {kind}_N {key}{extra}"
        )

    if verb == "install" and len(parts) >= 3:
        if not s.get("hut_built"):
            raise ValueError("先 build 小屋")
        slot = parts[1].lower()
        key = _resolve_fitting_key(parts[2])
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
                    await _maybe_dump_compost_bin(
                        conn, s["id"], old_key, except_slot=slot,
                    )
                    if old_key.startswith("deco_"):
                        await db.add_item(conn, s["id"], old_key, 1, over_cap=True)
                    else:
                        await db.add_item(conn, s["id"], f"fit_{old_key}", 1, over_cap=True)
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
                    await _maybe_dump_compost_bin(
                        conn, s["id"], old[slot], except_slot=slot,
                    )
                    old_key = old[slot]
                    if old_key.startswith("deco_"):
                        await db.add_item(conn, s["id"], old_key, 1, over_cap=True)
                    else:
                        await db.add_item(conn, s["id"], f"fit_{old_key}", 1, over_cap=True)
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
        compost_dumped = 0
        async with db.connect() as conn:
            if not await db.take_item(conn, s["id"], fit_item, 1):
                if meta.get("craft_only"):
                    raise ValueError(
                        f"行囊没有 {meta['name']}，先 craft_ops 打 {meta['name']}"
                    )
                raise ValueError(f"行囊没有 {meta['name']}，先 buy {key}")
            old = await _fittings(conn, s["id"])
            if slot in old:
                dumped = await _maybe_dump_cabinet(
                    conn, s["id"], old[slot], except_slot=slot,
                )
                compost_dumped = await _maybe_dump_compost_bin(
                    conn, s["id"], old[slot], except_slot=slot,
                )
                await db.add_item(conn, s["id"], f"fit_{old[slot]}", 1, over_cap=True)
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
        if compost_dumped:
            msg += f" 堆肥桶结肥回行囊 x{compost_dumped}"
        return msg

    if verb == "remove" and len(parts) >= 2:
        slot = parts[1].lower()
        async with db.connect() as conn:
            fittings = await _fittings(conn, s["id"])
            if slot not in fittings:
                raise ValueError("该槽位是空的")
            key = fittings[slot]
            dumped = await _maybe_dump_cabinet(conn, s["id"], key, except_slot=slot)
            compost_dumped = await _maybe_dump_compost_bin(
                conn, s["id"], key, except_slot=slot,
            )
            await conn.execute(
                "DELETE FROM hut_fittings WHERE steward_id=? AND slot=?",
                (s["id"], slot),
            )
            if key.startswith("deco_"):
                await db.add_item(conn, s["id"], key, 1, over_cap=True)
            else:
                await db.add_item(conn, s["id"], f"fit_{key}", 1, over_cap=True)
            await conn.commit()
        msg = f"已拆下 {slot} 的 {_fit_name(key)}，装件回行囊"
        if dumped:
            msg += f"；潮柜货回行囊 x{dumped}"
        if compost_dumped:
            msg += f"；堆肥桶结肥回行囊 x{compost_dumped}"
        msg += "。要按折旧卖掉：hut_ops 卖掉 槽位"
        return msg

    raise ValueError(
        f"未知 hut 指令: {command}（status/build/upgrade/label/catalog/buy/install/remove/睡/冰柜/柜子/堆肥桶/卖掉）"
    )


async def public_snapshot() -> dict[str, Any]:
    from . import world
    from .catalog import HUT_LEVELS

    weather = world.current_weather()
    tide = world.current_tide()
    phase = world.current_day_phase()
    shore_bits = {
        ("clear", "ebb"): "晴天退潮，木栈道上还有点湿。",
        ("clear", "slack"): "平潮很安静，屋檐影子贴在沙上。",
        ("clear", "flood"): "涨潮拍到堤边，靠海的门先别敞着。",
        ("misty", "ebb"): "海雾还没散尽，退潮后岸线显得更远。",
        ("misty", "slack"): "雾里看不清谁家的灯，只听见栈道响。",
        ("misty", "flood"): "雾和潮一起上来，小屋门缝都发潮。",
        ("gale", "ebb"): "阵风刮过退潮滩，晾衣绳全歪了。",
        ("gale", "slack"): "风很大，畜栏顶棚一直在响。",
        ("gale", "flood"): "涨潮加阵风，靠岸的人都把窗扣上了。",
    }
    shore_blurb = shore_bits.get((weather, tide), "岸边风平浪静。")
    if phase == "night":
        shore_blurb = shore_blurb.rstrip("。") + "。夜里灯更稀。"
    elif phase == "dusk":
        shore_blurb = shore_blurb.rstrip("。") + "。暮色压下来了。"

    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        huts = (await (await conn.execute(
            "SELECT COUNT(*) FROM stewards WHERE enrolled=1 AND hut_built=1"
        )).fetchone())[0]
        barns = (await (await conn.execute(
            "SELECT COUNT(*) FROM stewards WHERE enrolled=1 AND barn_built=1"
        )).fetchone())[0]
        mascots = (await (await conn.execute(
            "SELECT COUNT(*) FROM stewards WHERE enrolled=1 AND mascot_name != ''"
        )).fetchone())[0]
        top = await (await conn.execute(
            """
            SELECT name, COALESCE(hut_level, 0) AS hut_level
            FROM stewards
            WHERE enrolled=1 AND hut_built=1
            ORDER BY hut_level DESC, last_active_at DESC
            LIMIT 12
            """
        )).fetchall()
        feed = await (await conn.execute(
            """
            SELECT c.text, c.created_at, a.name AS actor
            FROM chronicle c
            LEFT JOIN stewards a ON a.id = c.actor_id
            WHERE c.action IN ('hut', 'barn', 'mascot')
            ORDER BY c.created_at DESC LIMIT 16
            """
        )).fetchall()
    levels = []
    for r in top:
        lv = max(1, int(r["hut_level"] or 1))
        meta = HUT_LEVELS.get(lv, HUT_LEVELS[1])
        levels.append({
            "name": r["name"],
            "level": lv,
            "label": meta["name"],
        })
    return {
        "climate": world.climate_line(),
        "shore_blurb": shore_blurb,
        "huts": int(huts or 0),
        "barns": int(barns or 0),
        "mascots": int(mascots or 0),
        "levels": levels,
        "hints": [
            "AI 用 hut_ops build → catalog → buy / install",
            "潮柜存生鲜，冰箱存熟菜，粪便走堆肥桶",
            "工坊打的秤锤/铁锄刃/滤网/潮冠要装上才生效",
        ],
        "feed": [
            {
                "text": r["text"],
                "actor": r["actor"] or "系统",
                "created_at": r["created_at"],
            }
            for r in feed
        ],
    }
