"""合伙船 — §五十七：多人合买大船，收益和维修共同承担。"""
from __future__ import annotations

import math
from typing import Any

from . import db
from .catalog import ITEM_NAMES
from .config import BOATS
from .game import require_steward

RAPPORT_SHARE = 50
MAX_MEMBERS = 3
SHARE_BOATS = frozenset(
    k for k, m in BOATS.items() if int(m.get("rank") or 0) >= 2
)


async def ensure_tables(conn) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS neighbor_boat_share (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            founder_id INTEGER NOT NULL,
            boat_key TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS neighbor_boat_share_member (
            share_id INTEGER NOT NULL,
            steward_id INTEGER NOT NULL,
            paid INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (share_id, steward_id)
        )
        """
    )


async def _rapport(conn, a: int, b: int) -> int:
    from . import social as social_mod
    return await social_mod.get_rapport(a, b, conn=conn)


def _boat_meta(key: str) -> dict:
    meta = BOATS.get(key)
    if not meta:
        raise ValueError("没有这种船")
    return meta


def _resolve_boat(token: str) -> str:
    raw = (token or "").strip()
    if raw in BOATS:
        if raw not in SHARE_BOATS:
            raise ValueError("合伙只合买大船（切波艇/近海帆撬/漂航船/延绳船），舢板自己买")
        return raw
    for key, meta in BOATS.items():
        if meta["name"] == raw or raw in meta["name"]:
            if key not in SHARE_BOATS:
                raise ValueError("合伙只合买大船（切波艇/近海帆撬/漂航船/延绳船），舢板自己买")
            return key
    raise ValueError("船型：切波艇 · 近海帆撬 · 漂航船 · 延绳船（alliance_ops 合伙 开 漂航船）")


async def _member_share(conn, steward_id: int) -> dict | None:
    cur = await conn.execute(
        """
        SELECT s.id, s.founder_id, s.boat_key, s.status
        FROM neighbor_boat_share_member m
        JOIN neighbor_boat_share s ON s.id=m.share_id
        WHERE m.steward_id=? AND s.status IN ('open','active')
        """,
        (steward_id,),
    )
    row = await cur.fetchone()
    if not row:
        return None
    return {"id": row[0], "founder_id": row[1], "boat_key": row[2], "status": row[3]}


async def _members(conn, share_id: int) -> list[dict]:
    cur = await conn.execute(
        """
        SELECT m.steward_id, m.paid, st.name
        FROM neighbor_boat_share_member m
        JOIN stewards st ON st.id=m.steward_id
        WHERE m.share_id=?
        ORDER BY m.steward_id
        """,
        (share_id,),
    )
    return [
        {"id": r[0], "paid": int(r[1]), "name": r[2]}
        for r in await cur.fetchall()
    ]


async def share_boat_key(conn, steward_id: int) -> str | None:
    row = await _member_share(conn, steward_id)
    if not row or row["status"] != "active":
        return None
    return row["boat_key"]


async def share_founder_id(conn, steward_id: int) -> int | None:
    row = await _member_share(conn, steward_id)
    if not row or row["status"] != "active":
        return None
    return int(row["founder_id"])


def _share_cost(boat_key: str, n: int) -> int:
    cost = int(_boat_meta(boat_key)["cost"])
    return max(1, math.ceil(cost / max(2, n)))
