"""畜栏 — 牛羊猪狗兔鸡鸭山羊蜂箱，喂食产出与日常收奶。"""

from __future__ import annotations

import random

import aiosqlite

from . import config, db, flavor
from . import upkeep as upkeep_mod
from .catalog import ITEM_NAMES, LIVESTOCK, MANURE
from .game import require_steward

BARN_HELP = """畜栏子命令（整句写进 hut_ops command，前缀 barn）：
  status — 看栏。空 barn 也是这个
  catalog — 图鉴
  erect — 搭畜栏
  buy 鸡 2 — 买进指定槽（中文名或 chicken/cow/goat…）
  feed / feed 2 — 不写槽位喂全部；每个游戏日先喂再收
  collect / collect 2 / 收 — 日常收奶/蛋/蜜。每个游戏日一次（UTC 午夜=北京时间早上 8 点），不是一周一次。不写槽位=全收
  shear / 剪 — 剪羊毛（要剪刀）。不写槽位=全剪
  harvest 2 — 出栏收肉，动物会清空。不是每天收
  偷 名字 / 偷 名字 2 — 偷邻居还没收的奶/蛋/蜜（最多三成、留一份）。牲口本身不能偷。和偷菜共用逾篱次数
  churn 2 — 山羊奶→奶酪（牛奶不能搅）
日常收和床、偷菜一样按游戏日换班；人和 AI 共用这个号，管家收过也算。守夜狗要当天喂过才看家。"""


def _day_id() -> int:
    return db.day_id()


def _shift_hint() -> str:
    secs = db.seconds_until_next_day()
    if secs < 3600:
        wait = f"约 {max(1, secs // 60)} 分钟后"
    else:
        wait = f"约 {(secs + 3599) // 3600} 小时后"
    return f"游戏日 UTC 午夜换班（北京时间早上 8 点），{wait}"


def _fed_today(animal: dict | None, day: int | None = None) -> bool:
    if not animal:
        return False
    day = _day_id() if day is None else day
    return bool(animal.get("fed")) and int(animal.get("fed_day") or 0) == day


def _daily_meta(meta: dict) -> bool:
    return bool(meta.get("daily") or meta.get("hive"))


def _resolve_species(token: str) -> str | None:
    raw = (token or "").strip()
    if not raw:
        return None
    key = raw.lower()
    if key in LIVESTOCK:
        return key
    for sid, meta in LIVESTOCK.items():
        if meta["name"] == raw or str(meta.get("emoji") or "") == raw:
            return sid
    return None


def _parse_optional_slot(parts: list[str]) -> int | None:
    if len(parts) < 2:
        return None
    token = parts[1]
    if token in ("全部", "all", "*", "全"):
        return None
    try:
        slot = int(token)
    except ValueError:
        raise ValueError(f"槽位用数字 1~{config.BARN_SLOTS}，或不写槽位表示全部")
    if slot < 1 or slot > config.BARN_SLOTS:
        raise ValueError(f"槽位 1~{config.BARN_SLOTS}")
    return slot


async def _clear_slot_daily(conn: aiosqlite.Connection, steward_id: int, slot: int) -> None:
    await conn.execute(
        "DELETE FROM barn_daily_collect WHERE steward_id=? AND slot=?",
        (steward_id, slot),
    )
    await conn.execute(
        "DELETE FROM barn_daily_stolen WHERE steward_id=? AND slot=?",
        (steward_id, slot),
    )


async def _stolen_qty(conn: aiosqlite.Connection, steward_id: int, slot: int, day: int) -> int:
    cur = await conn.execute(
        "SELECT qty FROM barn_daily_stolen WHERE steward_id=? AND slot=? AND day=?",
        (steward_id, slot, day),
    )
    row = await cur.fetchone()
    if not row:
        return 0
    return int(row[0] if not hasattr(row, "keys") else row["qty"])


async def _collected_today(conn: aiosqlite.Connection, steward_id: int, slot: int, day: int) -> bool:
    cur = await conn.execute(
        "SELECT 1 FROM barn_daily_collect WHERE steward_id=? AND slot=? AND day=?",
        (steward_id, slot, day),
    )
    return await cur.fetchone() is not None


async def has_guard_dog(conn: aiosqlite.Connection, steward_id: int) -> bool:
    day = _day_id()
    cur = await conn.execute(
        """
        SELECT 1 FROM barn_animals
        WHERE steward_id=? AND species='dog' AND guard=1 AND fed_day=?
        LIMIT 1
        """,
        (steward_id, day),
    )
    return await cur.fetchone() is not None


def _ready(animal: dict, species: str) -> bool:
    meta = LIVESTOCK[species]
    if meta.get("guard") or meta.get("hive"):
        return False
    if not animal.get("stocked_at"):
        return False
    grow = meta["grow"]
    if _fed_today(animal) or animal.get("fed"):
        grow = int(grow * 0.85)
    return db.now() - animal["stocked_at"] >= grow


def _base_product_qty(species: str) -> int:
    return int(LIVESTOCK[species]["product_qty"])


def _steal_left(species: str, stolen: int) -> int:
    from . import farming

    return farming.scrump_take_qty(max(0, _base_product_qty(species) - stolen))


def _line(
    animal: dict | None,
    slot: int,
    *,
    day: int,
    collected: set[int],
    stolen: dict[int, int],
) -> str:
    if not animal or not animal.get("species"):
        return f"  #{slot}: 空栏"
    spec = LIVESTOCK[animal["species"]]
    fed = _fed_today(animal, day)
    took = slot in collected
    nicked = int(stolen.get(slot) or 0)
    if spec.get("guard"):
        state = "守夜中" if animal.get("guard") and fed else "待喂"
    elif spec.get("hive"):
        if took:
            state = "今日已收"
        elif fed:
            state = "采蜜中·可 collect"
        else:
            state = "待喂"
        if nicked and not took:
            state += f"·被偷{nicked}"
    elif spec.get("daily"):
        if took:
            state = "今日已收"
        elif fed:
            state = "放养·可 collect"
        else:
            state = "待喂"
        if nicked and not took:
            state += f"·被偷{nicked}"
        if _ready(animal, animal["species"]):
            state += "·可出栏 harvest"
    elif animal["species"] == "sheep":
        if took:
            state = "今日已剪"
        elif fed:
            state = "放养·可 shear"
        else:
            state = "待喂"
        if _ready(animal, "sheep"):
            state += "·可出栏 harvest"
    elif _ready(animal, animal["species"]):
        state = "可收(harvest出栏)"
    elif fed:
        state = "放养"
    else:
        state = "待喂"
    return f"  #{slot}: {spec['emoji']}{spec['name']}（{state}）"


async def stealable_count(conn: aiosqlite.Connection, steward_id: int) -> int:
    day = _day_id()
    conn.row_factory = aiosqlite.Row
    rows = await (await conn.execute(
        "SELECT * FROM barn_animals WHERE steward_id=?",
        (steward_id,),
    )).fetchall()
    collected = {
        int(r[0])
        for r in await (await conn.execute(
            "SELECT slot FROM barn_daily_collect WHERE steward_id=? AND day=?",
            (steward_id, day),
        )).fetchall()
    }
    stolen_rows = await (await conn.execute(
        "SELECT slot, qty FROM barn_daily_stolen WHERE steward_id=? AND day=?",
        (steward_id, day),
    )).fetchall()
    stolen = {int(r[0]): int(r[1]) for r in stolen_rows}
    n = 0
    for row in rows:
        animal = dict(row)
        species = animal.get("species")
        if not species or species not in LIVESTOCK:
            continue
        meta = LIVESTOCK[species]
        if not _daily_meta(meta):
            continue
        if not _fed_today(animal, day):
            continue
        if animal["slot"] in collected:
            continue
        if _steal_left(species, stolen.get(animal["slot"], 0)) > 0:
            n += 1
    return n


async def _take_feed(conn: aiosqlite.Connection, steward_id: int, meta: dict) -> None:
    if await db.take_item(conn, steward_id, meta["feed"], meta["feed_qty"]):
        return
    if await db.take_item(conn, steward_id, "feed_animal", 1):
        return
    need = ITEM_NAMES.get(meta["feed"], meta["feed"])
    raise ValueError(
        f"需要 {need} x{meta['feed_qty']}（或 visit_ops tt buy 动物饲料）"
    )


async def _feed_slot(
    conn: aiosqlite.Connection,
    steward_id: int,
    slot: int,
    day: int,
) -> str:
    conn.row_factory = aiosqlite.Row
    row = dict(await (await conn.execute(
        "SELECT * FROM barn_animals WHERE steward_id=? AND slot=?",
        (steward_id, slot),
    )).fetchone() or {})
    if not row.get("species"):
        raise ValueError(f"#{slot} 空栏")
    meta = LIVESTOCK[row["species"]]
    if _fed_today(row, day):
        return f"#{slot} 今日已喂"
    await _take_feed(conn, steward_id, meta)
    if meta.get("guard"):
        await conn.execute(
            "UPDATE barn_animals SET guard=1, fed=1, fed_day=? WHERE steward_id=? AND slot=?",
            (day, steward_id, slot),
        )
    else:
        await conn.execute(
            "UPDATE barn_animals SET fed=1, fed_day=? WHERE steward_id=? AND slot=?",
            (day, steward_id, slot),
        )
    manure_msg = ""
    if meta.get("manure"):
        qty = meta.get("manure_feed", 1)
        await db.add_item(conn, steward_id, meta["manure"], qty)
        manure_msg = f"，顺手收 {MANURE[meta['manure']]['name']} x{qty}"
    return f"#{slot} 已喂食{manure_msg}"


async def _collect_slot(
    conn: aiosqlite.Connection,
    steward_id: int,
    slot: int,
    day: int,
    *,
    shear: bool = False,
) -> str:
    conn.row_factory = aiosqlite.Row
    row = dict(await (await conn.execute(
        "SELECT * FROM barn_animals WHERE steward_id=? AND slot=?",
        (steward_id, slot),
    )).fetchone() or {})
    if not row.get("species"):
        raise ValueError(f"#{slot} 空栏")
    species = row["species"]
    meta = LIVESTOCK[species]
    if shear:
        if species != "sheep":
            raise ValueError(f"#{slot} 只有羊能剪毛")
        cur = await conn.execute(
            "SELECT 1 FROM satchel WHERE steward_id=? AND item='tool_shears' AND quantity>0",
            (steward_id,),
        )
        if not await cur.fetchone():
            raise ValueError("剪毛需要剪毛剪刀 — visit_ops tt buy 剪毛剪刀")
        product = "wool"
        verb_done = "已剪过"
        verb_need_feed = "先 feed 再 shear"
    else:
        if not _daily_meta(meta):
            raise ValueError(f"#{slot} 不支持 collect，用 harvest 出栏")
        product = meta["product"]
        verb_done = "已收过"
        verb_need_feed = "先 feed 再 collect"
    if not _fed_today(row, day):
        raise ValueError(f"#{slot} {verb_need_feed}")
    if await _collected_today(conn, steward_id, slot, day):
        raise ValueError(
            f"#{slot} 今日{verb_done}。日常收奶/蛋/蜜是每个游戏日一次，不是一周一次。"
            f"人和 AI 共用这个号，管家收过也算。{_shift_hint()}。"
            "其它槽不写槽位会全收：barn collect"
        )
    stolen = await _stolen_qty(conn, steward_id, slot, day)
    qty = _base_product_qty(species)
    extra = ""
    if not shear and meta.get("hive") and random.random() < 0.2:
        qty += 1
        extra = " · 丰年+1"
    if not shear and species in ("cow", "goat"):
        cur = await conn.execute(
            "SELECT 1 FROM satchel WHERE steward_id=? AND item='tool_milker' AND quantity>0",
            (steward_id,),
        )
        if await cur.fetchone():
            qty += 1
            extra = (extra + " · 挤奶器+1").strip()
        else:
            extra = (extra + " · 没挤奶器（Tt酱店有卖，装上多收 1）").strip()
    qty = max(0, qty - stolen)
    if qty <= 0:
        await conn.execute(
            "INSERT OR IGNORE INTO barn_daily_collect (steward_id, slot, day) VALUES (?,?,?)",
            (steward_id, slot, day),
        )
        return (
            f"#{slot} 今日产出已被偷光，记作已收。{_shift_hint()}"
        )
    await db.add_item(conn, steward_id, product, qty)
    await conn.execute(
        "INSERT INTO barn_daily_collect (steward_id, slot, day) VALUES (?,?,?)",
        (steward_id, slot, day),
    )
    stolen_note = f"（已扣被偷 {stolen}）" if stolen else ""
    label = ITEM_NAMES.get(product, product)
    if shear:
        return f"#{slot} 剪下{label} x{qty}{stolen_note}（羊还在）"
    return f"#{slot} 收取 {label} x{qty}{extra}{stolen_note}"


def _occupied_slots(by_slot: dict[int, dict], slots: list[int]) -> list[int]:
    out = []
    for slot in slots:
        row = by_slot.get(slot) or {}
        if row.get("species"):
            out.append(slot)
    return out


async def _load_barn(
    conn: aiosqlite.Connection, steward_id: int
) -> dict[int, dict]:
    conn.row_factory = aiosqlite.Row
    rows = await (await conn.execute(
        "SELECT * FROM barn_animals WHERE steward_id=? ORDER BY slot",
        (steward_id,),
    )).fetchall()
    return {r["slot"]: dict(r) for r in rows}


async def barn_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    parts = command.strip().split()
    verb = parts[0].lower() if parts else "status"
    if verb in ("收",):
        verb = "collect"
    elif verb in ("喂",):
        verb = "feed"
    elif verb in ("剪",):
        verb = "shear"
    elif verb in ("偷", "steal", "逾篱"):
        verb = "steal"
    elif verb in ("看",):
        verb = "status"
    elif verb in ("help", "?", "帮助"):
        return BARN_HELP

    if verb == "status":
        day = _day_id()
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            by_slot = await _load_barn(conn, s["id"])
            collected = {
                int(r["slot"])
                for r in await (await conn.execute(
                    "SELECT slot FROM barn_daily_collect WHERE steward_id=? AND day=?",
                    (s["id"], day),
                )).fetchall()
            }
            stolen = {
                int(r["slot"]): int(r["qty"])
                for r in await (await conn.execute(
                    "SELECT slot, qty FROM barn_daily_stolen WHERE steward_id=? AND day=?",
                    (s["id"], day),
                )).fetchall()
            }
        built = s.get("barn_built")
        lines = [
            f"畜栏: {'已建' if built else '未建'}（erect {config.BARN_ERECT_COST} 票）",
            f"槽位 {config.BARN_SLOTS}",
        ]
        for slot in range(1, config.BARN_SLOTS + 1):
            lines.append(_line(
                by_slot.get(slot), slot, day=day, collected=collected, stolen=stolen,
            ))
        lines.append(f"可购: {', '.join(LIVESTOCK.keys())}")
        lines.append(
            "日常收奶/蛋/蜜是每个游戏日一次（UTC 午夜=北京时间早上 8 点），不是一周一次。"
            f"{_shift_hint()}。人和 AI 共用这个号。"
        )
        lines.append(
            "catalog 看详情 · feed / collect 不写槽位=全部 · shear 剪羊毛 · harvest 出栏 · "
            "偷 名字 偷未收的奶蛋蜜（牲口不能偷） · churn 山羊奶→奶酪"
        )
        lines.append("粪便进堆肥桶：hut_ops 堆肥桶 存 羊粪 3（先 buy compost_bin → install）")
        if built:
            lines.append(
                f"岸维：畜栏每周 {upkeep_mod.BARN_BASE} 票 + 在栏 {upkeep_mod.BARN_STOCKED} 票/槽"
                " → visit_ops 潮生会 维"
            )
        return "\n".join(lines)

    if verb == "catalog":
        lines = ["畜栏图鉴（buy 鸡 2 / feed / collect 不写槽位=全部 / harvest 出栏）:"]
        for key, meta in LIVESTOCK.items():
            feed = ITEM_NAMES.get(meta["feed"], meta["feed"])
            if meta.get("guard"):
                lines.append(
                    f"  {meta['emoji']}{meta['name']} {meta['buy']}票 — 当天喂{feed}才守夜："
                    f"野兽总掷×0.78、兔/鹿/猪权重×0.45、斑鸠偷包×0.35、拾叶小偷拆穿+0.22"
                )
            elif meta.get("hive"):
                lines.append(
                    f"  {meta['emoji']}{meta['name']} {meta['buy']}票 — "
                    f"每天 feed 后 collect 采{ITEM_NAMES.get(meta['product'], meta['product'])}"
                    "（游戏日一次）"
                )
            elif meta.get("daily"):
                prod = ITEM_NAMES.get(meta["product"], meta["product"])
                extra = " · 挤奶器（Tt酱）多收 1" if key in ("cow", "goat") else ""
                lines.append(
                    f"  {meta['emoji']}{meta['name']} {meta['buy']}票 — "
                    f"每天 feed 后 collect 日常{prod}（游戏日一次，不是一周） · harvest 出栏收肉{extra}"
                )
            else:
                prod = ITEM_NAMES.get(meta["product"], meta["product"])
                manure = ""
                if meta.get("manure"):
                    manure = f" · 产{MANURE[meta['manure']]['name']}"
                shear = " · shear 剪毛（要剪刀，不杀羊，游戏日一次）" if key == "sheep" else ""
                lines.append(
                    f"  {meta['emoji']}{meta['name']} {meta['buy']}票 — "
                    f"喂{feed} x{meta['feed_qty']} → {prod} x{meta['product_qty']}{manure}{shear}"
                )
        lines.append("牲口本身不能偷。未收的奶/蛋/蜜：hut_ops barn 偷 名字（和偷菜共用逾篱次数）")
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
                    "INSERT OR IGNORE INTO barn_animals (steward_id, slot, species, fed, fed_day) VALUES (?,?,NULL,0,0)",
                    (s["id"], slot),
                )
            await conn.commit()
        return f"畜栏就绪（-{config.BARN_ERECT_COST} 票，{config.BARN_SLOTS} 槽）。每周岸维 {upkeep_mod.BARN_BASE} 票起 → visit_ops 潮生会 维"

    if verb == "buy" and len(parts) >= 2:
        if not s.get("barn_built"):
            raise ValueError("先 barn_ops erect")
        species = _resolve_species(parts[1])
        slot = int(parts[2]) if len(parts) > 2 else 1
        if not species:
            raise ValueError(f"可购: {', '.join(meta['name'] + '/' + k for k, meta in LIVESTOCK.items())}")
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
                    "INSERT INTO barn_animals (steward_id, slot, species, fed, fed_day) VALUES (?,?,NULL,0,0)",
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
            await _clear_slot_daily(conn, s["id"], slot)
            await conn.commit()
        if meta.get("guard"):
            return f"#{slot} 入驻 {meta['name']} — 当天喂过才守夜（减偷菜/偷畜产概率）"
        if meta.get("hive"):
            return f"#{slot} 安置 {meta['emoji']}{meta['name']} — 每天 feed 后 collect 采蜜"
        return f"#{slot} 购入 {meta['emoji']}{meta['name']}（-{meta['buy']} 票）"

    if verb == "feed":
        slot = _parse_optional_slot(parts)
        day = _day_id()
        async with db.connect() as conn:
            if slot is not None:
                msg = await _feed_slot(conn, s["id"], slot, day)
                await conn.commit()
                return msg
            by_slot = await _load_barn(conn, s["id"])
            targets = _occupied_slots(by_slot, list(range(1, config.BARN_SLOTS + 1)))
            if not targets:
                raise ValueError("栏是空的")
            done: list[str] = []
            skipped: list[str] = []
            err: str | None = None
            for n in targets:
                try:
                    line = await _feed_slot(conn, s["id"], n, day)
                    if "今日已喂" in line:
                        skipped.append(line)
                    else:
                        done.append(line)
                except ValueError as exc:
                    err = str(exc)
                    break
            await conn.commit()
        if done:
            extra = ("\n" + "\n".join(skipped)) if skipped else ""
            tail = f"\n{err}" if err else ""
            return "\n".join(done) + extra + tail
        if skipped and not err:
            return "今日都喂过了。" + _shift_hint()
        raise ValueError(err or "没有能喂的")

    if verb in ("collect", "shear"):
        slot = _parse_optional_slot(parts)
        day = _day_id()
        shear = verb == "shear"
        async with db.connect() as conn:
            if slot is not None:
                msg = await _collect_slot(conn, s["id"], slot, day, shear=shear)
                await conn.commit()
                tail = flavor.maybe_suffix(
                    ["剪刀咔嚓，羊：还行", "不杀羊也能出毛，文明"]
                    if shear else
                    ["日常小收，积少成多", "栏里忙，票里稳"]
                )
                return msg + (f" · {tail}" if tail else "")
            by_slot = await _load_barn(conn, s["id"])
            targets = _occupied_slots(by_slot, list(range(1, config.BARN_SLOTS + 1)))
            if not targets:
                raise ValueError("栏是空的")
            done: list[str] = []
            blocked: list[str] = []
            for n in targets:
                row = by_slot.get(n) or {}
                species = row.get("species")
                if not species:
                    continue
                meta = LIVESTOCK[species]
                if shear and species != "sheep":
                    continue
                if not shear and not _daily_meta(meta):
                    continue
                try:
                    done.append(await _collect_slot(conn, s["id"], n, day, shear=shear))
                except ValueError as exc:
                    blocked.append(str(exc).split("。")[0])
            await conn.commit()
        if done:
            extra = ("\n" + "\n".join(blocked)) if blocked else ""
            return "\n".join(done) + extra
        if blocked:
            raise ValueError(
                "没有可收的。" + "；".join(blocked[:3]) + f"。{_shift_hint()}"
            )
        kind = "羊" if shear else "鸡/鸭/牛/山羊/蜂箱"
        raise ValueError(f"没有可{'剪' if shear else '收'}的{kind}")

    if verb == "harvest":
        if len(parts) < 2:
            raise ValueError("harvest 要写槽位，出栏会把动物清空。日常收奶/蛋/蜜用 collect（不写槽位=全收）")
        slot = int(parts[1])
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
                raise ValueError("还没长成，继续 feed（鸡鸭牛羊的奶蛋先 collect，harvest 是出栏）")
            product = meta["product"]
            qty = meta["product_qty"]
            if not _fed_today(row):
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
            await _clear_slot_daily(conn, s["id"], slot)
            await conn.commit()
        msg = f"#{slot} 出栏 {ITEM_NAMES.get(product, product)} x{qty}{bonus_msg}{manure_msg}（栏空了）"
        msg += flavor.maybe_suffix(["栏里忙，票里稳", "牲畜：今天也努力了"])
        await db.add_chronicle("barn", f"{s['name']} 畜栏收 {product}", s["id"])
        return msg

    if verb == "steal":
        return await _barn_steal(s, parts)

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
        "日常收是每个游戏日一次，不是一周。牲口不能偷，未收的奶蛋蜜可以 barn 偷 名字。"
        "粪便进堆肥桶：hut_ops 堆肥桶 存 羊粪 3"
    )


async def _barn_steal(steward: dict, parts: list[str]) -> str:
    from . import bond as bond_mod
    from . import events, survival

    rest = parts[1:]
    if not rest:
        raise ValueError(
            "用法: hut_ops barn 偷 名字 [槽位]。牲口本身不能偷，只偷还没收的奶/蛋/蜜。"
            "和 plot_ops 偷菜 共用逾篱次数。"
        )
    slot: int | None = None
    if rest[-1].isdigit():
        slot = int(rest[-1])
        rest = rest[:-1]
        if slot < 1 or slot > config.BARN_SLOTS:
            raise ValueError(f"槽位 1~{config.BARN_SLOTS}")
    target_name = " ".join(rest).strip()
    if not target_name:
        raise ValueError("用法: hut_ops barn 偷 名字 [槽位]")

    peer = await db.get_steward_by_name(target_name)
    if not peer or not peer.get("enrolled"):
        raise ValueError(
            f"找不到管理员「{target_name}」。先 steward_ops 邻居 看名单。"
        )
    if peer["id"] == steward["id"]:
        raise ValueError("不能偷自己栏里的")
    if not peer.get("barn_built"):
        raise ValueError(f"{peer['name']} 还没搭畜栏")

    day = _day_id()
    async with db.connect() as conn:
        used = (await (await conn.execute(
            "SELECT COUNT(*) FROM scrump_log WHERE thief_id=? AND day=?",
            (steward["id"], day),
        )).fetchone())[0]
        if used >= config.SCRUMP_DAILY:
            raise ValueError(f"今日逾篱已满 {config.SCRUMP_DAILY} 次，明天再来")
        same = await (await conn.execute(
            "SELECT 1 FROM scrump_log WHERE thief_id=? AND target_id=? AND day=?",
            (steward["id"], peer["id"], day),
        )).fetchone()
        if same:
            raise ValueError(f"今天已经摘过 {peer['name']} 一次（偷菜或偷畜产），换一家或明天再来")

        conn.row_factory = aiosqlite.Row
        by_slot = await _load_barn(conn, peer["id"])
        stolen_map = {
            int(r["slot"]): int(r["qty"])
            for r in await (await conn.execute(
                "SELECT slot, qty FROM barn_daily_stolen WHERE steward_id=? AND day=?",
                (peer["id"], day),
            )).fetchall()
        }
        collected = {
            int(r["slot"])
            for r in await (await conn.execute(
                "SELECT slot FROM barn_daily_collect WHERE steward_id=? AND day=?",
                (peer["id"], day),
            )).fetchall()
        }

        def _can_nick(n: int) -> tuple[dict, str, int] | None:
            animal = by_slot.get(n) or {}
            species = animal.get("species")
            if not species or species not in LIVESTOCK:
                return None
            meta = LIVESTOCK[species]
            if not _daily_meta(meta):
                return None
            if not _fed_today(animal, day):
                return None
            if n in collected:
                return None
            take = _steal_left(species, stolen_map.get(n, 0))
            if take <= 0:
                return None
            return animal, species, take

        picked: tuple[int, dict, str, int] | None = None
        if slot is not None:
            hit = _can_nick(slot)
            if not hit:
                raise ValueError(
                    f"{peer['name']} #{slot} 没有能偷的奶/蛋/蜜"
                    "（要已喂、今日还没收完、份数够留一份）。牲口本身不能偷。"
                )
            animal, species, take = hit
            picked = (slot, animal, species, take)
        else:
            for n in range(1, config.BARN_SLOTS + 1):
                hit = _can_nick(n)
                if hit:
                    animal, species, take = hit
                    picked = (n, animal, species, take)
                    break
            if not picked:
                raise ValueError(
                    f"{peer['name']} 栏里没有能偷的奶/蛋/蜜。"
                    "要对方当天喂过且还没收。牲口本身不能偷。"
                )

        slot_n, _animal, species, take = picked
        product = LIVESTOCK[species]["product"]
        dog = await has_guard_dog(conn, peer["id"])
        chance = events._scrump_catch_chance(
            steward, peer, {"scarecrow": 0, "camera": 0}, dog=dog,
        )
        caught = events.random.random() < chance
        fine = config.SCRUMP_FINE_TICKETS
        if caught and steward.get("mascot_trait") == "scout":
            fine = max(1, fine // 2)

        await conn.execute(
            "INSERT INTO scrump_log (thief_id, target_id, day) VALUES (?,?,?)",
            (steward["id"], peer["id"], day),
        )

        if caught:
            await conn.execute(
                "UPDATE stewards SET tickets=MAX(0, tickets-?) WHERE id=?",
                (fine, steward["id"]),
            )
            await survival.bump(conn, steward["id"], standing=-random.randint(6, 12))
            from . import undertide as _ut
            jail_note = await _ut.on_scrump_busted(conn, steward) or ""
            dog_bit = "守夜狗叫了，" if dog else ""
            msg = (
                f"{dog_bit}摸 {peer['name']} 畜栏 #{slot_n} 被逮正着，罚 {fine} 票。"
                f"{jail_note}（可 plot_ops amends {peer['name']}）"
            )
            action = "scrump_busted"
            loot = "被抓"
        else:
            await db.add_item(conn, steward["id"], product, take)
            await conn.execute(
                """
                INSERT INTO barn_daily_stolen (steward_id, slot, day, qty)
                VALUES (?,?,?,?)
                ON CONFLICT(steward_id, slot, day) DO UPDATE SET qty = qty + excluded.qty
                """,
                (peer["id"], slot_n, day, take),
            )
            await bond_mod.grant(conn, steward["id"], bond_mod.SCRUMP, "labor")
            label = f"{ITEM_NAMES.get(product, product)} x{take}"
            left = _base_product_qty(species) - stolen_map.get(slot_n, 0) - take
            msg = (
                f"摸进 {peer['name']} 畜栏 #{slot_n}，顺走 {label}。"
                f"栏里还留着 {left}。"
                f"今日逾篱 {used + 1}/{config.SCRUMP_DAILY}"
            )
            action = "scrump"
            loot = label

        await conn.execute(
            "INSERT INTO chronicle (action, actor_id, target_id, text, created_at) VALUES (?,?,?,?,?)",
            (
                action,
                steward["id"],
                peer["id"],
                f"{steward['name']} 偷畜产 {peer['name']} #{slot_n} {loot}",
                db.now(),
            ),
        )
        await conn.commit()
    return msg
