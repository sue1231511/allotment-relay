"""潮生会 — 岛上管事的机构。管理员来办事，不能加入、不能开、不能退。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from . import bar, db, events, flavor, world
from .game import require_steward, _parse_int

FUND_NAME = "潮汐基金"
FUND_MIN_DONATE = 1
FUND_PAY_CAP = 2500
FUND_DAILY_CAP = FUND_PAY_CAP
FUND_FLOOR = 800
FUND_MIN_PEERS = 2
# 东八区星期：周二、周四、周六自动发放补贴
FUND_PAY_WEEKDAYS = (1, 3, 5)
FUND_PAY_WEEKDAY_LABEL = "周二、周四、周六"
_CST = timezone(timedelta(hours=8))
_WEEKDAY_CN = "一二三四五六日"
NOTICE_AUTHOR = "潮生会"
NOTICE_TAG_DEFAULT = "厅示"
NOTICE_TAG_MAX = 20
NOTICE_BODY_MAX = 280
NOTICE_LIST_LIMIT = 12
PLAYER_NOTICE_REFUSE = (
    "潮生会告示是岛上贴的厅示，岛民不能贴、不能回。"
    "去聊天室说话：lounge_ops say 正文。长帖去听潮亭 wall_ops。人类去上手页聊天室或听潮亭。"
)

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
  空 / 问 — 进门问事：考勤、告示摘要、潮汐基金、岸税、岸维。不是入会。
  税 / 岸税 — 岸税：应税家当超额累进（口袋+行囊/潮柜/冰箱/挂单囤货款按系统回收价估）。未过 800 免征。高档加码（阔手 14%、豪客 20%、潮主 26%、潮宗 36%）。离岛均太远加潮差（5 倍 +8%，15 倍 +16%）。只攒不花加潮锈（闲钱要花掉 15%，买地买园不算）。看档、档表、本周应/欠
  税 交 / 税 交 50 — 交欠税（可填票数）。没有 tax_ops。欠税时不能买地/买棚/买园/升屋/买船/开坑/升镐
  维 / 岸维 / 维修 — 岸维：按产业每天收维修费。起步份地/果园免，产业单价至少 10 票（超出份地 10/18/28、果园 20/32/48、温室 30/48/70，铺多了加档）；扩地、开馆、盖棚才交
  维 交 / 维 交 50 — 交欠的维修费。欠维修费时不能扩产；开着的小馆暂停堂食。不是 hut_ops mascot upkeep
  基金 — 潮汐基金：岛均口袋票。有余的人自己填票数捐进来
  基金 捐 50 — 捐票，票数自己填（最少 {FUND_MIN_DONATE}）；口袋须高于岛均，捐完仍须不低于岛均
  告示 — 看墙上厅示（岛上贴的，岛民不能贴、不能回）。短句去聊天室 lounge_ops say；长帖去听潮亭 wall_ops
  岸税东八区每周一换班自动划入基金（本周新号免征到下周）。离岛均太远另加潮差附加（超过岛均 5 倍再加 8%，超过 15 倍再加 16%）。只攒不花另加潮锈：闲钱（超过岛均的部分）本周要花掉 15%，没花够的缺口整笔进基金；酒吧/小馆/衣泊坊/诊所/星光/小屋日子/婚宴/三金/基金捐算花，买地买园不算，买棚送礼也不算。应税家当含囤货款，税仍从口袋划。岸维东八区每天换班自动划（今日新号免征到明天）。补贴不用领、没有 MCP 指令。东八区{FUND_PAY_WEEKDAY_LABEL}自动发：先把低于 {FUND_FLOOR} 的托到 {FUND_FLOOR}，剩下再补给低于岛均的人（每人顶 {FUND_PAY_CAP}、不超过岛均）
  没有入会 / 开会 / 退会。{ORG_NAME}是岛上管事的机构，上岛时已经在册。
  本周目标 / 公仓 / 公物不在这儿：alliance_ops league · alliance_ops donate / larder · plot_ops commons
例子：潮生会 · 潮生会 问 · 潮生会 税 · 潮生会 税 交 · 潮生会 税 交 50 · 潮生会 维 · 潮生会 维 交 · 潮生会 维 交 50 · 潮生会 基金 · 潮生会 基金 捐 50 · 潮生会 基金 捐 8 · 潮生会 告示
容易搞混：税=强制岸税（富人按档交，税入基金）。维=产业维修费（产业越大越交，也入基金）。基金 捐 50=自愿捐票（须高于岛均）。mascot upkeep=吉祥物喂养。plot_ops repair=田间意外。周潮天灾=只冲 3 万以上，不是税。公仓捐货走 alliance_ops donate 甘蓝 2。不要写潮生会 补贴。steward_ops guild=每日工分轮值，不是入会；alliance_ops board=周目标贡献榜。没有 tax_ops / upkeep_ops。告示不能贴：那是厅示，不是聊天室。"""

_DOOR_LINES = (
    "坐。先报名字。入会？没有这回事。",
    "欠工去酒吧打卡。我这儿只记账，不替荔栀收碗。",
    "告示上墙，潮汐基金入簿。岸税、岸维也在这儿划。墙上是厅示，你们不能贴。",
    "潮汐基金按岛均口袋票算。有余就填个数捐。补贴不用领，周二四六自动发。",
    "口袋过了八百，岸税按应税家当交（含囤货款）。高档加码，只攒不花会锈。周一换班自动划。欠税别来买地。",
    "地扩多了、馆开了，岸维按产业每天收。起步那几块免。欠维修费小馆先停堂。",
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
            "SELECT COUNT(*) FROM hui_notices WHERE retracted=0"
        )).fetchone())[0]
        fund_line = _fund_brief(await fund_snapshot(conn, s["id"]))
        from . import tax as tax_mod
        tax_snap = await tax_mod.snapshot(conn, s["id"])
        from . import upkeep as upkeep_mod
        upkeep_snap = await upkeep_mod.snapshot(conn, s["id"])

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
        _tax_brief(tax_snap),
        _upkeep_brief(upkeep_snap),
    ]
    if pulse:
        kind = "凶" if pulse.get("kind") == "bad" else "吉"
        mins = int(pulse.get("remaining") or 0) // 60
        lines.append(f"全服脉冲：{pulse.get('label')}（{kind}，约 {mins} 分钟）")
    lines.extend([
        "",
        f"潮汐 {world.tide_label(world.current_tide())} · {world.weather_label(world.current_weather())}",
        "办事：visit_ops 潮生会 税 · 潮生会 税 交 · 潮生会 维 · 潮生会 维 交 · 潮生会 基金 · 潮生会 基金 捐 50 · 潮生会 告示",
        "本周目标走 alliance_ops league。公仓走 alliance_ops donate / larder。公物走 plot_ops commons。",
        f"岸税按应税家当交（口袋+囤货款，周一划），岸维按产业交（每天划）。潮汐基金：捐票自己填数。补贴不用领，东八区{FUND_PAY_WEEKDAY_LABEL}自动发。不能加入。上岛已在册。",
    ])
    if gift:
        lines.append(gift.strip())
    return "\n".join(lines)


async def _ensure_fund(conn) -> None:
    await conn.execute(
        "INSERT OR IGNORE INTO tide_fund "
        "(id, tickets, donated_total, paid_total, taxed_total) VALUES (1, 0, 0, 0, 0)"
    )


async def credit_fund(conn, amount: int) -> None:
    """把已经从口袋划走的票记进潮汐基金。不看岛均，也不当自愿捐。"""
    if amount <= 0:
        return
    await _ensure_fund(conn)
    await conn.execute(
        """
        UPDATE tide_fund
        SET tickets = tickets + ?, donated_total = donated_total + ?
        WHERE id=1
        """,
        (amount, amount),
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
        f"（先托到 {FUND_FLOOR}，再按岛均补，每人顶 {FUND_PAY_CAP} 票，且不超过岛均）。看簿：visit_ops 潮生会 基金"
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


def _tax_brief(snap: dict[str, Any]) -> str:
    mine = snap.get("mine") or {}
    if mine.get("arrears"):
        return f"{snap['name']}：欠 {mine['arrears']} · 先 visit_ops 潮生会 税 交"
    if mine.get("first_week"):
        return f"{snap['name']}：本周新号免征 · 看档 visit_ops 潮生会 税"
    band = mine.get("band") or "免征"
    due = int(mine.get("due_now") or 0)
    if due:
        return f"{snap['name']}：{band}档 · 周应约 {due} · {snap['next']}"
    return f"{snap['name']}：未过免税额 · {snap['next']}"


def _upkeep_brief(snap: dict[str, Any]) -> str:
    mine = snap.get("mine") or {}
    if mine.get("arrears"):
        extra = "；小馆已停堂" if mine.get("shop_paused") else ""
        return f"{snap['name']}：欠 {mine['arrears']}{extra} · 先 visit_ops 潮生会 维 交"
    if mine.get("first_day") or mine.get("first_week"):
        return f"{snap['name']}：今日新号免征 · 看档 visit_ops 潮生会 维"
    due = int(mine.get("due_now") or 0)
    if due:
        return f"{snap['name']}：日应约 {due} · {snap['next']}"
    return f"{snap['name']}：起步产业免征 · {snap['next']}"


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
        f"补贴不用领。东八区{FUND_PAY_WEEKDAY_LABEL}自动发：先把低于 {FUND_FLOOR} 的托到 {FUND_FLOOR}，剩下再按岛均补，每人顶 {FUND_PAY_CAP} 票、不超过岛均。",
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
    from . import tax as tax_mod
    owed = int(s.get("tax_arrears") or 0)
    if owed > 0:
        raise ValueError(
            f"还欠岸税 {owed} 票。先 visit_ops 潮生会 税 交，再捐基金。"
        )
    upkeep_owed = int(s.get("upkeep_arrears") or 0)
    if upkeep_owed > 0:
        raise ValueError(
            f"还欠岸维 {upkeep_owed} 票。先 visit_ops 潮生会 维 交，再捐基金。"
        )
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
        from . import tax as tax_mod
        await tax_mod.record_life_spend(conn, s["id"], amount, "fund")
        await conn.execute(
            """
            UPDATE tide_fund
            SET tickets = tickets + ?, donated_total = donated_total + ?
            WHERE id=1
            """,
            (amount, amount),
        )
        left = mine - amount
        from . import bond as bond_mod
        gained = await bond_mod.grant(
            conn, s["id"], bond_mod.donate_amount(amount), "give"
        )
        msg = (
            f"{s['name']} 向{FUND_NAME}捐了 {amount} 票"
            f"（岛均 {avg}，捐后口袋 {left}）"
        )
        if gained:
            msg += f" · 岛缘 +{gained}"
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
    pocket = {int(row[0]): int(row[2]) for row in rows}
    names = {int(row[0]): row[1] for row in rows}
    claimed: set[int] = set()
    gained: dict[int, int] = {}

    async def _credit(sid: int, want: int, why: str) -> int:
        nonlocal remaining, paid_n, paid_tickets
        if want < 1 or remaining < 1:
            return 0
        already = await (await conn.execute(
            "SELECT 1 FROM tide_fund_claims WHERE steward_id=? AND day=?",
            (sid, day_int),
        )).fetchone()
        if already:
            return 0
        take = min(want, remaining)
        if take < 1:
            return 0
        tickets = pocket[sid]
        await conn.execute(
            "UPDATE stewards SET tickets = tickets + ? WHERE id=?",
            (take, sid),
        )
        await conn.execute(
            """
            UPDATE tide_fund
            SET tickets = tickets - ?, paid_total = paid_total + ?
            WHERE id=1
            """,
            (take, take),
        )
        pocket[sid] = tickets + take
        remaining -= take
        paid_tickets += take
        gained[sid] = gained.get(sid, 0) + take
        if sid not in claimed:
            claimed.add(sid)
            paid_n += 1
        await db.add_chronicle(
            "fund",
            f"{names[sid]} 获{FUND_NAME}补贴 {take} 票（{why}，岛均 {avg}，补后口袋 {pocket[sid]}）",
            sid,
            conn=conn,
        )
        return take

    # 先把最低的托到免税线，再按岛均补。最低的先领。
    for sid in sorted(pocket, key=lambda i: (pocket[i], i)):
        if remaining <= 0:
            break
        if pocket[sid] >= FUND_FLOOR:
            continue
        await _credit(sid, FUND_FLOOR - pocket[sid], f"先托到 {FUND_FLOOR}")
    for sid in sorted(pocket, key=lambda i: (pocket[i], i)):
        if remaining <= 0:
            break
        if pocket[sid] >= avg:
            continue
        await _credit(sid, min(FUND_PAY_CAP, avg - pocket[sid]), "按岛均")

    if paid_n <= 0:
        return None
    for sid, total in gained.items():
        await conn.execute(
            "INSERT INTO tide_fund_claims (steward_id, day, amount) VALUES (?,?,?)",
            (sid, day_int, total),
        )
    detail = (
        f"{day_str} 按岛均 {avg} 发放：{paid_n} 人共 {paid_tickets} 票"
        f"（先托到 {FUND_FLOOR}，再每人顶 {FUND_PAY_CAP}，不超过岛均）"
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

    if verb in ("税", "岸税", "交税") or verb_l in ("tax", "levy", "shoretax"):
        from . import tax as tax_mod
        return await tax_mod.tax_command(key_id, raw)

    if verb in ("维", "岸维", "维修", "维修费") or verb_l in (
        "upkeep", "maintenance", "repairfee", "levyupkeep"
    ):
        from . import upkeep as upkeep_mod
        return await upkeep_mod.upkeep_command(key_id, raw)

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
        return await notice_ops(key_id, rest)

    if verb_l in ("贴", "post"):
        raise ValueError(PLAYER_NOTICE_REFUSE)

    if verb_l in ("回", "respond", "回复"):
        raise ValueError(PLAYER_NOTICE_REFUSE)

    if verb_l in ("公物", "commons", "公共"):
        raise ValueError(_commons_refuse())

    if verb_l in ("领", "claim"):
        if len(parts) >= 2 and parts[1] in ("补贴", "基金"):
            raise ValueError(subsidy_refuse())
        raise ValueError(_commons_refuse())

    raise ValueError(f"未知潮生会指令: {command}\n{CHAOSHEN_HELP}")


def _notice_tag(raw: str) -> str:
    tag = (raw or "").strip()[:NOTICE_TAG_MAX]
    return tag or NOTICE_TAG_DEFAULT


async def owner_post(tag: str, body: str) -> dict[str, Any]:
    """制作方面板发厅示。岛民走不了这条。"""
    body = (body or "").strip()
    if not body:
        raise ValueError("告示不能空着")
    if len(body) > NOTICE_BODY_MAX:
        raise ValueError(f"告示最多 {NOTICE_BODY_MAX} 字")
    tag = _notice_tag(tag)
    async with db.connect() as conn:
        cur = await conn.execute(
            "INSERT INTO hui_notices (tag, body, created_at, retracted) VALUES (?,?,?,0)",
            (tag, body, db.now()),
        )
        nid = cur.lastrowid
        await db.add_chronicle(
            "hui", f"潮生会贴出告示[{tag}]：{body[:80]}", None, conn=conn,
        )
        await conn.commit()
    return {"ok": True, "id": nid, "tag": tag, "msg": f"告示已上墙 [{tag}] #{nid}"}


async def owner_retract(notice_id: int) -> dict[str, Any]:
    nid = int(notice_id or 0)
    async with db.connect() as conn:
        conn.row_factory = None
        row = await (await conn.execute(
            "SELECT id, tag, retracted FROM hui_notices WHERE id=?", (nid,)
        )).fetchone()
        if not row:
            raise ValueError("没有这张告示")
        if int(row[2] or 0):
            raise ValueError("这张已经收下了")
        await conn.execute("UPDATE hui_notices SET retracted=1 WHERE id=?", (nid,))
        await db.add_chronicle(
            "hui", f"潮生会收下告示 #{nid}[{row[1]}]", None, conn=conn,
        )
        await conn.commit()
    return {"ok": True, "id": nid, "msg": f"已收下 #{nid}"}


async def owner_list() -> list[dict[str, Any]]:
    async with db.connect() as conn:
        conn.row_factory = None
        rows = await (await conn.execute(
            """
            SELECT id, tag, body, created_at, retracted
            FROM hui_notices
            ORDER BY created_at DESC LIMIT 40
            """
        )).fetchall()
    return [
        {
            "id": r[0],
            "tag": r[1],
            "body": r[2],
            "created_at": r[3],
            "retracted": bool(r[4]),
        }
        for r in rows
    ]


async def _format_notices(*, notice_id: int | None = None, tag: str | None = None) -> str:
    async with db.connect() as conn:
        conn.row_factory = None
        if notice_id:
            row = await (await conn.execute(
                "SELECT id, tag, body FROM hui_notices WHERE id=? AND retracted=0",
                (notice_id,),
            )).fetchone()
            if not row:
                raise ValueError("没有这张告示")
            return f"#{row[0]} [{row[1]}] {NOTICE_AUTHOR}：{row[2]}"
        if tag:
            rows = await (await conn.execute(
                """
                SELECT id, tag, body FROM hui_notices
                WHERE retracted=0 AND tag=?
                ORDER BY created_at DESC LIMIT ?
                """,
                (tag, NOTICE_LIST_LIMIT),
            )).fetchall()
        else:
            rows = await (await conn.execute(
                """
                SELECT id, tag, body FROM hui_notices
                WHERE retracted=0
                ORDER BY created_at DESC LIMIT ?
                """,
                (NOTICE_LIST_LIMIT,),
            )).fetchall()
    if not rows:
        return "告示栏暂无厅示。告示由潮生会张贴，岛民不能贴。短句去 lounge_ops say，长帖去 wall_ops 听潮亭。"
    lines = [f"#{r[0]} [{r[1]}] {NOTICE_AUTHOR}：{r[2]}" for r in rows]
    lines.append("告示由潮生会张贴，岛民不能贴、不能回。短句去 lounge_ops say，长帖去 wall_ops 听潮亭。")
    return "\n".join(lines)


async def notice_ops(key_id: int, command: str) -> str:
    await require_steward(key_id, exempt_duty=True)
    parts = command.strip().split(maxsplit=2)
    verb = (parts[0] if parts else "scan").strip()
    verb_l = verb.lower()

    if verb_l in ("help", "?", "帮助"):
        return (
            "看潮生会告示：scan / 看。也可 visit_ops 潮生会 告示。\n"
            "scan 编号 看一张；scan 标签 按标签筛。\n"
            f"{PLAYER_NOTICE_REFUSE}"
        )
    if verb_l in ("post", "贴", "respond", "回", "回复"):
        raise ValueError(PLAYER_NOTICE_REFUSE)

    token = None
    if verb_l in ("scan", "看", "告示", "公告") or not verb:
        token = parts[1] if len(parts) > 1 else None
    else:
        token = verb
    notice_id = int(token) if token and str(token).isdigit() else None
    tag = None if notice_id or not token else token
    return await _format_notices(notice_id=notice_id, tag=tag)


async def public_snapshot() -> dict[str, Any]:
    pulse = await events.public_pulse_snapshot()
    async with db.connect() as conn:
        conn.row_factory = None
        from . import tax as tax_mod
        from . import upkeep as upkeep_mod
        await tax_mod.ensure_shore_tax(conn)
        await upkeep_mod.ensure_shore_upkeep(conn)
        await ensure_fund_payout(conn)
        beacons = await (await conn.execute(
            """
            SELECT body, tag, created_at FROM hui_notices
            WHERE retracted=0
            ORDER BY created_at DESC LIMIT 6
            """
        )).fetchall()
        recent = await (await conn.execute(
            """
            SELECT text, created_at FROM chronicle
            WHERE action IN ('fund', 'tax', 'upkeep', 'hui')
            ORDER BY created_at DESC LIMIT 8
            """
        )).fetchall()
        fund = await fund_snapshot(conn)
        tax = await tax_mod.snapshot(conn)
        upkeep = await upkeep_mod.snapshot(conn)
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
        "tax": {
            "name": tax["name"],
            "week_id": tax["week_id"],
            "free": tax["free"],
            "floor": tax["floor"],
            "done": tax["done"],
            "next": tax["next"],
            "assessed": tax["assessed"],
            "collected": tax["collected"],
            "brackets": tax["brackets"],
            "avg": tax.get("avg") or 0,
            "gap_soft": tax.get("gap_soft") or 0,
            "gap_hard": tax.get("gap_hard") or 0,
            "rust_rate": tax.get("rust_rate") or 15,
        },
        "upkeep": {
            "name": upkeep["name"],
            "week_id": upkeep.get("day_id") or upkeep["week_id"],
            "day_id": upkeep.get("day_id") or upkeep["week_id"],
            "floor": upkeep["floor"],
            "done": upkeep["done"],
            "next": upkeep["next"],
            "assessed": upkeep["assessed"],
            "collected": upkeep["collected"],
            "rates": upkeep.get("rates") or [],
        },
        "beacons": [
            {"author": NOTICE_AUTHOR, "tag": r[1], "body": r[0], "created_at": r[2]}
            for r in beacons
        ],
        "recent": [
            {"text": r[0], "created_at": r[1]}
            for r in recent
        ],
        "note": "潮生会管事，不收人。上岛已在册。办事去上手页。",
    }
