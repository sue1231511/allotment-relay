"""岛缘 — 账号总人生进度。岸上动手只加，井下只减，无上限，地板 0。"""
from __future__ import annotations

import math
from typing import Any

import aiosqlite

from . import db

STORY_COMPLETE = 100
VISIT_FIRST = 20
VISIT_DAILY = 4
AFFINITY_EACH = 3
DOVE_FEED = 5
GUILD = 8
ASSIST = 3
CONTRACT_FILL = 8
LEAGUE_STEP = 5
LEAGUE_DONE = 40
BEACON_POST = 6
BEACON_DAILY_CAP = 2
DINE_GUEST = 10
DINE_HOST = 6
EATERY_OPEN = 80
COOK = 3
EAT = 2
SLEEP = 5
SHIYE = 8
DOVE_STALK = 6
EVENT_GOOD = 10
EVENT_BAD = 5
COMMONS_CLAIM = 15
DISCOVERY = 8
LORE_TOPIC = 12
EXHIBIT_SET = 60
SOUVENIR = 8
SOW = 3
TEND = 4
WATER = 2
FERTILIZE = 2
GATHER_PLOT = 4
FORAGE = 6
SHAKE = 3
CHOP = 4
COMPOST = 2
SCARECROW = 3
CAMERA = 6
BUY_LAND = 25
SCRUMP = 5
AMENDS = 4
GIFT = 5
MARKET_SELL = 4
MARKET_DEAL = 6
CLINIC_TREAT = 4
LILI_TRADE = 3
MUSONG_NAME = 12
JINGSHAN_DONE = 80
BUXING_LIGHT = 30
BUXING_WATCH = 50
HUT_UPGRADE = 12
HUT_INSTALL = 6
BARN_CHORE = 4
MASCOT_ADOPT = 20
GEAR_UPGRADE = 15
PEN_HARVEST = 8
VOYAGE_RETURN = 10
THEATER_PAY = 4
STAR_CHEER_SEEN = 8

WELL_FIRST = -25
WELL_ENTER = -12
WELL_FIGHT = -8
WELL_WIN = -4
WELL_LOSE = -6
WELL_MEDIC = -6
WELL_CHEER = -8
WELL_MARKET = -4
WELL_CRIME = -10
WELL_DEEPER = -6

ENERGY_MAP: dict[str, tuple[int, str]] = {
    "撒网": (5, "labor"),
    "坐钓": (6, "labor"),
    "赶海": (8, "labor"),
    "掏洞": (5, "labor"),
    "捞怪鱼": (4, "labor"),
    "探脉": (8, "labor"),
    "崖矿": (5, "labor"),
    "洗矿": (4, "labor"),
    "工坊": (8, "labor"),
    "灌盐田": (5, "labor"),
    "收盐": (4, "labor"),
    "打捞": (10, "labor"),
    "酒吧上工": (10, "labor"),
    "小剧场试镜": (4, "labor"),
    "小剧场对戏": (6, "labor"),
    "小剧场演出": (12, "labor"),
    "star_watch": (4, "labor"),
    "tale_explore": (4, "labor"),
    "讨伐": (10, "labor"),
    "砍缆跑路": (4, "labor"),
    "黑旗接舷": (4, "labor"),
}

CATS = ("labor", "people", "story", "life", "give", "well")
CAT_LABEL = {
    "labor": "劳作",
    "people": "人情",
    "story": "叙事",
    "life": "生活",
    "give": "投入",
    "well": "井下已蚀",
}

FLAVORS = (
    (60000, "潮生故人"),
    (30000, "这座岛记得你"),
    (15000, "潮里有名字"),
    (8000, "岛缘已深"),
    (4000, "结过缘"),
    (1500, "岛上有人喊得应"),
    (500, "认得路"),
    (100, "沾了潮气"),
    (0, "新上岸"),
)


def fmt(n: int) -> str:
    return f"{int(n):,}"


def flavor(n: int) -> str:
    v = max(0, int(n or 0))
    for need, label in FLAVORS:
        if v >= need:
            return label
    return "新上岸"


def donate_amount(tickets: int) -> int:
    n = max(0, int(tickets))
    if n <= 0:
        return 0
    return max(1, int(math.floor(6 * math.sqrt(n))))


def sheet_lines(s: dict[str, Any]) -> list[str]:
    n = int(s.get("island_bond") or 0)
    return [
        f"岛缘 {fmt(n)} ∞ · {flavor(n)}",
        "你与潮汐岛结下的所有联系。",
    ]


def inspect_text(s: dict[str, Any]) -> str:
    n = int(s.get("island_bond") or 0)
    lines = [
        f"岛缘 {fmt(n)} ∞ · {flavor(n)}",
        "你与潮汐岛结下的所有联系。",
        "",
    ]
    for cat in CATS:
        raw = int(s.get(f"island_bond_{cat}") or 0)
        if cat == "well" and raw <= 0:
            continue
        shown = fmt(raw) if cat != "well" else fmt(raw)
        lines.append(f"{CAT_LABEL[cat]} {shown}")
    lines.extend([
        "",
        "岸上动手都算进岛缘，井下减，地板 0，无上限。",
        "一篇潮闻或人物故事通关 +100。查看类指令（status/help/回看）不算。",
        "等级吃工分票；岛缘吃你和这座岛发生过的事。两套账。",
        "看：steward_ops 岛缘 · 空 command 的 sheet 也会写这一行。",
    ])
    return "\n".join(lines)


async def _flag(conn: aiosqlite.Connection, steward_id: int, key: str) -> bool:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS island_bond_flags (
            steward_id INTEGER NOT NULL,
            flag_key TEXT NOT NULL,
            PRIMARY KEY (steward_id, flag_key)
        )
        """
    )
    cur = await conn.execute(
        "SELECT 1 FROM island_bond_flags WHERE steward_id=? AND flag_key=?",
        (steward_id, key),
    )
    if await cur.fetchone():
        return False
    await conn.execute(
        "INSERT INTO island_bond_flags (steward_id, flag_key) VALUES (?,?)",
        (steward_id, key),
    )
    return True


async def _daily(conn: aiosqlite.Connection, steward_id: int, key: str, cap: int) -> bool:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS island_bond_daily (
            steward_id INTEGER NOT NULL,
            day INTEGER NOT NULL,
            flag_key TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (steward_id, day, flag_key)
        )
        """
    )
    day = db.day_id()
    row = await (await conn.execute(
        "SELECT count FROM island_bond_daily WHERE steward_id=? AND day=? AND flag_key=?",
        (steward_id, day, key),
    )).fetchone()
    used = int(row[0] if row else 0)
    if used >= cap:
        return False
    await conn.execute(
        """
        INSERT INTO island_bond_daily (steward_id, day, flag_key, count)
        VALUES (?,?,?,1)
        ON CONFLICT(steward_id, day, flag_key) DO UPDATE SET count = count + 1
        """,
        (steward_id, day, key),
    )
    return True


async def grant(
    conn: aiosqlite.Connection,
    steward_id: int,
    amount: int,
    cat: str = "labor",
    *,
    once: str | None = None,
    daily: str | None = None,
    daily_cap: int = 1,
) -> int:
    if not steward_id or not amount:
        return 0
    if cat not in CATS:
        cat = "life"
    if once and not await _flag(conn, steward_id, once):
        return 0
    if daily and not await _daily(conn, steward_id, daily, daily_cap):
        return 0
    row = await (await conn.execute(
        "SELECT island_bond FROM stewards WHERE id=?", (steward_id,)
    )).fetchone()
    if row is None:
        return 0
    current = int(row[0] or 0)
    applied = int(amount)
    if applied < 0:
        applied = max(applied, -current)
    if applied == 0:
        return 0
    new_total = current + applied
    col = f"island_bond_{cat}"
    if cat == "well":
        await conn.execute(
            f"UPDATE stewards SET island_bond=?, {col}={col}+? WHERE id=?",
            (new_total, abs(applied), steward_id),
        )
    else:
        await conn.execute(
            f"UPDATE stewards SET island_bond=?, {col}={col}+? WHERE id=?",
            (new_total, applied, steward_id),
        )
    return applied


async def from_energy(conn: aiosqlite.Connection, steward_id: int, action: str, spent: int = 0) -> int:
    act = (action or "").strip()
    if act == "出海":
        if spent >= 35:
            n = 28
        elif spent >= 24:
            n = 20
        else:
            n = 12
        return await grant(conn, steward_id, n, "labor")
    hit = ENERGY_MAP.get(act)
    if not hit:
        return 0
    n, cat = hit
    return await grant(conn, steward_id, n, cat)


async def note_visit(conn: aiosqlite.Connection, steward_id: int, npc_key: str) -> int:
    key = (npc_key or "").strip()
    if not key:
        return 0
    first = await _flag(conn, steward_id, f"visit:{key}")
    if first:
        return await grant(conn, steward_id, VISIT_FIRST, "people")
    return await grant(
        conn, steward_id, VISIT_DAILY, "people", daily=f"visit:{key}", daily_cap=1
    )


async def affinity_gain(conn: aiosqlite.Connection, steward_id: int, delta: int) -> int:
    if delta <= 0:
        return 0
    return await grant(conn, steward_id, int(delta) * AFFINITY_EACH, "people")


async def story_complete(conn: aiosqlite.Connection, steward_id: int, key: str) -> int:
    return await grant(conn, steward_id, STORY_COMPLETE, "story", once=key)


async def well(conn: aiosqlite.Connection, steward_id: int, amount: int, *, once: str | None = None) -> int:
    if amount >= 0:
        amount = -abs(amount) if amount else 0
    return await grant(conn, steward_id, amount, "well", once=once)


async def ensure_backfill(conn: aiosqlite.Connection, steward_id: int) -> None:
    row = await (await conn.execute(
        "SELECT island_bond_backfill FROM stewards WHERE id=?", (steward_id,)
    )).fetchone()
    if row is None or int(row[0] or 0):
        return
    tales = await (await conn.execute(
        "SELECT tale_key FROM steward_tales_done WHERE steward_id=? AND outcome='completed'",
        (steward_id,),
    )).fetchall()
    for (key,) in tales:
        await story_complete(conn, steward_id, f"tale:{key}")
    stories = await (await conn.execute(
        """
        SELECT DISTINCT story_key FROM steward_stories
        WHERE steward_id=? AND status='completed' AND COALESCE(reward_granted,0)=1
        """,
        (steward_id,),
    )).fetchall()
    for (key,) in stories:
        await story_complete(conn, steward_id, f"story:{key}")
    tt = await (await conn.execute(
        "SELECT score FROM tt_affinity WHERE steward_id=?", (steward_id,)
    )).fetchone()
    if tt:
        await affinity_gain(conn, steward_id, int(tt[0] or 0))
    th = await (await conn.execute(
        "SELECT score FROM star_theater_affinity WHERE steward_id=?", (steward_id,)
    )).fetchone()
    if th:
        await affinity_gain(conn, steward_id, int(th[0] or 0))
    dove = await (await conn.execute(
        "SELECT clinic_dove_affinity, eatery_open FROM stewards WHERE id=?",
        (steward_id,),
    )).fetchone()
    if dove:
        favor = int(dove[0] or 0)
        if favor:
            await grant(conn, steward_id, (favor // 2) * DOVE_FEED, "people")
        if int(dove[1] or 0):
            await grant(conn, steward_id, EATERY_OPEN, "life", once="eatery_open")
    await conn.execute(
        "UPDATE stewards SET island_bond_backfill=1 WHERE id=?",
        (steward_id,),
    )


async def backfill_all(conn: aiosqlite.Connection) -> None:
    rows = await (await conn.execute(
        "SELECT id FROM stewards WHERE enrolled=1 AND COALESCE(island_bond_backfill,0)=0"
    )).fetchall()
    for (sid,) in rows:
        await ensure_backfill(conn, int(sid))
