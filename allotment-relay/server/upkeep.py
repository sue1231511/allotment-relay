"""岸维 — 产业维修费。潮生会征收，费入潮汐基金。

岸税看口袋现票；岸维看你开了多少产业。起步份地/果园、棚屋 Lv1、
第一口盐田、第一个矿坑免征。扩了、开了馆、盖了棚才交。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from . import config, db, land
from .tax import EXPAND_LOCK, TAX_COLLECT_FLOOR

UPKEEP_NAME = "岸维"
FLAG_PREFIX = "shore_upkeep:"
COLLECT_FLOOR = TAX_COLLECT_FLOOR
_CST = timezone(timedelta(hours=8))

# 每天单价。起步产业免，扩出来的才计。产业单价至少 10。
# 菜地超出 10；果园超出 20（比菜地贵）；温室每座 30（比果园贵）。
PLOT_EXTRA = 10
ORCHARD_EXTRA = 20
GREENHOUSE = 30
BARN_BASE = 10
BARN_STOCKED = 10
EATERY = 12
HUT_BY_LEVEL = {0: 0, 1: 0, 2: 10, 3: 15, 4: 20}
PEN = 10
SALT_EXTRA = 10
QUARRY_EXTRA = 10
BOAT_FEE = {"skiff": 10, "cutter": 15, "drifter": 20}

UPKEEP_HELP = f"""visit_ops 潮生会 维（整句写进 command）：
  维 / 岸维 / 维修 — 看档：哪些产业要交、今日应/已划/欠
  维 交 — 把欠的维修费（含今日未划完的）能交的交清。也可 维 交 50 交一部分
  没有 upkeep_ops。吉祥物喂养是 hut_ops mascot upkeep，不是这条。
  田间意外一次性处理是 plot_ops repair 编号，也不是这条。
{UPKEEP_NAME}按产业每天收，东八区换班后第一次有人动手时自动划入潮汐基金。不是岸税（岸税仍周一划）。
岸税看口袋现票；岸维看份地/果园/温室/畜栏/小馆/小屋/渔排/盐田/矿坑/船。
起步 3 块份地、3 树位、棚屋 Lv1、第 1 口盐田、第 1 个矿坑免征。产业单价至少 10 票（超出起步的份地 10、果园 20、温室 30，畜栏 10+在栏 10，开馆 12，小屋/船 10/15/20，渔排/盐田/矿坑 10）。今日新号免征到明天。
欠{UPKEEP_NAME}时不能{EXPAND_LOCK}；开着的小馆会暂停堂食。
例子：潮生会 维 · 潮生会 维 交 · 潮生会 维 交 50
容易搞混：税=强制岸税（富人按口袋交，周一划）。维=产业维修费（产业越大越交，每天划）。
mascot upkeep=吉祥物花 4 票主动喂养。plot_ops repair=处理田间意外。voyage repair=修船。"""


def human_day_id(ts: int | None = None) -> str:
    """东八区日历日，例如 2026-08-25。"""
    dt = datetime.fromtimestamp(ts if ts is not None else db.now(), _CST)
    return dt.strftime("%Y-%m-%d")


def day_flag_key(day_id: str | None = None, ts: int | None = None) -> str:
    return f"{FLAG_PREFIX}{day_id or human_day_id(ts)}"


def _in_first_day(created_at: int, ts: int | None = None) -> bool:
    return human_day_id(int(created_at or 0)) == human_day_id(ts)


def next_levy_line(ts: int | None = None, *, done: bool = False) -> str:
    day_id = human_day_id(ts)
    if done:
        nxt = datetime.strptime(day_id, "%Y-%m-%d") + timedelta(days=1)
        return f"今日（{day_id}）已入簿 · 下次 {nxt.strftime('%m-%d')}"
    return f"今天（{day_id}）会自动划维修费"


def hut_fee(level: int, built: bool) -> int:
    if not built:
        return 0
    lv = max(0, int(level or 0))
    if lv in HUT_BY_LEVEL:
        return HUT_BY_LEVEL[lv]
    return HUT_BY_LEVEL[4]


def boat_fee(boat_key: str) -> int:
    key = (boat_key or "").strip()
    if not key:
        return 0
    return int(BOAT_FEE.get(key, BOAT_FEE["skiff"]))


def due_from_holdings(h: dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
    """按当前产业算今日应缴。返回 (总额, 分项)。"""
    items: list[dict[str, Any]] = []

    def add(key: str, label: str, qty: int, rate: int) -> None:
        if qty <= 0 or rate <= 0:
            return
        fee = int(qty) * int(rate)
        items.append({"key": key, "label": label, "qty": int(qty), "rate": int(rate), "fee": fee})

    extra_plots = max(0, int(h.get("plots") or 0) - config.START_PARCELS)
    add("plot", f"份地超出起步 {config.START_PARCELS}", extra_plots, PLOT_EXTRA)
    extra_orchards = max(0, int(h.get("orchards") or 0) - config.START_ORCHARDS)
    add("orchard", f"果园超出起步 {config.START_ORCHARDS}", extra_orchards, ORCHARD_EXTRA)
    add("greenhouse", "温室", int(h.get("greenhouses") or 0), GREENHOUSE)
    if h.get("barn"):
        add("barn", "畜栏", 1, BARN_BASE)
        add("barn_stocked", "畜栏在栏", int(h.get("barn_stocked") or 0), BARN_STOCKED)
    if h.get("eatery"):
        add("eatery", "开馆小馆", 1, EATERY)
    hut_due = hut_fee(int(h.get("hut_level") or 0), bool(h.get("hut_built")))
    if hut_due:
        add("hut", f"小屋 Lv{int(h.get('hut_level') or 0)}", 1, hut_due)
    add("pen", "渔排", int(h.get("pens") or 0), PEN)
    extra_pans = max(0, int(h.get("pans") or 0) - 1)
    add("salt", "盐田超出第 1 口", extra_pans, SALT_EXTRA)
    extra_pits = max(0, int(h.get("pits") or 0) - 1)
    add("quarry", "矿坑超出第 1 个", extra_pits, QUARRY_EXTRA)
    boat_due = boat_fee(str(h.get("boat_key") or ""))
    if boat_due:
        add("boat", "泊船", 1, boat_due)
    total = sum(int(it["fee"]) for it in items)
    return total, items


def rate_table_lines() -> list[str]:
    return [
        f"  份地超出起步 {config.START_PARCELS} 块    {PLOT_EXTRA} 票/块",
        f"  果园超出起步 {config.START_ORCHARDS} 树位  {ORCHARD_EXTRA} 票/树位",
        f"  温室                      {GREENHOUSE} 票/座",
        f"  畜栏已建                  {BARN_BASE} 票 + 在栏 {BARN_STOCKED} 票/槽",
        f"  开馆小馆                  {EATERY} 票",
        f"  小屋 Lv1 免；Lv2/3/4      {HUT_BY_LEVEL[2]}/{HUT_BY_LEVEL[3]}/{HUT_BY_LEVEL[4]} 票",
        f"  渔排                      {PEN} 票/座",
        f"  盐田超出第 1 口           {SALT_EXTRA} 票/口",
        f"  矿坑超出第 1 个           {QUARRY_EXTRA} 票/坑",
        f"  船 舢板/切波艇/漂航船     {BOAT_FEE['skiff']}/{BOAT_FEE['cutter']}/{BOAT_FEE['drifter']} 票",
    ]


async def holdings_for(conn, steward: dict[str, Any]) -> dict[str, Any]:
    sid = int(steward["id"])
    barn_stocked = 0
    if steward.get("barn_built"):
        row = await (await conn.execute(
            "SELECT COUNT(*) FROM barn_animals "
            "WHERE steward_id=? AND species IS NOT NULL AND species != ''",
            (sid,),
        )).fetchone()
        barn_stocked = int(row[0] or 0) if row else 0
    pens = int((await (await conn.execute(
        "SELECT COUNT(*) FROM fish_pens WHERE steward_id=?", (sid,),
    )).fetchone())[0] or 0)
    pans = int((await (await conn.execute(
        "SELECT COUNT(*) FROM craft_pans WHERE steward_id=?", (sid,),
    )).fetchone())[0] or 0)
    pits = int((await (await conn.execute(
        "SELECT COUNT(*) FROM quarry_claims WHERE steward_id=?", (sid,),
    )).fetchone())[0] or 0)
    return {
        "plots": land.count_of(steward, False),
        "orchards": land.count_of(steward, True),
        "greenhouses": land.count_of(steward, greenhouse=True),
        "barn": bool(steward.get("barn_built")),
        "barn_stocked": barn_stocked,
        "eatery": bool(steward.get("eatery_open")),
        "hut_built": bool(steward.get("hut_built")),
        "hut_level": int(steward.get("hut_level") or 0),
        "pens": pens,
        "pans": pans,
        "pits": pits,
        "boat_key": steward.get("boat_key") or "",
    }


def shop_paused(steward: dict[str, Any] | None) -> bool:
    if not steward:
        return False
    return int(steward.get("upkeep_arrears") or 0) > 0 and bool(steward.get("eatery_open"))


def assert_upkeep_clear(steward: dict[str, Any]) -> None:
    owed = int(steward.get("upkeep_arrears") or 0)
    if owed <= 0:
        return
    raise ValueError(
        f"欠{UPKEEP_NAME} {owed} 票。先 visit_ops 潮生会 维 交。"
        f"欠维修费时不能{EXPAND_LOCK}；开着的小馆会暂停堂食。"
    )


def assert_shop_serving(steward: dict[str, Any]) -> None:
    if not shop_paused(steward):
        return
    owed = int(steward.get("upkeep_arrears") or 0)
    label = steward.get("eatery_label") or f"{steward.get('name', '这')}的馆"
    raise ValueError(
        f"「{label}」欠{UPKEEP_NAME} {owed} 票，卫生未过，暂停堂食。"
        f"店主要 visit_ops 潮生会 维 交。"
    )


async def _ensure_fund(conn) -> None:
    await conn.execute(
        "INSERT OR IGNORE INTO tide_fund "
        "(id, tickets, donated_total, paid_total, taxed_total, upkeep_total) "
        "VALUES (1, 0, 0, 0, 0, 0)"
    )


async def _this_day_bill(conn, steward_id: int, day_id: str) -> dict[str, int]:
    row = await (await conn.execute(
        "SELECT assessed, paid FROM shore_upkeep_bills "
        "WHERE steward_id=? AND week_id=?",
        (steward_id, day_id),
    )).fetchone()
    if not row:
        return {"assessed": 0, "paid": 0, "exists": 0}
    return {"assessed": int(row[0] or 0), "paid": int(row[1] or 0), "exists": 1}


async def _bump_bill_paid(conn, steward_id: int, day_id: str, amount: int) -> None:
    if amount <= 0:
        return
    await conn.execute(
        """
        INSERT INTO shore_upkeep_bills (steward_id, week_id, assessed, paid)
        VALUES (?, ?, 0, ?)
        ON CONFLICT(steward_id, week_id) DO UPDATE SET paid = paid + excluded.paid
        """,
        (steward_id, day_id, amount),
    )


async def _deposit_fund(conn, amount: int) -> None:
    if amount <= 0:
        return
    await _ensure_fund(conn)
    await conn.execute(
        """
        UPDATE tide_fund
        SET tickets = tickets + ?, upkeep_total = COALESCE(upkeep_total, 0) + ?
        WHERE id=1
        """,
        (amount, amount),
    )


async def collect_steward(
    conn,
    steward_id: int,
    *,
    amount: int | None = None,
    floor: int | None = None,
    ts: int | None = None,
) -> dict[str, Any]:
    """从口袋划欠的维修费。floor=自动划的保底；手动交 floor=0。"""
    row = await (await conn.execute(
        "SELECT name, tickets, COALESCE(upkeep_arrears, 0) FROM stewards WHERE id=?",
        (steward_id,),
    )).fetchone()
    if not row:
        return {"taken": 0, "left": 0, "owed": 0}
    name, tickets, arrears = row[0], int(row[1] or 0), int(row[2] or 0)
    if arrears <= 0:
        return {"taken": 0, "left": tickets, "owed": 0, "name": name}
    cap_floor = COLLECT_FLOOR if floor is None else floor
    payable = max(0, tickets - cap_floor)
    want = arrears if amount is None else min(arrears, max(0, int(amount)))
    take = min(want, payable)
    if take <= 0:
        return {"taken": 0, "left": tickets, "owed": arrears, "name": name}
    left = tickets - take
    owed = arrears - take
    await conn.execute(
        "UPDATE stewards SET tickets=?, upkeep_arrears=? WHERE id=?",
        (left, owed, steward_id),
    )
    await _deposit_fund(conn, take)
    day_id = human_day_id(ts)
    await _bump_bill_paid(conn, steward_id, day_id, take)
    await db.add_chronicle(
        "upkeep",
        f"{name} 交{UPKEEP_NAME} {take} 票（欠余 {owed}，口袋 {left}）",
        steward_id,
        conn=conn,
    )
    return {"taken": take, "left": left, "owed": owed, "name": name}


async def _steward_row_as_dict(row) -> dict[str, Any]:
    return {
        "id": int(row[0]),
        "name": row[1],
        "tickets": int(row[2] or 0),
        "created_at": int(row[3] or 0),
        "upkeep_arrears": int(row[4] or 0),
        "parcel_count": int(row[5] or config.START_PARCELS),
        "orchard_count": int(row[6] or config.START_ORCHARDS),
        "greenhouse_count": int(row[7] or 0),
        "greenhouse": int(row[8] or 0),
        "barn_built": int(row[9] or 0),
        "eatery_open": int(row[10] or 0),
        "hut_built": int(row[11] or 0),
        "hut_level": int(row[12] or 0),
        "boat_key": row[13] or "",
    }


async def ensure_shore_upkeep(
    conn=None,
    *,
    ts: int | None = None,
) -> dict[str, Any] | None:
    """每个东八区日历日第一次有人动手时，按当时产业给在册的人开维修单并尽量划走。"""
    if conn is None:
        async with db.connect() as owned:
            result = await ensure_shore_upkeep(owned, ts=ts)
            if result:
                await owned.commit()
            return result
    moment = ts if ts is not None else db.now()
    day_id = human_day_id(moment)
    flag_key = day_flag_key(day_id)
    existing = await (await conn.execute(
        "SELECT 1 FROM world_flags WHERE flag_key=?", (flag_key,)
    )).fetchone()
    if existing:
        return None
    rows = await (await conn.execute(
        """
        SELECT id, name, tickets, created_at, COALESCE(upkeep_arrears, 0),
               COALESCE(parcel_count, 3), COALESCE(orchard_count, 3),
               COALESCE(greenhouse_count, 0), COALESCE(greenhouse, 0),
               COALESCE(barn_built, 0), COALESCE(eatery_open, 0),
               COALESCE(hut_built, 0), COALESCE(hut_level, 0),
               COALESCE(boat_key, '')
        FROM stewards WHERE enrolled=1
        ORDER BY id ASC
        """
    )).fetchall()
    assessed_n = 0
    assessed_tickets = 0
    collected = 0
    skipped_new = 0
    for row in rows:
        s = await _steward_row_as_dict(row)
        if _in_first_day(s["created_at"], moment):
            skipped_new += 1
            continue
        holdings = await holdings_for(conn, s)
        assessed, _items = due_from_holdings(holdings)
        existing_bill = await _this_day_bill(conn, s["id"], day_id)
        if not existing_bill["exists"]:
            await conn.execute(
                """
                INSERT INTO shore_upkeep_bills (steward_id, week_id, assessed, paid)
                VALUES (?, ?, ?, 0)
                """,
                (s["id"], day_id, assessed),
            )
            if assessed > 0:
                await conn.execute(
                    "UPDATE stewards SET upkeep_arrears = upkeep_arrears + ? WHERE id=?",
                    (assessed, s["id"]),
                )
                assessed_n += 1
                assessed_tickets += assessed
                await db.add_chronicle(
                    "upkeep",
                    f"{s['name']} 今日{UPKEEP_NAME}应 {assessed} 票",
                    s["id"],
                    conn=conn,
                )
        elif assessed > 0:
            assessed_n += 1
            assessed_tickets += int(existing_bill["assessed"] or assessed)
        paid = await collect_steward(conn, s["id"], ts=moment)
        collected += int(paid.get("taken") or 0)
    detail = (
        f"{day_id} {UPKEEP_NAME}：{assessed_n} 人应 {assessed_tickets} 票，"
        f"已划 {collected}"
        + (f"，新号免征 {skipped_new}" if skipped_new else "")
    )
    await conn.execute(
        "INSERT INTO world_flags (flag_key, applied_at, detail) VALUES (?,?,?)",
        (flag_key, moment, detail),
    )
    if assessed_n or collected:
        await db.add_chronicle("upkeep", f"{UPKEEP_NAME}今日开征：{detail}", None, conn=conn)
    return {
        "day": day_id,
        "week": day_id,
        "assessed_n": assessed_n,
        "assessed": assessed_tickets,
        "collected": collected,
        "skipped_new": skipped_new,
        "detail": detail,
    }


async def snapshot(conn, steward_id: int | None = None, ts: int | None = None) -> dict[str, Any]:
    day_id = human_day_id(ts)
    flag = await (await conn.execute(
        "SELECT 1 FROM world_flags WHERE flag_key=?", (day_flag_key(day_id),)
    )).fetchone()
    totals = await (await conn.execute(
        """
        SELECT COALESCE(SUM(assessed), 0), COALESCE(SUM(paid), 0)
        FROM shore_upkeep_bills WHERE week_id=?
        """,
        (day_id,),
    )).fetchone()
    mine = None
    if steward_id:
        row = await (await conn.execute(
            """
            SELECT id, name, tickets, created_at, COALESCE(upkeep_arrears, 0),
                   COALESCE(parcel_count, 3), COALESCE(orchard_count, 3),
                   COALESCE(greenhouse_count, 0), COALESCE(greenhouse, 0),
                   COALESCE(barn_built, 0), COALESCE(eatery_open, 0),
                   COALESCE(hut_built, 0), COALESCE(hut_level, 0),
                   COALESCE(boat_key, '')
            FROM stewards WHERE id=?
            """,
            (steward_id,),
        )).fetchone()
        if row:
            s = await _steward_row_as_dict(row)
            holdings = await holdings_for(conn, s)
            due_now, items = due_from_holdings(holdings)
            bill = await _this_day_bill(conn, steward_id, day_id)
            first_day = _in_first_day(s["created_at"], ts)
            mine = {
                "tickets": s["tickets"],
                "arrears": s["upkeep_arrears"],
                "due_now": due_now,
                "items": items,
                "holdings": holdings,
                "assessed": bill["assessed"],
                "paid": bill["paid"],
                "first_day": first_day,
                "first_week": first_day,
                "shop_paused": shop_paused(s),
            }
    return {
        "name": UPKEEP_NAME,
        "day_id": day_id,
        "week_id": day_id,
        "floor": COLLECT_FLOOR,
        "done": bool(flag),
        "next": next_levy_line(ts, done=bool(flag)),
        "assessed": int(totals[0] or 0) if totals else 0,
        "collected": int(totals[1] or 0) if totals else 0,
        "mine": mine,
        "rates": [
            {"label": "份地超出起步", "rate": PLOT_EXTRA, "unit": "块"},
            {"label": "果园超出起步", "rate": ORCHARD_EXTRA, "unit": "树位"},
            {"label": "温室", "rate": GREENHOUSE, "unit": "座"},
            {"label": "畜栏", "rate": BARN_BASE, "unit": "座"},
            {"label": "在栏牲口", "rate": BARN_STOCKED, "unit": "槽"},
            {"label": "开馆", "rate": EATERY, "unit": "馆"},
            {"label": "小屋 Lv2", "rate": HUT_BY_LEVEL[2], "unit": "座"},
            {"label": "渔排", "rate": PEN, "unit": "座"},
            {"label": "盐田超出第1口", "rate": SALT_EXTRA, "unit": "口"},
            {"label": "矿坑超出第1个", "rate": QUARRY_EXTRA, "unit": "坑"},
            {"label": "泊船舢板", "rate": BOAT_FEE["skiff"], "unit": "艘"},
        ],
    }


def _item_line(it: dict[str, Any]) -> str:
    return f"  {it['label']} ×{it['qty']} · {it['rate']}票 = {it['fee']}"


def _status_text(snap: dict[str, Any]) -> str:
    mine = snap.get("mine") or {}
    lines = [
        f"潮生会 · {UPKEEP_NAME}",
        "阿簿：产业越大越要修。起步那几块地免，扩出去的、开了馆的、盖了棚的才交。",
        "岸税看口袋；岸维看产业。岸维每天划，岸税周一划，入同一本潮汐基金。",
        "",
        f"今日 {snap.get('day_id') or snap['week_id']} · {snap['next']}",
        f"全岛今日应 {snap['assessed']} / 已入池 {snap['collected']}",
        "",
        "价目（每天）：",
        *rate_table_lines(),
        f"自动划不会收到 {COLLECT_FLOOR} 以下。今日新号免征到明天。",
    ]
    if mine:
        lines.append("")
        items = mine.get("items") or []
        if mine.get("first_day") or mine.get("first_week"):
            lines.append(
                f"你今日产业应约 {mine['due_now']} 票 · 今日新号，免征到明天"
            )
        elif mine["assessed"] or mine["paid"] or mine["arrears"] or mine["due_now"]:
            lines.append(
                f"你今日应 {mine['assessed']} · 已划 {mine['paid']}"
                + (f" · 欠 {mine['arrears']}" if mine["arrears"] else " · 已结清")
            )
        else:
            lines.append("你现在只有起步产业，不用交。扩地、开馆、盖棚之后才会记。")
        if items:
            lines.append("分项：")
            lines.extend(_item_line(it) for it in items)
        elif mine["due_now"] == 0:
            lines.append("分项：无（起步份地/果园、棚屋 Lv1、第一口盐田、第一个矿坑免）")
        if mine["arrears"]:
            extra = "；你的小馆已暂停堂食" if mine.get("shop_paused") else ""
            lines.append(
                f"欠维修费时不能{EXPAND_LOCK}{extra}。交：visit_ops 潮生会 维 交"
            )
    lines.extend([
        "",
        "交：visit_ops 潮生会 维 交（可 维 交 50 交一部分）",
        "不是岸税：口袋现票走 潮生会 税。不是吉祥物：hut_ops mascot upkeep。",
        "不是田间意外：plot_ops repair 编号。没有 upkeep_ops。周潮天灾不是维修费。",
    ])
    return "\n".join(lines)


async def upkeep_status(key_id: int) -> str:
    from .game import require_steward

    s = await require_steward(key_id, exempt_duty=True)
    async with db.connect() as conn:
        conn.row_factory = None
        await ensure_shore_upkeep(conn)
        await collect_steward(conn, s["id"])
        snap = await snapshot(conn, s["id"])
        await conn.commit()
    return _status_text(snap)


async def upkeep_pay(key_id: int, amount: int | None = None) -> str:
    from .game import require_steward

    s = await require_steward(key_id, exempt_duty=True)
    if amount is not None and amount < 1:
        raise ValueError("票数至少 1。用法：visit_ops 潮生会 维 交 或 维 交 50")
    async with db.connect() as conn:
        conn.row_factory = None
        await ensure_shore_upkeep(conn)
        await collect_steward(conn, s["id"])
        result = await collect_steward(conn, s["id"], amount=amount, floor=0)
        from . import chaoshen as chaoshen_mod
        paid_out = await chaoshen_mod.ensure_fund_payout(conn)
        await conn.commit()
    taken = int(result.get("taken") or 0)
    owed = int(result.get("owed") or 0)
    left = int(result.get("left") or 0)
    extra = ""
    if paid_out:
        extra = f"\n今天是发放日，刚入簿的维修费已按岛均补出去：{paid_out['detail']}"
    if taken <= 0:
        if owed <= 0:
            return (
                f"阿簿翻了翻簿：你没有欠{UPKEEP_NAME}。"
                f"口袋 {left} 票。看档：visit_ops 潮生会 维"
            )
        return (
            f"口袋 {left} 票，交不出欠的 {owed}。"
            f"先去挣钱再 潮生会 维 交。欠维修费时不能{EXPAND_LOCK}。"
        )
    msg = (
        f"阿簿把 {taken} 票划进{UPKEEP_NAME}簿（入口袋 {left}"
        + (f"，仍欠 {owed}" if owed else "，本笔结清")
        + "）。"
    )
    if owed:
        msg += f"\n还欠 {owed}。欠维修费时不能{EXPAND_LOCK}；开着的小馆仍暂停堂食。"
    else:
        msg += f"\n可以买地了，小馆也能再开堂。费进潮汐基金。"
    return msg + extra


async def upkeep_command(key_id: int, command: str = "") -> str:
    raw = (command or "").strip()
    parts = raw.split()
    verb = parts[0] if parts else "维"
    verb_l = verb.lower()
    rest = parts[1:]

    if verb_l in ("help", "?", "帮助"):
        return UPKEEP_HELP
    if verb in ("交", "付", "还") or verb_l in ("pay", "payupkeep"):
        amt = None
        if rest:
            from .game import _parse_int
            amt = _parse_int(rest[0], "票数")
        return await upkeep_pay(key_id, amt)
    if verb in ("维", "岸维", "维修", "维修费") or verb_l in (
        "upkeep", "maintenance", "repairfee", "levyupkeep"
    ):
        if rest and rest[0] in ("交", "付", "还", "pay"):
            amt = None
            if len(rest) >= 2:
                from .game import _parse_int
                amt = _parse_int(rest[1], "票数")
            return await upkeep_pay(key_id, amt)
        if rest and rest[0].lower() in ("help", "?", "帮助"):
            return UPKEEP_HELP
        return await upkeep_status(key_id)
    if not raw:
        return await upkeep_status(key_id)
    raise ValueError(
        f"未知{UPKEEP_NAME}指令。看：visit_ops 潮生会 维 · 交：潮生会 维 交。"
        f"没有 upkeep_ops。吉祥物喂养走 hut_ops mascot upkeep。"
    )


async def sheet_line(s: dict[str, Any]) -> str | None:
    arrears = int(s.get("upkeep_arrears") or 0)
    if arrears > 0:
        shop = "；小馆已暂停堂食" if shop_paused(s) else ""
        return (
            f"{UPKEEP_NAME}：欠 {arrears} → visit_ops 潮生会 维 交"
            f"（欠维修费时不能{EXPAND_LOCK}{shop}）"
        )
    return None


def tax_week_overlap_note() -> str:
    """给岸税文案用的一句对照。"""
    return f"{UPKEEP_NAME}按产业另算，每天划：visit_ops 潮生会 维"