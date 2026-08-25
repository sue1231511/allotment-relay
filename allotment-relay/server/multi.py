from typing import Any

import aiosqlite

from . import db, world
from .catalog import ITEM_NAMES
from .config import (
    ASSIST_RAPPORT,
    ASSIST_TICKETS,
    FORAGE_COOLDOWN_DAY,
    LARDER_DRAW_FEE,
    LARDER_DRAWS_PER_DAY,
    LEAGUE_BONUS_TICKETS,
    LEAGUE_GOALS,
    ONLINE_WINDOW,
    SCRUMP_DAILY,
)
from .game import require_steward, _parse_int


def _ago(ts: int) -> str:
    delta = max(0, db.now() - int(ts or 0))
    if delta < 60:
        return "刚刚"
    if delta < 3600:
        return f"{delta // 60} 分钟前"
    if delta < 86400:
        return f"{delta // 3600} 小时前"
    return f"{delta // 86400} 天前"


async def _ripe_outdoor_count(conn: aiosqlite.Connection, steward_id: int) -> int:
    from . import farming
    conn.row_factory = aiosqlite.Row
    rows = await (await conn.execute(
        "SELECT * FROM parcels WHERE steward_id=? AND crop IS NOT NULL AND greenhouse=0",
        (steward_id,),
    )).fetchall()
    return sum(1 for r in rows if farming.plot_ready(dict(r)))


async def neighbor_roster(steward: dict[str, Any], *, online_only: bool = False) -> dict[str, Any]:
    """全岛管理员人数 + 邻居名册（不含自己）。peer / 偷菜 / assist 都要先有名字。"""
    cut = db.now() - ONLINE_WINDOW
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        total = int((await (await conn.execute(
            "SELECT COUNT(*) FROM stewards WHERE enrolled=1"
        )).fetchone())[0])
        rows = await (await conn.execute(
            """
            SELECT id, name, badge, last_active_at, COALESCE(xp, 0) AS xp,
                   COALESCE(worn_title, '') AS worn_title
            FROM stewards
            WHERE enrolled=1 AND id != ?
            ORDER BY last_active_at DESC LIMIT 40
            """,
            (steward["id"],),
        )).fetchall()
        peers = [dict(r) for r in rows]
        from . import ranks as ranks_mod
        from . import barn as barn_mod
        peers = [ranks_mod.attach_level(p) for p in peers]
        for p in peers:
            p["ripe"] = await _ripe_outdoor_count(conn, p["id"])
            p["barn"] = await barn_mod.stealable_count(conn, p["id"])
            p["home"] = bool(p["last_active_at"] and p["last_active_at"] > cut)

    if online_only:
        peers = [p for p in peers if p["home"]]
    people = [
        {
            "name": p["name"],
            "title": p.get("display_title") or p.get("title") or p["badge"],
            "ripe": int(p.get("ripe") or 0),
            "home": bool(p.get("home")),
            "ago": _ago(p["last_active_at"]),
        }
        for p in peers
    ]
    return {
        "total": total,
        "listed": len(people),
        "online": sum(1 for p in people if p["home"]),
        "window_min": ONLINE_WINDOW // 60,
        "people": people,
        "_peers": peers,
    }


async def list_neighbors(steward: dict[str, Any], *, online_only: bool = False) -> str:
    """在线管理员 + 邻居名册。peer / 偷菜 / assist 都要先有名字。"""
    roster = await neighbor_roster(steward, online_only=online_only)
    peers = roster["_peers"]

    if not peers and not online_only:
        return "联盟里还没有其他管理员。有人 enroll 之后才能串门、偷菜、assist。"

    def _line(p: dict[str, Any]) -> str:
        ripe = f"熟地 {p['ripe']}" if p["ripe"] else "暂无熟地"
        barn = f" · 可偷畜产 {p['barn']}" if p.get("barn") else ""
        steal_barn = f" · hut_ops barn 偷 {p['name']}" if p.get("barn") else ""
        return (
            f"- {p['name']} · {p.get('display_title') or p.get('title') or p['badge']} · {ripe}{barn} · {_ago(p['last_active_at'])}\n"
            f"  steward_ops peer {p['name']} · plot_ops 偷菜 {p['name']}{steal_barn} · alliance_ops assist {p['name']}"
        )

    home = [p for p in peers if p["home"]]
    away = [p for p in peers if not p["home"]]
    lines: list[str] = []
    if online_only:
        lines.append(f"在档口（{roster['window_min']} 分钟内有操作）:")
        if home:
            lines.extend(_line(p) for p in home)
        else:
            lines.append("（此刻没有别人在档口）")
            lines.append("全员邻居：alliance_ops 邻居  或  steward_ops 邻居")
        return "\n".join(lines)

    lines.append(
        f"邻居 {roster['listed']} 人 / 全岛 {roster['total']} 位管理员"
        f"（{roster['window_min']} 分钟内算在档口）:"
    )
    if home:
        lines.append("")
        lines.append("在档口:")
        lines.extend(_line(p) for p in home)
    if away:
        lines.append("")
        lines.append("不在档口:")
        lines.extend(_line(p) for p in away)
    lines.append("")
    lines.append(
        f"偷菜：plot_ops 偷菜 名字。最多掐走三成，永远留一把。"
        f"对方在档口、稻草人、守夜狗更容易被抓。"
        f"每日 {SCRUMP_DAILY} 次、同一人每天 1 次。温室摘不到。"
        f"牲口本身不能偷；未收的奶/蛋/蜜：hut_ops barn 偷 名字（和偷菜共用次数）。"
    )
    return "\n".join(lines)


def _week_id() -> int:
    return db.week_id()


def _day_id() -> int:
    return db.day_id()


def _pair_ids(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


async def _bump_rapport(conn: aiosqlite.Connection, a: int, b: int, delta: int) -> None:
    from . import shaonian as shaonian_mod
    mult = await shaonian_mod.rapport_multiplier(conn, a)
    if mult > 1.0 and delta > 0:
        delta = max(1, int(delta * mult))
    sa, sb = _pair_ids(a, b)
    await conn.execute(
        """
        INSERT INTO rapport (steward_a, steward_b, score) VALUES (?, ?, ?)
        ON CONFLICT(steward_a, steward_b) DO UPDATE SET score = score + excluded.score
        """,
        (sa, sb, delta),
    )


async def _get_rapport(a: int, b: int) -> int:
    sa, sb = _pair_ids(a, b)
    async with db.connect() as conn:
        cur = await conn.execute(
            "SELECT score FROM rapport WHERE steward_a=? AND steward_b=?",
            (sa, sb),
        )
        row = await cur.fetchone()
        return row[0] if row else 0


def _pick_league_goal(wid: int) -> dict[str, Any]:
    """抽周目标时跳过当季不能种的作物；没有合季作物就回落到甘蓝。"""
    from . import season as season_mod

    n = len(LEAGUE_GOALS)
    for i in range(n):
        goal = LEAGUE_GOALS[(wid + i) % n]
        item = goal.get("item") or ""
        if item.startswith("crop_") and not season_mod.crop_in_season(item[5:]):
            continue
        return goal
    return next(g for g in LEAGUE_GOALS if g["key"] == "crop_kale")


async def _ensure_league_week(conn: aiosqlite.Connection) -> dict[str, Any]:
    conn.row_factory = aiosqlite.Row
    wid = _week_id()
    cur = await conn.execute("SELECT * FROM league_week WHERE week_id=?", (wid,))
    row = await cur.fetchone()
    if row:
        return dict(row)
    goal = _pick_league_goal(wid)
    await conn.execute(
        "INSERT INTO league_week (week_id, goal_key, target, progress, completed) VALUES (?,?,?,0,0)",
        (wid, goal["key"], goal["target"]),
    )
    return {"week_id": wid, "goal_key": goal["key"], "target": goal["target"], "progress": 0, "completed": 0}


def _goal_meta(key: str) -> dict[str, Any]:
    for g in LEAGUE_GOALS:
        if g["key"] == key:
            return g
    return {"key": key, "label": key, "target": 0}


async def league_snapshot() -> dict[str, Any]:
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        row = await _ensure_league_week(conn)
        await conn.commit()
        meta = _goal_meta(row["goal_key"])
        return {
            "label": meta.get("label", row["goal_key"]),
            "progress": row["progress"],
            "target": row["target"],
            "completed": bool(row["completed"]),
        }


async def _league_add_progress(conn: aiosqlite.Connection, steward_id: int, amount: int = 1) -> str | None:
    row = await _ensure_league_week(conn)
    if row["completed"]:
        return None
    wid = row["week_id"]
    await conn.execute(
        "UPDATE league_week SET progress = progress + ? WHERE week_id=?",
        (amount, wid),
    )
    await conn.execute(
        """
        INSERT INTO league_contrib (week_id, steward_id, amount) VALUES (?,?,?)
        ON CONFLICT(week_id, steward_id) DO UPDATE SET amount = amount + excluded.amount
        """,
        (wid, steward_id, amount),
    )
    cur = await conn.execute("SELECT progress, target FROM league_week WHERE week_id=?", (wid,))
    prog, target = await cur.fetchone()
    from . import bond as bond_mod
    await bond_mod.grant(conn, steward_id, bond_mod.LEAGUE_STEP, "give")
    if prog >= target:
        await conn.execute(
            "UPDATE league_week SET completed=1, completed_at=? WHERE week_id=?",
            (db.now(), wid),
        )
        cur = await conn.execute("SELECT steward_id FROM league_contrib WHERE week_id=?", (wid,))
        for (sid,) in await cur.fetchall():
            await conn.execute(
                "UPDATE stewards SET tickets = tickets + ? WHERE id=?",
                (LEAGUE_BONUS_TICKETS, sid),
            )
            await bond_mod.grant(conn, int(sid), bond_mod.LEAGUE_DONE, "give")
        meta = _goal_meta(row["goal_key"])
        return f"联盟周目标「{meta['label']}」达成！参与者各 +{LEAGUE_BONUS_TICKETS} 票"
    return None


async def _league_on_item(conn: aiosqlite.Connection, steward_id: int, item: str, qty: int = 1) -> str | None:
    row = await _ensure_league_week(conn)
    if row["completed"]:
        return None
    meta = _goal_meta(row["goal_key"])
    if meta.get("item") != item:
        return None
    return await _league_add_progress(conn, steward_id, qty)


async def _league_on_assist(conn: aiosqlite.Connection, steward_id: int) -> str | None:
    row = await _ensure_league_week(conn)
    if row["completed"] or row["goal_key"] != "assist":
        return None
    return await _league_add_progress(conn, steward_id, 1)


async def on_league_item(steward_id: int, item: str, qty: int = 1) -> str | None:
    async with db.connect() as conn:
        bonus = await _league_on_item(conn, steward_id, item, qty)
        await conn.commit()
        return bonus


async def on_league_assist(steward_id: int) -> str | None:
    async with db.connect() as conn:
        bonus = await _league_on_assist(conn, steward_id)
        await conn.commit()
        return bonus


async def public_contracts_list() -> list[dict[str, Any]]:
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            """
            SELECT c.id, c.want_item, c.want_qty, c.reward_tickets, p.name AS poster
            FROM contracts c JOIN stewards p ON p.id = c.poster_id
            WHERE c.status='open' ORDER BY c.created_at DESC LIMIT 15
            """
        )).fetchall()
        return [
            {
                "id": r["id"],
                "poster": r["poster"],
                "item": r["want_item"],
                "item_name": ITEM_NAMES.get(r["want_item"], r["want_item"]),
                "quantity": r["want_qty"],
                "reward": r["reward_tickets"],
            }
            for r in rows
        ]


async def alliance_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    parts = command.strip().split(maxsplit=2)
    verb = parts[0].lower() if parts else "online"

    if verb in ("online", "在线"):
        return await list_neighbors(s, online_only=True)

    if verb in ("neighbors", "邻居", "neighbour", "cohort", "peers"):
        return await list_neighbors(s, online_only=False)

    if verb == "rapport" and len(parts) >= 2:
        peer = await db.get_steward_by_name(parts[1])
        if not peer:
            raise ValueError("找不到该管理员")
        score = await _get_rapport(s["id"], peer["id"])
        return f"与 {peer['name']} 的协作度：{score}（互助/合约/协助会提升）"

    if verb == "assist" and len(parts) >= 2:
        peer = await db.get_steward_by_name(parts[1])
        if not peer:
            raise ValueError("找不到该管理员")
        if peer["id"] == s["id"]:
            raise ValueError("不能 assist 自己")
        day = _day_id()
        extra_tickets = 0
        async with db.connect() as conn:
            cur = await conn.execute(
                "SELECT 1 FROM assist_log WHERE helper_id=? AND target_id=? AND day=?",
                (s["id"], peer["id"], day),
            )
            if await cur.fetchone():
                raise ValueError(f"今天已帮过 {peer['name']}，明天再来")
            cur = await conn.execute(
                "SELECT id FROM parcels WHERE steward_id=? AND crop IS NOT NULL AND tended=0",
                (peer["id"],),
            )
            rows = await cur.fetchall()
            if not rows:
                raise ValueError(f"{peer['name']} 的份地不需要打理")
            for (pid,) in rows:
                await conn.execute("UPDATE parcels SET tended=1 WHERE id=?", (pid,))
            await conn.execute(
                "INSERT INTO assist_log (helper_id, target_id, day) VALUES (?,?,?)",
                (s["id"], peer["id"], day),
            )
            await conn.execute(
                "UPDATE stewards SET tickets = tickets + ? WHERE id=?",
                (ASSIST_TICKETS, s["id"]),
            )
            await _bump_rapport(conn, s["id"], peer["id"], ASSIST_RAPPORT)
            from . import social as social_mod
            rapport = await social_mod.get_rapport(s["id"], peer["id"])
            extra_tickets = social_mod.assist_ticket_bonus(rapport)
            if extra_tickets:
                await conn.execute(
                    "UPDATE stewards SET tickets = tickets + ? WHERE id=?",
                    (extra_tickets, s["id"]),
                )
            bonus = await _league_on_assist(conn, s["id"])
            from . import bond as bond_mod
            await bond_mod.grant(conn, s["id"], bond_mod.ASSIST, "give")
            await conn.commit()
        ticket_gain = ASSIST_TICKETS + extra_tickets
        msg = f"{s['name']} 帮 {peer['name']} 打理了 {len(rows)} 块份地，+{ticket_gain} 票"
        if extra_tickets:
            msg += f"（协作度≥{social_mod.RAPPORT_ASSIST_BONUS} 额外 +{extra_tickets}）"
        await db.add_chronicle("assist", msg, s["id"], peer["id"])
        if bonus:
            await db.add_chronicle("league", bonus, s["id"])
            return msg + f"\n{bonus}"
        return msg

    if verb == "donate" and len(parts) >= 3:
        item, qty = parts[1], int(parts[2])
        async with db.connect() as conn:
            if not await db.take_item(conn, s["id"], item, qty):
                raise ValueError("行囊不足")
            await conn.execute(
                """
                INSERT INTO larder (item, quantity) VALUES (?, ?)
                ON CONFLICT(item) DO UPDATE SET quantity = quantity + excluded.quantity
                """,
                (item, qty),
            )
            bonus = await _league_on_item(conn, s["id"], item, qty)
            await conn.commit()
        msg = f"{s['name']} 向联盟储藏室捐赠 {ITEM_NAMES.get(item, item)} x{qty}"
        await db.add_chronicle("donate", msg, s["id"])
        if bonus:
            await db.add_chronicle("league", bonus, None)
            return msg + f"\n{bonus}"
        return msg

    if verb == "larder":
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            rows = await (await conn.execute(
                "SELECT item, quantity FROM larder WHERE quantity > 0 ORDER BY item"
            )).fetchall()
        if not rows:
            return "储藏室是空的，欢迎 donate"
        return "联盟储藏室：\n" + "\n".join(
            f"  {ITEM_NAMES.get(r['item'], r['item'])} x{r['quantity']}" for r in rows
        )

    if verb == "draw" and len(parts) >= 3:
        item, qty = parts[1], int(parts[2])
        day = _day_id()
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                "SELECT count FROM larder_draws WHERE steward_id=? AND day=?",
                (s["id"], day),
            )
            row = await cur.fetchone()
            used = row["count"] if row else 0
            if used >= LARDER_DRAWS_PER_DAY:
                raise ValueError(f"今日领取上限 {LARDER_DRAWS_PER_DAY}")
            cur = await conn.execute("SELECT quantity FROM larder WHERE item=?", (item,))
            lrow = await cur.fetchone()
            if not lrow or lrow[0] < qty:
                raise ValueError("储藏室库存不足")
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < LARDER_DRAW_FEE:
                raise ValueError(f"领取需 {LARDER_DRAW_FEE} 票")
            await conn.execute(
                "UPDATE larder SET quantity = quantity - ? WHERE item=?",
                (qty, item),
            )
            await db.add_item(conn, s["id"], item, qty)
            await conn.execute(
                "UPDATE stewards SET tickets = tickets - ? WHERE id=?",
                (LARDER_DRAW_FEE, s["id"]),
            )
            await conn.execute(
                """
                INSERT INTO larder_draws (steward_id, day, count) VALUES (?,?,1)
                ON CONFLICT(steward_id, day) DO UPDATE SET count = count + 1
                """,
                (s["id"], day),
            )
            await conn.commit()
        return f"从储藏室领取 {ITEM_NAMES.get(item, item)} x{qty}（-{LARDER_DRAW_FEE} 票）"

    raise ValueError(f"未知 alliance 指令: {command}")


async def contract_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    parts = command.strip().split()
    verb = parts[0].lower() if parts else "list"

    if verb == "list":
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            rows = await (await conn.execute(
                """
                SELECT c.*, p.name AS poster_name FROM contracts c
                JOIN stewards p ON p.id = c.poster_id
                WHERE c.status='open' ORDER BY c.created_at DESC LIMIT 20
                """
            )).fetchall()
        if not rows:
            return "暂无开放合约"
        return "\n".join(
            f"#{r['id']} {r['poster_name']} 要 {ITEM_NAMES.get(r['want_item'], r['want_item'])} x{r['want_qty']} "
            f"酬 {r['reward_tickets']} 票"
            for r in rows
        )

    if verb == "mine":
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            rows = await (await conn.execute(
                "SELECT * FROM contracts WHERE poster_id=? AND status='open' ORDER BY id DESC",
                (s["id"],),
            )).fetchall()
        if not rows:
            return "你没有挂出的合约"
        return "\n".join(
            f"#{r['id']} 要 {ITEM_NAMES.get(r['want_item'], r['want_item'])} x{r['want_qty']} "
            f"酬 {r['reward_tickets']} 票"
            for r in rows
        )

    if verb == "post" and len(parts) >= 4:
        item, qty, reward = parts[1], int(parts[2]), int(parts[3])
        if reward < 1:
            raise ValueError("酬劳至少 1 票")
        async with db.connect() as conn:
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < reward:
                raise ValueError("工分票不足以支付酬劳")
            await conn.execute(
                "UPDATE stewards SET tickets = tickets - ? WHERE id=?",
                (reward, s["id"]),
            )
            await conn.execute(
                """
                INSERT INTO contracts (poster_id, want_item, want_qty, reward_tickets, created_at)
                VALUES (?,?,?,?,?)
                """,
                (s["id"], item, qty, reward, db.now()),
            )
            await conn.commit()
        msg = f"{s['name']} 发布合约：{ITEM_NAMES.get(item, item)} x{qty}，酬 {reward} 票"
        await db.add_chronicle("contract", msg, s["id"])
        return msg + "（酬劳已托管）"

    if verb == "fill" and len(parts) >= 2:
        cid = _parse_int(parts[1], "合约编号")
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            c = dict(await (await conn.execute(
                "SELECT * FROM contracts WHERE id=? AND status='open'", (cid,)
            )).fetchone() or {})
            if not c:
                raise ValueError("合约不存在或已关闭")
            if c["poster_id"] == s["id"]:
                raise ValueError("不能交付自己的合约")
            if not await db.take_item(conn, s["id"], c["want_item"], c["want_qty"]):
                raise ValueError("行囊里没有足够物资")
            await db.add_item(conn, c["poster_id"], c["want_item"], c["want_qty"])
            await conn.execute(
                "UPDATE stewards SET tickets = tickets + ? WHERE id=?",
                (c["reward_tickets"], s["id"]),
            )
            await conn.execute(
                "UPDATE contracts SET status='filled', filler_id=? WHERE id=?",
                (s["id"], cid),
            )
            poster = await db.get_steward_by_id(c["poster_id"])
            await _bump_rapport(conn, s["id"], c["poster_id"], ASSIST_RAPPORT * 2)
            from . import bond as bond_mod
            await bond_mod.grant(conn, s["id"], bond_mod.CONTRACT_FILL, "give")
            await conn.commit()
        pname = poster["name"] if poster else "?"
        msg = f"{s['name']} 完成 {pname} 的合约 #{cid}，+{c['reward_tickets']} 票"
        await db.add_chronicle("contract_fill", msg, s["id"], c["poster_id"])
        return msg

    if verb == "cancel" and len(parts) >= 2:
        cid = _parse_int(parts[1], "合约编号")
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            c = dict(await (await conn.execute(
                "SELECT * FROM contracts WHERE id=? AND poster_id=? AND status='open'",
                (cid, s["id"]),
            )).fetchone() or {})
            if not c:
                raise ValueError("无法取消该合约")
            await conn.execute(
                "UPDATE stewards SET tickets = tickets + ? WHERE id=?",
                (c["reward_tickets"], s["id"]),
            )
            await conn.execute("UPDATE contracts SET status='cancelled' WHERE id=?", (cid,))
            await conn.commit()
        return f"合约 #{cid} 已取消，酬劳退回"

    raise ValueError(f"未知 contract 指令: {command}")


async def league_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    parts = command.strip().split()
    verb = parts[0].lower() if parts else "status"

    if verb == "status":
        snap = await league_snapshot()
        if snap["completed"]:
            return f"本周「{snap['label']}」已达成 ({snap['progress']}/{snap['target']})"
        return f"本周联盟目标：{snap['label']} {snap['progress']}/{snap['target']}"

    if verb == "contribute" and len(parts) >= 3:
        item, qty = parts[1], int(parts[2])
        async with db.connect() as conn:
            row = await _ensure_league_week(conn)
            if row["completed"]:
                raise ValueError("本周目标已完成")
            meta = _goal_meta(row["goal_key"])
            if meta.get("item") != item:
                raise ValueError(f"本周目标是「{meta['label']}」，请捐 {meta.get('item', '?')}")
            if not await db.take_item(conn, s["id"], item, qty):
                raise ValueError("行囊不足")
            bonus = await _league_add_progress(conn, s["id"], qty)
            await conn.commit()
        msg = f"{s['name']} 为联盟周目标贡献 {ITEM_NAMES.get(item, item)} x{qty}"
        await db.add_chronicle("league", msg, s["id"])
        if bonus:
            await db.add_chronicle("league", bonus, None)
            return msg + f"\n{bonus}"
        snap = await league_snapshot()
        return msg + f"\n进度 {snap['progress']}/{snap['target']}"

    if verb == "board":
        wid = _week_id()
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            row = await _ensure_league_week(conn)
            meta = _goal_meta(row["goal_key"])
            leaders = await (await conn.execute(
                """
                SELECT s.name, c.amount FROM league_contrib c
                JOIN stewards s ON s.id=c.steward_id
                WHERE c.week_id=? ORDER BY c.amount DESC LIMIT 8
                """,
                (wid,),
            )).fetchall()
        lines = [
            f"联盟周目标：{meta['label']} {row['progress']}/{row['target']}",
            "贡献榜：",
        ]
        if not leaders:
            lines.append("  尚无贡献 — league_ops contribute 物品 数量")
        for r in leaders:
            lines.append(f"  · {r['name']} +{r['amount']}")
        return "\n".join(lines)

    raise ValueError(f"未知 league 指令: {command}（status/contribute/board）")
