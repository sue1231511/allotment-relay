"""渔市行情 — 海产回收价随全岛供给浮动。

vend 回收海产时按近 7 日全岛卖出压力调价：集中卖同一种鱼，
该鱼越卖越贱；没什么人卖则略贵（轻稀缺溢价 20%）。系数夹在
0.65~1.20：供给约一倍平价、两倍八折、三倍以上跌停，价格不会
崩穿也不会暴涨。非海产不受影响；禁捕鱼在 vend 入口就被拦下，
不进这套行情。
"""
from __future__ import annotations

from datetime import datetime

import aiosqlite

from . import config, db
from .catalog import ITEM_NAMES, SEA_CATCH
from .disaster import CST

FLOW_WINDOW_DAYS = 7
MULT_FLOOR = 0.65
SCARCE_CAP = 1.20
SLOPE = 0.20
NORM_REF = 600  # 周参照：基准价 600/价票 的鱼，全岛一周卖出这么多条算平价


def _cst_day(ts: int | None = None) -> str:
    return datetime.fromtimestamp(
        ts if ts is not None else db.now(), CST
    ).strftime("%Y-%m-%d")


def week_norm(base_price: int) -> int:
    """全岛一周的正常吸收量：便宜鱼市场吃得多，贵鱼吃得少。"""
    price = max(int(base_price or 1), 1)
    return max(8, int(NORM_REF / price))


def is_market_fish(item: str) -> bool:
    if not item.startswith("fish_"):
        return False
    species = item[len("fish_"):]
    return species in SEA_CATCH


async def record_sale(conn: aiosqlite.Connection, item: str, qty: int) -> None:
    if not is_market_fish(item) or qty <= 0:
        return
    day = _cst_day()
    await conn.execute(
        """
        INSERT INTO fish_market_flow (day, item, qty) VALUES (?,?,?)
        ON CONFLICT(day, item) DO UPDATE SET qty = qty + excluded.qty
        """,
        (day, item, int(qty)),
    )


async def _window_flow(conn: aiosqlite.Connection, item: str) -> int:
    since = _cst_day(db.now() - (FLOW_WINDOW_DAYS - 1) * 86400)
    row = await (await conn.execute(
        "SELECT COALESCE(SUM(qty), 0) FROM fish_market_flow WHERE item=? AND day>=?",
        (item, since),
    )).fetchone()
    return int(row[0] or 0)


async def mult_for(conn: aiosqlite.Connection, item: str) -> tuple[float, str]:
    """该鱼当前行情系数与一句说明。非渔市货恒为 (1.0, '')。"""
    if not is_market_fish(item):
        return 1.0, ""
    from .catalog import suggested_price

    base = int(suggested_price(item) or 0)
    if base <= 0:
        return 1.0, ""
    ratio = await _window_flow(conn, item) / week_norm(base)
    mult = max(MULT_FLOOR, min(SCARCE_CAP, SCARCE_CAP - SLOPE * ratio))
    mult = round(mult, 2)
    note = ""
    if mult >= 1.08:
        note = "稀少看涨"
    elif mult <= 0.92:
        note = "近期卖得多了，走低"
    return mult, note


async def market_board(conn: aiosqlite.Connection) -> str:
    """潮生会行情牌：有波动的鱼按幅度排序，末尾附本周禁捕。"""
    from . import fish_ban

    rows = await (await conn.execute(
        "SELECT DISTINCT item FROM fish_market_flow"
    )).fetchall()
    entries: list[tuple[float, str]] = []
    for r in rows:
        item = r[0]
        if not is_market_fish(item):
            continue
        mult, _ = await mult_for(conn, item)
        if abs(mult - 1.0) >= 0.08:
            name = ITEM_NAMES.get(item, item)
            arrow = "↑" if mult > 1.0 else "↓"
            entries.append((mult, f"  {name} ×{mult:.2f} {arrow}"))
    lines = ["【渔市行情】近 7 日全岛卖出越多价越低（×0.65~×1.20），卖出按当时行情结算。"]
    if entries:
        entries.sort(key=lambda e: -abs(e[0] - 1.0))
        lines.extend(e[1] for e in entries[:12])
    else:
        lines.append("  这几日各行其是，鱼价都平平。")
    ban = fish_ban.brief_ban()
    if ban:
        lines.append(f"  {ban}")
    return "\n".join(lines)


async def fortune_hint(conn: aiosqlite.Connection) -> str:
    """韶年的渔市卦象：按当前压力给一句方向性建议。"""
    rows = await (await conn.execute(
        "SELECT DISTINCT item FROM fish_market_flow"
    )).fetchall()
    worst: tuple[float, str] | None = None
    best: tuple[float, str] | None = None
    for r in rows:
        item = r[0]
        if not is_market_fish(item):
            continue
        mult, _ = await mult_for(conn, item)
        name = ITEM_NAMES.get(item, item)
        if worst is None or mult < worst[0]:
            worst = (mult, name)
        if best is None or mult > best[0]:
            best = (mult, name)
    if worst and worst[0] <= 0.9 and best and best[0] >= 1.05:
        return (
            f"渔市卦象：{worst[1]}近来堆市（×{worst[0]:.2f}），"
            f"{best[1]}稀少（×{best[0]:.2f}）。想多换票，改捕后者。"
        )
    if best and best[0] >= 1.15:
        return f"渔市卦象：{best[1]}稀少（×{best[0]:.2f}），此刻出手不吃亏。"
    if worst and worst[0] <= 0.8:
        return f"渔市卦象：{worst[1]}卖的人太多（×{worst[0]:.2f}），缓缓再出手。"
    return "渔市卦象：近日鱼价平平，捕什么卖什么都是常价。"
