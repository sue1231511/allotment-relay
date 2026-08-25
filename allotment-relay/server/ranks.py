"""全服排行榜 — 工分票榜 + 岛缘榜。

票榜看口袋里现在有多少张。岛缘榜看账号总养成（岸上动手只加，井下减，无上限）。
等级（1～99、累计入账）仍在 sheet 上，不再单独占一栏全服榜。
"""
from __future__ import annotations

import math
from typing import Any

import aiosqlite

from . import db

MAX_LEVEL = 99
BOARD_LIMIT = 20
MCP_LIMIT = 12

# 称号按等级门槛，从高到低匹配
TITLES: tuple[tuple[int, str], ...] = (
    (99, "潮汐本尊"),
    (90, "岛上的传说"),
    (80, "百年岸人"),
    (70, "潮渊老人"),
    (60, "半个岛"),
    (50, "岸上的根"),
    (40, "潮痕"),
    (30, "潮声旧人"),
    (25, "岛上的影子"),
    (20, "潮汐老人"),
    (16, "盟里有名"),
    (12, "老岸人"),
    (8, "潮客"),
    (5, "份地手"),
    (3, "岸民"),
    (1, "新客"),
)


def xp_to_reach(level: int) -> int:
    """升到该级所需累计入账。Lv1 = 0。公式 18 × (L-1) × L。"""
    if level <= 1:
        return 0
    n = min(int(level), MAX_LEVEL + 1)
    return 18 * (n - 1) * n


def level_from_xp(xp: int) -> int:
    xp = max(0, int(xp or 0))
    # L(L-1) <= xp/18  →  L = (1 + sqrt(1 + 4*xp/18)) / 2
    lvl = int((1 + math.sqrt(1 + (4 * xp) / 18.0)) / 2)
    return max(1, min(MAX_LEVEL, lvl))


def title_for_level(level: int) -> str:
    level = int(level or 1)
    for threshold, title in TITLES:
        if level >= threshold:
            return title
    return "新客"


def progress_line(xp: int) -> str:
    xp = max(0, int(xp or 0))
    lvl = level_from_xp(xp)
    title = title_for_level(lvl)
    if lvl >= MAX_LEVEL:
        return f"等级 Lv{lvl} {title}（满级 · 累计入账 {xp}）"
    cur = xp_to_reach(lvl)
    nxt = xp_to_reach(lvl + 1)
    have = xp - cur
    need = nxt - cur
    return f"等级 Lv{lvl} {title}（{have}/{need} 距下级 · 累计入账 {xp}）"


def attach_level(row: dict[str, Any]) -> dict[str, Any]:
    from . import bond as bond_mod
    from . import progress as progress_mod

    xp = int(row.get("xp") or 0)
    lvl = level_from_xp(xp)
    n = int(row.get("island_bond") or 0)
    out = dict(row)
    out["xp"] = xp
    out["level"] = lvl
    out["title"] = title_for_level(lvl)
    out["display_title"] = progress_mod.display_title(out)
    out["island_bond"] = n
    out["bond_flavor"] = bond_mod.flavor(n)
    return out


def sheet_level_line(steward: dict[str, Any]) -> str:
    return progress_line(int(steward.get("xp") or 0))


async def seed_xp(conn: aiosqlite.Connection) -> None:
    """老存档：还没入账记录的，用当前票 + 产业估一笔起步经验。"""
    await conn.execute(
        """
        UPDATE stewards SET xp =
            tickets
            + parcel_count * 20
            + COALESCE(orchard_count, 0) * 20
            + COALESCE(hut_level, 0) * 40
            + COALESCE(greenhouse_count, 0) * 50
            + CASE WHEN greenhouse = 1 AND COALESCE(greenhouse_count, 0) = 0 THEN 50 ELSE 0 END
            + CASE WHEN COALESCE(barn_built, 0) = 1 THEN 50 ELSE 0 END
            + CASE WHEN COALESCE(eatery_open, 0) = 1 THEN 40 ELSE 0 END
        WHERE enrolled = 1 AND COALESCE(xp, 0) = 0
        """
    )


async def _board_rows(
    conn: aiosqlite.Connection,
    *,
    order: str,
    limit: int,
) -> list[dict[str, Any]]:
    conn.row_factory = aiosqlite.Row
    cur = await conn.execute(
        f"""
        SELECT id, name, badge, tickets,
               COALESCE(xp, 0) AS xp,
               COALESCE(island_bond, 0) AS island_bond,
               last_active_at
        FROM stewards
        WHERE enrolled = 1
        ORDER BY {order}
        LIMIT ?
        """,
        (limit,),
    )
    return [attach_level(dict(r)) for r in await cur.fetchall()]


async def ticket_board(limit: int = BOARD_LIMIT) -> list[dict[str, Any]]:
    async with db.connect() as conn:
        return await _board_rows(
            conn, order="tickets DESC, xp DESC, id ASC", limit=limit
        )


async def bond_board(limit: int = BOARD_LIMIT) -> list[dict[str, Any]]:
    async with db.connect() as conn:
        return await _board_rows(
            conn, order="island_bond DESC, tickets DESC, id ASC", limit=limit
        )


async def level_board(limit: int = BOARD_LIMIT) -> list[dict[str, Any]]:
    """旧名。全服第二栏已改成岛缘榜，数据源是 island_bond。"""
    return await bond_board(limit)


async def _rank_of(
    conn: aiosqlite.Connection,
    steward: dict[str, Any],
    *,
    kind: str,
) -> int:
    sid = steward["id"]
    tickets = int(steward.get("tickets") or 0)
    xp = int(steward.get("xp") or 0)
    bond = int(steward.get("island_bond") or 0)
    if kind == "tickets":
        cur = await conn.execute(
            """
            SELECT COUNT(*) FROM stewards
            WHERE enrolled = 1 AND (
                tickets > ?
                OR (tickets = ? AND COALESCE(xp, 0) > ?)
                OR (tickets = ? AND COALESCE(xp, 0) = ? AND id < ?)
            )
            """,
            (tickets, tickets, xp, tickets, xp, sid),
        )
    else:
        cur = await conn.execute(
            """
            SELECT COUNT(*) FROM stewards
            WHERE enrolled = 1 AND (
                COALESCE(island_bond, 0) > ?
                OR (COALESCE(island_bond, 0) = ? AND tickets > ?)
                OR (COALESCE(island_bond, 0) = ? AND tickets = ? AND id < ?)
            )
            """,
            (bond, bond, tickets, bond, tickets, sid),
        )
    ahead = (await cur.fetchone())[0]
    return int(ahead) + 1


async def my_ranks(steward: dict[str, Any]) -> dict[str, Any]:
    s = attach_level(steward)
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        total = (await (await conn.execute(
            "SELECT COUNT(*) FROM stewards WHERE enrolled = 1"
        )).fetchone())[0]
        ticket_rank = await _rank_of(conn, s, kind="tickets")
        bond_rank = await _rank_of(conn, s, kind="bond")
    s["ticket_rank"] = ticket_rank
    s["bond_rank"] = bond_rank
    s["level_rank"] = bond_rank
    s["total"] = int(total)
    return s


def _fmt_row(i: int, row: dict[str, Any], *, kind: str) -> str:
    from . import bond as bond_mod

    mark = {1: "①", 2: "②", 3: "③"}.get(i, f"{i:>2}.")
    if kind == "tickets":
        return (
            f"  {mark} {row['name']}  {row['tickets']} 票"
            f"  · Lv{row['level']} {row['title']}"
        )
    n = int(row.get("island_bond") or 0)
    return (
        f"  {mark} {row['name']}  {bond_mod.fmt(n)} ∞"
        f" · {row.get('bond_flavor') or bond_mod.flavor(n)}"
    )


def _fmt_board(title: str, rows: list[dict[str, Any]], *, kind: str) -> list[str]:
    lines = [title]
    if not rows:
        lines.append("  还没有人上榜。steward_ops enroll 之后就会出现。")
        return lines
    for i, row in enumerate(rows, 1):
        lines.append(_fmt_row(i, row, kind=kind))
    return lines


async def public_board(limit: int = BOARD_LIMIT) -> dict[str, Any]:
    from . import bond as bond_mod

    tickets = await ticket_board(limit)
    bonds = await bond_board(limit)

    ticket_lead = None
    if tickets:
        top = tickets[0]
        gap = int(top["tickets"]) - int(tickets[1]["tickets"]) if len(tickets) > 1 else 0
        ticket_lead = {
            "name": top["name"],
            "tickets": int(top["tickets"]),
            "level": int(top["level"]),
            "title": top.get("display_title") or top.get("title") or "",
            "gap_second": gap,
        }

    bond_lead = None
    if bonds:
        top = bonds[0]
        n = int(top["island_bond"])
        prog = bond_mod.flavor_progress(n)
        gap = n - int(bonds[1]["island_bond"]) if len(bonds) > 1 else 0
        bond_lead = {
            "name": top["name"],
            "bond": n,
            "flavor": top.get("bond_flavor") or bond_mod.flavor(n),
            "gap_second": gap,
            "next_need": prog["next_need"],
            "next_label": prog["next_label"],
            "to_next": prog["to_next"],
            "progress_pct": prog["pct"],
            "cur_need": prog["cur_need"],
        }

    avg_bond = 0.0
    if bonds:
        avg_bond = round(sum(int(r["island_bond"]) for r in bonds) / len(bonds), 1)
    top10_floor = (
        int(bonds[9]["island_bond"]) if len(bonds) >= 10
        else (int(bonds[-1]["island_bond"]) if bonds else 0)
    )

    return {
        "tickets": tickets,
        "bonds": bonds,
        "levels": bonds,
        "limit": limit,
        "count": max(len(tickets), len(bonds)),
        "ticket_lead": ticket_lead,
        "bond_lead": bond_lead,
        "level_lead": bond_lead,
        "notes": {
            "avg_bond": avg_bond,
            "top10_bond_floor": top10_floor,
            "ticket_top_name": ticket_lead["name"] if ticket_lead else "",
            "bond_top_name": bond_lead["name"] if bond_lead else "",
            "bond_top": bond_lead["bond"] if bond_lead else 0,
        },
    }


BOND_BOARD_TITLE = "全服岛缘榜（岸上动手只加，井下减，无上限）"


async def board_ops(key_id: int, command: str = "") -> str:
    from . import bond as bond_mod
    from .game import require_steward
    s = await require_steward(key_id, exempt_duty=True)
    s = await db.get_steward_by_id(s["id"]) or s
    raw = (command or "").strip()
    verb = raw.split()[0].lower() if raw else "status"
    mine = await my_ranks(s)
    you = (
        f"你：{mine['name']}  {mine['tickets']} 票"
        f" · 岛缘 {bond_mod.fmt(mine['island_bond'])} ∞ · {mine['bond_flavor']}"
        f" · 票榜 #{mine['ticket_rank']}/{mine['total']}"
        f" · 岛缘榜 #{mine['bond_rank']}/{mine['total']}"
    )

    aliases_tickets = {"tickets", "ticket", "票", "票榜", "工分票", "钱"}
    aliases_bond = {
        "level", "levels", "xp", "等级", "等级榜", "经验",
        "岛缘", "bond", "缘", "岛缘榜", "bonds",
    }
    aliases_me = {"me", "mine", "我", "自己"}
    aliases_status = {"", "status", "board", "help", "榜", "排行", "排行榜"}

    if verb in aliases_me:
        return you

    if verb in aliases_tickets:
        rows = await ticket_board(MCP_LIMIT)
        return "\n".join(_fmt_board("全服工分票榜（口袋现票）", rows, kind="tickets") + ["", you])

    if verb in aliases_bond:
        rows = await bond_board(MCP_LIMIT)
        return "\n".join(_fmt_board(BOND_BOARD_TITLE, rows, kind="bond") + ["", you])

    if verb in aliases_status:
        t_rows = await ticket_board(MCP_LIMIT)
        b_rows = await bond_board(MCP_LIMIT)
        return "\n".join([
            *_fmt_board("全服工分票榜（口袋现票）", t_rows, kind="tickets"),
            "",
            *_fmt_board(BOND_BOARD_TITLE, b_rows, kind="bond"),
            "",
            you,
            "steward_ops board tickets · steward_ops board 岛缘 · steward_ops board me",
            "board level / board 等级榜 仍可用，指向同一张岛缘榜。不是周目标贡献榜。",
        ])

    raise ValueError(
        "未知 board 指令（tickets / 岛缘 / me / status）。"
        "board level、board 等级榜 仍可用，指向岛缘榜。"
    )
