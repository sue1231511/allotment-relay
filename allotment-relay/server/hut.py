"""岸畔小屋 — 硬装 / 软装 / 升级。装件加成在 catalog hint 里写了，这里真正生效。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import aiosqlite

from . import config, db, flavor
from .catalog import (
    CROPS,
    HUT_HARD,
    HUT_LEVELS,
    HUT_MAX_LEVEL,
    HUT_MAX_NAME,
    HUT_SOFT,
    ITEM_NAMES,
    LILI_DECOR,
    LILI_JUNK_DECOR,
    LIVESTOCK,
    MANURE,
    dish_item,
    is_bed_key,
    item_label,
    item_stack_cap,
    resolve_item_key,
    unknown_item_message,
)


def _slots(level: int) -> tuple[list[str], list[str]]:
    meta = HUT_LEVELS.get(level, HUT_LEVELS[1])
    hard = [f"hard_{i}" for i in range(1, meta["hard"] + 1)]
    soft = [f"soft_{i}" for i in range(1, meta["soft"] + 1)]
    return hard, soft


def first_empty_slot(level: int, fittings: dict[str, str], kind: str) -> str | None:
    hard, soft = _slots(max(1, int(level or 1)))
    pool = hard if kind == "hard" else soft
    for slot in pool:
        if slot not in fittings:
            return slot
    return None


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
    f"潮柜基础 {config.CABINET_SLOTS} 格，满了 hut_ops 潮柜 扩（{config.CABINET_SLOT_COST}票/格，顶 {config.CABINET_SLOTS_MAX}）。"
    "粪便不能进潮柜，走 hut_ops 堆肥桶。"
)

COMPOST_BIN_ALIASES = {
    "堆肥桶", "肥桶", "堆肥箱", "compost_bin", "composter", "compostbin",
}

COMPOST_BIN_USAGE = (
    "用法：hut_ops 堆肥桶 存 羊粪 3｜堆肥桶 转化 羊粪 3｜堆肥桶 取 堆肥 2"
    "（肥桶/compost_bin 同义；转化/沤 也是存）。"
    "买：hut_ops buy compost_bin → install soft_1 compost_bin（空槽也能装）。"
    "装完 hut_ops status 槽位上要能看见堆肥桶。"
    "桶不是柜子：粪便丢进去沤层，不能当货存着。满 7 层结 1 份堆肥（羊粪+2 / 猪粪+3 / 牛粪+4），只能取堆肥。"
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


async def _has_named_fitting(
    conn: aiosqlite.Connection,
    steward_id: int,
    name: str,
    *,
    except_slot: str | None = None,
) -> bool:
    fittings = await _fittings(conn, steward_id)
    return any(
        _fitting_bare(key) == name and slot != except_slot
        for slot, key in fittings.items()
    )


async def _return_displaced_fitting(
    conn: aiosqlite.Connection, steward_id: int, item_key: str,
) -> None:
    if item_key.startswith("deco_"):
        await db.add_item(conn, steward_id, item_key, 1, over_cap=True)
        return
    await db.add_item(conn, steward_id, f"fit_{_fitting_bare(item_key)}", 1, over_cap=True)


async def _upsert_fitting(
    conn: aiosqlite.Connection, steward_id: int, slot: str, item_key: str,
) -> None:
    await conn.execute(
        """
        INSERT INTO hut_fittings (steward_id, slot, item_key, installed_at)
        VALUES (?,?,?,?)
        ON CONFLICT(steward_id, slot) DO UPDATE SET item_key=excluded.item_key,
        installed_at=excluded.installed_at
        """,
        (steward_id, slot, item_key, db.now()),
    )


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
    return await _has_named_fitting(conn, steward_id, "cabinet")


async def has_fridge(conn: aiosqlite.Connection, steward_id: int) -> bool:
    return await _has_named_fitting(conn, steward_id, "fridge")


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
    if await _has_named_fitting(conn, steward_id, "cabinet", except_slot=except_slot):
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
    return await _has_named_fitting(conn, steward_id, "compost_bin")


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
    if await _has_named_fitting(
        conn, steward_id, "compost_bin", except_slot=except_slot,
    ):
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
            "粪便别进潮柜，恶心。装堆肥桶：hut_ops buy compost_bin → install soft_1 compost_bin（空槽也能装），"
            "status 看见桶后再 hut_ops 堆肥桶 存 羊粪 3"
        )
    if item.startswith("dish_") or item.startswith("meal_"):
        return "熟菜放冰箱 — hut_ops 冰柜 存 菜名（先 buy fridge → install）"
    if item.startswith("live_"):
        return "活物走畜栏 hut_ops barn"
    if item.startswith("fit_"):
        return "装件直接 install，不必进柜子"
    return None


def _parse_storage_name_qty(tokens: list[str]) -> tuple[str, int]:
    qty = 1
    name_tokens = list(tokens)
    if name_tokens and name_tokens[-1].isdigit():
        qty = max(1, int(name_tokens[-1]))
        name_tokens = name_tokens[:-1]
    if not name_tokens:
        raise ValueError("要写物品名")
    return " ".join(name_tokens), qty


def _parse_storage_item_qty(tokens: list[str]) -> tuple[str, int]:
    raw, qty = _parse_storage_name_qty(tokens)
    item = resolve_item_key(raw)
    if not item:
        from . import cook_mix
        dish = cook_mix.resolve_dish_key(raw.rstrip("★☆*"))
        if dish:
            item = f"dish_{dish}"
        elif raw.startswith("dish_") or raw.startswith("meal_"):
            item = raw
        else:
            raise ValueError(unknown_item_message(raw))
    return item, qty


def _is_cooked_item(item: str) -> bool:
    return item.startswith("dish_") or item.startswith("meal_")


async def _cabinet_status_text(s: dict[str, Any]) -> str:
    stack_cap = item_stack_cap("crop_kale", stack_tier=int(s.get("satchel_stack_extra") or 0))
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
            f"潮柜空（{cap} 格；每组最多 {stack_cap}，同种可占多组）。"
            f"hut_ops 冰柜 存 甘蓝 3。{expand_hint}"
        )
    from .catalog import format_stack_qty, stacks_needed

    used = sum(
        stacks_needed(q, item_stack_cap(it, stack_tier=int(s.get("satchel_stack_extra") or 0)))
        for it, q in rows
    )
    lines = [f"潮柜 {used}/{cap} 格（{len(rows)} 种货；每组最多 {stack_cap}，同种可多组）:"]
    for item, qty in rows:
        item_cap = item_stack_cap(item, stack_tier=int(s.get("satchel_stack_extra") or 0))
        lines.append(f"  {item_label(item)}（{item}） {format_stack_qty(qty, item_cap)}")
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
    from .catalog import cabinet_stacks_full_message, stacks_needed

    tier = int(s.get("satchel_stack_extra") or 0)
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
        slot_cap = cabinet_capacity(await _cabinet_extra(conn, s["id"]))
        stack_cap = item_stack_cap(item, stack_tier=tier)
        used = sum(
            stacks_needed(q, item_stack_cap(it, stack_tier=tier)) for it, q in have.items()
        )
        stacked = have.get(item, 0)
        old_stacks = stacks_needed(stacked, stack_cap)
        new_stacks = stacks_needed(stacked + qty, stack_cap)
        extra_slots = new_stacks - old_stacks
        if used + extra_slots > slot_cap:
            raise ValueError(
                cabinet_stacks_full_message(
                    item,
                    stacked,
                    qty,
                    stack_cap,
                    used_slots=used,
                    max_slots=slot_cap,
                    free_slots=max(0, slot_cap - used),
                )
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
        f"每组最多 {item_stack_cap('crop_kale', stack_tier=int(s.get('satchel_stack_extra') or 0))}，同种可占多组。"
        f"格子跟着人走，卸了柜子再装还在。"
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

    raw_name, qty = _parse_storage_name_qty(rest[1:])
    from . import kitchen
    if taking:
        try:
            return await kitchen.fridge_take(s, raw_name, qty)
        except ValueError as exc:
            if "冰箱里没有" not in str(exc):
                raise
        item, _ = _parse_storage_item_qty(rest[1:])
        return await cabinet_take(s, item, qty)

    cooked_token = kitchen._resolve_cooked_token(raw_name)
    if cooked_token and kitchen.is_cooked_item(cooked_token):
        return await kitchen.fridge_put(s, raw_name, qty)
    async with db.connect() as conn:
        try:
            satchel_item = await kitchen._pick_cooked_satchel(conn, s["id"], raw_name)
        except ValueError:
            satchel_item = None
        else:
            if kitchen.is_cooked_item(satchel_item):
                return await kitchen.fridge_put(s, raw_name, qty)
    item, _ = _parse_storage_item_qty(rest[1:])
    return await cabinet_put(s, item, qty)


def _compost_bin_need_msg() -> str:
    return (
        "还没装堆肥桶。粪便别进潮柜。"
        "hut_ops buy compost_bin → install soft_1 compost_bin（空槽也能装），"
        "再用 hut_ops status 确认槽位上有堆肥桶，然后 堆肥桶 存 羊粪 3。"
        "桶不是柜子，只能丢粪便沤层、取堆肥。"
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
    if verb in ("status", "list", "看"):
        return await compost_bin_status_text(s)
    if verb in ("搅", "stir"):
        text = await compost_bin_status_text(s)
        return text + "\n木棍搅了搅。层数没变：丢粪便才涨。"
    if verb == "compost" and len(rest) < 2:
        return await compost_bin_status_text(s)

    putting_verbs = {
        "put", "store", "存", "放", "入", "丢", "扔", "add",
        "转化", "沤", "沤肥", "compost",
    }
    first_item = resolve_item_key(verb) or verb
    putting = verb in putting_verbs or first_item in MANURE
    taking = verb in ("take", "取", "拿", "收", "harvest")
    if putting:
        if first_item in MANURE and verb not in putting_verbs:
            tokens = rest
        else:
            tokens = rest[1:]
        if not tokens:
            raise ValueError(COMPOST_BIN_USAGE)
        item, qty = _parse_storage_item_qty(tokens)
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
        health_gain = 0
        if restored <= 0:
            from . import health as health_mod
            cur = await conn.execute("SELECT health FROM stewards WHERE id=?", (s["id"],))
            body = int((await cur.fetchone())[0])
            if body >= 100:
                raise ValueError("精力是满的，不困。先干活去")
            health_gain = await health_mod.restore_health(conn, s["id"], config.SLEEP_HEALTH)
            if health_gain <= 0:
                raise ValueError("精力是满的，不困。先干活去")
        else:
            from . import health as health_mod
            health_gain = await health_mod.restore_health(conn, s["id"], config.SLEEP_HEALTH)
        await conn.execute(
            "UPDATE stewards SET bed_rest_at=? WHERE id=?", (db.now(), s["id"])
        )
        await survival.bump(conn, s["id"], satiety=8)
        vanity = await _vanity_note(conn, s["id"])
        from . import bond as bond_mod
        await bond_mod.grant(conn, s["id"], bond_mod.SLEEP, "labor")
        await conn.commit()
    bed_name = HUT_HARD.get(bed_key, {}).get("name", "麻绳吊床" if not bed_key else "床")
    bits = []
    if restored > 0:
        bits.append(f"精力 +{restored}")
    if health_gain > 0:
        bits.append(f"身体 +{health_gain}")
    bits.append("饱食 +8")
    msg = (
        f"在{bed_name}上睡到潮声换班（{'，'.join(bits)}）。"
        "今天先这样；明天换班后还能再睡。饿醒不算病，记得正经吃饭。"
        "身子大虚还是去诊所 clinic 调理，睡觉只是顺带缓一缓。"
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
        if int(s.get("invite_lantern") or 0):
            lines.append("岸灯（引航纪念）亮着。")
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
                "粪便：hut_ops buy compost_bin → install soft_1 compost_bin（空槽也能装），"
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
                "粪便：buy compost_bin → install soft_1 compost_bin（空槽也能装）→ 堆肥桶 存 羊粪 3"
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
            from . import tax as tax_mod
            await tax_mod.record_life_spend(conn, s["id"], config.HUT_BUILD_COST, "hut")
            from . import bond as bond_mod
            await bond_mod.grant(conn, s["id"], bond_mod.HUT_UPGRADE, "life", once="hut_build")
            await conn.commit()
        await db.add_chronicle("hut", f"{s['name']} 搭了岸畔棚屋", s["id"])
        return (
            f"棚屋就绪（-{config.HUT_BUILD_COST} 票）。"
            f"hard_1 / soft_1~2 可装 → catalog / buy / install。"
            "存菜：buy cabinet 潮柜（生鲜）或 buy fridge 冰箱（熟菜），"
            "装好后 hut_ops 冰柜 存 甘蓝 3。"
            "粪便：buy compost_bin → install soft_1 compost_bin（空槽也能装）→ 堆肥桶 存 羊粪 3"
        )

    if verb == "upgrade":
        if not s.get("hut_built"):
            raise ValueError("先 build 小屋")
        lvl = s.get("hut_level") or 1
        if lvl >= max(HUT_LEVELS):
            return "已是最高档小屋了——换软装或升级床吧"
        nxt = HUT_LEVELS[lvl + 1]
        cost = nxt["upgrade"]
        from . import tax as tax_mod
        tax_mod.assert_clear(s)
        async with db.connect() as conn:
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < cost:
                raise ValueError(f"升级需要 {cost} 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-?, hut_level=? WHERE id=?",
                (cost, lvl + 1, s["id"]),
            )
            await tax_mod.record_life_spend(conn, s["id"], cost, "hut")
            from . import bond as bond_mod
            await bond_mod.grant(conn, s["id"], bond_mod.HUT_UPGRADE, "life")
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
            from . import tax as tax_mod
            await tax_mod.record_life_spend(conn, s["id"], meta["cost"], "hut")
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
            extra = (
                "。空槽也能装：install soft_1 compost_bin。"
                "装完 status 看见桶后 hut_ops 堆肥桶 存 羊粪 3｜取 堆肥 2。"
                "桶不是柜子，粪便丢进去沤层（别进潮柜）"
            )
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
                await _return_displaced_fitting(conn, s["id"], old[slot])
            await _upsert_fitting(conn, s["id"], slot, key)
            from . import bond as bond_mod
            await bond_mod.grant(conn, s["id"], bond_mod.HUT_INSTALL, "life")
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


def _sku(
    *,
    sid: str,
    kind: str,
    name: str,
    emoji: str = "·",
    note: str = "",
    detail: str = "",
    price: str = "看",
    can: bool = False,
    target: str = "",
    qty: int = 0,
) -> dict[str, Any]:
    return {
        "id": sid,
        "kind": kind,
        "name": name,
        "emoji": emoji,
        "note": note,
        "detail": detail or note,
        "price": price,
        "can": can,
        "target": target,
        "qty": int(qty or 0),
    }


def _item_emoji(item: str) -> str:
    key = str(item or "")
    if key.startswith("crop_") and key[5:] in CROPS:
        return str(CROPS[key[5:]].get("emoji") or "🥬")
    if key.startswith("seed_") and key[5:] in CROPS:
        return str(CROPS[key[5:]].get("emoji") or "🌱")
    if key in MANURE:
        return str(MANURE[key].get("emoji") or "💩")
    if key in LIVESTOCK:
        return str(LIVESTOCK[key].get("emoji") or "·")
    if key == "compost":
        return "🪴"
    if key.startswith("dish_") or key.startswith("meal_"):
        return "🍽️"
    label = item_label(key)
    if label and not label[0].isalnum():
        return label[0]
    return "·"


def _has_bed(fittings: dict[str, str]) -> bool:
    for key in fittings.values():
        bare = _fitting_bare(key)
        if is_bed_key(bare) or bare == "hammock":
            return True
    return False


def _has_fit(fittings: dict[str, str], name: str) -> bool:
    return any(_fitting_bare(key) == name for key in fittings.values())


async def _cook_tab_items(
    conn: aiosqlite.Connection,
    s: dict[str, Any],
    stock: dict[str, Any],
) -> tuple[list[dict[str, Any]], int, int]:
    """小屋灶栏。数值仍走 kitchen_ops cook，这里只摊开能点的定点菜和乱炖材料。"""
    from collections import Counter

    from . import cook_mix, kitchen
    from .catalog import KITCHEN_DISHES, is_fiber_item

    used, mix_used = await kitchen._cook_counts(conn, s["id"])
    recipe_cap = int(config.KITCHEN_RECIPE_COOK_DAILY)
    mix_cap = int(config.KITCHEN_MIX_COOK_DAILY)
    recipe_left = max(0, recipe_cap - used)
    mix_left = max(0, mix_cap - mix_used)
    rows: list[dict[str, Any]] = []
    rows.append(_sku(
        sid="cook-quota-recipe",
        kind="quota",
        name="定点菜",
        emoji="🍳",
        note=f"今日 {used}/{recipe_cap}。菜单上那几道，每天 {recipe_cap} 次。",
        detail=(
            f"点菜名下锅。每天 {recipe_cap} 次，换班刷新。"
            "缺料的也能点开看差什么。乱炖是另一栏次数。"
        ),
        price=f"{recipe_left} 次",
        can=True,
        target="",
    ))
    rows.append(_sku(
        sid="cook-quota-mix",
        kind="quota",
        name="乱炖",
        emoji="🥘",
        note=f"今日 {mix_used}/{mix_cap}。点 2～5 样材料再下锅。",
        detail=(
            f"点行囊里的料，凑 2～5 样再点乱炖下锅。每天 {mix_cap} 次，换班刷新。"
            "活物、工具、装饰、熟菜、衣料不能下锅。乱搭也按材料身价兜底。"
        ),
        price=f"{mix_left} 次",
        can=True,
        target="",
    ))
    rows.append(_sku(
        sid="cook-mix",
        kind="cook_mix",
        name="乱炖下锅",
        emoji="🔥",
        note="先点下面的材料 2～5 样，再点这里下锅。",
        detail="自由组合 2～5 样。点材料会亮，再点乱炖下锅。和定点菜不是同一次数。",
        price="煮",
        can=mix_left > 0,
        target="",
    ))

    ready_n = 0
    recipe_rows: list[dict[str, Any]] = []
    for key, meta in KITCHEN_DISHES.items():
        need = Counter(meta["ings"])
        short: list[str] = []
        labels: list[str] = []
        for item, n in need.items():
            labels.append(item_label(item) if n == 1 else f"{item_label(item)}×{n}")
            have = int(stock.get(item) or 0)
            if have < n:
                short.append(f"{item_label(item)}差{n - have}")
        ings_txt = " + ".join(labels)
        energy = int(meta.get("energy") or 0)
        if short:
            note = "缺 " + "、".join(short)
            can = False
            price = "看"
        elif recipe_left <= 0:
            note = f"今日定点菜满了（{recipe_cap} 次）。"
            can = False
            price = "看"
        else:
            note = f"{ings_txt} · eat +{energy}"
            can = True
            price = "煮"
            ready_n += 1
        recipe_rows.append(_sku(
            sid=f"cook-{key}",
            kind="cook",
            name=str(meta.get("name") or key),
            emoji=str(meta.get("emoji") or "🍳"),
            note=note,
            detail=(
                f"{ings_txt}。定点菜，每天 {recipe_cap} 次。"
                + (f"缺：{'、'.join(short)}。" if short else f"下锅后可 eat 回 {energy} 精力。")
            ),
            price=price,
            can=can,
            target=str(meta.get("name") or key),
        ))
    recipe_rows.sort(key=lambda row: (not row["can"], row["name"]))
    rows.extend(recipe_rows)

    mix_rows: list[dict[str, Any]] = []
    for item, qty in (stock or {}).items():
        n = int(qty or 0)
        if n <= 0:
            continue
        if is_fiber_item(item):
            continue
        if cook_mix.classify(item) == "refuse":
            continue
        mix_rows.append(_sku(
            sid=f"mix-{item}",
            kind="mix_pick",
            name=item_label(item),
            emoji=_item_emoji(item),
            note=f"行囊 {n}。点一下算一份，最多 5 样。",
            detail="点亮算入锅，再点乱炖下锅。同一料可点多份。衣料、熟菜、工具不能下锅。",
            price="点",
            can=mix_left > 0,
            target=item_label(item),
            qty=n,
        ))
    mix_rows.sort(key=lambda row: row["name"])
    if mix_rows:
        rows.extend(mix_rows)
    else:
        rows.append(_sku(
            sid="cook-need",
            kind="quota",
            name="行囊没有能下锅的料",
            emoji="🥬",
            note="份地收菜、海边拿鱼，再回来煮。",
            detail="定点菜看上面缺什么。乱炖至少 2 样。蔬菜不能生吃，要先下锅。",
            price="看",
            can=True,
            target="",
        ))
    return rows, recipe_left, ready_n


async def player_view(conn: aiosqlite.Connection, s: dict[str, Any]) -> dict[str, Any]:
    """给 /island 小屋用。数值仍走 hut_ops / barn_ops / kitchen_ops cook，这里只摊开能点的。"""
    from . import barn, kitchen
    from .catalog import bed_sleep_energy

    built = bool(s.get("hut_built"))
    lvl = max(1, int(s.get("hut_level") or 1)) if built else 0
    meta = HUT_LEVELS.get(lvl, HUT_LEVELS[1]) if built else HUT_LEVELS[1]
    name = (s.get("hut_label") or meta["name"]) if built else "岸畔小屋"
    tickets = int(s.get("tickets") or 0)
    energy_now = int(s.get("energy") or 0)
    health_now = int(s.get("health") or 0)
    tax_owed = int(s.get("tax_arrears") or 0)
    upkeep_owed = int(s.get("upkeep_arrears") or 0)
    fittings = await _fittings(conn, s["id"]) if built else {}
    stock = await db.get_satchel(s["id"])
    empty_hard = first_empty_slot(lvl, fittings, "hard") if built else None
    empty_soft = first_empty_slot(lvl, fittings, "soft") if built else None
    has_bed = _has_bed(fittings)
    has_cab = _has_fit(fittings, "cabinet")
    has_fridge = _has_fit(fittings, "fridge")
    has_bin = _has_fit(fittings, "compost_bin")
    slept = False
    if built:
        row = await (await conn.execute(
            "SELECT bed_rest_at FROM stewards WHERE id=?", (s["id"],)
        )).fetchone()
        last = int(row[0] if row else 0)
        slept = bool(last and db.day_id(last) >= db.day_id())
    need_rest = energy_now < 100 or health_now < 100
    can_sleep = bool(built and has_bed and not slept and need_rest)
    sleep_energy = config.BED_REST_ENERGY
    if has_bed:
        for key in fittings.values():
            bare = _fitting_bare(key)
            if is_bed_key(bare):
                sleep_energy = bed_sleep_energy(bare)
                break
        else:
            sleep_energy = config.HAMMOCK_ENERGY

    nxt = HUT_LEVELS.get(lvl + 1) if built and lvl < HUT_MAX_LEVEL else None
    upgrade_cost = int((nxt or {}).get("upgrade") or 0)
    dues_ok = tax_owed <= 0 and upkeep_owed <= 0
    can_upgrade = bool(nxt and dues_ok and tickets >= upgrade_cost)
    if not built:
        spoken = "还没搭棚屋。点搭棚屋。"
    elif can_sleep:
        spoken = "困了就睡。灶、潮柜、堆肥桶、畜栏也在这儿。"
    elif not has_bed:
        spoken = "先买张床再睡。灶、潮柜、堆肥、畜栏也在这儿。"
    else:
        spoken = "今天睡过了。灶、潮柜、堆肥、畜栏还在。"

    home_items: list[dict[str, Any]] = []
    if built:
        home_items.append(_sku(
            sid="look",
            kind="look",
            name="看屋",
            emoji="🏠",
            note="门牌和装件。",
            detail="点开看这间屋现在装了什么。",
            price="看",
            can=True,
            target="status",
        ))
        if can_sleep:
            sleep_note = f"回 {sleep_energy} 精力，顺带缓身体。每天一次。"
        elif not has_bed:
            sleep_note = "屋里还没有床。先买岸柏板床再睡。"
        elif slept:
            wait = db.seconds_until_next_day()
            hours = wait // 3600 + (1 if wait % 3600 else 0)
            sleep_note = f"今天睡过了，约 {hours} 小时后再来。"
        else:
            sleep_note = "精力是满的，不困。"
        home_items.append(_sku(
            sid="sleep",
            kind="sleep",
            name="睡",
            emoji="🛏️",
            note=sleep_note,
            detail=sleep_note + "身子大虚去诊所调理，睡觉只是顺带缓一缓。",
            price="睡" if can_sleep else "看",
            can=can_sleep,
            target="",
        ))
        if not has_bed:
            bag_bed = int(stock.get("fit_bed") or 0) > 0
            if bag_bed and empty_hard:
                home_items.append(_sku(
                    sid="install-bed",
                    kind="install",
                    name="装岸柏板床",
                    emoji="🛏️",
                    note="行囊里有床，装上才能睡。",
                    detail="装到空的硬装槽。装好就能睡。",
                    price="装",
                    can=True,
                    target="bed",
                ))
            elif empty_hard:
                home_items.append(_sku(
                    sid="buy-bed",
                    kind="buy_install",
                    name="买岸柏板床",
                    emoji="🛏️",
                    note=f"{HUT_HARD['bed']['cost']} 票。装上才能睡。",
                    detail=f"买岸柏板床并装上，要 {HUT_HARD['bed']['cost']} 票。不是装修游戏，只为能睡。",
                    price=f"{HUT_HARD['bed']['cost']} 票",
                    can=tickets >= HUT_HARD["bed"]["cost"],
                    target="bed",
                ))
            else:
                home_items.append(_sku(
                    sid="bed-slot",
                    kind="look",
                    name="硬装槽满了",
                    emoji="🛏️",
                    note="没有空槽装床。先升级小屋。",
                    detail="硬装槽满了。先升级再买床。",
                    price="看",
                    can=True,
                    target="status",
                ))
        if nxt:
            if not dues_ok:
                up_note = "欠岸税或岸维，交清才能升屋。去潮生会。"
            elif tickets < upgrade_cost:
                up_note = f"要 {upgrade_cost} 票，现在 {tickets}。"
            else:
                up_note = f"升到 Lv{lvl + 1} {nxt['name']}，要 {upgrade_cost} 票。"
            home_items.append(_sku(
                sid="upgrade",
                kind="upgrade",
                name=f"升级 · {nxt['name']}",
                emoji="🪜",
                note=up_note,
                detail=up_note + f"求婚发出前必须升到 {HUT_MAX_NAME}。",
                price="升" if can_upgrade else "看",
                can=can_upgrade,
                target="",
            ))
        else:
            home_items.append(_sku(
                sid="max",
                kind="look",
                name=f"已是 {HUT_MAX_NAME}",
                emoji="🏡",
                note="最高档了。换软装或升级床。",
                detail="已经是岛上最高档小屋。求婚发出前要这一档。",
                price="看",
                can=True,
                target="status",
            ))

    cab_items: list[dict[str, Any]] = []
    if built and not has_cab:
        bag_cab = int(stock.get("fit_cabinet") or 0) > 0
        if bag_cab and empty_soft:
            cab_items.append(_sku(
                sid="install-cab",
                kind="install",
                name="装潮柜",
                emoji="🗄️",
                note="行囊里有潮柜，装上才能存生鲜。",
                detail="装到空的软装槽。生鲜进潮柜，小偷翻不到。",
                price="装",
                can=True,
                target="cabinet",
            ))
        elif empty_soft:
            cab_items.append(_sku(
                sid="buy-cab",
                kind="buy_install",
                name="买潮柜",
                emoji="🗄️",
                note=f"{HUT_SOFT['cabinet']['cost']} 票。生鲜放这儿。",
                detail="买潮柜并装上。粪便别进潮柜，走堆肥桶。",
                price=f"{HUT_SOFT['cabinet']['cost']} 票",
                can=tickets >= HUT_SOFT["cabinet"]["cost"],
                target="cabinet",
            ))
        else:
            cab_items.append(_sku(
                sid="cab-slot",
                kind="look",
                name="软装槽满了",
                emoji="🗄️",
                note="没有空槽装潮柜。先升级小屋。",
                detail="软装槽满了。先升级再买潮柜。",
                price="看",
                can=True,
                target="status",
            ))
    elif built and has_cab:
        extra = await _cabinet_extra(conn, s["id"])
        cap = cabinet_capacity(extra)
        rows = await _cabinet_rows(conn, s["id"])
        used = 0
        from .catalog import stacks_needed
        tier = int(s.get("satchel_stack_extra") or 0)
        for item, qty in rows:
            used += stacks_needed(qty, item_stack_cap(item, stack_tier=tier))
            cab_items.append(_sku(
                sid=f"take-{item}",
                kind="take",
                name=item_label(item),
                emoji=_item_emoji(item),
                note=f"柜里 {qty}",
                detail="取回行囊。",
                price="取",
                can=True,
                target=item_label(item),
                qty=qty,
            ))
        for item, qty in (stock or {}).items():
            n = int(qty or 0)
            if n <= 0:
                continue
            if _cabinet_forbid(item):
                continue
            if kitchen.is_cooked_item(item):
                continue
            cab_items.append(_sku(
                sid=f"put-{item}",
                kind="put",
                name=item_label(item),
                emoji=_item_emoji(item),
                note=f"行囊 {n}",
                detail="放进潮柜。小偷翻不到。",
                price="存",
                can=True,
                target=item_label(item),
                qty=n,
            ))
        if cap < config.CABINET_SLOTS_MAX:
            cab_items.append(_sku(
                sid="expand",
                kind="expand",
                name="潮柜加一格",
                emoji="➕",
                note=f"{used}/{cap} 格。每格 {config.CABINET_SLOT_COST} 票，顶 {config.CABINET_SLOTS_MAX}。",
                detail=f"加一格要 {config.CABINET_SLOT_COST} 票。",
                price=f"{config.CABINET_SLOT_COST} 票",
                can=tickets >= config.CABINET_SLOT_COST,
                target="1",
            ))
        if not any(row["kind"] == "put" for row in cab_items) and not any(row["kind"] == "take" for row in cab_items):
            cab_items.insert(0, _sku(
                sid="cab-empty",
                kind="look",
                name="潮柜空着",
                emoji="🗄️",
                note=f"{used}/{cap} 格。行囊这会儿没有能存的生鲜。",
                detail="生鲜进潮柜。熟菜走冰箱。粪便走堆肥桶。",
                price="看",
                can=True,
                target="status",
            ))

    if built and not has_fridge:
        bag_fr = int(stock.get("fit_fridge") or 0) > 0
        if bag_fr and empty_soft:
            cab_items.append(_sku(
                sid="install-fridge",
                kind="install",
                name="装冰箱",
                emoji="🧊",
                note="行囊里有冰箱，装上才能存熟菜。开小馆也要它。",
                detail="装到空的软装槽。熟菜进冰箱。",
                price="装",
                can=True,
                target="fridge",
            ))
        elif empty_soft:
            cab_items.append(_sku(
                sid="buy-fridge",
                kind="buy_install",
                name="买冰箱",
                emoji="🧊",
                note=f"{HUT_SOFT['fridge']['cost']} 票。熟菜放这儿。开小馆要冰箱。",
                detail="买冰箱并装上。生鲜走潮柜。",
                price=f"{HUT_SOFT['fridge']['cost']} 票",
                can=tickets >= HUT_SOFT["fridge"]["cost"],
                target="fridge",
            ))
    elif built and has_fridge:
        prev_factory = conn.row_factory
        conn.row_factory = aiosqlite.Row
        fridge_rows = await (await conn.execute(
            """
            SELECT dish_key, stars, quantity FROM meal_storage
            WHERE steward_id=? AND quantity>0 ORDER BY stored_at
            """,
            (s["id"],),
        )).fetchall()
        conn.row_factory = prev_factory
        for r in fridge_rows:
            label = kitchen._fridge_label(r["dish_key"], r["stars"])
            q = int(r["quantity"] or 0)
            cab_items.append(_sku(
                sid=f"fridge-take-{r['dish_key']}-{r['stars']}",
                kind="take",
                name=label,
                emoji="🧊",
                note=f"冰箱 {q}",
                detail="取出回行囊。",
                price="取",
                can=True,
                target=label,
                qty=q,
            ))
        for item, qty in (stock or {}).items():
            n = int(qty or 0)
            if n <= 0 or not kitchen.is_cooked_item(item):
                continue
            cab_items.append(_sku(
                sid=f"fridge-put-{item}",
                kind="put",
                name=item_label(item),
                emoji="🍽️",
                note=f"行囊 {n}",
                detail="熟菜进冰箱。",
                price="存",
                can=True,
                target=item_label(item),
                qty=n,
            ))

    compost_items: list[dict[str, Any]] = []
    fill, ready = (0, 0)
    if built and not has_bin:
        bag_bin = int(stock.get("fit_compost_bin") or 0) > 0
        if bag_bin and empty_soft:
            compost_items.append(_sku(
                sid="install-bin",
                kind="install",
                name="装堆肥桶",
                emoji="🪣",
                note="行囊里有桶，装上才能沤粪。",
                detail="空槽也能装。桶不是柜子，粪便丢进去沤层。",
                price="装",
                can=True,
                target="compost_bin",
            ))
        elif empty_soft:
            compost_items.append(_sku(
                sid="buy-bin",
                kind="buy_install",
                name="买堆肥桶",
                emoji="🪣",
                note=f"{HUT_SOFT['compost_bin']['cost']} 票。粪便丢进去沤。",
                detail="买堆肥桶并装上。粪便别进潮柜。",
                price=f"{HUT_SOFT['compost_bin']['cost']} 票",
                can=tickets >= HUT_SOFT["compost_bin"]["cost"],
                target="compost_bin",
            ))
        else:
            compost_items.append(_sku(
                sid="bin-slot",
                kind="look",
                name="软装槽满了",
                emoji="🪣",
                note="没有空槽装堆肥桶。先升级小屋。",
                detail="软装槽满了。先升级再买桶。",
                price="看",
                can=True,
                target="status",
            ))
    elif built and has_bin:
        fill, ready = await _compost_bin_row(conn, s["id"])
        compost_items.append(_sku(
            sid="bin-look",
            kind="look",
            name="堆肥桶",
            emoji="🪣",
            note=f"{fill}/{config.COMPOST_BIN_LAYERS} 层，可取堆肥 x{ready}",
            detail="粪便丢进去沤层，满 7 层结 1 份堆肥。只能取堆肥。",
            price="看",
            can=True,
            target="status",
        ))
        for item, qty in (stock or {}).items():
            n = int(qty or 0)
            if n <= 0 or item not in MANURE:
                continue
            compost_items.append(_sku(
                sid=f"bin-put-{item}",
                kind="compost_put",
                name=item_label(item),
                emoji=_item_emoji(item),
                note=f"行囊 {n} · 沤 +{int(MANURE[item]['compost_yield'])}/份",
                detail="丢进堆肥桶沤层。满 7 层结 1 份堆肥。",
                price="沤",
                can=True,
                target=item_label(item),
                qty=n,
            ))
        if ready > 0:
            compost_items.append(_sku(
                sid="bin-take",
                kind="compost_take",
                name="取出堆肥",
                emoji="🪴",
                note=f"桶里结好 {ready} 份。",
                detail="取出回行囊，拿去份地施肥。",
                price="取",
                can=True,
                target=str(ready),
                qty=ready,
            ))
        if not any(row["kind"] == "compost_put" for row in compost_items):
            compost_items.append(_sku(
                sid="bin-need",
                kind="look",
                name="行囊没有粪便",
                emoji="💩",
                note="喂畜栏会顺手收粪。粪便别进潮柜。",
                detail="羊粪 / 猪粪 / 牛粪才能沤。先去畜栏喂。",
                price="看",
                can=True,
                target="status",
            ))

    barn_built = bool(s.get("barn_built"))
    barn_items: list[dict[str, Any]] = []
    collectable = 0
    if built and not barn_built:
        barn_items.append(_sku(
            sid="erect",
            kind="barn_erect",
            name="搭畜栏",
            emoji="🪵",
            note=f"{config.BARN_ERECT_COST} 票，{config.BARN_SLOTS} 槽。每天算岸维。",
            detail=f"搭畜栏要 {config.BARN_ERECT_COST} 票。粪便进堆肥桶，不要进潮柜。",
            price=f"{config.BARN_ERECT_COST} 票",
            can=tickets >= config.BARN_ERECT_COST,
            target="",
        ))
    elif built and barn_built:
        prev_factory = conn.row_factory
        conn.row_factory = aiosqlite.Row
        animals = await (await conn.execute(
            "SELECT * FROM barn_animals WHERE steward_id=? ORDER BY slot",
            (s["id"],),
        )).fetchall()
        day = db.day_id()
        collected = {
            int(r["slot"])
            for r in await (await conn.execute(
                "SELECT slot FROM barn_daily_collect WHERE steward_id=? AND day=?",
                (s["id"], day),
            )).fetchall()
        }
        conn.row_factory = prev_factory
        by_slot = {int(r["slot"]): dict(r) for r in animals}
        empty_slots = [
            slot for slot in range(1, config.BARN_SLOTS + 1)
            if not (by_slot.get(slot) or {}).get("species")
        ]
        for slot in range(1, config.BARN_SLOTS + 1):
            row = by_slot.get(slot) or {}
            species = row.get("species")
            if not species or species not in LIVESTOCK:
                continue
            spec = LIVESTOCK[species]
            fed = bool(row.get("fed"))
            ready_h = barn._ready(row, species)
            feed_name = ITEM_NAMES.get(spec["feed"], spec["feed"])
            have_feed = int(stock.get(spec["feed"]) or 0) >= int(spec["feed_qty"])
            have_generic = int(stock.get("feed_animal") or 0) > 0
            can_feed = (not fed) and (have_feed or have_generic)
            if not fed:
                barn_items.append(_sku(
                    sid=f"feed-{slot}",
                    kind="barn_feed",
                    name=f"喂 #{slot} {spec['name']}",
                    emoji=spec.get("emoji") or "·",
                    note=f"要 {feed_name} x{spec['feed_qty']}（或动物饲料）。",
                    detail="喂过才收。粪便会顺手进行囊，拿去堆肥桶。",
                    price="喂" if can_feed else "看",
                    can=can_feed,
                    target=str(slot),
                ))
            if spec.get("daily") or spec.get("hive"):
                can_c = bool(fed) and slot not in collected
                if can_c:
                    collectable += 1
                barn_items.append(_sku(
                    sid=f"collect-{slot}",
                    kind="barn_collect",
                    name=f"收 #{slot} {spec['name']}",
                    emoji=spec.get("emoji") or "·",
                    note="今日已收。" if slot in collected else ("先喂再收。" if not fed else "可以收了。"),
                    detail="日常收奶/蛋/蜜。羊剪毛走剪。",
                    price="收" if can_c else "看",
                    can=can_c,
                    target=str(slot),
                ))
            if species == "sheep":
                have_shears = int(stock.get("tool_shears") or 0) > 0
                can_sh = bool(fed) and have_shears and slot not in collected
                barn_items.append(_sku(
                    sid=f"shear-{slot}",
                    kind="barn_shear",
                    name=f"剪 #{slot} 羊毛",
                    emoji="✂️",
                    note="要剪毛剪刀。羊还在。" if have_shears else "先去广场杂货铺买剪毛剪刀。",
                    detail="剪毛不杀羊。",
                    price="剪" if can_sh else "看",
                    can=can_sh,
                    target=str(slot),
                ))
            if not spec.get("guard") and not spec.get("hive"):
                barn_items.append(_sku(
                    sid=f"harvest-{slot}",
                    kind="barn_harvest",
                    name=f"大收 #{slot} {spec['name']}",
                    emoji=spec.get("emoji") or "·",
                    note="长成了，栏位会空出来。" if ready_h else "还没长成。",
                    detail="大收会清栏。日常动物可先每日收。",
                    price="收" if ready_h else "看",
                    can=bool(ready_h),
                    target=str(slot),
                ))
        if empty_slots:
            slot = empty_slots[0]
            for key, spec in LIVESTOCK.items():
                barn_items.append(_sku(
                    sid=f"buy-{key}",
                    kind="barn_buy",
                    name=f"买{spec['name']}",
                    emoji=spec.get("emoji") or "·",
                    note=f"{spec['buy']} 票，进空栏 #{slot}。",
                    detail=f"买{spec['name']}放到空栏。粪便进堆肥桶。",
                    price=f"{spec['buy']} 票",
                    can=tickets >= int(spec["buy"]),
                    target=f"{key} {slot}",
                ))
        milk = int(stock.get("goat_milk") or 0)
        if milk >= 2:
            barn_items.append(_sku(
                sid="churn",
                kind="barn_churn",
                name="搅山羊奶",
                emoji="🧀",
                note=f"行囊山羊奶 {milk}。两份奶一份奶酪。",
                detail="只搅山羊奶。牛奶不能搅。",
                price="搅",
                can=True,
                target=str(milk - (milk % 2)),
                qty=milk - (milk % 2),
            ))
        if not barn_items:
            barn_items.append(_sku(
                sid="barn-empty",
                kind="look",
                name="畜栏空着",
                emoji="🪵",
                note="栏位都空。先买一只。",
                detail="买鸡鸭羊牛山羊兔猪狗或蜂箱。",
                price="看",
                can=True,
                target="status",
            ))

    cook_items: list[dict[str, Any]] = []
    cook_ready = 0
    if built:
        cook_items, _recipe_left, cook_ready = await _cook_tab_items(conn, s, stock)

    cab_badge = ""
    if has_cab or has_fridge:
        cab_badge = str(sum(1 for row in cab_items if row["kind"] in ("put", "take"))) or ""
    tabs = [
        {"key": "home", "label": "屋里", "badge": "睡" if can_sleep else ""},
        {"key": "cook", "label": "灶", "badge": str(cook_ready) if cook_ready else ""},
        {"key": "cabinet", "label": "潮柜", "badge": cab_badge},
        {"key": "compost", "label": "堆肥", "badge": str(ready) if ready else ""},
        {"key": "barn", "label": "畜栏", "badge": str(collectable) if collectable else ""},
    ]
    return {
        "name": name,
        "line": spoken,
        "built": built,
        "level": lvl,
        "level_name": meta["name"] if built else "",
        "scene_id": f"hut-{lvl}" if built else "",
        "tabs": tabs,
        "items": {
            "home": home_items,
            "cook": cook_items,
            "cabinet": cab_items,
            "compost": compost_items,
            "barn": barn_items,
        },
        "sleep_energy": sleep_energy,
        "can_sleep": can_sleep,
        "upgrade_cost": upgrade_cost,
        "can_upgrade": can_upgrade,
    }
