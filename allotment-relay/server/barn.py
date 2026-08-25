"""畜栏 — 牛羊猪狗兔鸡鸭山羊蜂箱，喂食产出与日常收奶。"""

from __future__ import annotations

import random

import aiosqlite

from . import config, db, flavor, survival
from . import upkeep as upkeep_mod
from .catalog import ITEM_NAMES, LIVESTOCK, MANURE, resolve_livestock
from .game import require_steward


def _day_id() -> int:
    return db.day_id()


def _shift_hint() -> str:
    wait = db.seconds_until_next_day()
    hours, rem = divmod(wait, 3600)
    mins = rem // 60
    if hours <= 0:
        when = f"{mins} 分钟"
    else:
        when = f"{hours} 小时" + (f" {mins} 分" if mins else "")
    return f"游戏日 UTC 午夜换班（北京 08:00），还要约 {when}"


def _fed_today(animal: dict, day: int | None = None) -> bool:
    day = _day_id() if day is None else day
    return int(animal.get("fed_day") or 0) == day


def _daily_kind(species: str) -> str | None:
    """日常产物：collect / shear。活畜本身不是这个。"""
    meta = LIVESTOCK.get(species) or {}
    if meta.get("hive") or meta.get("daily"):
        return "collect"
    if species == "sheep":
        return "shear"
    return None


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


def _remaining(collect_row: dict | None, full_qty: int) -> tuple[int, str]:
    """返回 (还能收多少, 状态标签)。"""
    if not collect_row:
        return full_qty, "open"
    if int(collect_row.get("collected") or 0):
        return 0, "collected"
    left = int(collect_row.get("qty") or 0)
    if left <= 0:
        return 0, "stolen"
    return left, "leftover"


def _line(animal: dict | None, slot: int, collect_row: dict | None = None) -> str:
    if not animal or not animal.get("species"):
        return f"  #{slot}: 空栏"
    spec = LIVESTOCK[animal["species"]]
    day = _day_id()
    if spec.get("guard"):
        state = "守夜中" if animal.get("guard") else "幼犬"
    elif not _fed_today(animal, day) and not spec.get("guard"):
        state = "待喂"
    elif spec.get("hive") or spec.get("daily"):
        full = spec["product_qty"]
        left, flag = _remaining(collect_row, full)
        if flag == "collected":
            state = "今日已收"
        elif flag == "stolen":
            thief = collect_row.get("thief_name") or "有人"
            state = f"今日被{thief}偷光"
        elif flag == "leftover":
            thief = collect_row.get("thief_name") or "有人"
            state = f"被{thief}偷过，还剩{left}·可 collect"
        else:
            extra = " · 可出栏" if _ready(animal, animal["species"]) else ""
            state = f"可 collect{extra}"
    elif animal["species"] == "sheep":
        full = spec["product_qty"]
        left, flag = _remaining(collect_row, full)
        grow = " · 可出栏" if _ready(animal, "sheep") else ""
        if flag == "collected":
            state = f"今日已剪{grow}"
        elif flag == "stolen":
            thief = collect_row.get("thief_name") or "有人"
            state = f"今日羊毛被{thief}偷走{grow}"
        elif flag == "leftover":
            thief = collect_row.get("thief_name") or "有人"
            state = f"被{thief}偷过，还剩{left}·可 shear{grow}"
        else:
            state = f"可 shear{grow}"
    elif _ready(animal, animal["species"]):
        state = "可收（出栏 harvest，不是日常 collect）"
    elif animal.get("fed") or _fed_today(animal, day):
        state = "放养"
    else:
        state = "待喂"
    return f"  #{slot}: {spec['emoji']}{spec['name']}（{state}）"


def _parse_slot_arg(token: str | None) -> int | None:
    """None = 全栏。"""
    if not token or token.lower() in ("all", "全", "全部", "*", "全栏"):
        return None
    text = token.strip().lstrip("#号第槽栏")
    try:
        n = int(text)
    except ValueError:
        raise ValueError(f"槽位写 1~{config.BARN_SLOTS}，或不写=全栏") from None
    if n < 1 or n > config.BARN_SLOTS:
        raise ValueError(f"槽位 1~{config.BARN_SLOTS}")
    return n


async def _daily_row(
    conn: aiosqlite.Connection, steward_id: int, slot: int, day: int
) -> dict | None:
    row = await (await conn.execute(
        "SELECT * FROM barn_daily_collect WHERE steward_id=? AND slot=? AND day=?",
        (steward_id, slot, day),
    )).fetchone()
    return dict(row) if row else None


async def _upsert_daily(
    conn: aiosqlite.Connection,
    steward_id: int,
    slot: int,
    day: int,
    *,
    qty: int,
    stolen: int,
    thief_name: str,
    collected: int,
) -> None:
    await conn.execute(
        """
        INSERT INTO barn_daily_collect
            (steward_id, slot, day, qty, stolen, thief_name, collected)
        VALUES (?,?,?,?,?,?,?)
        ON CONFLICT(steward_id, slot, day) DO UPDATE SET
            qty=excluded.qty,
            stolen=excluded.stolen,
            thief_name=excluded.thief_name,
            collected=excluded.collected
        """,
        (steward_id, slot, day, qty, stolen, thief_name, collected),
    )


def _steal_take(available: int) -> tuple[int, int]:
    """掐走约 30%；活畜还在，qty=1 也可以整份偷走。"""
    if available <= 0:
        return 0, 0
    taken = max(1, int(available * config.SCRUMP_TAKE_RATE))
    taken = min(taken, available)
    return taken, available - taken


async def stealable_slots(
    conn: aiosqlite.Connection, steward_id: int
) -> list[dict]:
    """邻居未收的日常产物（蛋/奶/蜜/毛）。活畜不在此列。"""
    day = _day_id()
    conn.row_factory = aiosqlite.Row
    rows = await (await conn.execute(
        "SELECT * FROM barn_animals WHERE steward_id=? AND species IS NOT NULL",
        (steward_id,),
    )).fetchall()
    out: list[dict] = []
    for raw in rows:
        animal = dict(raw)
        species = animal.get("species")
        kind = _daily_kind(species or "")
        if not kind or not _fed_today(animal, day):
            continue
        meta = LIVESTOCK[species]
        rec = await _daily_row(conn, steward_id, animal["slot"], day)
        left, flag = _remaining(rec, meta["product_qty"])
        if left <= 0:
            continue
        out.append({
            "slot": animal["slot"],
            "animal": animal,
            "species": species,
            "kind": kind,
            "meta": meta,
            "available": left,
            "record": rec,
        })
    return out


async def stealable_count(conn: aiosqlite.Connection, steward_id: int) -> int:
    return len(await stealable_slots(conn, steward_id))


def _barn_catch_chance(steward: dict, peer: dict, *, dog: bool) -> float:
    home = db.now() - peer["last_active_at"] <= config.SCRUMP_ACTIVE_WINDOW
    chance = 0.70 if home else 0.18
    if dog:
        chance += 0.28
    if steward.get("mascot_trait") == "scout":
        chance -= 0.10
    return max(0.08, min(0.95, chance))


async def barn_steal(steward: dict, target_name: str, slot: int | None = None) -> str:
    """偷邻居未收的蛋/奶/蜜/毛。活畜偷不走。和偷菜共用逾篱次数。"""
    peer = await db.get_steward_by_name(target_name)
    if not peer or not peer.get("enrolled"):
        raise ValueError(
            f"找不到管理员「{target_name}」。先 steward_ops 邻居 看名单。"
        )
    if peer["id"] == steward["id"]:
        raise ValueError("不能偷自己的畜栏")
    day = _day_id()
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        used = (await (await conn.execute(
            "SELECT COUNT(*) FROM scrump_log WHERE thief_id=? AND day=?",
            (steward["id"], day),
        )).fetchone())[0]
        if used >= config.SCRUMP_DAILY:
            raise ValueError(
                f"今日逾篱已满 {config.SCRUMP_DAILY} 次，明天再来（{_shift_hint()}）"
            )
        same = await (await conn.execute(
            "SELECT 1 FROM scrump_log WHERE thief_id=? AND target_id=? AND day=?",
            (steward["id"], peer["id"], day),
        )).fetchone()
        if same:
            raise ValueError(
                f"今天已经摘过 {peer['name']} 一次（菜或畜栏算同一次），换一家或明天再来"
            )

        candidates = await stealable_slots(conn, peer["id"])
        if slot is not None:
            candidates = [c for c in candidates if c["slot"] == slot]
            if not candidates:
                raise ValueError(
                    f"{peer['name']} 畜栏 #{slot} 没有未收的蛋/奶/蜜/毛。"
                    "活畜偷不走；已经 collect/shear 进袋的也偷不走。"
                )
        if not candidates:
            raise ValueError(
                f"{peer['name']} 畜栏没有未收的日常产物。"
                "只能偷蛋/奶/蜜/毛，活畜偷不走。先 steward_ops 邻居 看谁家栏里还没收。"
            )
        pick = max(candidates, key=lambda c: (c["available"], -c["slot"]))
        dog = await has_guard_dog(conn, peer["id"])
        chance = _barn_catch_chance(steward, peer, dog=dog)
        caught = random.random() < chance
        fine = config.SCRUMP_FINE_TICKETS
        if caught and steward.get("mascot_trait") == "scout":
            fine = max(1, fine // 2)

        await conn.execute(
            "INSERT INTO scrump_log (thief_id, target_id, day) VALUES (?,?,?)",
            (steward["id"], peer["id"], day),
        )

        slot_n = pick["slot"]
        meta = pick["meta"]
        product = meta["product"]
        label = ITEM_NAMES.get(product, product)

        if caught:
            await conn.execute(
                "UPDATE stewards SET tickets=MAX(0, tickets-?) WHERE id=?",
                (fine, steward["id"]),
            )
            await survival.bump(conn, steward["id"], standing=-random.randint(6, 12))
            from . import undertide as _ut
            jail_note = await _ut.on_scrump_busted(conn, steward) or ""
            dog_note = "（守夜狗叫了）" if dog else ""
            msg = (
                f"摸 {peer['name']} 畜栏 #{slot_n} 被逮正着，罚 {fine} 票{dog_note}"
                f"{jail_note}（可 plot_ops amends {peer['name']}）"
            )
            loot = "被抓"
            action = "scrump_busted"
        else:
            taken, remain = _steal_take(pick["available"])
            await db.add_item(conn, steward["id"], product, taken)
            thief_name = pick["record"].get("thief_name") if pick["record"] else ""
            names = "、".join(
                x for x in (thief_name, steward["name"]) if x
            )
            await _upsert_daily(
                conn, peer["id"], slot_n, day,
                qty=remain, stolen=1, thief_name=names, collected=0,
            )
            from . import bond as bond_mod
            await bond_mod.grant(conn, steward["id"], bond_mod.SCRUMP, "labor")
            left_note = f"还剩 {remain} 给主人收" if remain else "这栏今天被掏空了"
            msg = (
                f"摸走 {peer['name']} 畜栏 #{slot_n} {label} x{taken}。"
                f"{left_note}。活畜还在。今日逾篱 {used + 1}/{config.SCRUMP_DAILY}"
            )
            loot = f"{label} x{taken}"
            action = "scrump"

        await conn.execute(
            "INSERT INTO chronicle (action, actor_id, target_id, text, created_at) VALUES (?,?,?,?,?)",
            (
                action,
                steward["id"],
                peer["id"],
                f"{steward['name']} 逾篱 {peer['name']} 畜栏#{slot_n} {loot}",
                db.now(),
            ),
        )
        await conn.commit()
    return msg


async def _collect_slot(
    conn: aiosqlite.Connection,
    s: dict,
    slot: int,
    row: dict,
    day: int,
    *,
    as_shear: bool = False,
) -> str:
    if not row.get("species"):
        raise ValueError("空栏")
    species = row["species"]
    meta = LIVESTOCK[species]
    kind = _daily_kind(species)
    if as_shear:
        if species != "sheep":
            raise ValueError("只有羊能剪毛")
        cur = await conn.execute(
            "SELECT 1 FROM satchel WHERE steward_id=? AND item='tool_shears' AND quantity>0",
            (s["id"],),
        )
        if not await cur.fetchone():
            raise ValueError("剪毛需要剪毛剪刀 — visit_ops tt buy 剪毛剪刀")
    else:
        if kind != "collect":
            if species == "sheep":
                raise ValueError("羊不走 collect，用 shear 剪毛（要剪刀）")
            raise ValueError("该动物不支持 collect，长成后 harvest 出栏（一次性，不是每天）")
    if not _fed_today(row, day):
        raise ValueError(f"先 barn feed {slot} 再收（每个游戏日要喂一次）")

    rec = await _daily_row(conn, s["id"], slot, day)
    full = meta["product_qty"]
    left, flag = _remaining(rec, full)
    if flag == "collected":
        raise ValueError(
            f"#{slot} 今日已收过（{_shift_hint()}）。"
            "空 command 的 collect 会收其它还没收的栏：hut_ops barn collect"
        )
    if flag == "stolen":
        thief = (rec or {}).get("thief_name") or "有人"
        raise ValueError(
            f"#{slot} 今日产物被{thief}偷走了（{_shift_hint()}）。活畜还在。"
        )
    product = meta["product"]
    qty = left
    extra = ""
    leftover = flag == "leftover"
    if leftover:
        thief = (rec or {}).get("thief_name") or "有人"
        extra = f" · {thief}偷过，收走剩下的"
    elif not as_shear:
        if meta.get("hive") and random.random() < 0.2:
            qty += 1
        if species in ("cow", "goat"):
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
    await _upsert_daily(
        conn, s["id"], slot, day,
        qty=0, stolen=int((rec or {}).get("stolen") or 0),
        thief_name=str((rec or {}).get("thief_name") or ""),
        collected=1,
    )
    if as_shear:
        return f"#{slot} 剪下羊毛 x{qty}（羊还在）{extra}"
    return f"#{slot} 收取 {ITEM_NAMES.get(product, product)} x{qty}{extra}"


async def barn_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    parts = command.strip().split(maxsplit=2)
    verb = (parts[0] if parts else "status").lower()

    if verb in ("status", "看", "栏"):
        day = _day_id()
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            rows = await (await conn.execute(
                "SELECT * FROM barn_animals WHERE steward_id=? ORDER BY slot",
                (s["id"],),
            )).fetchall()
            recs = await (await conn.execute(
                "SELECT * FROM barn_daily_collect WHERE steward_id=? AND day=?",
                (s["id"], day),
            )).fetchall()
        built = s.get("barn_built")
        by_slot = {r["slot"]: dict(r) for r in rows}
        by_rec = {r["slot"]: dict(r) for r in recs}
        lines = [
            f"畜栏: {'已建' if built else '未建'}（erect {config.BARN_ERECT_COST} 票）",
            f"槽位 {config.BARN_SLOTS}",
            f"日常 collect / shear：每个游戏日一次，不是一周一次。{_shift_hint()}",
            "出栏 harvest：兔/猪/羊/牛/山羊长成后一次性（约 8～20 小时），会清栏。",
        ]
        for slot in range(1, config.BARN_SLOTS + 1):
            lines.append(_line(by_slot.get(slot), slot, by_rec.get(slot)))
        lines.append(f"可购: {', '.join(LIVESTOCK.keys())}（也认中文：barn buy 鸡 2）")
        lines.append(
            "collect 不写槽位=全栏日收 · feed 不写槽位=全栏喂 · "
            "shear 剪羊毛（要剪刀） · churn 山羊奶→奶酪"
        )
        lines.append(
            "偷：hut_ops barn 偷 名字（或 plot_ops 偷畜 名字）。"
            "只能偷未收的蛋/奶/蜜/毛，活畜偷不走；和偷菜共用每日逾篱次数。"
        )
        lines.append("粪便进堆肥桶：hut_ops 堆肥桶 存 羊粪 3（先 buy compost_bin → install）")
        if built:
            lines.append(
                f"岸维：畜栏每周 {upkeep_mod.BARN_BASE} 票 + 在栏 {upkeep_mod.BARN_STOCKED} 票/槽"
                " → visit_ops 潮生会 维"
            )
        return "\n".join(lines)

    if verb == "catalog":
        lines = [
            "畜栏图鉴（buy 物种 槽位 / feed / collect|shear 槽位）：",
            "日常产物每个游戏日一次（UTC 午夜=北京 08:00），不是一周一次。",
            "空 collect / feed = 全栏。出栏 harvest 是一次性清栏，别和日收搞混。",
        ]
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
                    f"每天喂{feed} x{meta['feed_qty']} · collect 采{ITEM_NAMES.get(meta['product'], meta['product'])}"
                )
            elif meta.get("daily"):
                prod = ITEM_NAMES.get(meta["product"], meta["product"])
                extra = " · 挤奶器（Tt酱）多收 1" if key in ("cow", "goat") else ""
                lines.append(
                    f"  {meta['emoji']}{meta['name']} {meta['buy']}票 — "
                    f"每天 feed 后 collect {prod} · harvest 满周期出栏{extra}"
                )
            else:
                prod = ITEM_NAMES.get(meta["product"], meta["product"])
                manure = ""
                if meta.get("manure"):
                    manure = f" · 产{MANURE[meta['manure']]['name']}"
                shear = " · 每天 shear 剪毛（要剪刀，不杀羊）" if key == "sheep" else ""
                lines.append(
                    f"  {meta['emoji']}{meta['name']} {meta['buy']}票 — "
                    f"喂{feed} x{meta['feed_qty']} → {prod} x{meta['product_qty']}{manure}{shear}"
                )
        lines.append("活畜偷不走。未收的蛋/奶/蜜/毛：hut_ops barn 偷 名字")
        lines.append("粪便进堆肥桶 hut_ops 堆肥桶 存，不能进潮柜")
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
        return f"畜栏就绪（-{config.BARN_ERECT_COST} 票，{config.BARN_SLOTS} 槽）。每周岸维 {upkeep_mod.BARN_BASE} 票起 → visit_ops 潮生会 维"

    if verb == "buy" and len(parts) >= 2:
        if not s.get("barn_built"):
            raise ValueError("先 barn_ops erect")
        species = resolve_livestock(parts[1])
        slot = int(parts[2]) if len(parts) > 2 else 1
        if not species:
            raise ValueError(f"可购: {', '.join(LIVESTOCK.keys())}（也认中文名）")
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
            stocked = db.now()
            await conn.execute(
                """
                UPDATE barn_animals SET species=?, stocked_at=?, fed=0, fed_day=0, guard=?
                WHERE steward_id=? AND slot=?
                """,
                (species, stocked, guard, s["id"], slot),
            )
            await conn.commit()
        if meta.get("guard"):
            return f"#{slot} 入驻 {meta['name']} — 守夜减偷菜/偷栏概率"
        if meta.get("hive"):
            return f"#{slot} 安置 {meta['emoji']}{meta['name']} — 每天 feed 后 collect 采蜜"
        return f"#{slot} 购入 {meta['emoji']}{meta['name']}（-{meta['buy']} 票）"

    if verb in ("feed", "喂", "喂食"):
        day = _day_id()
        want = _parse_slot_arg(parts[1] if len(parts) > 1 else None)
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            if want is None:
                slots = list(range(1, config.BARN_SLOTS + 1))
            else:
                slots = [want]
            notes: list[str] = []
            fed_n = 0
            for slot in slots:
                row = dict(await (await conn.execute(
                    "SELECT * FROM barn_animals WHERE steward_id=? AND slot=?",
                    (s["id"], slot),
                )).fetchone() or {})
                if not row.get("species"):
                    if want is not None:
                        raise ValueError("空栏")
                    continue
                meta = LIVESTOCK[row["species"]]
                if meta.get("guard"):
                    if row.get("guard"):
                        if want is not None:
                            notes.append(f"#{slot} 已经在守夜，不必每天喂")
                        continue
                    if not await db.take_item(conn, s["id"], meta["feed"], meta["feed_qty"]):
                        if not await db.take_item(conn, s["id"], "feed_animal", 1):
                            raise ValueError(
                                f"喂狗需要 {ITEM_NAMES.get(meta['feed'], meta['feed'])}"
                                "（或 Tt酱店里的动物饲料）"
                            )
                    await conn.execute(
                        "UPDATE barn_animals SET guard=1, fed=1, fed_day=? WHERE steward_id=? AND slot=?",
                        (day, s["id"], slot),
                    )
                    notes.append(f"#{slot} 已喂，开始守夜")
                    fed_n += 1
                    continue
                if _fed_today(row, day):
                    if want is not None:
                        notes.append(f"#{slot} 今日已喂（{_shift_hint()}）")
                    continue
                if not await db.take_item(conn, s["id"], meta["feed"], meta["feed_qty"]):
                    if not await db.take_item(conn, s["id"], "feed_animal", 1):
                        raise ValueError(
                            f"#{slot} 需要 {ITEM_NAMES.get(meta['feed'], meta['feed'])} x{meta['feed_qty']}"
                            "（或 visit_ops tt buy 动物饲料）"
                        )
                await conn.execute(
                    "UPDATE barn_animals SET fed=1, fed_day=? WHERE steward_id=? AND slot=?",
                    (day, s["id"], slot),
                )
                manure_msg = ""
                if meta.get("manure"):
                    qty = meta.get("manure_feed", 1)
                    await db.add_item(conn, s["id"], meta["manure"], qty)
                    manure_msg = f"，顺手收 {MANURE[meta['manure']]['name']} x{qty}"
                notes.append(f"#{slot} 已喂食{manure_msg}")
                fed_n += 1
            await conn.commit()
        if not notes:
            return f"没有需要喂的栏（空栏或今日已喂）。{_shift_hint()}"
        if want is not None and notes and "今日已喂" in notes[0] and fed_n == 0:
            return notes[0]
        return "\n".join(notes)

    if verb in ("collect", "收", "收取", "挤奶", "收蛋", "采蜜"):
        day = _day_id()
        want = _parse_slot_arg(parts[1] if len(parts) > 1 else None)
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            if want is None:
                slots = list(range(1, config.BARN_SLOTS + 1))
            else:
                slots = [want]
            ok: list[str] = []
            skipped: list[str] = []
            for slot in slots:
                row = dict(await (await conn.execute(
                    "SELECT * FROM barn_animals WHERE steward_id=? AND slot=?",
                    (s["id"], slot),
                )).fetchone() or {})
                if not row.get("species"):
                    if want is not None:
                        raise ValueError("空栏")
                    continue
                if _daily_kind(row["species"]) != "collect":
                    if want is not None:
                        return await _collect_slot(conn, s, slot, row, day)
                    continue
                try:
                    ok.append(await _collect_slot(conn, s, slot, row, day))
                except ValueError as exc:
                    if want is not None:
                        raise
                    skipped.append(str(exc))
            await conn.commit()
        if want is not None:
            msg = ok[0] if ok else "没有收取"
            tail = flavor.maybe_suffix(["日常小收，积少成多", "栏里忙，票里稳"])
            if tail:
                msg += f" · {tail}"
            return msg
        if not ok:
            if any("今日已收过" in x or "偷走" in x for x in skipped):
                return (
                    f"本游戏日没有还能收的栏。{_shift_hint()}。"
                    "status 看哪栏是「今日已收 / 被偷」。"
                    "人和 AI 共用一个号，可能是管家已经收过。"
                )
            hint = skipped[0] if skipped else "没有可收的日常产物（鸡鸭牛山羊蜂箱，先每天 feed）"
            return f"{hint}\n{_shift_hint()}"
        msg = "\n".join(ok)
        if skipped:
            msg += "\n（跳过已收/待喂的栏）"
        tail = flavor.maybe_suffix(["日常小收，积少成多", "栏里忙，票里稳"])
        if tail:
            msg += f" · {tail}"
        return msg

    if verb in ("harvest", "出栏", "宰"):
        slot = _parse_slot_arg(parts[1] if len(parts) > 1 else "1") or 1
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
                raise ValueError("还没长成，继续每天 feed（鸡鸭牛山羊可先 collect 日收）")
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
                UPDATE barn_animals SET species=NULL, stocked_at=NULL, fed=0, fed_day=0, guard=0
                WHERE steward_id=? AND slot=?
                """,
                (s["id"], slot),
            )
            await conn.commit()
        msg = f"#{slot} 出栏 {ITEM_NAMES.get(product, product)} x{qty}{bonus_msg}{manure_msg}"
        msg += flavor.maybe_suffix(["栏里忙，票里稳", "牲畜：今天也努力了"])
        await db.add_chronicle("barn", f"{s['name']} 畜栏收 {product}", s["id"])
        return msg

    if verb in ("shear", "剪", "剪毛"):
        day = _day_id()
        want = _parse_slot_arg(parts[1] if len(parts) > 1 else None)
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            if want is None:
                slots = list(range(1, config.BARN_SLOTS + 1))
            else:
                slots = [want]
            ok: list[str] = []
            for slot in slots:
                row = dict(await (await conn.execute(
                    "SELECT * FROM barn_animals WHERE steward_id=? AND slot=?",
                    (s["id"], slot),
                )).fetchone() or {})
                if not row.get("species"):
                    if want is not None:
                        raise ValueError("空栏")
                    continue
                if row["species"] != "sheep":
                    if want is not None:
                        raise ValueError("只有羊能剪毛")
                    continue
                try:
                    ok.append(await _collect_slot(conn, s, slot, row, day, as_shear=True))
                except ValueError as exc:
                    if want is not None:
                        raise
            await conn.commit()
        if not ok:
            raise ValueError("没有可剪的羊（先每天 feed，要剪刀）")
        return "\n".join(ok) + flavor.maybe_suffix(["剪刀咔嚓，羊：还行", "不杀羊也能出毛，文明"])

    if verb in ("steal", "偷", "偷畜", "偷栏"):
        if len(parts) < 2:
            raise ValueError(
                "用法: hut_ops barn 偷 名字 [槽位]\n"
                "只能偷未收的蛋/奶/蜜/毛，活畜偷不走。也可 plot_ops 偷畜 名字。"
                "和 plot_ops 偷菜 共用每日逾篱次数。"
            )
        slot = _parse_slot_arg(parts[2]) if len(parts) > 2 else None
        return await barn_steal(s, parts[1], slot)

    if verb == "compost" and len(parts) >= 2:
        from . import hut
        return await hut.compost_bin_command(s, ["存", *parts[1:]])

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
        f"未知 barn 指令: {command}（status/catalog/erect/buy/feed/collect/shear/harvest/偷/compost/churn）。"
        "日常 collect 每个游戏日一次，空 collect=全栏；活畜偷不走，蛋奶蜜毛 hut_ops barn 偷 名字。"
        "粪便进堆肥桶：hut_ops 堆肥桶 存 羊粪 3（barn compost 还认，但要先装桶）"
    )
