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
BRACKETS: tuple[tuple[int | None, float, str], ...] = (
    (2500, 0.04, "温水"),
    (6000, 0.08, "殷实"),
    (15000, 0.12, "阔手"),
    (30000, 0.16, "豪客"),
    (None, 0.18, "潮主"),
)

FLAG_PREFIX = "shore_tax:"
_CST = timezone(timedelta(hours=8))
_WEEKDAY_CN = "一二三四五六日"

EXPAND_LOCK = "买地/买棚/买园/升屋/买船/开坑/升镐"

TAX_HELP = f"""visit_ops 潮生会 税（整句写进 command）：
  税 / 岸税 — 看档：免税额、累进档表、你的档、本周应/已划/欠
  税 交 — 把欠税（含本周未划完的）能交的交清。也可 税 交 50 交一部分
  没有 tax_ops，没有 逃税 / 免税申请。补贴仍不用领。
{TAX_NAME}按口袋现票超额累进，只算口袋，不算行囊/井下存款。未过 {TAX_FREE} 免征。
东八区每周一换班自动划入潮汐基金（本周新号免征到下周）。自动划不会收到 {TAX_COLLECT_FLOOR} 以下；欠税时不能{EXPAND_LOCK}。
例子：潮生会 税 · 潮生会 税 交 · 潮生会 税 交 50
容易搞混：税=强制岸税（富人按档交）。维=产业维修费（visit_ops 潮生会 维）。基金 捐 50=自愿捐票（须高于岛均）。周潮天灾=只冲 3 万以上，不是税。"""


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


def tax_due(tickets: int) -> int:
    """口袋现票的本周应税。超额累进；未过免税额为 0。"""
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
        assessed = tax_due(tickets)
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
                await db.add_chronicle(
                    "tax",
                    f"{name} 本周{TAX_NAME}应 {assessed} 票（{band_name(tickets)}档，口袋 {tickets}）",
                    sid,
                    conn=conn,
                )
        elif assessed > 0:
            assessed_n += 1
            assessed_tickets += int(existing_bill["assessed"] or assessed)
        paid = await collect_steward(conn, sid, ts=moment)
        collected += int(paid.get("taken") or 0)
    detail = (
        f"{week_id} {TAX_NAME}：{assessed_n} 人应 {assessed_tickets} 票，"
        f"已划 {collected}"
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
        mine = {
            "tickets": tickets,
            "arrears": arrears,
            "due_now": tax_due(tickets),
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
        "阿簿：口袋过了免税额就要按档交。超额累进，只算口袋现票。税进潮汐基金。",
        "",
        f"本周 {snap['week_id']} · {snap['next']}",
        f"全岛本周应 {snap['assessed']} / 已入池 {snap['collected']}",
        "",
        f"免税额 {TAX_FREE} 票。档表（超额累进）：",
        *bracket_lines(),
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
            lines.append(
                f"你的口袋：{mine['tickets']} 票 · {mine['band']}档"
                f" · 本周应 {mine['assessed']} · 已划 {mine['paid']}"
                + (f" · 欠 {mine['arrears']}" if mine["arrears"] else " · 已结清")
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
    due = tax_due(tickets)
    if due > 0:
        return (
            f"{TAX_NAME}：{band_name(tickets)}档 · 周应约 {due}"
            f"（周一换班自动划）→ visit_ops 潮生会 税"
        )
    return None
