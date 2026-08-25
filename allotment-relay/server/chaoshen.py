"""潮生会 — 岛上管事的机构。管理员来办事，不能加入、不能开、不能退。"""
from __future__ import annotations

from typing import Any

from . import bar, db, events, flavor, multi, world
from .catalog import ITEM_NAMES, resolve_item_key, unknown_item_message
from .game import require_steward, _parse_int

FUND_NAME = "潮汐基金"
FUND_MIN_DONATE = 10
FUND_DAILY_CAP = 30
FUND_MIN_PEERS = 2

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
  空 / 问 — 进门问事：本周岛务、考勤、公仓、告示摘要、潮汐基金。不是入会。
  周 — 本周目标；周 交 甘蓝 2 推进（和 alliance_ops league contribute 同一目标）
  仓 — 公仓；捐 甘蓝 2 / 取 甘蓝 1（领取 2 票、每日 3 次；和 alliance_ops donate/larder 同一仓）
  基金 — 潮汐基金：岛均口袋票。有余的人捐，低于平均的人领补贴，领完不超过岛均
  基金 捐 50 — 口袋票高于岛均才能捐；最少 {FUND_MIN_DONATE} 票，捐完仍须不低于岛均
  补贴 — 低于岛均才领；每个游戏日一次，最多 {FUND_DAILY_CAP} 票，且不超过岛均。基金没票就领不到
  告示 — 看告示；贴 标签 正文 发告示；回 编号 正文 回复（同 alliance_ops beacon）
  公物 — 稀有公共物资；领 编号 领取（同 plot_ops commons）。不是领补贴
  没有入会 / 开会 / 退会。{ORG_NAME}是岛上管事的机构，上岛时已经在册。
例子：潮生会 · 潮生会 问 · 潮生会 周 · 潮生会 捐 甘蓝 2 · 潮生会 基金 · 潮生会 基金 捐 50 · 潮生会 补贴
容易搞混：捐 甘蓝=公仓货物；基金 捐 50=给潮汐基金捐票。steward_ops guild=每日工分轮值，不是入会；alliance_ops board=周目标贡献榜；小橘粉丝团才是入团。"""

_DOOR_LINES = (
    "坐。先报名字。入会？没有这回事。",
    "牌子上写着这周岛上要什么。交到这边，记到簿上。",
    "欠工去酒吧打卡。我这儿只记账，不替荔栀收碗。",
    "公仓进出、告示上墙，都是潮生会的事。你来办事就行。",
    "潮汐基金按岛均口袋票算。有余就捐，不够就领补贴。没有入会这一说。",
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


async def _front_desk(key_id: int) -> str:
    s = await require_steward(key_id, exempt_duty=True)
    league = await multi.league_snapshot()
    duty = bar.duty_line(s)
    pulse = await events.public_pulse_snapshot()
    async with db.connect() as conn:
        conn.row_factory = None
        larder_n = (await (await conn.execute(
            "SELECT COUNT(*) FROM larder WHERE quantity > 0"
        )).fetchone())[0]
        larder_sum = (await (await conn.execute(
            "SELECT COALESCE(SUM(quantity), 0) FROM larder WHERE quantity > 0"
        )).fetchone())[0]
        beacon_n = (await (await conn.execute(
            "SELECT COUNT(*) FROM beacons"
        )).fetchone())[0]
        from . import commons as commons_mod
        commons_rows = await commons_mod._active_spawns(conn)
        now = db.now()
        commons_live = sum(1 for r in commons_rows if r["appears_at"] <= now)
        fund_line = _fund_brief(await fund_snapshot(conn, s["id"]))

    from . import npc as npc_mod
    gift = await npc_mod._daily_visit_gift(s["id"], CLERK_KEY)

    done = "已达成" if league.get("completed") else f"{league['progress']}/{league['target']}"
    door = flavor.pick(_DOOR_LINES)
    lines = [
        f"{ORG_NAME} · 值事{CLERK_NAME}",
        f"{CLERK_NAME}：「{door}」",
        "",
        f"本周岛务：「{league['label']}」{done}",
        f"考勤：{duty}",
        f"公仓：{int(larder_n)} 种货、共 {int(larder_sum)} 份",
        f"告示：{int(beacon_n)} 条",
        f"公物：在架 {commons_live} 件",
        fund_line,
    ]
    if pulse:
        kind = "凶" if pulse.get("kind") == "bad" else "吉"
        mins = int(pulse.get("remaining") or 0) // 60
        lines.append(f"全服脉冲：{pulse.get('label')}（{kind}，约 {mins} 分钟）")
    lines.extend([
        "",
        f"潮汐 {world.tide_label(world.current_tide())} · {world.weather_label(world.current_weather())}",
        "办事：visit_ops 潮生会 周 · 潮生会 仓 · 潮生会 基金 · 潮生会 补贴 · 潮生会 告示 · 潮生会 公物",
        "周目标/公仓/告示与 alliance_ops 是同一套，不是第二本账。",
        "潮汐基金按岛均口袋票；有余捐票、不够领补贴。不能加入。上岛已在册。",
    ])
    if gift:
        lines.append(gift.strip())
    return "\n".join(lines)


def _resolve_item(token: str) -> str:
    item = resolve_item_key(token)
    if not item:
        raise ValueError(unknown_item_message(token))
    return item


async def _ensure_fund(conn) -> None:
    await conn.execute(
        "INSERT OR IGNORE INTO tide_fund (id, tickets, donated_total, paid_total) VALUES (1, 0, 0, 0)"
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
    claimed_today = 0
    if steward_id:
        mine_row = await (await conn.execute(
            "SELECT tickets FROM stewards WHERE id=?", (steward_id,)
        )).fetchone()
        mine = int(mine_row[0]) if mine_row else 0
        day = db.day_id()
        claim_row = await (await conn.execute(
            "SELECT amount FROM tide_fund_claims WHERE steward_id=? AND day=?",
            (steward_id, day),
        )).fetchone()
        claimed_today = int(claim_row[0]) if claim_row else 0
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
        "claimed_today": claimed_today,
        "gap": gap,
        "can_donate": bool(ready and mine is not None and mine > avg and (mine - avg) >= FUND_MIN_DONATE),
        "can_claim": bool(
            ready
            and mine is not None
            and mine < avg
            and claimed_today == 0
            and pool_tickets > 0
        ),
        "max_donate": max(0, (mine - avg) if mine is not None else 0),
        "max_claim": min(FUND_DAILY_CAP, max(0, gap), pool_tickets) if mine is not None else 0,
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
        f"{CLERK_NAME}：有余的人把票放进来，不够岛均的人按水准领补贴。领完不超过岛均。",
        "",
        f"池里：{snap['pool']} 票（累计入 {snap['donated_total']} / 已发补贴 {snap['paid_total']}）",
    ]
    if not snap["ready"]:
        lines.append(f"岛均：在册 {snap['n']} 人，还不够 {FUND_MIN_PEERS} 人，算不出平均水准。")
        lines.append("捐票 / 领补贴都要先有岛均。")
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
                if snap["claimed_today"]:
                    lines.append(
                        f"你的口袋：{mine} 票 · 低于平均 {avg - mine} · 今日已领过补贴"
                    )
                elif snap["pool"] <= 0:
                    lines.append(
                        f"你的口袋：{mine} 票 · 低于平均 {avg - mine} · 基金里没票，等有余的人捐"
                    )
                else:
                    lines.append(
                        f"你的口袋：{mine} 票 · 低于平均 {avg - mine} · 今日可领 {snap['max_claim']} 票"
                    )
            else:
                lines.append(f"你的口袋：{mine} 票 · 正好岛均，不捐不领")
    lines.extend([
        "",
        f"捐：visit_ops 潮生会 基金 捐 {FUND_MIN_DONATE}（最少 {FUND_MIN_DONATE}，捐完仍须不低于岛均）",
        f"领：visit_ops 潮生会 补贴（每游戏日一次，顶 {FUND_DAILY_CAP} 票，且不超过岛均）",
        "不是公仓：公仓捐的是货（潮生会 捐 甘蓝 2），基金捐的是票。",
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
        raise ValueError(f"一次至少捐 {FUND_MIN_DONATE} 票。用法：visit_ops 潮生会 基金 捐 50")
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
        await conn.commit()
    return (
        f"{CLERK_NAME}把 {amount} 票入了{FUND_NAME}簿。\n"
        f"{msg}\n"
        f"低于岛均的人可以 visit_ops 潮生会 补贴 来领。"
    )


async def fund_claim(key_id: int) -> str:
    s = await require_steward(key_id, exempt_duty=True)
    day = db.day_id()
    async with db.connect() as conn:
        conn.row_factory = None
        await _ensure_fund(conn)
        stats = await island_ticket_stats(conn)
        if stats["n"] < FUND_MIN_PEERS:
            raise ValueError(
                f"在册还不够 {FUND_MIN_PEERS} 人，算不出岛均，领不了补贴。"
            )
        avg = stats["avg"]
        mine = int((await (await conn.execute(
            "SELECT tickets FROM stewards WHERE id=?", (s["id"],)
        )).fetchone())[0])
        if mine >= avg:
            raise ValueError(
                f"口袋 {mine} 票，已经到岛均 {avg}。"
                f"{FUND_NAME}只补给低于平均的人。"
            )
        claimed = await (await conn.execute(
            "SELECT amount FROM tide_fund_claims WHERE steward_id=? AND day=?",
            (s["id"], day),
        )).fetchone()
        if claimed:
            raise ValueError(f"今日已经领过补贴（{int(claimed[0])} 票）。下个游戏日再来。")
        pool = int((await (await conn.execute(
            "SELECT tickets FROM tide_fund WHERE id=1"
        )).fetchone())[0])
        if pool <= 0:
            raise ValueError(
                f"{FUND_NAME}里没票。口袋过了岛均的人可以 visit_ops 潮生会 基金 捐 50"
            )
        gap = avg - mine
        payout = min(FUND_DAILY_CAP, gap, pool)
        if payout < 1:
            raise ValueError("这次算下来没有可领的票。")
        await conn.execute(
            "UPDATE stewards SET tickets = tickets + ? WHERE id=?",
            (payout, s["id"]),
        )
        await conn.execute(
            """
            UPDATE tide_fund
            SET tickets = tickets - ?, paid_total = paid_total + ?
            WHERE id=1
            """,
            (payout, payout),
        )
        await conn.execute(
            "INSERT INTO tide_fund_claims (steward_id, day, amount) VALUES (?,?,?)",
            (s["id"], day, payout),
        )
        after = mine + payout
        msg = (
            f"{s['name']} 从{FUND_NAME}领了补贴 {payout} 票"
            f"（岛均 {avg}，领后口袋 {after}）"
        )
        await db.add_chronicle("fund", msg, s["id"], conn=conn)
        await conn.commit()
    leftover = gap - payout
    extra = ""
    if leftover > 0:
        extra = f" 离岛均还差 {leftover}，下个游戏日还可以再领。"
    return (
        f"{CLERK_NAME}按岛均补了 {payout} 票。\n"
        f"{msg}。{extra}\n"
        f"补贴不超过岛均，也不是公仓领货（公仓是 潮生会 取 甘蓝 1）。"
    )


async def _fund_command(key_id: int, parts: list[str]) -> str:
    rest = parts[1:]
    if not rest or rest[0].lower() in ("看", "status", "scan", "问"):
        return await fund_status(key_id)
    head = rest[0].lower()
    if head in ("捐", "donate", "捐票"):
        if len(rest) < 2:
            raise ValueError("用法：visit_ops 潮生会 基金 捐 50")
        return await fund_donate(key_id, _parse_int(rest[1], "票数"))
    if head in ("领", "补贴", "claim", "draw"):
        return await fund_claim(key_id)
    raise ValueError(
        f"未知{FUND_NAME}指令。看：visit_ops 潮生会 基金 · 捐：基金 捐 50 · 领：潮生会 补贴"
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
        return await fund_claim(key_id)

    if verb in ("捐票",) or verb_l in ("donatetickets", "donate_tickets"):
        if len(parts) < 2:
            raise ValueError("用法：visit_ops 潮生会 基金 捐 50")
        return await fund_donate(key_id, _parse_int(parts[1], "票数"))

    if verb_l in ("周", "league", "目标", "周目标"):
        rest = parts[1:]
        if not rest:
            return await multi.league_ops(key_id, "status")
        head = rest[0].lower()
        if head in ("交", "缴", "献", "contribute"):
            if len(rest) < 3:
                raise ValueError("用法：visit_ops 潮生会 周 交 甘蓝 2")
            item = _resolve_item(rest[1])
            qty = _parse_int(rest[2], "数量")
            return await multi.league_ops(key_id, f"contribute {item} {qty}")
        if head in ("board", "榜", "贡献榜"):
            return await multi.league_ops(key_id, "board")
        if head == "status":
            return await multi.league_ops(key_id, "status")
        return await multi.league_ops(key_id, " ".join(rest))

    if verb_l in ("仓", "larder", "公仓", "库"):
        return await multi.alliance_ops(key_id, "larder")

    if verb_l in ("捐", "donate"):
        if len(parts) < 3:
            raise ValueError(
                "捐货：visit_ops 潮生会 捐 甘蓝 2\n"
                "捐票进潮汐基金：visit_ops 潮生会 基金 捐 50"
            )
        if parts[1].isdigit() or parts[1] in ("票", "工分票"):
            raise ValueError(
                "捐票请走潮汐基金：visit_ops 潮生会 基金 捐 50\n"
                "捐货进公仓仍是：visit_ops 潮生会 捐 甘蓝 2"
            )
        item = _resolve_item(parts[1])
        qty = _parse_int(parts[2], "数量")
        return await multi.alliance_ops(key_id, f"donate {item} {qty}")

    if verb_l in ("取", "draw", "领货"):
        if len(parts) < 3:
            raise ValueError("用法：visit_ops 潮生会 取 甘蓝 1")
        item = _resolve_item(parts[1])
        qty = _parse_int(parts[2], "数量")
        return await multi.alliance_ops(key_id, f"draw {item} {qty}")

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
        from . import commons as commons_mod
        rest = " ".join(parts[1:]) if len(parts) > 1 else "scan"
        if not rest or rest.lower() in ("scan", "看"):
            rest = "scan"
        return await commons_mod.commons_ops(key_id, rest)

    if verb_l in ("领", "claim"):
        if len(parts) >= 2 and parts[1] in ("补贴", "基金"):
            return await fund_claim(key_id)
        if len(parts) < 2:
            raise ValueError(
                "领公物：visit_ops 潮生会 领 编号\n"
                "领潮汐基金补贴：visit_ops 潮生会 补贴"
            )
        from . import commons as commons_mod
        return await commons_mod.commons_ops(key_id, f"claim {parts[1]}")

    raise ValueError(f"未知潮生会指令: {command}\n{CHAOSHEN_HELP}")


async def public_snapshot() -> dict[str, Any]:
    league = await multi.league_snapshot()
    pulse = await events.public_pulse_snapshot()
    async with db.connect() as conn:
        conn.row_factory = None
        larder_rows = await (await conn.execute(
            "SELECT item, quantity FROM larder WHERE quantity > 0 ORDER BY quantity DESC, item LIMIT 8"
        )).fetchall()
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
            WHERE action IN ('donate', 'league', 'commons', 'fund')
            ORDER BY created_at DESC LIMIT 8
            """
        )).fetchall()
        from . import commons as commons_mod
        commons_rows = await commons_mod._active_spawns(conn)
        now = db.now()
        commons_live = sum(1 for r in commons_rows if r["appears_at"] <= now)
        larder_kinds = (await (await conn.execute(
            "SELECT COUNT(*) FROM larder WHERE quantity > 0"
        )).fetchone())[0]
        fund = await fund_snapshot(conn)

    return {
        "org": ORG_NAME,
        "clerk": CLERK_NAME,
        "line": flavor.pick(_DOOR_LINES),
        "climate": world.climate_line(),
        "league": {
            "label": league.get("label") or "",
            "progress": int(league.get("progress") or 0),
            "target": int(league.get("target") or 0),
            "completed": bool(league.get("completed")),
        },
        "pulse": pulse,
        "fund": {
            "name": FUND_NAME,
            "pool": fund["pool"],
            "avg": fund["avg"],
            "n": fund["n"],
            "ready": fund["ready"],
            "donated_total": fund["donated_total"],
            "paid_total": fund["paid_total"],
        },
        "larder": [
            {
                "item": r[0],
                "name": ITEM_NAMES.get(r[0], r[0]),
                "qty": int(r[1]),
            }
            for r in larder_rows
        ],
        "larder_kinds": int(larder_kinds),
        "beacons": [
            {"author": r[1], "body": (r[0] or "")[:80], "created_at": r[2]}
            for r in beacons
        ],
        "commons_live": int(commons_live),
        "recent": [
            {"text": r[0], "created_at": r[1]}
            for r in recent
        ],
        "note": "潮生会管事，不收人。上岛已在册。办事去上手页。",
    }
