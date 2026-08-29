"""岸税 — 口袋现票超额累进。潮生会征收，税入潮汐基金。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from . import db
from .disaster import human_week_id

TAX_NAME = "岸税"
TAX_FREE = 800
# 自动划税不低于这个数，避免把人划进包宿线
TAX_COLLECT_FLOOR = 200

# (档顶含，本档税率，档名)。从 TAX_FREE 往上超额累进。
# 低档不动，护新号；阔手以上加码，免得口袋差越滚越大。
BRACKETS: tuple[tuple[int | None, float, str], ...] = (
    (2500, 0.04, "温水"),
    (6000, 0.08, "殷实"),
    (15000, 0.14, "阔手"),
    (30000, 0.20, "豪客"),
    (80000, 0.26, "潮主"),
    (None, 0.36, "潮宗"),
)

# 潮差附加：按本周岛均口袋。第二十名刚到岛均的人加不到。
# 岛均 4000 时：2 万以下不加；2–6 万再加 8%；6 万以上再加 16%。
GAP_SOFT_MULT = 5
GAP_HARD_MULT = 15
GAP_SOFT_RATE = 0.08
GAP_HARD_RATE = 0.16

# 潮锈：闲票（口袋超过岛均的部分）本周要花掉这一成半，缺口整笔进基金。
# 岛均 4000 时，第二十名闲票为 0；榜首 20 万不花则锈 29400。
RUST_RATE = 0.15
RUST_NAME = "潮锈"

FLAG_PREFIX = "shore_tax:"
_CST = timezone(timedelta(hours=8))
_WEEKDAY_CN = "一二三四五六日"

EXPAND_LOCK = "买地/买棚/买园/升屋/买船/开坑/升镐"

TAX_HELP = f"""visit_ops 潮生会 税（整句写进 command）：
  税 / 岸税 — 看档：免税额、累进档表、你的档、本周应/已划/欠
  税 交 — 把欠税（含本周未划完的）能交的交清。也可 税 交 50 交一部分
  没有 tax_ops，没有 逃税 / 免税申请。补贴仍不用领。
{TAX_NAME}按口袋现票超额累进，只算口袋，不算行囊/井下存款。未过 {TAX_FREE} 免征。
低档（温水/殷实）不动；阔手 14%、豪客 20%、潮主 26%、潮宗 36%。高档加码是为了把滚出来的票划回潮汐基金。
潮差附加：口袋超过本周岛均 {GAP_SOFT_MULT} 倍的部分再加 {int(GAP_SOFT_RATE * 100)}%，超过 {GAP_HARD_MULT} 倍再加 {int(GAP_HARD_RATE * 100)}%。岛均四千时，两万以下不加；刚到岛均的人（第二十名那种）加不到。
{RUST_NAME}：口袋超过岛均的闲票，本周生活花销要够闲票的 {int(RUST_RATE * 100)}%。没花够的缺口整笔进基金。酒吧、小馆、衣泊坊、诊所、星光、小屋日子、婚宴、三金、基金捐算花；买地、买园、买棚、送礼不算。刚到岛均的人闲票为 0。周一按上周花销划。
东八区每周一换班自动划入潮汐基金（本周新号免征到下周）。自动划不会收到 {TAX_COLLECT_FLOOR} 以下；欠税时不能{EXPAND_LOCK}。
例子：潮生会 税 · 潮生会 税 交 · 潮生会 税 交 50
容易搞混：税=强制岸税（富人按档交）。维=产业维修费（visit_ops 潮生会 维，每天划）。基金 捐 50=自愿捐票（须高于岛均），也算生活花销、能抵锈。周潮天灾=只冲 3 万以上，不是税。"""


def _cst_dt(ts: int | None = None) -> datetime:
    return datetime.fromtimestamp(ts if ts is not None else db.now(), _CST)


def week_flag_key(week_id: str | None = None, ts: int | None = None) -> str:
    return f"{FLAG_PREFIX}{week_id or human_week_id(ts)}"


def band_name(tickets: int) -> str:
    if tickets <= TAX_FREE:
        return "免征"
    lower = TAX_FREE
    for upper, _rate, name in BRACKETS:
        if upper is None or tickets <= upper:
            return name
        lower = upper
    return BRACKETS[-1][2]


def gap_thresholds(avg: int) -> tuple[int, int]:
    avg = max(0, int(avg or 0))
    if avg < 1:
        return (0, 0)
    soft = max(TAX_FREE, avg * GAP_SOFT_MULT)
    hard = max(soft, avg * GAP_HARD_MULT)
    return soft, hard


def gap_surcharge(tickets: int, avg: int | None) -> int:
    """离岛均太远的附加。avg 缺省或口袋未过免税额则为 0。"""
    if not avg or avg < 1 or tickets <= TAX_FREE:
        return 0
    soft, hard = gap_thresholds(int(avg))
    extra = 0
    if tickets > soft:
        extra += int((min(tickets, hard) - soft) * GAP_SOFT_RATE)
    if tickets > hard:
        extra += int((tickets - hard) * GAP_HARD_RATE)
    return extra


def rust_idle(tickets: int, avg: int | None) -> int:
    """口袋超过岛均（且过了免税额）的闲票。刚到岛均的人为 0。"""
    if not avg or avg < 1 or tickets <= TAX_FREE:
        return 0
    floor = max(TAX_FREE, int(avg))
    return max(0, int(tickets) - floor)


def rust_need(tickets: int, avg: int | None) -> int:
    return int(rust_idle(tickets, avg) * RUST_RATE)


def rust_surcharge(tickets: int, avg: int | None, spent: int | None) -> int:
    """没花够的闲票缺口。spent 缺省不加锈（只算档表+潮差）。"""
    if spent is None:
        return 0
    need = rust_need(tickets, avg)
    if need <= 0:
        return 0
    return max(0, need - max(0, int(spent)))


def week_monday_ts(ts: int | None = None) -> int:
    dt = _cst_dt(ts).replace(hour=0, minute=0, second=0, microsecond=0)
    monday = dt - timedelta(days=dt.weekday())
    return int(monday.timestamp())


def rust_window(ts: int | None = None, *, previous: bool = False) -> tuple[int, int]:
    monday = week_monday_ts(ts)
    if previous:
        start = int((datetime.fromtimestamp(monday, _CST) - timedelta(days=7)).timestamp())
        return start, monday
    now = ts if ts is not None else db.now()
    return monday, max(int(now), monday)


def rust_use_previous(ts: int | None, done: bool) -> bool:
    """周一尚未入簿时，预览和划税都看上周花销。"""
    return _cst_dt(ts).weekday() == 0 and not done


async def record_life_spend(
    conn,
    steward_id: int,
    amount: int,
    kind: str,
    ts: int | None = None,
) -> None:
    """记下生活花销。买地/买园/送礼不要走这里。amount 可为负（退席退票）。"""
    if not amount:
        return
    try:
        await conn.execute(
            """
            INSERT INTO shore_life_spend (steward_id, amount, kind, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (int(steward_id), int(amount), (kind or "")[:32], ts if ts is not None else db.now()),
        )
    except Exception:
        return


async def life_spent(conn, steward_id: int, start_ts: int, end_ts: int) -> int:
    """酒吧/小馆/星光旧账 + 新记的生活花销。自己请自己吃饭不算。"""
    sid = int(steward_id)
    total = 0
    queries = (
        (
            "SELECT COALESCE(SUM(cost), 0) FROM bar_drink_orders "
            "WHERE patron_id=? AND created_at>=? AND created_at<?",
            (sid, start_ts, end_ts),
        ),
        (
            "SELECT COALESCE(SUM(cost), 0) FROM bar_orders "
            "WHERE patron_id=? AND created_at>=? AND created_at<? "
            "AND (host_id IS NULL OR host_id!=?)",
            (sid, start_ts, end_ts, sid),
        ),
        (
            "SELECT COALESCE(SUM(amount), 0) FROM bar_tips "
            "WHERE from_id=? AND created_at>=? AND created_at<? AND to_id!=from_id",
            (sid, start_ts, end_ts),
        ),
        (
            "SELECT COALESCE(SUM(price), 0) FROM eatery_orders "
            "WHERE patron_id=? AND created_at>=? AND created_at<? AND shop_id!=patron_id",
            (sid, start_ts, end_ts),
        ),
        (
            "SELECT COALESCE(SUM(amount), 0) FROM star_tips "
            "WHERE steward_id=? AND created_at>=? AND created_at<?",
            (sid, start_ts, end_ts),
        ),
        (
            "SELECT COALESCE(SUM(amount), 0) FROM shore_life_spend "
            "WHERE steward_id=? AND created_at>=? AND created_at<?",
            (sid, start_ts, end_ts),
        ),
    )
    for sql, args in queries:
        try:
            row = await (await conn.execute(sql, args)).fetchone()
        except Exception:
            continue
        total += int((row[0] if row else 0) or 0)
    return max(0, total)


def bracket_due(tickets: int) -> int:
    """只算档表，不含潮差。"""
    if tickets <= TAX_FREE:
        return 0
    due = 0
    lower = TAX_FREE
    for upper, rate, _name in BRACKETS:
        cap = tickets if upper is None else min(tickets, upper)
        if cap > lower:
            due += int((cap - lower) * rate)
        if upper is None or tickets <= upper:
            break
        lower = upper
    return due


def tax_due(
    tickets: int,
    avg: int | None = None,
    spent: int | None = None,
) -> int:
    """口袋现票的本周应税。超额累进 + 潮差 + 潮锈；未过免税额为 0。spent 缺省不加锈。"""
    return (
        bracket_due(tickets)
        + gap_surcharge(tickets, avg)
        + rust_surcharge(tickets, avg, spent)
    )


def gap_lines(avg: int) -> list[str]:
    avg = max(0, int(avg or 0))
    if avg < 1:
        return [
            f"潮差附加：岛均还没算出来。超过岛均 {GAP_SOFT_MULT} 倍的部分再加 "
            f"{int(GAP_SOFT_RATE * 100)}%，超过 {GAP_HARD_MULT} 倍再加 "
            f"{int(GAP_HARD_RATE * 100)}%。",
            f"{RUST_NAME}：闲票本周要花掉 {int(RUST_RATE * 100)}%。买地买园不算花。",
        ]
    soft, hard = gap_thresholds(avg)
    return [
        f"潮差附加（本周岛均 {avg}）：超过 {soft}（{GAP_SOFT_MULT} 倍）再加 "
        f"{int(GAP_SOFT_RATE * 100)}%，超过 {hard}（{GAP_HARD_MULT} 倍）再加 "
        f"{int(GAP_HARD_RATE * 100)}%。刚到岛均的人加不到。",
        f"{RUST_NAME}：闲票（超过岛均的部分）本周要花掉 {int(RUST_RATE * 100)}%，"
        "没花够的缺口整笔进基金。酒吧/小馆/衣泊坊/诊所/星光/小屋日子/婚宴/三金/基金捐算花；"
        "买地买园不算，买棚送礼也不算。刚到岛均的人闲票为 0。",
    ]


async def island_pocket_avg(conn) -> int:
    row = await (await conn.execute(
        "SELECT COALESCE(AVG(tickets), 0) FROM stewards WHERE enrolled=1"
    )).fetchone()
    return int(round(float(row[0] or 0)))


def bracket_lines() -> list[str]:
    lines = [f"  ≤{TAX_FREE}        免征"]
    lower = TAX_FREE
    for upper, rate, name in BRACKETS:
        pct = int(round(rate * 100))
        if upper is None:
            lines.append(f"  {lower}+         {name} {pct}%")
        else:
            lines.append(f"  {lower}–{upper}    {name} {pct}%")
            lower = upper
    return lines


def next_levy_line(ts: int | None = None, *, done: bool = False) -> str:
    dt = _cst_dt(ts)
    if done:
        return f"本周（{human_week_id(ts)}）已入簿"
    if dt.weekday() == 0:
        return "今天（东八区周一）会自动划税"
    for i in range(1, 8):
        nxt = dt + timedelta(days=i)
        if nxt.weekday() == 0:
            return (
                f"下一次划税：周一 {nxt.strftime('%m-%d')}"
                "（东八区每周一换班）"
            )
    return "东八区每周一换班自动划税"


def assert_clear(steward: dict[str, Any]) -> None:
    owed = int(steward.get("tax_arrears") or 0)
    if owed > 0:
        raise ValueError(
            f"欠{TAX_NAME} {owed} 票。先 visit_ops 潮生会 税 交。"
            f"欠税时不能{EXPAND_LOCK}。"
        )
    from . import upkeep as upkeep_mod
    upkeep_mod.assert_upkeep_clear(steward)


def _in_first_week(created_at: int, ts: int | None = None) -> bool:
    return human_week_id(int(created_at or 0)) == human_week_id(ts)


async def _ensure_fund(conn) -> None:
    await conn.execute(
        "INSERT OR IGNORE INTO tide_fund (id, tickets, donated_total, paid_total, taxed_total) "
        "VALUES (1, 0, 0, 0, 0)"
    )


async def _this_week_bill(conn, steward_id: int, week_id: str) -> dict[str, int]:
    row = await (await conn.execute(
        "SELECT assessed, paid, tickets_at FROM shore_tax_bills "
        "WHERE steward_id=? AND week_id=?",
        (steward_id, week_id),
    )).fetchone()
    if not row:
        return {"assessed": 0, "paid": 0, "tickets_at": 0, "exists": 0}
    return {
        "assessed": int(row[0] or 0),
        "paid": int(row[1] or 0),
        "tickets_at": int(row[2] or 0),
        "exists": 1,
    }


async def _bump_bill_paid(conn, steward_id: int, week_id: str, amount: int) -> None:
    if amount <= 0:
        return
    await conn.execute(
        """
        INSERT INTO shore_tax_bills (steward_id, week_id, assessed, paid, tickets_at)
        VALUES (?, ?, 0, ?, 0)
        ON CONFLICT(steward_id, week_id) DO UPDATE SET paid = paid + excluded.paid
        """,
        (steward_id, week_id, amount),
    )


async def _deposit_fund(conn, amount: int) -> None:
    if amount <= 0:
        return
    await _ensure_fund(conn)
    await conn.execute(
        """
        UPDATE tide_fund
        SET tickets = tickets + ?, taxed_total = taxed_total + ?
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
    """从口袋划欠税。floor=自动划的保底；手动交税 floor=0。"""
    row = await (await conn.execute(
        "SELECT name, tickets, tax_arrears FROM stewards WHERE id=?",
        (steward_id,),
    )).fetchone()
    if not row:
        return {"taken": 0, "left": 0, "owed": 0}
    name, tickets, arrears = row[0], int(row[1] or 0), int(row[2] or 0)
    if arrears <= 0:
        return {"taken": 0, "left": tickets, "owed": 0, "name": name}
    cap_floor = TAX_COLLECT_FLOOR if floor is None else floor
    payable = max(0, tickets - cap_floor)
    want = arrears if amount is None else min(arrears, max(0, int(amount)))
    take = min(want, payable)
    if take <= 0:
        return {"taken": 0, "left": tickets, "owed": arrears, "name": name}
    left = tickets - take
    owed = arrears - take
    await conn.execute(
        "UPDATE stewards SET tickets=?, tax_arrears=? WHERE id=?",
        (left, owed, steward_id),
    )
    await _deposit_fund(conn, take)
    week_id = human_week_id(ts)
    await _bump_bill_paid(conn, steward_id, week_id, take)
    await db.add_chronicle(
        "tax",
        f"{name} 交{TAX_NAME} {take} 票（欠余 {owed}，口袋 {left}）",
        steward_id,
        conn=conn,
    )
    return {"taken": take, "left": left, "owed": owed, "name": name}


async def ensure_shore_tax(
    conn=None,
    *,
    ts: int | None = None,
) -> dict[str, Any] | None:
    """每个东八区 ISO 周第一次有人动手时，按当时口袋给在册的人开税单并尽量划走。"""
    if conn is None:
        async with db.connect() as owned:
            result = await ensure_shore_tax(owned, ts=ts)
            if result:
                await owned.commit()
            return result
    moment = ts if ts is not None else db.now()
    week_id = human_week_id(moment)
    flag_key = week_flag_key(week_id)
    existing = await (await conn.execute(
        "SELECT 1 FROM world_flags WHERE flag_key=?", (flag_key,)
    )).fetchone()
    if existing:
        return None
    rows = await (await conn.execute(
        """
        SELECT id, name, tickets, created_at, COALESCE(tax_arrears, 0)
        FROM stewards WHERE enrolled=1
        ORDER BY id ASC
        """
    )).fetchall()
    pocket = [int(row[2] or 0) for row in rows]
    avg = int(round(sum(pocket) / len(pocket))) if pocket else 0
    rust_start, rust_end = rust_window(moment, previous=True)
    assessed_n = 0
    assessed_tickets = 0
    collected = 0
    skipped_new = 0
    for row in rows:
        sid = int(row[0])
        name = row[1]
        tickets = int(row[2] or 0)
        created_at = int(row[3] or 0)
        if _in_first_week(created_at, moment):
            skipped_new += 1
            continue
        spent = await life_spent(conn, sid, rust_start, rust_end)
        extra = gap_surcharge(tickets, avg)
        rust = rust_surcharge(tickets, avg, spent)
        assessed = tax_due(tickets, avg, spent)
        existing_bill = await _this_week_bill(conn, sid, week_id)
        if not existing_bill["exists"]:
            await conn.execute(
                """
                INSERT INTO shore_tax_bills (steward_id, week_id, assessed, paid, tickets_at)
                VALUES (?, ?, ?, 0, ?)
                """,
                (sid, week_id, assessed, tickets),
            )
            if assessed > 0:
                await conn.execute(
                    "UPDATE stewards SET tax_arrears = tax_arrears + ? WHERE id=?",
                    (assessed, sid),
                )
                assessed_n += 1
                assessed_tickets += assessed
                detail = (
                    f"{name} 本周{TAX_NAME}应 {assessed} 票（{band_name(tickets)}档，口袋 {tickets}"
                )
                if extra:
                    detail += f"，潮差 +{extra}"
                if rust:
                    detail += f"，{RUST_NAME} +{rust}（上周花 {spent}）"
                await db.add_chronicle("tax", detail + "）", sid, conn=conn)
        elif assessed > 0:
            assessed_n += 1
            assessed_tickets += int(existing_bill["assessed"] or assessed)
        paid = await collect_steward(conn, sid, ts=moment)
        collected += int(paid.get("taken") or 0)
    detail = (
        f"{week_id} {TAX_NAME}：{assessed_n} 人应 {assessed_tickets} 票，"
        f"已划 {collected}，岛均 {avg}"
        + (f"，新号免征 {skipped_new}" if skipped_new else "")
    )
    await conn.execute(
        "INSERT INTO world_flags (flag_key, applied_at, detail) VALUES (?,?,?)",
        (flag_key, moment, detail),
    )
    if assessed_n or collected:
        await db.add_chronicle("tax", f"{TAX_NAME}本周开征：{detail}", None, conn=conn)
    return {
        "week": week_id,
        "assessed_n": assessed_n,
        "assessed": assessed_tickets,
        "collected": collected,
        "skipped_new": skipped_new,
        "detail": detail,
    }


async def snapshot(conn, steward_id: int | None = None, ts: int | None = None) -> dict[str, Any]:
    week_id = human_week_id(ts)
    avg = await island_pocket_avg(conn)
    flag = await (await conn.execute(
        "SELECT 1 FROM world_flags WHERE flag_key=?", (week_flag_key(week_id),)
    )).fetchone()
    totals = await (await conn.execute(
        """
        SELECT COALESCE(SUM(assessed), 0), COALESCE(SUM(paid), 0)
        FROM shore_tax_bills WHERE week_id=?
        """,
        (week_id,),
    )).fetchone()
    mine = None
    if steward_id:
        row = await (await conn.execute(
            "SELECT tickets, COALESCE(tax_arrears, 0), created_at FROM stewards WHERE id=?",
            (steward_id,),
        )).fetchone()
        tickets = int(row[0] or 0) if row else 0
        arrears = int(row[1] or 0) if row else 0
        created_at = int(row[2] or 0) if row else 0
        bill = await _this_week_bill(conn, steward_id, week_id)
        start, end = rust_window(ts, previous=rust_use_previous(ts, bool(flag)))
        spent = await life_spent(conn, steward_id, start, end)
        extra = gap_surcharge(tickets, avg)
        rust = rust_surcharge(tickets, avg, spent)
        idle = rust_idle(tickets, avg)
        need = rust_need(tickets, avg)
        mine = {
            "tickets": tickets,
            "arrears": arrears,
            "due_now": tax_due(tickets, avg, spent),
            "gap": extra,
            "rust": rust,
            "spent": spent,
            "idle": idle,
            "rust_need": need,
            "band": band_name(tickets),
            "assessed": bill["assessed"],
            "paid": bill["paid"],
            "first_week": _in_first_week(created_at, ts),
        }
    return {
        "name": TAX_NAME,
        "week_id": week_id,
        "free": TAX_FREE,
        "floor": TAX_COLLECT_FLOOR,
        "avg": avg,
        "gap_soft": gap_thresholds(avg)[0],
        "gap_hard": gap_thresholds(avg)[1],
        "rust_rate": int(RUST_RATE * 100),
        "done": bool(flag),
        "next": next_levy_line(ts, done=bool(flag)),
        "assessed": int(totals[0] or 0) if totals else 0,
        "collected": int(totals[1] or 0) if totals else 0,
        "mine": mine,
        "brackets": [
            {
                "lo": TAX_FREE if i == 0 else int(BRACKETS[i - 1][0] or 0),
                "hi": upper,
                "rate": int(round(rate * 100)),
                "name": name,
            }
            for i, (upper, rate, name) in enumerate(BRACKETS)
        ],
    }


def _status_text(snap: dict[str, Any]) -> str:
    mine = snap.get("mine") or {}
    lines = [
        f"潮生会 · {TAX_NAME}",
        "阿簿：口袋过了免税额就要按档交。超额累进，只算口袋现票。高档加码，离岛均太远再加潮差。只攒不花再加潮锈。税进潮汐基金。",
        "",
        f"本周 {snap['week_id']} · {snap['next']}",
        f"全岛本周应 {snap['assessed']} / 已入池 {snap['collected']}",
        "",
        f"免税额 {TAX_FREE} 票。档表（超额累进）：",
        *bracket_lines(),
        *gap_lines(int(snap.get("avg") or 0)),
        f"自动划不会收到 {TAX_COLLECT_FLOOR} 以下。本周新号免征到下周。",
    ]
    if mine:
        lines.append("")
        if mine["first_week"]:
            lines.append(
                f"你的口袋：{mine['tickets']} 票 · {mine['band']}档"
                f"（周应约 {mine['due_now']}）· 本周新号，免征到下周"
            )
        elif mine["assessed"] or mine["paid"] or mine["arrears"] or mine["due_now"]:
            gap = int(mine.get("gap") or 0)
            rust = int(mine.get("rust") or 0)
            spent = int(mine.get("spent") or 0)
            need = int(mine.get("rust_need") or 0)
            lines.append(
                f"你的口袋：{mine['tickets']} 票 · {mine['band']}档"
                f" · 本周应 {mine['assessed']} · 已划 {mine['paid']}"
                + (f" · 潮差 +{gap}" if gap else "")
                + (f" · {RUST_NAME} +{rust}" if rust else "")
                + (f" · 欠 {mine['arrears']}" if mine["arrears"] else " · 已结清")
            )
            if need or spent:
                short = max(0, need - spent)
                lines.append(
                    f"生活花销 {spent} / 免锈要 {need}"
                    + (f" · 还差 {short}" if short else " · 本周够了")
                    + "（买地买园不算）"
                )
        else:
            lines.append(
                f"你的口袋：{mine['tickets']} 票 · 未过免税额 {TAX_FREE}，不用交"
            )
        if mine["arrears"]:
            lines.append(
                f"欠税时不能{EXPAND_LOCK}。交：visit_ops 潮生会 税 交"
            )
    lines.extend([
        "",
        "交：visit_ops 潮生会 税 交（可 税 交 50 交一部分）",
        "不是自愿捐：有余捐票走 潮生会 基金 捐 50。产业维修走 潮生会 维。周潮天灾不是税。",
    ])
    return "\n".join(lines)


async def tax_status(key_id: int) -> str:
    from .game import require_steward

    s = await require_steward(key_id, exempt_duty=True)
    async with db.connect() as conn:
        conn.row_factory = None
        await ensure_shore_tax(conn)
        await collect_steward(conn, s["id"])
        snap = await snapshot(conn, s["id"])
        await conn.commit()
    return _status_text(snap)


async def tax_pay(key_id: int, amount: int | None = None) -> str:
    from .game import require_steward

    s = await require_steward(key_id, exempt_duty=True)
    if amount is not None and amount < 1:
        raise ValueError("票数至少 1。用法：visit_ops 潮生会 税 交 或 税 交 50")
    async with db.connect() as conn:
        conn.row_factory = None
        await ensure_shore_tax(conn)
        await collect_steward(conn, s["id"])
        result = await collect_steward(
            conn, s["id"], amount=amount, floor=0
        )
        from . import chaoshen as chaoshen_mod
        paid_out = await chaoshen_mod.ensure_fund_payout(conn)
        await conn.commit()
    taken = int(result.get("taken") or 0)
    owed = int(result.get("owed") or 0)
    left = int(result.get("left") or 0)
    extra = ""
    if paid_out:
        extra = f"\n今天是发放日，刚入簿的税已按岛均补出去：{paid_out['detail']}"
    if taken <= 0:
        if owed <= 0:
            return (
                f"阿簿翻了翻簿：你没有欠{TAX_NAME}。"
                f"口袋 {left} 票。看档：visit_ops 潮生会 税"
            )
        return (
            f"口袋 {left} 票，交不出欠的 {owed}。"
            f"先去挣钱再 潮生会 税 交。欠税时不能{EXPAND_LOCK}。"
        )
    msg = (
        f"阿簿把 {taken} 票划进{TAX_NAME}簿（入口袋 {left}"
        + (f"，仍欠 {owed}" if owed else "，本笔结清")
        + "）。"
    )
    if owed:
        msg += f"\n还欠 {owed}。欠税时不能{EXPAND_LOCK}。"
    else:
        msg += f"\n可以买地了。税进潮汐基金，补贴东八区周二四六自动发。"
    return msg + extra


async def tax_command(key_id: int, command: str = "") -> str:
    raw = (command or "").strip()
    parts = raw.split()
    verb = parts[0] if parts else "税"
    verb_l = verb.lower()
    rest = parts[1:]

    if verb_l in ("help", "?", "帮助"):
        return TAX_HELP
    if verb in ("交", "付", "还") or verb_l in ("pay", "paytax"):
        amt = None
        if rest:
            from .game import _parse_int
            amt = _parse_int(rest[0], "票数")
        return await tax_pay(key_id, amt)
    if verb in ("税", "岸税", "交税") or verb_l in ("tax", "levy", "shoretax"):
        if rest and rest[0] in ("交", "付", "还", "pay"):
            amt = None
            if len(rest) >= 2:
                from .game import _parse_int
                amt = _parse_int(rest[1], "票数")
            return await tax_pay(key_id, amt)
        if rest and (rest[0].isdigit() or rest[0].lower() in ("help", "?", "帮助")):
            if rest[0].lower() in ("help", "?", "帮助"):
                return TAX_HELP
        return await tax_status(key_id)
    if not raw:
        return await tax_status(key_id)
    raise ValueError(
        f"未知{TAX_NAME}指令。看：visit_ops 潮生会 税 · 交：潮生会 税 交。"
        f"没有 tax_ops。"
    )


async def sheet_line(s: dict[str, Any]) -> str | None:
    arrears = int(s.get("tax_arrears") or 0)
    tickets = int(s.get("tickets") or 0)
    if arrears > 0:
        return (
            f"{TAX_NAME}：欠 {arrears} → visit_ops 潮生会 税 交"
            f"（欠税时不能{EXPAND_LOCK}）"
        )
    async with db.connect() as conn:
        conn.row_factory = None
        avg = await island_pocket_avg(conn)
        flag = await (await conn.execute(
            "SELECT 1 FROM world_flags WHERE flag_key=?", (week_flag_key(),)
        )).fetchone()
        start, end = rust_window(previous=rust_use_previous(None, bool(flag)))
        spent = await life_spent(conn, int(s["id"]), start, end)
    extra = gap_surcharge(tickets, avg)
    rust = rust_surcharge(tickets, avg, spent)
    due = tax_due(tickets, avg, spent)
    if due > 0:
        extras = []
        if extra:
            extras.append(f"潮差 +{extra}")
        if rust:
            extras.append(f"{RUST_NAME} +{rust}")
        return (
            f"{TAX_NAME}：{band_name(tickets)}档 · 周应约 {due}"
            + (f"（含{'，'.join(extras)}）" if extras else "")
            + f"（周一换班自动划）→ visit_ops 潮生会 税"
        )
    return None
