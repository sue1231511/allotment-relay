"""台风季 — 秋季周的全岛事件：预报 → 备灾 → 周四夜登陆结算。

每个秋季周（一周一季）一座台风：周一换班起潮生会出预报，周四
东八区 20:00 登陆。登陆前岛民三选一备灾（加固小屋 / 抢收熟菜 /
闭门不出），全岛凑防灾工程（捐岸木或票）；工程凑满全岛无恙。
结算惰性触发：任何台风命令先补结算，幂等。
"""
from __future__ import annotations

from typing import Any

import aiosqlite

from . import config, db

LANDFALL_OFFSET = (3 * 86400) + (20 * 3600)  # 本周一 00:00 + 周四 20:00
PREP_HOUSE_TICKETS = 20      # 加固小屋
PREP_HARVEST_ENERGY = 12     # 抢收熟菜（收成归自己）
PROJECT_GOAL_PER_PEER = 8    # 防灾工程目标：活跃岛民每人 8 票当量
WOOD_TICKET_VALUE = 5        # 一根岸木抵 5 票当量
HOUSE_LOSS_MIN = 10
HOUSE_LOSS_MAX = 20
CROP_LOSS_CHANCE = 0.5

PREP_KINDS = {
    "加固": "house",
    "抢收": "harvest",
    "闭门": "hunker",
}


def _is_typhoon_week(ts: int | None = None) -> bool:
    from .season import current_season
    from .disaster import CST
    from datetime import datetime

    at = datetime.fromtimestamp(ts if ts is not None else db.now(), CST)
    return current_season(at) == "秋"


def _event_week(ts: int | None = None) -> int:
    from .disaster import cst_week_ordinal

    return cst_week_ordinal(ts)


def _landfall_at(ts: int | None = None) -> int:
    from .disaster import cst_week_start

    return cst_week_start(ts) + LANDFALL_OFFSET


async def ensure_event(conn: aiosqlite.Connection) -> dict[str, Any] | None:
    """秋季周确保有一行台风事件；非秋季周返回 None。"""
    if not _is_typhoon_week():
        return None
    week = _event_week()
    conn.row_factory = aiosqlite.Row
    row = await (await conn.execute(
        "SELECT * FROM typhoon_events WHERE week=?", (week,)
    )).fetchone()
    if row:
        return dict(row)
    await conn.execute(
        """
        INSERT INTO typhoon_events (week, phase, landfall_at, created_at)
        VALUES (?, 'pending', ?, ?)
        """,
        (week, _landfall_at(), db.now()),
    )
    await conn.commit()
    row = await (await conn.execute(
        "SELECT * FROM typhoon_events WHERE week=?", (week,)
    )).fetchone()
    return dict(row)


async def typhoon_ops(key_id: int, command: str = "") -> str:
    from .game import require_steward

    s = await require_steward(key_id, exempt_duty=True)
    parts = (command or "").strip().split()
    verb = parts[0] if parts else "看"

    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        ev = await ensure_event(conn)
        if not ev:
            return "本周不是台风季。秋季的那一周潮生会会出台风预报，周四夜里登陆。"
        settled = await _ensure_settled(conn, ev, s["id"])
        if settled is not None:
            return settled

        if verb in ("看", "台风", "status", "help", "?"):
            return await _forecast(conn, ev, s["id"])

        if verb == "备灾" and len(parts) >= 2:
            return await _prep(conn, ev, s, parts[1])

        if verb == "捐" and len(parts) >= 3:
            return await _donate(conn, ev, s, parts[1], _to_int(parts[2]))

    raise ValueError("用法：潮生会 台风 · 台风 备灾 加固|抢收|闭门 · 台风 捐 票 10 / 捐 岸木 2")


def _to_int(raw: str) -> int:
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError("数量要写数字") from exc


async def _project_view(conn: aiosqlite.Connection, ev: dict[str, Any]) -> tuple[int, int]:
    peers = (await (await conn.execute(
        "SELECT COUNT(*) FROM stewards WHERE enrolled=1"
    )).fetchone())[0]
    goal = max(20, int(peers) * PROJECT_GOAL_PER_PEER)
    got = int(ev["prep_wood"] or 0) * WOOD_TICKET_VALUE + int(ev["prep_tickets"] or 0)
    return got, goal


async def _forecast(conn: aiosqlite.Connection, ev: dict[str, Any], steward_id: int) -> str:
    now = db.now()
    prepped = await (await conn.execute(
        "SELECT kind FROM typhoon_preps WHERE event_id=? AND steward_id=?",
        (ev["id"], steward_id),
    )).fetchone()
    got, goal = await _project_view(conn, ev)
    prep_label = {"house": "已加固小屋", "harvest": "已抢收熟菜", "hunker": "已决定闭门"}
    lines = [
        f"【台风预报】本季台风周四 20:00（东八区）登陆，还有 {max(0, (ev['landfall_at'] - now) // 3600)} 小时。",
        "不备灾的话：屋顶要修（10~20 票），地里的熟菜可能被浪头打落一半。",
        "备灾三选一（一季一次）：",
        "  潮生会 台风 备灾 加固 — 20 票，屋顶稳了",
        "  潮生会 台风 备灾 抢收 — 12 精力，熟菜全收进自己行囊",
        "  潮生会 台风 备灾 闭门 — 免费，损失掷半",
        f"全岛防灾工程：{got}/{goal} 票当量（捐 岸木 N / 票 N；凑满全岛无恙）",
    ]
    if prepped:
        lines.append(f"你已备灾：{prep_label.get(prepped['kind'], prepped['kind'])}")
    return "\n".join(lines)


async def _prep(conn: aiosqlite.Connection, ev: dict[str, Any], s: dict[str, Any], kind_raw: str) -> str:
    kind = PREP_KINDS.get(kind_raw)
    if not kind:
        raise ValueError("备灾三选一：加固 / 抢收 / 闭门")
    if db.now() >= ev["landfall_at"]:
        raise ValueError("台风已经登陆，备灾来不及了")
    dup = await (await conn.execute(
        "SELECT 1 FROM typhoon_preps WHERE event_id=? AND steward_id=?",
        (ev["id"], s["id"]),
    )).fetchone()
    if dup:
        raise ValueError("这一季已经备过灾了，一季一次")
    if kind == "house":
        cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
        if (await cur.fetchone())[0] < PREP_HOUSE_TICKETS:
            raise ValueError(f"加固要 {PREP_HOUSE_TICKETS} 票")
        await conn.execute(
            "UPDATE stewards SET tickets=tickets-? WHERE id=?",
            (PREP_HOUSE_TICKETS, s["id"]),
        )
    elif kind == "harvest":
        if int(s.get("energy") or 0) < PREP_HARVEST_ENERGY:
            raise ValueError(f"抢收要 {PREP_HARVEST_ENERGY} 精力")
        rows = await (await conn.execute(
            """
            SELECT * FROM parcels WHERE steward_id=? AND greenhouse=0 AND orchard=0
              AND crop IS NOT NULL AND ready_at>0 AND ready_at<=?
            """,
            (s["id"], db.now()),
        )).fetchall()
        from . import farming

        got: list[str] = []
        for plot in rows:
            item, qty, _keep = await farming.gather_yield(conn, s["id"], dict(plot))
            if qty > 0:
                await db.add_item(conn, s["id"], item, qty)
            await conn.execute(
                "UPDATE parcels SET crop=NULL, planted_at=NULL, ready_at=0, tended=0, "
                "dove_yield_mult=1.0 WHERE id=?",
                (plot["id"],),
            )
            got.append(f"{item}x{qty}")
        await conn.execute(
            "UPDATE stewards SET energy=energy-? WHERE id=?", (PREP_HARVEST_ENERGY, s["id"])
        )
        await conn.commit()
        await conn.execute(
            "INSERT INTO typhoon_preps (event_id, steward_id, kind, created_at) VALUES (?,?,?,?)",
            (ev["id"], s["id"], kind, db.now()),
        )
        await conn.commit()
        return (
            f"抢收完成：{len(rows)} 块地的熟菜进了行囊（{'、'.join(got) or '地里本来没有熟的'}），"
            f"台风来了也打不掉了"
        )
    await conn.execute(
        "INSERT INTO typhoon_preps (event_id, steward_id, kind, created_at) VALUES (?,?,?,?)",
        (ev["id"], s["id"], kind, db.now()),
    )
    await conn.commit()
    label = {
        "house": f"小屋加固好了（-{PREP_HOUSE_TICKETS} 票），屋顶这季稳了",
        "hunker": "决定闭门不出，登陆夜哪儿也不去（损失掷半）",
    }
    return label[kind]


async def _donate(conn: aiosqlite.Connection, ev: dict[str, Any], s: dict[str, Any], what: str, n: int) -> str:
    if n < 1:
        raise ValueError("数量至少 1")
    if what in ("票", "工分票", "tickets"):
        cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
        if (await cur.fetchone())[0] < n:
            raise ValueError("票不够")
        await conn.execute(
            "UPDATE stewards SET tickets=tickets-? WHERE id=?", (n, s["id"])
        )
        await conn.execute(
            "UPDATE typhoon_events SET prep_tickets=prep_tickets+? WHERE id=?", (n, ev["id"])
        )
        await conn.commit()
    elif what in ("岸木", "shorewood"):
        ok = await db.take_item(conn, s["id"], "wood_shore", n)
        if not ok:
            raise ValueError(f"行囊里没有 岸木 x{n}")
        await conn.execute(
            "UPDATE typhoon_events SET prep_wood=prep_wood+? WHERE id=?", (n, ev["id"])
        )
        await conn.commit()
    else:
        raise ValueError("捐 岸木 N 或 捐 票 N")
    ev_now = dict(await (await conn.execute(
        "SELECT * FROM typhoon_events WHERE id=?", (ev["id"],)
    )).fetchone())
    got, goal = await _project_view(conn, ev_now)
    await db.add_chronicle("typhoon", f"{s['name']} 给台风防灾工程捐了 {what} x{n}", s["id"], conn=conn)
    await conn.commit()
    if got >= goal:
        return f"防灾工程凑满了（{got}/{goal}）！周四登陆夜全岛无恙。"
    return f"防灾工程 {got}/{goal} 票当量，还差 {goal - got}。"


async def _ensure_settled(
    conn: aiosqlite.Connection, ev: dict[str, Any], asker_id: int
) -> str | None:
    """过了登陆时刻就补结算；返回结算报告，未到时刻返回 None。"""
    if ev["phase"] != "pending" or db.now() < ev["landfall_at"]:
        return None
    import random

    got, goal = await _project_view(conn, ev)
    shielded = got >= goal
    peers = await (await conn.execute(
        "SELECT id, name FROM stewards WHERE enrolled=1"
    )).fetchall()
    preps = {
        int(r["steward_id"]): r["kind"]
        for r in await (await conn.execute(
            "SELECT steward_id, kind FROM typhoon_preps WHERE event_id=?", (ev["id"],)
        )).fetchall()
    }
    loss_total = 0
    crop_hits = 0
    worst_name = ""
    worst_loss = -1
    saved_n = 0
    for p in peers:
        pid, pname = int(p["id"]), p["name"]
        kind = preps.get(pid)
        personal = 0
        # 修屋账
        lost_tickets = 0
        if not (shielded or kind == "house"):
            if not (kind == "hunker" and random.random() < 0.5):
                lost_tickets = random.randint(HOUSE_LOSS_MIN, HOUSE_LOSS_MAX)
                await conn.execute(
                    "UPDATE stewards SET tickets=MAX(0, tickets-?) WHERE id=?",
                    (lost_tickets, pid),
                )
        # 熟菜打落
        dropped = 0
        if not shielded and kind != "harvest":
            ripe = await (await conn.execute(
                """
                SELECT id FROM parcels WHERE steward_id=? AND greenhouse=0 AND orchard=0
                  AND crop IS NOT NULL AND ready_at>0 AND ready_at<=?
                """,
                (pid, db.now()),
            )).fetchall()
            for plot in ripe:
                if kind == "hunker" and random.random() < 0.5:
                    continue
                if random.random() < CROP_LOSS_CHANCE:
                    await conn.execute(
                        "UPDATE parcels SET crop=NULL, planted_at=NULL, ready_at=0, tended=0 "
                        "WHERE id=?",
                        (plot["id"],),
                    )
                    dropped += 1
        personal = lost_tickets + dropped
        crop_hits += dropped
        if personal == 0:
            saved_n += 1
            await db.add_chronicle(
                "typhoon", f"台风夜：{pname} 家无恙", None, pid, conn=conn
            )
        else:
            loss_total += personal
            parts_txt = []
            if lost_tickets:
                parts_txt.append(f"修屋 {lost_tickets} 票")
            if dropped:
                parts_txt.append(f"地里打落 {dropped} 块")
            await db.add_chronicle(
                "typhoon",
                f"台风夜：{pname} 家受了损（{'、'.join(parts_txt)}）",
                None, pid, conn=conn,
            )
        if personal > worst_loss:
            worst_loss = personal
            worst_name = pname
    summary = (
        f"台风过境：{'防灾工程凑满，全岛无恙' if shielded else f'{saved_n} 家无恙'}；"
        + (f"共损失约 {loss_total} 项（修屋票 + 打落熟菜 {crop_hits} 块）" if loss_total or crop_hits else "")
    )
    await conn.execute(
        "UPDATE typhoon_events SET phase='done', summary=? WHERE id=?",
        (summary, ev["id"]),
    )
    await conn.execute(
        "INSERT INTO hui_notices (tag, body, created_at, retracted) VALUES (?,?,?,0)",
        ("台风纪事", f"【台风过境】{summary}。备灾的都稳了，没备灾的修屋顶去吧。", db.now()),
    )
    await db.add_chronicle("typhoon", summary, None, conn=conn)
    await conn.commit()
    return f"{summary}\n（你家的情况看纪事；下一场台风在下一个秋季周）"


def is_typhoon_now(ts: int | None = None) -> bool:
    return _is_typhoon_week(ts)
