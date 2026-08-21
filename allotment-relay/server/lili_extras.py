"""栗栗扩充 — 贝壳品相、铃鹿乱捡款、手劲、夜栖祝福。"""

from __future__ import annotations

import json
import random
from typing import Any

import aiosqlite

from . import config, db, energy, survival
from .catalog import ITEM_NAMES, ITEM_PRICES, LILI_JUNK_DECOR, RARE_CURIO, resolve_item_key

SHELL_BASES = (
    "shell_catseye", "shell_conch", "shell_scallop", "shell_starfish", "shell_mussel",
)
SHELL_GRADE_MULT = {"shine": 2.0, "normal": 1.0, "rough": 0.35}
ROUGH_JUNK_COST = 12
DOG_FUR_FOR_JUNK = 9
SUMMON_ALIASES = {
    "shell_cat_eye": "shell_catseye",
    "shell_cateye": "shell_catseye",
    "cat_eye": "shell_catseye",
    "catseye": "shell_catseye",
}
SUMMON_RARE_KEYS = frozenset({"curio_pearl", "sea_glass", "fossil_shell"})
SUMMON_GOOD_KEYS = (frozenset({"fish_cockle"}) | frozenset(RARE_CURIO)) - SUMMON_RARE_KEYS
SUMMON_JUNK_PREFIXES = ("manure_", "deco_junk_")
SUMMON_JUNK_KEYS = frozenset({"compost", "wet_note", "ticket_stub"})
SUMMON_GIFTS = (
    ("bait_worm", 1),
    ("wild_mint", 1),
    ("crop_kelp", 1),
    ("fish_periwinkle", 1),
)
SUMMON_GRADE_LABEL = {
    "rare": "极品",
    "good": "优质",
    "plain": "普通",
    "junk": "劣质",
}

PET_BLESSINGS: list[dict[str, Any]] = [
    {"key": "fair_wind", "name": "顺风", "emoji": "🌊", "weight": 14,
     "desc": "下一次出海或赶海收获略好", "chronicle": "被栗栗的狗蹭了（顺风）"},
    {"key": "shield", "name": "挡一下", "emoji": "🛡️", "weight": 12,
     "desc": "下一次坏事件免疫一次", "chronicle": "被栗栗的狗蹭了（挡一下）"},
    {"key": "see_through", "name": "看破", "emoji": "👀", "weight": 12,
     "desc": "下一次拾叶碰瓷/小偷拆穿率大幅提高", "chronicle": "被栗栗的狗蹭了（看破）"},
    {"key": "guard_crop", "name": "护苗", "emoji": "🌱", "weight": 10,
     "desc": "下一次 tend 斑鸠不来", "chronicle": "被栗栗的狗蹭了（护苗）"},
    {"key": "bell_hint", "name": "铃响提示", "emoji": "🔔", "weight": 6,
     "desc": "栗栗下一摊到访时你提前收到纪事铃响", "chronicle": "被栗栗的狗蹭了（铃响提示）"},
    {"key": "night_watch", "name": "守夜", "emoji": "😴", "weight": 10,
     "desc": "精力恢复少许", "chronicle": "被栗栗的狗蹭了（守夜）"},
    {"key": "mist_nudge", "name": "蹭手心", "emoji": "🐾", "weight": 14,
     "desc": "雾智 +1", "chronicle": "被栗栗的狗蹭了（蹭手心）"},
    {"key": "fur_fail", "name": "翻车款", "emoji": "🖤", "weight": 8,
     "desc": "祝福摇散了，只得一根夜栖黑狗毛", "chronicle": "今日份惊喜由狗提供"},
]


def parse_shell(item: str) -> tuple[str, str] | None:
    if item.startswith("shell_shine_"):
        return "shell_" + item[len("shell_shine_"):], "shine"
    if item.startswith("shell_rough_"):
        return "shell_" + item[len("shell_rough_"):], "rough"
    if item.startswith("shell_"):
        return item, "normal"
    return None


def shell_item_key(base: str, grade: str) -> str:
    if grade == "shine":
        return base.replace("shell_", "shell_shine_", 1)
    if grade == "rough":
        return base.replace("shell_", "shell_rough_", 1)
    return base


def roll_shell_grade(*, ebb_fresh: bool = False) -> str:
    shine = 0.22 if ebb_fresh else 0.10
    rough = 0.18 if ebb_fresh else 0.28
    r = random.random()
    if r < shine:
        return "shine"
    if r < shine + rough:
        return "rough"
    return "normal"


def beach_shell_item(base_item: str) -> str:
    if not base_item.startswith("shell_"):
        return base_item
    from . import world
    from .config import TIDE_CYCLE

    ebb_fresh = False
    if world.current_tide() == "ebb":
        phase_elapsed = int(__import__("time").time()) % TIDE_CYCLE
        ebb_fresh = phase_elapsed < 600
    grade = roll_shell_grade(ebb_fresh=ebb_fresh)
    return shell_item_key(base_item, grade)


def item_trade_value(item: str, qty: int = 1) -> int:
    parsed = parse_shell(item)
    if parsed:
        base, grade = parsed
        base_price = ITEM_PRICES.get(base, ITEM_PRICES.get(item, 1))
        return max(1, int(base_price * SHELL_GRADE_MULT[grade] * qty))
    return ITEM_PRICES.get(item, 0) * qty


def give_requirement_value(give: dict[str, int]) -> int:
    return sum(item_trade_value(k, v) for k, v in give.items())


async def _ensure_state(conn: aiosqlite.Connection, steward_id: int) -> dict[str, Any]:
    conn.row_factory = aiosqlite.Row
    row = await (await conn.execute(
        "SELECT * FROM steward_lili WHERE steward_id=?", (steward_id,),
    )).fetchone()
    if row:
        return dict(row)
    await conn.execute("INSERT INTO steward_lili (steward_id) VALUES (?)", (steward_id,))
    row = await (await conn.execute(
        "SELECT * FROM steward_lili WHERE steward_id=?", (steward_id,),
    )).fetchone()
    return dict(row)


async def stars_block(conn: aiosqlite.Connection, steward_id: int) -> str | None:
    st = await _ensure_state(conn, steward_id)
    if int(st.get("stars_until") or 0) > db.now():
        return "你还在看星星"
    return None


async def fulfill_give(
    conn: aiosqlite.Connection,
    steward_id: int,
    give: dict[str, int],
) -> tuple[bool, dict[str, int], str]:
    """按品相折算收壳；非贝壳物品须精确匹配。"""
    stock = await db.get_satchel(steward_id)
    taken: dict[str, int] = {}

    for req_item, req_qty in give.items():
        base_shell = parse_shell(req_item)
        if base_shell and base_shell[0] == req_item and base_shell[1] == "normal":
            need_value = item_trade_value(req_item, req_qty)
            got_value = 0
            variants = [
                shell_item_key(req_item, "shine"),
                req_item,
                shell_item_key(req_item, "rough"),
            ]
            for variant in variants:
                have = stock.get(variant, 0) - taken.get(variant, 0)
                if have <= 0:
                    continue
                grade = parse_shell(variant)[1]
                unit = max(1, int(ITEM_PRICES.get(req_item, 1) * SHELL_GRADE_MULT[grade]))
                while have > 0 and got_value < need_value:
                    take_n = min(have, max(1, (need_value - got_value + unit - 1) // unit))
                    taken[variant] = taken.get(variant, 0) + take_n
                    have -= take_n
                    got_value += unit * take_n
            if got_value < need_value:
                label = ITEM_NAMES.get(req_item, req_item)
                return False, {}, f"缺少 {label}（按品相折算还差约 {need_value - got_value} 票等价）"
            continue

        have = stock.get(req_item, 0) - taken.get(req_item, 0)
        if have < req_qty:
            return False, {}, f"缺少 {ITEM_NAMES.get(req_item, req_item)} x{req_qty}"
        taken[req_item] = taken.get(req_item, 0) + req_qty

    for item, qty in taken.items():
        if not await db.take_item(conn, steward_id, item, qty):
            return False, {}, f"扣货失败 {item}"
    return True, taken, ""


def offered_value_from_taken(taken: dict[str, int]) -> int:
    return sum(item_trade_value(k, v) for k, v in taken.items())


def count_shine_in_taken(taken: dict[str, int]) -> int:
    return sum(v for k, v in taken.items() if k.startswith("shell_shine_"))


def has_rare_curio(taken: dict[str, int]) -> bool:
    rare = set(RARE_CURIO) | {"sea_glass", "fossil_shell"}
    return any(k in rare for k, v in taken.items() if v > 0)


async def assess_hand_trick(
    conn: aiosqlite.Connection,
    steward_id: int,
    steward_name: str,
    visit_id: int,
    give: dict[str, int],
    taken: dict[str, int],
    offer: dict[str, Any],
) -> tuple[str, str]:
    """返回 (result, message)。result: ok | reject | fool | favor"""
    st = await _ensure_state(conn, steward_id)
    need = int(offer.get("value_total") or give_requirement_value(give))
    got = offered_value_from_taken(taken)
    tier = int(offer.get("offer_tier") or 1)

    if got >= int(need * 1.12) and (count_shine_in_taken(taken) >= 1 or has_rare_curio(taken)):
        await conn.execute(
            "UPDATE steward_lili SET favored_visit_id=? WHERE steward_id=?",
            (visit_id, steward_id),
        )
        return "favor", "栗栗多看你一眼，抬手把你头发揉乱。铃鹿铃铛轻响——当摊顺延 5 分钟。"

    if tier >= 2 and got < int(need * 0.58):
        fool_visit = int(st.get("fool_visit_id") or 0)
        fool_count = int(st.get("fool_count") or 0)
        if fool_visit != visit_id:
            fool_count = 0
        if fool_count == 0:
            await conn.execute(
                """
                INSERT INTO steward_lili (steward_id, fool_visit_id, fool_count)
                VALUES (?, ?, 1)
                ON CONFLICT(steward_id) DO UPDATE SET
                    fool_visit_id=excluded.fool_visit_id, fool_count=1
                """,
                (steward_id, visit_id),
            )
            return "reject", "铃鹿的铃铛没响。栗栗把货签推回来：「这壳不值这件。」（揣破壳指名要好货，算糊弄）"
        until = db.now() + 10
        await conn.execute(
            """
            UPDATE steward_lili SET stars_until=?, fool_visit_id=?, fool_count=fool_count+1
            WHERE steward_id=?
            """,
            (until, visit_id, steward_id),
        )
        await db.add_chronicle("lili", f"{steward_name} 被栗栗弹了脑壳（狗嫌）", steward_id, conn=conn)
        return "fool", "夜栖低吼一声你没收手。栗栗抬手一记脑壳——眼冒金星 10 秒。"

    return "ok", ""


async def extend_visit(conn: aiosqlite.Connection, visit_id: int, seconds: int) -> None:
    await conn.execute(
        "UPDATE lili_visits SET expires_at = expires_at + ? WHERE id=?",
        (seconds, visit_id),
    )


async def shorten_visit(conn: aiosqlite.Connection, visit_id: int, seconds: int) -> None:
    await conn.execute(
        "UPDATE lili_visits SET expires_at = MAX(started_at, expires_at - ?) WHERE id=?",
        (seconds, visit_id),
    )


async def pet_yexi(conn: aiosqlite.Connection, steward_id: int, visit_id: int, name: str) -> str:
    st = await _ensure_state(conn, steward_id)
    day = db.now() // config.FORAGE_COOLDOWN_DAY
    if int(st.get("pet_day") or 0) == day and int(st.get("pet_visit_id") or 0) == visit_id:
        raise ValueError("这摊已经摸过夜栖了，换个人蹲吧")

    pool = list(PET_BLESSINGS)
    weights = [b["weight"] for b in pool]
    pick = random.choices(pool, weights=weights)[0]

    await conn.execute(
        """
        INSERT INTO steward_lili (steward_id, pet_day, pet_visit_id)
        VALUES (?,?,?)
        ON CONFLICT(steward_id) DO UPDATE SET pet_day=excluded.pet_day, pet_visit_id=excluded.pet_visit_id
        """,
        (steward_id, day, visit_id),
    )

    if pick["key"] == "fur_fail":
        await conn.execute(
            "UPDATE steward_lili SET dog_fur = dog_fur + 1 WHERE steward_id=?",
            (steward_id,),
        )
        await db.add_chronicle("lili", f"{name} {pick['chronicle']}", steward_id, conn=conn)
        st2 = await _ensure_state(conn, steward_id)
        fur = int(st2.get("dog_fur") or 0)
        extra = ""
        if fur >= DOG_FUR_FOR_JUNK:
            junk_key = random.choice(list(LILI_JUNK_DECOR.keys()))
            await db.add_item(conn, steward_id, f"deco_junk_{junk_key}", 1)
            await conn.execute(
                "UPDATE steward_lili SET dog_fur = dog_fur - ? WHERE steward_id=?",
                (DOG_FUR_FOR_JUNK, steward_id),
            )
            extra = f"\n集满狗毛，栗栗塞来 {LILI_JUNK_DECOR[junk_key]['name']}"
        return f"夜栖太兴奋，祝福摇散了。获得夜栖黑狗毛 x1（{fur}/{DOG_FUR_FOR_JUNK}）{extra}"

    if pick["key"] == "night_watch":
        await energy.restore(conn, steward_id, 8)
    elif pick["key"] == "mist_nudge":
        await survival.bump(conn, steward_id, mist_wit=1)
    elif pick["key"] == "bell_hint":
        await conn.execute(
            "UPDATE steward_lili SET bell_hint_day=? WHERE steward_id=?",
            (day + 1, steward_id),
        )

    await conn.execute(
        """
        INSERT INTO steward_lili (steward_id, blessing_key, blessing_uses)
        VALUES (?, ?, 1)
        ON CONFLICT(steward_id) DO UPDATE SET blessing_key=excluded.blessing_key, blessing_uses=1
        """,
        (steward_id, pick["key"]),
    )
    await db.add_chronicle("lili", f"{name} {pick['chronicle']}", steward_id, conn=conn)
    return f"夜栖抖了抖铃铛。{pick['emoji']}{pick['name']}：{pick['desc']}"


async def trade_rough_for_junk(conn: aiosqlite.Connection, steward_id: int, name: str) -> str:
    stock = await db.get_satchel(steward_id)
    rough_total = sum(v for k, v in stock.items() if k.startswith("shell_rough_"))
    if rough_total < ROUGH_JUNK_COST:
        raise ValueError(f"糙壳不够。栗栗：「凑够 {ROUGH_JUNK_COST} 枚糙壳再来。」")
    left = ROUGH_JUNK_COST
    for item in sorted(stock):
        if not item.startswith("shell_rough_"):
            continue
        take = min(stock[item], left)
        if take <= 0:
            continue
        await db.take_item(conn, steward_id, item, take)
        left -= take
        if left <= 0:
            break
    junk_key = random.choice(list(LILI_JUNK_DECOR.keys()))
    await db.add_item(conn, steward_id, f"deco_junk_{junk_key}", 1)
    meta = LILI_JUNK_DECOR[junk_key]
    await db.add_chronicle(
        "lili",
        f"{name} 用糙壳换到铃鹿乱捡款「{meta['name']}」",
        steward_id,
        conn=conn,
    )
    return f"栗栗收下糙壳一把，从铃鹿驮包里摸出：{meta['emoji']}{meta['name']}。{meta['quip']}"


async def consume_blessing(conn: aiosqlite.Connection, steward_id: int, key: str) -> bool:
    st = await _ensure_state(conn, steward_id)
    if st.get("blessing_key") != key or int(st.get("blessing_uses") or 0) <= 0:
        return False
    await conn.execute(
        "UPDATE steward_lili SET blessing_uses = blessing_uses - 1 WHERE steward_id=?",
        (steward_id,),
    )
    if int(st.get("blessing_uses") or 0) <= 1:
        await conn.execute(
            "UPDATE steward_lili SET blessing_key='' WHERE steward_id=?",
            (steward_id,),
        )
    return True


async def has_blessing(conn: aiosqlite.Connection, steward_id: int, key: str) -> bool:
    st = await _ensure_state(conn, steward_id)
    return st.get("blessing_key") == key and int(st.get("blessing_uses") or 0) > 0


async def bell_chronicle_if_due(conn: aiosqlite.Connection, steward_id: int, name: str) -> str | None:
    st = await _ensure_state(conn, steward_id)
    day = db.now() // config.FORAGE_COOLDOWN_DAY
    if int(st.get("bell_hint_day") or 0) != day:
        return None
    await conn.execute(
        "UPDATE steward_lili SET bell_hint_day=0 WHERE steward_id=?",
        (steward_id,),
    )
    await db.add_chronicle("lili", f"远处铃响——{name} 听见栗栗下一摊快到了", steward_id, conn=conn)
    return "🔔 铃响提示：你提前听见栗栗要来了"

def visit_bell_warning(visit: dict[str, Any]) -> str | None:
    left = visit["expires_at"] - db.now()
    if 0 < left <= 600:
        return "铃鹿铃铛密响一串——摊将撤，最后十分钟。"
    return None

def junk_offer_note() -> str:
    return random.choice([
        "铃鹿乱捡款·不退不换",
        "铃鹿叼串了货签——离谱但抢手",
        "栗栗：「都是海给的，不好意思不要。」",
    ])


def _bare_item_name(text: str) -> str:
    out = (text or "").strip()
    for ch in "✨💧🐚⭐🦪🌊💎🪙🟠⚪⚙️·-— ":
        out = out.replace(ch, "")
    return out


def resolve_summon_item(token: str) -> str | None:
    raw = (token or "").strip()
    if not raw:
        return None
    key = raw.lower().replace("-", "_").replace(" ", "_")
    if key in SUMMON_ALIASES:
        return SUMMON_ALIASES[key]
    found = resolve_item_key(raw)
    if found:
        return found
    bare = _bare_item_name(raw)
    shine = "亮壳" in raw or "✨" in raw
    rough = "糙壳" in raw or "💧" in raw
    core = bare.replace("亮壳", "").replace("糙壳", "")
    hits: list[str] = []
    for item_key, name in ITEM_NAMES.items():
        b = _bare_item_name(name)
        if b == bare or (core and b == core):
            hits.append(item_key)
    if not hits:
        return None
    if shine:
        preferred = [h for h in hits if h.startswith("shell_shine_")]
        if preferred:
            return preferred[0]
    if rough:
        preferred = [h for h in hits if h.startswith("shell_rough_")]
        if preferred:
            return preferred[0]
    bases = [
        h for h in hits
        if h.startswith("shell_") and not h.startswith("shell_shine_") and not h.startswith("shell_rough_")
    ]
    if bases:
        return bases[0]
    return sorted(hits, key=len)[0]


def summon_grade(item: str) -> str:
    parsed = parse_shell(item)
    if parsed:
        _base, grade = parsed
        if grade == "shine":
            return "rare"
        if grade == "rough":
            return "plain"
        return "good"
    if item in SUMMON_RARE_KEYS:
        return "rare"
    if item in SUMMON_GOOD_KEYS:
        return "good"
    if item.startswith(SUMMON_JUNK_PREFIXES) or item in SUMMON_JUNK_KEYS:
        return "junk"
    return "junk"


def next_summon_chance(current: int, grade: str) -> tuple[int, int]:
    lo, hi = config.LILI_SUMMON_DELTA.get(grade, (0, 0))
    delta = lo if lo == hi else random.randint(lo, hi)
    nxt = max(config.LILI_SUMMON_MIN, min(config.LILI_SUMMON_MAX, int(current) + delta))
    return nxt, delta


def summon_payout(item: str, grade: str) -> int:
    value = item_trade_value(item, 1)
    if grade == "rare":
        return max(1, int(value * config.LILI_SUMMON_RARE_PAY))
    if grade == "good":
        return max(1, value)
    if grade == "plain":
        return max(1, value)
    return 0


def pick_summon_gift() -> tuple[str, int]:
    return random.choice(SUMMON_GIFTS)


async def load_summon_state(conn: aiosqlite.Connection, steward_id: int) -> dict[str, Any]:
    return await _ensure_state(conn, steward_id)


async def save_summon_state(
    conn: aiosqlite.Connection,
    steward_id: int,
    chance: int,
) -> None:
    await conn.execute(
        """
        INSERT INTO steward_lili (steward_id, summon_chance, summon_done)
        VALUES (?, ?, 1)
        ON CONFLICT(steward_id) DO UPDATE SET
            summon_chance=excluded.summon_chance, summon_done=1
        """,
        (steward_id, chance),
    )


def summon_rate_line(st: dict[str, Any]) -> str:
    if not int(st.get("summon_done") or 0):
        return "你还没用过贝壳引商，首次必来"
    chance = int(st.get("summon_chance") or config.LILI_SUMMON_BASE)
    return f"你下次引商成功率 {chance}%"
