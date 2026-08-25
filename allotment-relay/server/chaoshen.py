"""潮生会 — 岛上管事的机构。管理员来办事，不能加入、不能开、不能退。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from . import bar, db, events, flavor, world
from .game import require_steward, _parse_int

FUND_NAME = "潮汐基金"
FUND_MIN_DONATE = 1
FUND_PAY_CAP = 1000
FUND_DAILY_CAP = FUND_PAY_CAP
FUND_MIN_PEERS = 2
# 东八区星期：周二、周四、周六自动发放补贴
FUND_PAY_WEEKDAYS = (1, 3, 5)
FUND_PAY_WEEKDAY_LABEL = "周二、周四、周六"
_CST = timezone(timedelta(hours=8))
_WEEKDAY_CN = "一二三四五六日"

ORG_NAME = "潮生会"
CLERK_NAME = "阿簿"
CLERK_KEY = "aboo"

ALIASES = (
    "潮生会", "潮生", "阿簿", "chaoshen", "hui", "aboo", "clerk",
)

JOIN_VERBS = {
    "入", "入会", "加入", "申请", "apply", "join",
    "开", "开会", "立", "found", "create", "open",
    "退", "退会", "leave", "quit",
    "请", "邀", "招", "invite",
    "社", "湾", "船队", "公会",
}

JOIN_REFUSE = (
    f"{ORG_NAME}不是给管理员加入的组织。没有入会、开会、退会。"
    f"你 enroll 上岛那天就已经在册。来这儿是办事：visit_ops 潮生会"
)

CHAOSHEN_HELP = f"""visit_ops 潮生会 子命令（整句写进 command）：
  空 / 问 — 进门问事：考勤、告示摘要、潮汐基金。不是入会。
  基金 — 潮汐基金：岛均口袋票。有余的人自己填票数捐进来
  基金 捐 50 — 捐票，票数自己填（最少 {FUND_MIN_DONATE}）；口袋须高于岛均，捐完仍须不低于岛均
  告示 — 看告示；贴 标签 正文 发告示；回 编号 正文 回复（同 alliance_ops beacon）
  补贴不用领、没有 MCP 指令。东八区{FUND_PAY_WEEKDAY_LABEL}自动打到低于岛均的人口袋（每人顶 {FUND_PAY_CAP} 票，不超过岛均）
  没有入会 / 开会 / 退会。{ORG_NAME}是岛上管事的机构，上岛时已经在册。
  本周目标 / 公仓 / 公物不在这儿：alliance_ops league · alliance_ops donate / larder · plot_ops commons
例子：潮生会 · 潮生会 问 · 潮生会 基金 · 潮生会 基金 捐 50 · 潮生会 基金 捐 8 · 潮生会 告示
容易搞混：基金 捐 50=给潮汐基金捐票（票数自定义）。公仓捐货走 alliance_ops donate 甘蓝 2。不要写潮生会 补贴。steward_ops guild=每日工分轮值，不是入会；alliance_ops board=周目标贡献榜。"""

_DOOR_LINES = (
    "坐。先报名字。入会？没有这回事。",
    "欠工去酒吧打卡。我这儿只记账，不替荔栀收碗。",
    "告示上墙，潮汐基金入簿。你来办事就行。",
    "潮汐基金按岛均口袋票算。有余就填个数捐。补贴不用领，周二四六自动发。",
)


def is_alias(token: str) -> bool:
    raw = (token or "").strip()
    if not raw:
        return False
    if raw in {"潮生会", "潮生", "阿簿"}:
        return True
    return raw.lower() in {a.lower() for a in ALIASES}


def _join_refuse(verb: str) -> str:
    return JOIN_REFUSE + f"\n（你写的是「{verb}」。没有这条指令。）"


def _league_refuse(verb: str = "周") -> str:
    return (
        "本周目标不在潮生会办。"
        "看：alliance_ops league status · 交：alliance_ops league contribute 甘蓝 2"
        " · 榜：alliance_ops league board"
        f"\n（你写的是「{verb}」。）"
    )


def _larder_refuse() -> str:
    return (
        "公仓不在潮生会办。"
        "看：alliance_ops larder · 捐货：alliance_ops donate 甘蓝 2 · 取：alliance_ops draw 甘蓝 1"
        "\n捐票进潮汐基金仍是：visit_ops 潮生会 基金 捐 50"
    )


def _commons_refuse() -> str:
    return (
        "公物不在潮生会办。"
        "看：plot_ops commons scan · 领：plot_ops commons claim 编号"
        f"\n潮汐基金补贴不用领，东八区{FUND_PAY_WEEKDAY_LABEL}自动发"
    )


async def _front_desk(key_id: int) -> str:
    s = await require_steward(key_id, exempt_duty=True)
    duty = bar.duty_line(s)
    pulse = await events.public_pulse_snapshot()
    async with db.connect() as conn:
        conn.row_factory = None
        beacon_n = (await (await conn.execute(
            "SELECT COUNT(*) FROM beacons"
        )).fetchone())[0]
        fund_line = _fund_brief(await fund_snapshot(conn, s["id"]))

    from . import npc as npc_mod
    gift = await npc_mod._daily_visit_gift(s["id"], CLERK_KEY)

    door = flavor.pick(_DOOR_LINES)
    lines = [
        f"{ORG_NAME} · 值事{CLERK_NAME}",
        f"{CLERK_NAME}：「{door}」",
        "",
        f"考勤：{duty}",
        f"告示：{int(beacon_n)} 条",
        fund_line,
    ]
    if pulse:
        kind = "凶" if pulse.get("kind") == "bad" else "吉"
        mins = int(pulse.get("remaining") or 0) // 60
        lines.append(f"全服脉冲：{pulse.get('label')}（{kind}，约 {mins} 分钟）")
    lines.extend([
        "",
        f"潮汐 {world.tide_label(world.current_tide())} · {world.weather_label(world.current_weather())}",
        "办事：visit_ops 潮生会 基金 · 潮生会 基金 捐 50 · 潮生会 告示",
        "本周目标走 alliance_ops league。公仓走 alliance_ops donate / larder。公物走 plot_ops commons。",
        f"潮汐基金：捐票自己填数。补贴不用领，东八区{FUND_PAY_WEEKDAY_LABEL}自动发。不能加入。上岛已在册。",
    ])
    if gift:
        lines.append(gift.strip())
    return "\n".join(lines)


async def _ensure_fund(conn) -> None:
    await conn.execute(
        "INSERT OR IGNORE INTO tide_fund (id, tickets, donated_total, paid_total) VALUES (1, 0, 0, 0)"
    )


def _cst_dt(ts: int | None = None) -> datetime:
    return datetime.fromtimestamp(ts if ts is not None else db.now(), _CST)


def payout_day_id(ts: int | None = None) -> str:
    return _cst_dt(ts).strftime("%Y-%m-%d")


def payout_day_int(ts: int | None = None) -> int:
    return int(_cst_dt(ts).strftime("%Y%m%d"))


def is_payout_day(ts: int | None = None) -> bool:
    return _cst_dt(ts).weekday() in FUND_PAY_WEEKDAYS


def next_payout_line(ts: int | None = None) -> str:
    dt = _cst_dt(ts)
    if dt.weekday() in FUND_PAY_WEEKDAYS:
        return f"今天（东八区周{_WEEKDAY_CN[dt.weekday()]}）会自动发补贴"
    for i in range(1, 8):
        nxt = dt + timedelta(days=i)
        if nxt.weekday() in FUND_PAY_WEEKDAYS:
            return (
                f"下一次发放：周{_WEEKDAY_CN[nxt.weekday()]} {nxt.strftime('%m-%d')}"
                f"（东八区{FUND_PAY_WEEKDAY_LABEL}）"
            )
    return f"东八区{FUND_PAY_WEEKDAY_LABEL}自动发放"


def _pay_flag_key(day: str) -> str:
    return f"tide_fund_pay_{day}"


def subsidy_refuse() -> str:
    return (
        f"{FUND_NAME}的补贴不用自己领，也没有这条 MCP 指令。"
        f"东八区{FUND_PAY_WEEKDAY_LABEL}自动打到低于岛均的人口袋"
        f"（每人顶 {FUND_PAY_CAP} 票，且不超过岛均）。看簿：visit_ops 潮生会 基金"
    )


async def island_ticket_stats(conn) -> dict[str, Any]:
    row = await (await conn.execute(
        """
        SELECT COUNT(*), COALESCE(AVG(tickets), 0), COALESCE(SUM(tickets), 0)
        FROM stewards WHERE enrolled=1
        """
    )).fetchone()
    n = int(row[0] or 0)
    avg = int(round(float(row[1] or 0)))
    return {"n": n, "avg": avg, "sum": int(row[2] or 0)}


async def fund_snapshot(conn, steward_id: int | None = None) -> dict[str, Any]:
    await _ensure_fund(conn)
    pool = await (await conn.execute(
        "SELECT tickets, donated_total, paid_total FROM tide_fund WHERE id=1"
    )).fetchone()
    stats = await island_ticket_stats(conn)
    mine = None
    paid_today = 0
    day_int = payout_day_int()
    day_str = payout_day_id()
    if steward_id:
        mine_row = await (await conn.execute(
            "SELECT tickets FROM stewards WHERE id=?", (steward_id,)
        )).fetchone()
        mine = int(mine_row[0]) if mine_row else 0
        claim_row = await (await conn.execute(
            "SELECT amount FROM tide_fund_claims WHERE steward_id=? AND day=?",
            (steward_id, day_int),
        )).fetchone()
        paid_today = int(claim_row[0]) if claim_row else 0
    flag = await (await conn.execute(
        "SELECT 1 FROM world_flags WHERE flag_key=?", (_pay_flag_key(day_str),)
    )).fetchone()
    pool_tickets = int(pool[0] if pool else 0)
    avg = int(stats["avg"])
    n = int(stats["n"])
    ready = n >= FUND_MIN_PEERS
    gap = (avg - mine) if mine is not None else 0
    return {
        "pool": pool_tickets,
        "donated_total": int(pool[1] if pool else 0),
        "paid_total": int(pool[2] if pool else 0),
        "avg": avg,
        "n": n,
        "ready": ready,
        "mine": mine,
        "paid_today": paid_today,
        "payout_today": is_payout_day(),
        "payout_done": bool(flag),
        "next_pay": next_payout_line(),
        "gap": gap,
        "can_donate": bool(ready and mine is not None and mine > avg and (mine - avg) >= FUND_MIN_DONATE),
        "max_donate": max(0, (mine - avg) if mine is not None else 0),
        "max_claim": 0,
        "can_claim": False,
    }


def _fund_brief(snap: dict[str, Any]) -> str:
    if not snap["ready"]:
        return f"{FUND_NAME}：在册还不够 {FUND_MIN_PEERS} 人，算不出岛均"
    mine = snap["mine"]
    avg = snap["avg"]
    if mine is None:
        stand = "未在册"
    elif mine > avg:
        stand = f"你 {mine} · 高于平均 {mine - avg}"
    elif mine < avg:
        stand = f"你 {mine} · 低于平均 {avg - mine}"
    else:
        stand = f"你 {mine} · 正好岛均"
    return f"{FUND_NAME}：池里 {snap['pool']} 票 · 岛均 {avg}（{snap['n']} 人）· {stand}"


def _fund_status_text(snap: dict[str, Any]) -> str:
    lines = [
        f"{ORG_NAME} · {FUND_NAME}",
        f"{CLERK_NAME}：有余的人自己填票数捐进来。补贴不用领，{FUND_PAY_WEEKDAY_LABEL}自动打到低于岛均的人口袋。",
        "",
        f"池里：{snap['pool']} 票（累计入 {snap['donated_total']} / 已发补贴 {snap['paid_total']}）",
        snap["next_pay"],
    ]
    if not snap["ready"]:
        lines.append(f"岛均：在册 {snap['n']} 人，还不够 {FUND_MIN_PEERS} 人，算不出平均水准。")
        lines.append("捐票要先有岛均。")
    else:
        lines.append(f"岛均水准：{snap['avg']} 票（在册 {snap['n']} 人，口袋现票平均）")
        mine = snap["mine"]
        avg = snap["avg"]
        if mine is not None:
            if mine > avg:
                lines.append(
                    f"你的口袋：{mine} 票 · 高于平均 {mine - avg} · 最多可捐 {snap['max_donate']}"
                )
            elif mine < avg:
                if snap["paid_today"]:
                    lines.append(
                        f"你的口袋：{mine} 票 · 低于平均 {avg - mine} · 今日已自动补 {snap['paid_today']} 票"
                    )
                elif snap["payout_today"] and snap["pool"] <= 0:
                    lines.append(
                        f"你的口袋：{mine} 票 · 低于平均 {avg - mine} · 今天会发，但基金里还没票"
                    )
                else:
                    lines.append(
                        f"你的口袋：{mine} 票 · 低于平均 {avg - mine} · 到发放日自动补，不用自己领"
                    )
            else:
                lines.append(f"你的口袋：{mine} 票 · 正好岛均，不用捐也不用补")
    lines.extend([
        "",
        "捐：visit_ops 潮生会 基金 捐 50（票数自己填；捐完仍须不低于岛均）",
        f"补贴不用领。东八区{FUND_PAY_WEEKDAY_LABEL}自动发，每人顶 {FUND_PAY_CAP} 票、不超过岛均。",
        "不是公仓：公仓捐货走 alliance_ops donate 甘蓝 2，基金捐的是票。",
    ])
    return "\n".join(lines)


async def fund_status(key_id: int) -> str:
    s = await require_steward(key_id, exempt_duty=True)
    async with db.connect() as conn:
        conn.row_factory = None
        snap = await fund_snapshot(conn, s["id"])
    return _fund_status_text(snap)


async def fund_donate(key_id: int, amount: int) -> str:
    s = await require_steward(key_id, exempt_duty=True)
    if amount < FUND_MIN_DONATE:
        raise ValueError(f"票数自己填，至少 {FUND_MIN_DONATE}。用法：visit_ops 潮生会 基金 捐 50")
    async with db.connect() as conn:
        conn.row_factory = None
        await _ensure_fund(conn)
        stats = await island_ticket_stats(conn)
        if stats["n"] < FUND_MIN_PEERS:
            raise ValueError(
                f"在册还不够 {FUND_MIN_PEERS} 人，算不出岛均，先别捐。"
                "有人上岛之后再来。"
            )
        avg = stats["avg"]
        mine = int((await (await conn.execute(
            "SELECT tickets FROM stewards WHERE id=?", (s["id"],)
        )).fetchone())[0])
        if mine <= avg:
            raise ValueError(
                f"口袋 {mine} 票，没过岛均 {avg}，不算有余。"
                f"{FUND_NAME}只收高于平均的人捐的票。"
            )
        max_donate = mine - avg
        if amount > max_donate:
            raise ValueError(
                f"捐完不能低于岛均 {avg}。你口袋 {mine}，这次最多捐 {max_donate} 票。"
            )
        await conn.execute(
            "UPDATE stewards SET tickets = tickets - ? WHERE id=?",
            (amount, s["id"]),
        )
        await conn.execute(
            """
            UPDATE tide_fund
            SET tickets = tickets + ?, donated_total = donated_total + ?
            WHERE id=1
            """,
            (amount, amount),
        )
        left = mine - amount
        msg = (
            f"{s['name']} 向{FUND_NAME}捐了 {amount} 票"
            f"（岛均 {avg}，捐后口袋 {left}）"
        )
        await db.add_chronicle("fund", msg, s["id"], conn=conn)
        paid = await ensure_fund_payout(conn)
        await conn.commit()
    extra = ""
    if paid:
        extra = f"\n今天是发放日，刚入簿的票已按岛均补出去：{paid['detail']}"
    return (
        f"{CLERK_NAME}把 {amount} 票入了{FUND_NAME}簿。\n"
        f"{msg}{extra}\n"
        f"补贴不用领。东八区{FUND_PAY_WEEKDAY_LABEL}自动打到低于岛均的人口袋。"
    )


async def ensure_fund_payout(
    conn=None,
    *,
    ts: int | None = None,
) -> dict[str, Any] | None:
    """东八区周二/周四/周六把池里的票按岛均补给穷人。不用 MCP 领取。"""
    if conn is None:
        async with db.connect() as owned:
            result = await ensure_fund_payout(owned, ts=ts)
            if result:
                await owned.commit()
            return result
    moment = ts if ts is not None else db.now()
    if not is_payout_day(moment):
        return None
    day_str = payout_day_id(moment)
    day_int = payout_day_int(moment)
    flag_key = _pay_flag_key(day_str)
    existing = await (await conn.execute(
        "SELECT 1 FROM world_flags WHERE flag_key=?", (flag_key,)
    )).fetchone()
    if existing:
        return None
    await _ensure_fund(conn)
    stats = await island_ticket_stats(conn)
    if stats["n"] < FUND_MIN_PEERS:
        return None
    avg = int(stats["avg"])
    pool = int((await (await conn.execute(
        "SELECT tickets FROM tide_fund WHERE id=1"
    )).fetchone())[0])
    rows = await (await conn.execute(
        """
        SELECT id, name, tickets FROM stewards
        WHERE enrolled=1 AND tickets < ?
        ORDER BY tickets ASC, id ASC
        """,
        (avg,),
    )).fetchall()
    if not rows:
        await conn.execute(
            "INSERT INTO world_flags (flag_key, applied_at, detail) VALUES (?,?,?)",
            (flag_key, moment, "no-eligible"),
        )
        return {
            "day": day_str,
            "avg": avg,
            "paid_n": 0,
            "paid_tickets": 0,
            "detail": f"{day_str} 没有低于岛均 {avg} 的人",
        }
    if pool <= 0:
        return None
    remaining = pool
    paid_n = 0
    paid_tickets = 0
    for row in rows:
        if remaining <= 0:
            break
        sid, name, tickets = int(row[0]), row[1], int(row[2])
        want = min(FUND_PAY_CAP, avg - tickets, remaining)
        if want < 1:
            continue
        already = await (await conn.execute(
            "SELECT 1 FROM tide_fund_claims WHERE steward_id=? AND day=?",
            (sid, day_int),
        )).fetchone()
        if already:
            continue
        await conn.execute(
            "UPDATE stewards SET tickets = tickets + ? WHERE id=?",
            (want, sid),
        )
        await conn.execute(
            """
            UPDATE tide_fund
            SET tickets = tickets - ?, paid_total = paid_total + ?
            WHERE id=1
            """,
            (want, want),
        )
        await conn.execute(
            "INSERT INTO tide_fund_claims (steward_id, day, amount) VALUES (?,?,?)",
            (sid, day_int, want),
        )
        after = tickets + want
        await db.add_chronicle(
            "fund",
            f"{name} 获{FUND_NAME}补贴 {want} 票（岛均 {avg}，补后口袋 {after}）",
            sid,
            conn=conn,
        )
        remaining -= want
        paid_n += 1
        paid_tickets += want
    if paid_n <= 0:
        return None
    detail = (
        f"{day_str} 按岛均 {avg} 发放：{paid_n} 人共 {paid_tickets} 票"
        f"（每人顶 {FUND_PAY_CAP}，不超过岛均）"
    )
    await conn.execute(
        "INSERT INTO world_flags (flag_key, applied_at, detail) VALUES (?,?,?)",
        (flag_key, moment, detail),
    )
    await db.add_chronicle("fund", f"{FUND_NAME}今日发放：{detail}", None, conn=conn)
    return {
        "day": day_str,
        "avg": avg,
        "paid_n": paid_n,
        "paid_tickets": paid_tickets,
        "detail": detail,
    }


async def _fund_command(key_id: int, parts: list[str]) -> str:
    rest = parts[1:]
    if not rest or rest[0].lower() in ("看", "status", "scan", "问"):
        return await fund_status(key_id)
    head = rest[0].lower()
    if head in ("捐", "donate", "捐票"):
        if len(rest) < 2:
            raise ValueError("票数自己填。用法：visit_ops 潮生会 基金 捐 50")
        return await fund_donate(key_id, _parse_int(rest[1], "票数"))
    if head in ("领", "补贴", "claim", "draw"):
        raise ValueError(subsidy_refuse())
    raise ValueError(
        f"未知{FUND_NAME}指令。看：visit_ops 潮生会 基金 · 捐：基金 捐 50（票数自己填）。补贴不用领，{FUND_PAY_WEEKDAY_LABEL}自动发。"
    )


async def chaoshen_ops(key_id: int, command: str = "") -> str:
    raw = (command or "").strip()
    parts = raw.split()
    verb = parts[0] if parts else "问"
    verb_l = verb.lower()

    if verb_l in ("help", "?", "帮助"):
        return CHAOSHEN_HELP
    if verb_l in JOIN_VERBS or verb in JOIN_VERBS:
        raise ValueError(_join_refuse(verb))

    if verb_l in ("", "问", "看", "visit", "status", "事", "问事", "desk"):
        return await _front_desk(key_id)

    if verb in ("基金", "潮汐基金") or verb_l in ("fund", "tidefund"):
        return await _fund_command(key_id, parts)

    if verb in ("补贴", "领补贴") or verb_l in ("subsidy", "stipend"):
        raise ValueError(subsidy_refuse())

    if verb in ("捐票",) or verb_l in ("donatetickets", "donate_tickets"):
        if len(parts) < 2:
            raise ValueError("票数自己填。用法：visit_ops 潮生会 基金 捐 50")
        return await fund_donate(key_id, _parse_int(parts[1], "票数"))

    if verb_l in ("周", "league", "目标", "周目标"):
        raise ValueError(_league_refuse(verb))

    if verb_l in ("仓", "larder", "公仓", "库"):
        raise ValueError(_larder_refuse())

    if verb_l in ("捐", "donate"):
        if len(parts) >= 2 and (parts[1].isdigit() or parts[1] in ("票", "工分票")):
            raise ValueError("捐票请走潮汐基金：visit_ops 潮生会 基金 捐 50")
        if len(parts) >= 2:
            raise ValueError(_larder_refuse())
        raise ValueError(
            "捐票进潮汐基金：visit_ops 潮生会 基金 捐 50\n"
            "公仓捐货：alliance_ops donate 甘蓝 2"
        )

    if verb_l in ("取", "draw", "领货"):
        raise ValueError(_larder_refuse())

    if verb_l in ("告示", "beacon", "公告"):
        rest = " ".join(parts[1:]) if len(parts) > 1 else "scan"
        if not rest or rest.lower() in ("scan", "看"):
            rest = "scan"
        from . import game as game_mod
        return await game_mod.beacon_ops(key_id, rest)

    if verb_l in ("贴", "post"):
        if len(parts) < 3:
            raise ValueError("用法：visit_ops 潮生会 贴 标签 正文")
        from . import game as game_mod
        return await game_mod.beacon_ops(key_id, "post " + " ".join(parts[1:]))

    if verb_l in ("回", "respond", "回复"):
        if len(parts) < 3:
            raise ValueError("用法：visit_ops 潮生会 回 编号 正文")
        from . import game as game_mod
        return await game_mod.beacon_ops(key_id, "respond " + " ".join(parts[1:]))

    if verb_l in ("公物", "commons", "公共"):
        raise ValueError(_commons_refuse())

    if verb_l in ("领", "claim"):
        if len(parts) >= 2 and parts[1] in ("补贴", "基金"):
            raise ValueError(subsidy_refuse())
        raise ValueError(_commons_refuse())

    raise ValueError(f"未知潮生会指令: {command}\n{CHAOSHEN_HELP}")


async def public_snapshot() -> dict[str, Any]:
    pulse = await events.public_pulse_snapshot()
    async with db.connect() as conn:
        conn.row_factory = None
        await ensure_fund_payout(conn)
        beacons = await (await conn.execute(
            """
            SELECT b.body, a.name, b.created_at FROM beacons b
            JOIN stewards a ON a.id=b.author_id
            ORDER BY b.created_at DESC LIMIT 6
            """
        )).fetchall()
        recent = await (await conn.execute(
            """
            SELECT text, created_at FROM chronicle
            WHERE action = 'fund'
            ORDER BY created_at DESC LIMIT 8
            """
        )).fetchall()
        fund = await fund_snapshot(conn)
        await conn.commit()

    return {
        "org": ORG_NAME,
        "clerk": CLERK_NAME,
        "line": flavor.pick(_DOOR_LINES),
        "climate": world.climate_line(),
        "pulse": pulse,
        "fund": {
            "name": FUND_NAME,
            "pool": fund["pool"],
            "avg": fund["avg"],
            "n": fund["n"],
            "ready": fund["ready"],
            "donated_total": fund["donated_total"],
            "paid_total": fund["paid_total"],
            "next_pay": fund["next_pay"],
            "payout_today": fund["payout_today"],
            "payout_done": fund["payout_done"],
            "weekdays": FUND_PAY_WEEKDAY_LABEL,
        },
        "beacons": [
            {"author": r[1], "body": (r[0] or "")[:80], "created_at": r[2]}
            for r in beacons
        ],
        "recent": [
            {"text": r[0], "created_at": r[1]}
            for r in recent
        ],
        "note": "潮生会管事，不收人。上岛已在册。办事去上手页。",
    }
