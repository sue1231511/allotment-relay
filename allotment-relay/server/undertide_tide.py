"""潮汐法则 — 地面景气分 → 地下收益倍率（三期）。天天侧。"""

from __future__ import annotations

from typing import Any

import aiosqlite

from . import db
from . import undertide_config as utcfg
from . import undertide_copy as utcopy


def _week_id() -> int:
    return db.now() // (86400 * 7)


TIDE_LINES = {
    1.5: "上面的人最近手头太阔了。井下的东西，跟着贵了。",
    1.25: "地面行情好，井下水涨船高。",
    1.0: "潮平两岸阔。老样子。",
    0.9: "上面不景气，井下的也勒紧了。",
    0.8: "上面都揭不开锅了，井下能有什么好货。",
}


async def _score(conn: aiosqlite.Connection) -> int:
    """景气分 0~100：guild 领取率 30% / 酒吧工班 20% / 市场成交 25% / 票余额增速 25%（简化）。"""
    now = db.now()
    week_ago = now - 86400 * 7
    cur = await conn.execute(
        "SELECT COUNT(*) FROM guild_shifts WHERE day >= ?", (week_ago // 86400,)
    )
    guild_n = (await cur.fetchone())[0]
    cur = await conn.execute("SELECT COUNT(*) FROM stewards WHERE enrolled=1")
    players = max(1, (await cur.fetchone())[0])
    cur = await conn.execute(
        "SELECT COUNT(*) FROM chronicle WHERE action='bar_shift' AND created_at > ?", (week_ago,)
    )
    bar_n = (await cur.fetchone())[0]
    cur = await conn.execute(
        "SELECT COUNT(*) FROM chronicle WHERE action='market' AND created_at > ?", (week_ago,)
    )
    market_n = (await cur.fetchone())[0]
    cur = await conn.execute("SELECT AVG(tickets) FROM stewards WHERE enrolled=1")
    avg_tickets = (await cur.fetchone())[0] or 0

    s1 = min(100, guild_n / players * 25)            # 每人每周~3次 guild 满分
    s2 = min(100, bar_n / players * 50)
    s3 = min(100, market_n / players * 25)
    s4 = min(100, float(avg_tickets) / 3.0)            # 人均 300 票满分
    return int(s1 * 0.3 + s2 * 0.2 + s3 * 0.25 + s4 * 0.25)


async def ensure_tide(conn: aiosqlite.Connection) -> dict[str, Any]:
    """每周重算景气分；真人手动覆盖优先。返回状态 dict。"""
    week = _week_id()
    conn.row_factory = aiosqlite.Row
    await conn.execute(
        "INSERT OR IGNORE INTO ut_tide_state (id, week, score, mult, updated_at) VALUES (1,?,?,?,?)",
        (week, 50, 1.0, db.now()),
    )
    row = await (await conn.execute("SELECT * FROM ut_tide_state WHERE id=1")).fetchone()
    if int(row["week"]) != week:
        score = await _score(conn)
        mult = next(
            (m for cut, m in zip(utcfg.UT_TIDE_LADDER, utcfg.UT_TIDE_MULTS) if score >= cut),
            utcfg.UT_TIDE_MULTS[-1],
        )
        await conn.execute(
            "UPDATE ut_tide_state SET week=?, score=?, mult=?, updated_at=? WHERE id=1",
            (week, score, mult, db.now()),
        )
        row = await (await conn.execute("SELECT * FROM ut_tide_state WHERE id=1")).fetchone()
        await db.add_chronicle(
            "undertide",
            f"荔栀今晚擦杯子擦得很慢。「{TIDE_LINES.get(mult, '')}」",
            None, conn=conn,
        )
    return dict(row)


async def tide_mult(conn: aiosqlite.Connection) -> tuple[float, str]:
    """当前生效倍率（手动覆盖优先）+ 提示语。"""
    st = await ensure_tide(conn)
    mult = float(st["manual_mult"]) if st.get("manual_mult") else float(st["mult"])
    line = TIDE_LINES.get(mult, "")
    return mult, line


async def maybe_highlight_broadcast(conn: aiosqlite.Connection, s: dict[str, Any], ut: dict[str, Any], day_net: int) -> str:
    """单日地下净收益 ≥150 → 全服高光纪事（当日一次）。"""
    if day_net < utcfg.UT_HIGHLIGHT_BROADCAST:
        return ""
    day = db.now() // 86400
    if int(ut.get("highlight_done") or 0) == day:
        return ""
    await conn.execute(
        "UPDATE steward_undertide SET highlight_done=? WHERE steward_id=?", (day, s["id"])
    )
    tpl = random_line()
    await db.add_chronicle(
        "undertide",
        tpl.format(name=s["name"], net=day_net),
        None, conn=conn,
    )
    return "\n\n（今晚整个潮下都在传你的名字。）"


def random_line() -> str:
    import random
    return random.choice([
        "{name} 今晚在井下净赚 {net} 票。掌柜的帘子今晚没合上。",
        "{name} 从井下带上来 {net} 票。有人看见他在数第二遍。",
        "今晚死人抽牌的桌上出了个大数目——{name}，{net} 票。Silas 记住了他的脸。",
    ])
