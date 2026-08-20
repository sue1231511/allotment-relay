"""岸畔小屋 — 硬装 / 软装 / 升级。装件加成在 catalog hint 里写了，这里真正生效。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import aiosqlite

from . import config, db, flavor
from .catalog import HUT_HARD, HUT_LEVELS, HUT_SOFT, ITEM_NAMES, LILI_DECOR, LILI_JUNK_DECOR


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


async def hut_ops(key_id: int, command: str) -> str:
    from .game import require_steward

    s = await require_steward(key_id)
    parts = command.strip().split(maxsplit=2)
    verb = parts[0].lower() if parts else "status"

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
        return "\n".join(lines)

    if verb == "catalog":
        kind = parts[1].lower() if len(parts) > 1 else "all"
        lines = [
            f"小屋建造：{config.HUT_BUILD_COST} 票（hut_ops build）",
            "小屋装件 catalog（buy 后 install 到槽位）：",
        ]
        if kind in ("all", "hard"):
            lines.append("【硬装】")
            for k, v in HUT_HARD.items():
                lines.append(f"  {k} — {v['emoji']}{v['name']} {v['cost']} 票 · {v['hint']}")
        if kind in ("all", "soft"):
            lines.append("【软装】")
            for k, v in HUT_SOFT.items():
                lines.append(f"  {k} — {v['emoji']}{v['name']} {v['cost']} 票 · {v['hint']}")
            lines.append("【栗栗稀有装饰】deco_* — lili_ops 换，install soft_N 键名")
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
                    raise ValueError(f"行囊没有 {deco_meta['name']}，先 lili_ops trade")
                old = await _fittings(conn, s["id"])
                if slot in old:
                    old_key = old[slot]
                    await db.add_item(conn, s["id"], old_key, 1)
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
                if slot in old:
                    await db.add_item(conn, s["id"], old[slot], 1)
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
            return f"#{slot} 挂上 {deco_meta['emoji']}{deco_meta['name']}。{deco_meta['hint']}"

        kind, meta = _catalog_item(key)
        if slot.startswith("hard") and kind != "hard":
            raise ValueError("硬装槽只能装 hard 类")
        if slot.startswith("soft") and kind != "soft":
            raise ValueError("软装槽只能装 soft 类")
        fit_item = f"fit_{key}"
        async with db.connect() as conn:
            if not await db.take_item(conn, s["id"], fit_item, 1):
                raise ValueError(f"行囊没有 {meta['name']}，先 buy {key}")
            old = await _fittings(conn, s["id"])
            if slot in old:
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
        return msg

    if verb == "remove" and len(parts) >= 2:
        slot = parts[1].lower()
        async with db.connect() as conn:
            fittings = await _fittings(conn, s["id"])
            if slot not in fittings:
                raise ValueError("该槽位是空的")
            key = fittings[slot]
            await conn.execute(
                "DELETE FROM hut_fittings WHERE steward_id=? AND slot=?",
                (s["id"], slot),
            )
            if key.startswith("deco_"):
                await db.add_item(conn, s["id"], key, 1)
            else:
                await db.add_item(conn, s["id"], f"fit_{key}", 1)
            await conn.commit()
        return f"已拆下 {slot} 的 {_fit_name(key)}，装件回行囊"

    raise ValueError(
        f"未知 hut 指令: {command}（status/build/upgrade/label/catalog/buy/install/remove）"
    )
