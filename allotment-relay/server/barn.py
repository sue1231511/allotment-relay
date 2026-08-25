"""畜栏 — 牛羊猪狗兔鸡鸭山羊蜂箱，喂食产出与日常收奶。"""

from __future__ import annotations

import random

import aiosqlite

from . import config, db, flavor
from .catalog import ITEM_NAMES, LIVESTOCK, MANURE
from .game import require_steward

_VERB_ALIAS = {
    "收": "collect",
    "收蛋": "collect",
    "收奶": "collect",
    "喂": "feed",
    "喂食": "feed",
    "偷": "steal",
    "顺": "steal",
    "偷蛋": "steal",
    "偷奶": "steal",
    "图鉴": "catalog",
    "剪": "shear",
    "剪毛": "shear",
    "出栏": "harvest",
    "帮助": "help",
    "?": "help",
}

BARN_HELP = """畜栏 hut_ops barn（整句写进 command）：
  status — 看栏。每个槽会写：待喂 / 已喂·可收 / 今日已收 / 被顺走还可收
  catalog — 图鉴
  erect — 搭畜栏
  buy 鸡|duck|sheep|cow|goat|pig|rabbit|bee|dog [槽]
  feed — 今天还没喂的槽全喂；feed 2 只喂 2 号。每天先喂再收（游戏日 UTC 午夜换班刷新，不是一周一次）
  collect — 今天可收的槽全收（蛋/奶/蜜）；collect 2 只收 2 号。每个槽每天一次
  shear [槽] — 剪羊毛（要剪刀）。和 collect 一样按游戏日，不是一周一次
  harvest [槽] — 出栏（动物离开）。日常蛋奶不要用这条
  churn [数量] — 山羊奶→奶酪（先买山羊再 collect；牛奶不能搅）
  偷 名字 — 顺邻居今日未收的蛋/奶/蜜/毛（最多三成，份地那种留一把；活畜牵不走）
    和 plot_ops 偷菜 不是同一条。守夜狗更容易被抓。例子：barn 偷 安
人和 AI 共用一个号：管家可能已经收过。status 写「今日已收」就是收过了。
不会就 help。"""


def _day_id() -> int:
    return db.day_id()


def _shift_wait_text() -> str:
    wait = db.seconds_until_next_day()
    hours = wait // 3600 + (1 if wait % 3600 else 0)
    return f"潮声换班后再来（约 {hours} 小时后，游戏日 UTC 午夜，不是一周一次）"


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


def _fed_today(animal: dict | None) -> bool:
    if not animal:
        return False
    return int(animal.get("fed") or 0) == _day_id()


def _owner_done(daily: dict | None) -> bool:
    """今日这槽主人是否已经收/剪过。旧行（无 stolen_qty）视为已收。"""
    if not daily:
        return False
    if int(daily.get("owner_done") or 0):
        return True
    if int(daily.get("stolen_qty") or 0) <= 0:
        return True
    return False


def _stolen_qty(daily: dict | None) -> int:
    if not daily:
        return 0
    return max(0, int(daily.get("stolen_qty") or 0))


def _daily_product(species: str) -> bool:
    meta = LIVESTOCK.get(species) or {}
    return bool(meta.get("daily") or meta.get("hive") or species == "sheep")


def _barn_scrump_take(left: int) -> int:
    """日常产物份数少：2 份掐 1；只剩 1 份就掐不走（和份地一样留一把）。"""
    from . import farming
    return farming.scrump_take_qty(left)


def _line(animal: dict | None, slot: int, daily: dict | None = None) -> str:
    if not animal or not animal.get("species"):
        return f"  #{slot}: 空栏"
    spec = LIVESTOCK[animal["species"]]
    if spec.get("guard"):
        state = "守夜中" if animal.get("guard") else "幼犬"
    elif _owner_done(daily):
        who = (daily or {}).get("thief_name") or ""
        stolen = _stolen_qty(daily)
        if stolen and who:
            state = f"今日已收（曾被 {who} 顺走 {stolen}）"
        else:
            state = "今日已收"
    elif _stolen_qty(daily) > 0:
        who = (daily or {}).get("thief_name") or "邻人"
        state = f"被 {who} 顺走 {_stolen_qty(daily)}，还可 collect"
    elif spec.get("hive"):
        state = "已喂·可 collect" if _fed_today(animal) else "待喂"
    elif spec.get("daily"):
        if _fed_today(animal):
            extra = "·可 harvest 出栏" if _ready(animal, animal["species"]) else ""
            state = f"已喂·可 collect{extra}"
        elif _ready(animal, animal["species"]):
            state = "可 harvest 出栏（日常蛋奶仍要先 feed 再 collect）"
        else:
            state = "待喂"
    elif _ready(animal, animal["species"]):
        state = "可收（harvest 出栏）"
    elif _fed_today(animal):
        extra = "·可 shear" if animal["species"] == "sheep" else ""
        state = f"放养{extra}"
    else:
        state = "待喂"
    return f"  #{slot}: {spec['emoji']}{spec['name']}（{state}）"


async def _daily_map(
    conn: aiosqlite.Connection, steward_id: int, day: int
) -> dict[int, dict]:
    rows = await (
        await conn.execute(
            "SELECT * FROM barn_daily_collect WHERE steward_id=? AND day=?",
            (steward_id, day),
        )
    ).fetchall()
    return {int(r["slot"]): dict(r) for r in rows}


async def _load_slot(
    conn: aiosqlite.Connection, steward_id: int, slot: int
) -> dict:
    row = await (
        await conn.execute(
            "SELECT * FROM barn_animals WHERE steward_id=? AND slot=?",
            (steward_id, slot),
        )
    ).fetchone()
    return dict(row) if row else {}


async def _upsert_daily(
    conn: aiosqlite.Connection,
    steward_id: int,
    slot: int,
    day: int,
    *,
    owner_done: int | None = None,
    stolen_qty: int | None = None,
    thief_name: str | None = None,
) -> None:
    cur = await conn.execute(
        "SELECT stolen_qty, thief_name, owner_done FROM barn_daily_collect "
        "WHERE steward_id=? AND slot=? AND day=?",
        (steward_id, slot, day),
    )
    existing = await cur.fetchone()
    if existing:
        sq = existing[0] if stolen_qty is None else stolen_qty
        tn = existing[1] if thief_name is None else thief_name
        od = existing[2] if owner_done is None else owner_done
        await conn.execute(
            """
            UPDATE barn_daily_collect
            SET stolen_qty=?, thief_name=?, owner_done=?
            WHERE steward_id=? AND slot=? AND day=?
            """,
            (sq, tn, od, steward_id, slot, day),
        )
        return
    await conn.execute(
        """
        INSERT INTO barn_daily_collect
            (steward_id, slot, day, stolen_qty, thief_name, owner_done)
        VALUES (?,?,?,?,?,?)
        """,
        (
            steward_id,
            slot,
            day,
            0 if stolen_qty is None else stolen_qty,
            "" if thief_name is None else thief_name,
            0 if owner_done is None else owner_done,
        ),
    )


async def barn_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    parts = command.strip().split(maxsplit=2)
    raw_verb = parts[0].lower() if parts else "status"
    verb = _VERB_ALIAS.get(raw_verb, raw_verb)

    if verb in ("help",):
        return BARN_HELP

    if verb == "status":
        day = _day_id()
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            rows = await (
                await conn.execute(
                    "SELECT * FROM barn_animals WHERE steward_id=? ORDER BY slot",
                    (s["id"],),
                )
            ).fetchall()
            daily = await _daily_map(conn, s["id"], day)
        built = s.get("barn_built")
        lines = [
            f"畜栏: {'已建' if built else '未建'}（erect {config.BARN_ERECT_COST} 票）",
            f"槽位 {config.BARN_SLOTS}",
            f"日常 collect/shear：每个槽每天一次（游戏日 UTC 午夜换班，{_shift_wait_text()}），不是一周一次。",
            "空 collect / 空 feed = 全栏动手。人和 AI 共用一个号，管家可能已经收过。",
        ]
        by_slot = {r["slot"]: dict(r) for r in rows}
        for slot in range(1, config.BARN_SLOTS + 1):
            lines.append(_line(by_slot.get(slot), slot, daily.get(slot)))
        lines.append(f"可购: {', '.join(LIVESTOCK.keys())}")
        lines.append(
            "catalog 看详情 · collect 日常收奶/蛋/蜜 · shear 剪羊毛（要剪刀） · churn 山羊奶→奶酪"
        )
        lines.append(
            "barn 偷 名字 顺邻居未收的蛋奶蜜毛（活畜牵不走，不是 plot_ops 偷菜）"
        )
        lines.append("粪便进堆肥桶：hut_ops 堆肥桶 存 羊粪 3（先 buy compost_bin → install）")
        return "\n".join(lines)

    if verb == "catalog":
        lines = ["畜栏图鉴（buy 物种 槽位 / feed 槽位 / harvest|collect 槽位）:"]
        for key, meta in LIVESTOCK.items():
            feed = ITEM_NAMES.get(meta["feed"], meta["feed"])
            if meta.get("guard"):
                lines.append(
                    f"  {meta['emoji']}{meta['name']} {meta['buy']}票 — 喂{feed}守夜："
                    f"野兽总掷×0.78、兔/鹿/猪权重×0.45、斑鸠偷包×0.35、拾叶小偷拆穿+0.22、"
                    f"邻人偷蛋奶更容易被抓"
                )
            elif meta.get("hive"):
                lines.append(
                    f"  {meta['emoji']}{meta['name']} {meta['buy']}票 — "
                    f"喂{feed} x{meta['feed_qty']} · collect 采{ITEM_NAMES.get(meta['product'], meta['product'])}"
                    f"（每天一次，先喂）"
                )
            elif meta.get("daily"):
                prod = ITEM_NAMES.get(meta["product"], meta["product"])
                extra = " · 挤奶器（Tt酱）多收 1" if key in ("cow", "goat") else ""
                lines.append(
                    f"  {meta['emoji']}{meta['name']} {meta['buy']}票 — "
                    f"每天 feed 后 collect 日常{prod}（游戏日一次，不是一周）"
                    f" · harvest 才是出栏{extra}"
                )
            else:
                prod = ITEM_NAMES.get(meta["product"], meta["product"])
                manure = ""
                if meta.get("manure"):
                    manure = f" · 产{MANURE[meta['manure']]['name']}"
                shear = " · shear 剪毛（要剪刀，不杀羊，每天一次）" if key == "sheep" else ""
                lines.append(
                    f"  {meta['emoji']}{meta['name']} {meta['buy']}票 — "
                    f"喂{feed} x{meta['feed_qty']} → {prod} x{meta['product_qty']}{manure}{shear}"
                )
        lines.append("粪便进堆肥桶 hut_ops 堆肥桶 存，不能进潮柜")
        lines.append(
            "活畜不能偷。今日未收的蛋/奶/蜜/毛可 barn 偷 名字（最多三成，留一把）"
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
        name_map = {meta["name"]: key for key, meta in LIVESTOCK.items()}
        species = name_map.get(parts[1], species)
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
            stocked = db.now()
            await conn.execute(
                """
                UPDATE barn_animals SET species=?, stocked_at=?, fed=0, guard=?
                WHERE steward_id=? AND slot=?
                """,
                (species, stocked, guard, s["id"], slot),
            )
            await conn.commit()
        if meta.get("guard"):
            return f"#{slot} 入驻 {meta['name']} — 守夜减偷菜/偷蛋概率"
        if meta.get("hive"):
            return f"#{slot} 安置 {meta['emoji']}{meta['name']} — 每天 feed 后 collect 采蜜"
        if meta.get("daily"):
            return (
                f"#{slot} 购入 {meta['emoji']}{meta['name']}（-{meta['buy']} 票）"
                f" — 每天 feed 再 collect，不是一周一次"
            )
        return f"#{slot} 购入 {meta['emoji']}{meta['name']}（-{meta['buy']} 票）"

    if verb == "feed":
        return await _feed_cmd(s, parts)

    if verb == "collect":
        return await _collect_cmd(s, parts)

    if verb == "harvest":
        return await _harvest_cmd(s, parts)

    if verb == "shear":
        return await _shear_cmd(s, parts)

    if verb == "steal":
        return await _steal_cmd(s, parts)

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
        "日常蛋奶是每天一次（游戏日 UTC 午夜换班），不是一周一次。"
        "空 collect=全收。活畜不能偷，蛋奶蜜毛用 barn 偷 名字。"
        "粪便进堆肥桶：hut_ops 堆肥桶 存 羊粪 3（barn compost 还认，但要先装桶）"
    )


async def _feed_one(
    conn: aiosqlite.Connection, s: dict, row: dict, slot: int, day: int
) -> str:
    if not row.get("species"):
        raise ValueError(f"#{slot} 空栏")
    meta = LIVESTOCK[row["species"]]
    if meta.get("guard"):
        if row.get("guard") and _fed_today(row):
            return f"#{slot} 今日已喂，还在守夜"
        if not await db.take_item(conn, s["id"], meta["feed"], meta["feed_qty"]):
            if not await db.take_item(conn, s["id"], "feed_animal", 1):
                raise ValueError(
                    f"#{slot} 喂狗需要 {ITEM_NAMES.get(meta['feed'], meta['feed'])}"
                    "（或 Tt酱店里的动物饲料）"
                )
        await conn.execute(
            "UPDATE barn_animals SET guard=1, fed=? WHERE steward_id=? AND slot=?",
            (day, s["id"], slot),
        )
        return f"#{slot} 已喂食，守夜中"
    if _fed_today(row):
        return f"#{slot} 今日已喂（{_shift_wait_text()}）"
    if not await db.take_item(conn, s["id"], meta["feed"], meta["feed_qty"]):
        if not await db.take_item(conn, s["id"], "feed_animal", 1):
            raise ValueError(
                f"#{slot} 需要 {ITEM_NAMES.get(meta['feed'], meta['feed'])} x{meta['feed_qty']}"
                "（或 visit_ops tt buy 动物饲料）"
            )
    await conn.execute(
        "UPDATE barn_animals SET fed=? WHERE steward_id=? AND slot=?",
        (day, s["id"], slot),
    )
    manure_msg = ""
    if meta.get("manure"):
        qty = meta.get("manure_feed", 1)
        await db.add_item(conn, s["id"], meta["manure"], qty)
        manure_msg = f"，顺手收 {MANURE[meta['manure']]['name']} x{qty}"
    return f"#{slot} 已喂食{manure_msg}"


async def _feed_cmd(s: dict, parts: list[str]) -> str:
    day = _day_id()
    slots = _parse_slots(parts, optional=True)
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        notes: list[str] = []
        errors: list[str] = []
        did = 0
        for slot in slots:
            row = await _load_slot(conn, s["id"], slot)
            if not slots_were_explicit(parts) and not row.get("species"):
                continue
            if not slots_were_explicit(parts) and row.get("species") and _fed_today(row):
                continue
            try:
                notes.append(await _feed_one(conn, s, row, slot, day))
                if "已喂食" in notes[-1]:
                    did += 1
            except ValueError as exc:
                if slots_were_explicit(parts):
                    raise
                errors.append(str(exc))
        await conn.commit()
    if not notes and not errors:
        if not slots_were_explicit(parts):
            return f"栏里今天没有待喂的槽。{_shift_wait_text()}。"
        raise ValueError("空栏")
    msg = "\n".join(notes + errors)
    if did:
        msg += f"\n喂完记得 collect（每天一次，空 collect=全收）"
    return msg


def slots_were_explicit(parts: list[str]) -> bool:
    return len(parts) > 1 and parts[1].isdigit()


def _parse_slots(parts: list[str], *, optional: bool) -> list[int]:
    if len(parts) > 1 and parts[1].isdigit():
        slot = int(parts[1])
        if slot < 1 or slot > config.BARN_SLOTS:
            raise ValueError(f"槽位 1~{config.BARN_SLOTS}")
        return [slot]
    if optional:
        return list(range(1, config.BARN_SLOTS + 1))
    return [1]


async def _collect_qty(
    conn: aiosqlite.Connection, s: dict, row: dict, daily: dict | None
) -> tuple[str, int, str]:
    meta = LIVESTOCK[row["species"]]
    product = meta["product"]
    qty = int(meta["product_qty"])
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
    qty -= _stolen_qty(daily)
    return product, max(0, qty), extra


async def _collect_one(
    conn: aiosqlite.Connection, s: dict, row: dict, slot: int, day: int, daily: dict | None
) -> str:
    if not row.get("species"):
        raise ValueError(f"#{slot} 空栏")
    meta = LIVESTOCK[row["species"]]
    if not (meta.get("daily") or meta.get("hive")):
        raise ValueError(f"#{slot} 不支持 collect，用 harvest（出栏）或 shear（羊）")
    if _owner_done(daily):
        who = (daily or {}).get("thief_name") or ""
        stolen = _stolen_qty(daily)
        hint = f"曾被 {who} 顺走 {stolen}。" if stolen and who else ""
        raise ValueError(
            f"#{slot} 今日已收过。{hint}{_shift_wait_text()}。"
            "人和 AI 共用一个号，管家可能已经收过。"
            "空 collect 会跳过已收的槽去收别的。"
        )
    if not _fed_today(row):
        raise ValueError(f"#{slot} 今天还没喂。先 feed（空 feed=全喂），再 collect")
    product, qty, extra = await _collect_qty(conn, s, row, daily)
    if qty <= 0:
        who = (daily or {}).get("thief_name") or "邻人"
        await _upsert_daily(conn, s["id"], slot, day, owner_done=1)
        return f"#{slot} 今日产物被 {who} 顺走了，换班再收。{_shift_wait_text()}。"
    await db.add_item(conn, s["id"], product, qty)
    await _upsert_daily(conn, s["id"], slot, day, owner_done=1)
    stolen_note = ""
    if _stolen_qty(daily):
        who = (daily or {}).get("thief_name") or "邻人"
        stolen_note = f" · {who} 先掐走了 {_stolen_qty(daily)}"
    return f"#{slot} 收取 {ITEM_NAMES.get(product, product)} x{qty}{extra}{stolen_note}"


async def _collect_cmd(s: dict, parts: list[str]) -> str:
    day = _day_id()
    slots = _parse_slots(parts, optional=True)
    explicit = slots_were_explicit(parts)
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        daily_map = await _daily_map(conn, s["id"], day)
        notes: list[str] = []
        skipped = 0
        blocked: list[str] = []
        for slot in slots:
            row = await _load_slot(conn, s["id"], slot)
            daily = daily_map.get(slot)
            if not explicit:
                if not row.get("species"):
                    continue
                meta = LIVESTOCK.get(row["species"]) or {}
                if not (meta.get("daily") or meta.get("hive")):
                    continue
                if _owner_done(daily):
                    skipped += 1
                    continue
                if not _fed_today(row):
                    continue
            try:
                notes.append(await _collect_one(conn, s, row, slot, day, daily))
            except ValueError as exc:
                if explicit:
                    raise
                blocked.append(str(exc))
        await conn.commit()
    if notes:
        msg = "\n".join(notes)
        tail = flavor.maybe_suffix(["日常小收，积少成多", "栏里忙，票里稳"])
        if tail:
            msg += f" · {tail}"
        return msg
    if skipped:
        raise ValueError(
            f"今日栏里能收的槽都已收过了。{_shift_wait_text()}。"
            "人和 AI 共用一个号，管家可能已经收过。status 看哪一槽写着「今日已收」。"
        )
    if blocked:
        raise ValueError(blocked[0])
    raise ValueError(
        "没有可收的槽。鸡鸭牛羊山羊蜂箱要今天先 feed 再 collect；"
        f"每个槽每天一次，不是一周一次。{_shift_wait_text()}。"
    )


async def _harvest_cmd(s: dict, parts: list[str]) -> str:
    slot = _parse_slots(parts, optional=False)[0]
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        row = await _load_slot(conn, s["id"], slot)
        if not row.get("species"):
            raise ValueError("空栏")
        species = row["species"]
        meta = LIVESTOCK[species]
        if meta.get("guard"):
            raise ValueError("狗不产肉，它产安全感")
        if meta.get("hive"):
            raise ValueError("蜂箱用 collect 采蜜，别连箱端走")
        if not _ready(row, species):
            if meta.get("daily"):
                raise ValueError(
                    f"还没到出栏。日常蛋/奶用 collect（每天一次），"
                    f"harvest 会把{meta['name']}收走。"
                )
            raise ValueError("还没长成，继续 feed（日常动物先 collect）")
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


async def _shear_cmd(s: dict, parts: list[str]) -> str:
    slot = _parse_slots(parts, optional=False)[0]
    day = _day_id()
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        row = await _load_slot(conn, s["id"], slot)
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
        if not _fed_today(row):
            raise ValueError("今天还没喂。先 feed 再 shear")
        daily_map = await _daily_map(conn, s["id"], day)
        daily = daily_map.get(slot)
        if _owner_done(daily):
            raise ValueError(f"#{slot} 今日已剪过。{_shift_wait_text()}。")
        qty = int(LIVESTOCK["sheep"]["product_qty"]) - _stolen_qty(daily)
        if qty <= 0:
            who = (daily or {}).get("thief_name") or "邻人"
            await _upsert_daily(conn, s["id"], slot, day, owner_done=1)
            raise ValueError(f"#{slot} 羊毛被 {who} 顺走了。{_shift_wait_text()}。")
        await db.add_item(conn, s["id"], "wool", qty)
        await _upsert_daily(conn, s["id"], slot, day, owner_done=1)
        await conn.commit()
    return (
        f"#{slot} 剪下羊毛 x{qty}（羊还在）"
        + flavor.maybe_suffix(["剪刀咔嚓，羊：还行", "不杀羊也能出毛，文明"])
    )


def _steal_catch_chance(thief: dict, peer: dict, *, dog: bool) -> float:
    home = db.now() - peer["last_active_at"] <= config.SCRUMP_ACTIVE_WINDOW
    chance = 0.72 if home else 0.20
    if dog:
        chance += 0.28
    if thief.get("mascot_trait") == "scout":
        chance -= 0.10
    return max(0.08, min(0.94, chance))


async def _pick_steal_slot(
    conn: aiosqlite.Connection, peer_id: int, day: int, want: int | None
) -> tuple[dict, dict | None]:
    daily_map = await _daily_map(conn, peer_id, day)
    slots = [want] if want else list(range(1, config.BARN_SLOTS + 1))
    for slot in slots:
        row = await _load_slot(conn, peer_id, slot)
        if not row.get("species"):
            continue
        if not _daily_product(row["species"]):
            continue
        if not _fed_today(row):
            continue
        daily = daily_map.get(slot)
        if _owner_done(daily):
            continue
        meta = LIVESTOCK[row["species"]]
        left = int(meta["product_qty"]) - _stolen_qty(daily)
        if _barn_scrump_take(left) <= 0:
            continue
        row["slot"] = slot
        return row, daily
    return {}, None


async def _steal_cmd(s: dict, parts: list[str]) -> str:
    if len(parts) < 2:
        raise ValueError(
            "用法: hut_ops barn 偷 名字 [槽]\n"
            "顺的是邻居今日未收的蛋/奶/蜜/毛，活畜牵不走。"
            "不是 plot_ops 偷菜。"
        )
    target_name = parts[1]
    want_slot = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
    peer = await db.get_steward_by_name(target_name)
    if not peer or not peer.get("enrolled"):
        raise ValueError(
            f"找不到管理员「{target_name}」。先 steward_ops 邻居 看名单。"
        )
    if peer["id"] == s["id"]:
        raise ValueError("不能偷自己的栏")
    if not peer.get("barn_built"):
        raise ValueError(f"{peer['name']} 还没搭畜栏")
    day = _day_id()
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        used = (
            await (
                await conn.execute(
                    "SELECT COUNT(*) FROM barn_scrump_log WHERE thief_id=? AND day=?",
                    (s["id"], day),
                )
            ).fetchone()
        )[0]
        if used >= config.BARN_SCRUMP_DAILY:
            raise ValueError(
                f"今日顺栏已满 {config.BARN_SCRUMP_DAILY} 次，{_shift_wait_text()}。"
            )
        same = await (
            await conn.execute(
                "SELECT 1 FROM barn_scrump_log WHERE thief_id=? AND target_id=? AND day=?",
                (s["id"], peer["id"], day),
            )
        ).fetchone()
        if same:
            raise ValueError(f"今天已经顺过 {peer['name']} 的栏，换一家或明天再来")

        animal, daily = await _pick_steal_slot(conn, peer["id"], day, want_slot)
        if not animal:
            if want_slot:
                raise ValueError(
                    f"{peer['name']} #{want_slot} 没有可顺的日常产物"
                    "（要今天已喂、还没收；活畜牵不走）"
                )
            raise ValueError(
                f"{peer['name']} 栏里没有可顺的蛋/奶/蜜/毛。"
                "要对方今天已喂且还没 collect。活畜牵不走。"
            )

        slot = int(animal["slot"])
        meta = LIVESTOCK[animal["species"]]
        left = int(meta["product_qty"]) - _stolen_qty(daily)
        taken = _barn_scrump_take(left)
        if taken <= 0:
            raise ValueError("就剩一把了，不能再掏空")

        dog = await has_guard_dog(conn, peer["id"])
        chance = _steal_catch_chance(s, peer, dog=dog)
        caught = random.random() < chance
        fine = config.SCRUMP_FINE_TICKETS
        if caught and s.get("mascot_trait") == "scout":
            fine = max(1, fine // 2)

        await conn.execute(
            "INSERT INTO barn_scrump_log (thief_id, target_id, day) VALUES (?,?,?)",
            (s["id"], peer["id"], day),
        )

        prod_name = ITEM_NAMES.get(meta["product"], meta["product"])
        if caught:
            await conn.execute(
                "UPDATE stewards SET tickets=MAX(0, tickets-?) WHERE id=?",
                (fine, s["id"]),
            )
            from . import survival
            await survival.bump(conn, s["id"], standing=-random.randint(6, 12))
            from . import undertide as _ut
            jail_note = await _ut.on_scrump_busted(conn, s) or ""
            dog_note = "守夜狗叫了" if dog else ""
            detail = (
                f"摸进 {peer['name']} 畜栏 #{slot}，被逮正着，罚 {fine} 票"
                + (f"（{dog_note}）" if dog_note else "")
            )
            action = "barn_scrump_busted"
            loot = "被抓"
            msg = detail + jail_note + f"（可 plot_ops amends {peer['name']}）"
        else:
            new_stolen = _stolen_qty(daily) + taken
            await db.add_item(conn, s["id"], meta["product"], taken)
            await _upsert_daily(
                conn,
                peer["id"],
                slot,
                day,
                stolen_qty=new_stolen,
                thief_name=s["name"],
                owner_done=0,
            )
            leftover = left - taken
            action = "barn_scrump"
            loot = f"{prod_name} x{taken}"
            msg = (
                f"顺走 {peer['name']} #{slot} {loot}，栏里还留 {leftover}。"
                f"活畜没动。今日顺栏 {used + 1}/{config.BARN_SCRUMP_DAILY}"
            )
            from . import bond as bond_mod
            await bond_mod.grant(conn, s["id"], bond_mod.SCRUMP, "labor")

        await conn.execute(
            "INSERT INTO chronicle (action, actor_id, target_id, text, created_at) VALUES (?,?,?,?,?)",
            (
                action,
                s["id"],
                peer["id"],
                f"{s['name']} 顺栏 {peer['name']} #{slot} {loot}",
                db.now(),
            ),
        )
        await conn.commit()
    return msg
