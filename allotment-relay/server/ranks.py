"""全服排行榜 — 管理员等级 + 工分票榜。

等级跟累计入账（赚到的票，花掉不降级）。票榜看口袋里现在有多少张。
"""
from __future__ import annotations

import math
from typing import Any

import aiosqlite

from . import db

MAX_LEVEL = 30
BOARD_LIMIT = 20
MCP_LIMIT = 12

# 称号按等级门槛，从高到低匹配
TITLES: tuple[tuple[int, str], ...] = (
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
    xp = int(row.get("xp") or 0)
    lvl = level_from_xp(xp)
    out = dict(row)
    out["xp"] = xp
    out["level"] = lvl
    out["title"] = title_for_level(lvl)
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
            + COALESCE(hut_level, 0) * 40
            + CASE WHEN greenhouse = 1 THEN 50 ELSE 0 END
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
        SELECT id, name, badge, tickets, COALESCE(xp, 0) AS xp, last_active_at
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


async def level_board(limit: int = BOARD_LIMIT) -> list[dict[str, Any]]:
    async with db.connect() as conn:
        return await _board_rows(
            conn, order="xp DESC, tickets DESC, id ASC", limit=limit
        )


async def _rank_of(
    conn: aiosqlite.Connection,
    steward: dict[str, Any],
    *,
    kind: str,
) -> int:
    sid = steward["id"]
    tickets = int(steward.get("tickets") or 0)
    xp = int(steward.get("xp") or 0)
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
                COALESCE(xp, 0) > ?
                OR (COALESCE(xp, 0) = ? AND tickets > ?)
                OR (COALESCE(xp, 0) = ? AND tickets = ? AND id < ?)
            )
            """,
            (xp, xp, tickets, xp, tickets, sid),
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
        level_rank = await _rank_of(conn, s, kind="level")
    s["ticket_rank"] = ticket_rank
    s["level_rank"] = level_rank
    s["total"] = int(total)
    return s


def _fmt_row(i: int, row: dict[str, Any], *, kind: str) -> str:
    mark = {1: "①", 2: "②", 3: "③"}.get(i, f"{i:>2}.")
    if kind == "tickets":
        return (
            f"  {mark} {row['name']}  {row['tickets']} 票"
            f"  · Lv{row['level']} {row['title']}"
        )
    return (
        f"  {mark} {row['name']}  Lv{row['level']} {row['title']}"
        f"  · {row['xp']} 入账 · {row['tickets']} 票"
    )


def _fmt_board(title: str, rows: list[dict[str, Any]], *, kind: str) -> list[str]:
    lines = [title]
    if not rows:
        lines.append("  还没有人上榜。steward_enroll 之后就会出现。")
        return lines
    for i, row in enumerate(rows, 1):
        lines.append(_fmt_row(i, row, kind=kind))
    return lines


async def public_board(limit: int = BOARD_LIMIT) -> dict[str, Any]:
    tickets = await ticket_board(limit)
    levels = await level_board(limit)
    return {
        "tickets": tickets,
        "levels": levels,
        "limit": limit,
    }


async def board_ops(key_id: int, command: str = "") -> str:
    from .game import require_steward
    s = await require_steward(key_id, exempt_duty=True)
    s = await db.get_steward_by_id(s["id"]) or s
    raw = (command or "").strip()
    verb = raw.split()[0].lower() if raw else "status"
    mine = await my_ranks(s)
    you = (
        f"你：{mine['name']}  {mine['tickets']} 票"
        f" · {progress_line(mine['xp'])}"
        f" · 票榜 #{mine['ticket_rank']}/{mine['total']}"
        f" · 等级榜 #{mine['level_rank']}/{mine['total']}"
    )

    aliases_tickets = {"tickets", "ticket", "票", "票榜", "工分票", "钱"}
    aliases_level = {"level", "levels", "xp", "等级", "等级榜", "经验"}
    aliases_me = {"me", "mine", "我", "自己"}
    aliases_status = {"", "status", "board", "help", "榜", "排行", "排行榜"}

    if verb in aliases_me:
        return you

    if verb in aliases_tickets:
        rows = await ticket_board(MCP_LIMIT)
        return "\n".join(_fmt_board("全服工分票榜（口袋现票）", rows, kind="tickets") + ["", you])

    if verb in aliases_level:
        rows = await level_board(MCP_LIMIT)
        return "\n".join(_fmt_board("全服等级榜（累计入账，花掉不降级）", rows, kind="level") + ["", you])

    if verb in aliases_status:
        t_rows = await ticket_board(MCP_LIMIT)
        l_rows = await level_board(MCP_LIMIT)
        return "\n".join([
            *_fmt_board("全服工分票榜（口袋现票）", t_rows, kind="tickets"),
            "",
            *_fmt_board("全服等级榜（累计入账，花掉不降级）", l_rows, kind="level"),
            "",
            you,
            "board_ops tickets · board_ops level · board_ops me",
        ])

    raise ValueError("未知 board 指令（tickets/level/me/status）")
