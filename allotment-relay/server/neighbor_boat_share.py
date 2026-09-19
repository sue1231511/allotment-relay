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


async def open_share(conn, founder: dict, boat_token: str) -> str:
    await ensure_tables(conn)
    if await _member_share(conn, founder["id"]):
        raise ValueError("你已经在一艘合伙船里。alliance_ops 合伙 状态")
    boat_key = _resolve_boat(boat_token)
    await conn.execute(
        """
        INSERT INTO neighbor_boat_share (founder_id, boat_key, status, created_at)
        VALUES (?,?, 'open', ?)
        """,
        (founder["id"], boat_key, db.now()),
    )
    cur = await conn.execute("SELECT last_insert_rowid()")
    share_id = int((await cur.fetchone())[0])
    await conn.execute(
        "INSERT INTO neighbor_boat_share_member (share_id, steward_id, paid) VALUES (?,?,0)",
        (share_id, founder["id"]),
    )
    name = _boat_meta(boat_key)["name"]
    each = _share_cost(boat_key, 2)
    return (
        f"合伙开了：{name}。再找 1～2 人 alliance_ops 合伙 入 {founder['name']}。"
        f"满 2 人各付 {each} 票才下水和。协作要 ≥{RAPPORT_SHARE}。"
        f"不是借船（借船是把自己的船借三天）。"
    )


async def join_share(conn, joiner: dict, founder_name: str) -> str:
    await ensure_tables(conn)
    if await _member_share(conn, joiner["id"]):
        raise ValueError("你已经在一艘合伙船里")
    founder = await db.get_steward_by_name(founder_name)
    if not founder:
        raise ValueError("找不到该岛民")
    if founder["id"] == joiner["id"]:
        raise ValueError("发起人不用入自己的伙")
    cur = await conn.execute(
        """
        SELECT id, boat_key, status FROM neighbor_boat_share
        WHERE founder_id=? AND status IN ('open','active')
        ORDER BY id DESC LIMIT 1
        """,
        (founder["id"],),
    )
    row = await cur.fetchone()
    if not row:
        raise ValueError(f"{founder['name']} 没有进行中的合伙。请对方 合伙 开 漂航船")
    share_id, boat_key, status = int(row[0]), row[1], row[2]
    members = await _members(conn, share_id)
    if any(m["id"] == joiner["id"] for m in members):
        raise ValueError("你已经在这艘伙里")
    if len(members) >= MAX_MEMBERS:
        raise ValueError(f"这艘伙满了（最多 {MAX_MEMBERS} 人）")
    r = await _rapport(conn, joiner["id"], founder["id"])
    if r < RAPPORT_SHARE:
        raise ValueError(f"合伙要协作 ≥{RAPPORT_SHARE}（当前 {r}）")
    if status == "active":
        buyin = _share_cost(boat_key, len(members) + 1)
        cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (joiner["id"],))
        have = int((await cur.fetchone())[0])
        if have < buyin:
            raise ValueError(f"入伙买位要 {buyin} 票（现 {have}）")
        await conn.execute(
            "UPDATE stewards SET tickets=tickets-? WHERE id=?",
            (buyin, joiner["id"]),
        )
        refund = buyin // max(1, len(members))
        for m in members:
            await conn.execute(
                "UPDATE stewards SET tickets=tickets+? WHERE id=?",
                (refund, m["id"]),
            )
        await conn.execute(
            "INSERT INTO neighbor_boat_share_member (share_id, steward_id, paid) VALUES (?,?,?)",
            (share_id, joiner["id"], buyin),
        )
        return (
            f"入伙 { _boat_meta(boat_key)['name'] }（-{buyin} 票）。"
            f"原船员各分回 {refund} 票。收益和维修共同承担。"
        )

    await conn.execute(
        "INSERT INTO neighbor_boat_share_member (share_id, steward_id, paid) VALUES (?,?,0)",
        (share_id, joiner["id"]),
    )
    members = await _members(conn, share_id)
    each = _share_cost(boat_key, len(members))
    paid_ok = True
    for m in members:
        cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (m["id"],))
        have = int((await cur.fetchone())[0])
        if have < each:
            paid_ok = False
            break
    name = _boat_meta(boat_key)["name"]
    if not paid_ok or len(members) < 2:
        return (
            f"已入伙，等人齐。{name} 满 2 人各付 {each} 票才下水。"
            f"现在 {len(members)} 人。"
        )
    for m in members:
        await conn.execute(
            "UPDATE stewards SET tickets=tickets-? WHERE id=?",
            (each, m["id"]),
        )
        await conn.execute(
            "UPDATE neighbor_boat_share_member SET paid=? WHERE share_id=? AND steward_id=?",
            (each, share_id, m["id"]),
        )
    await conn.execute(
        "UPDATE neighbor_boat_share SET status='active' WHERE id=?",
        (share_id,),
    )
    founder_row = await db.get_steward_by_id(founder["id"])
    old = (founder_row or {}).get("boat_key") or ""
    refund_note = ""
    if old and old != boat_key:
        back = int(_boat_meta(old)["cost"]) // 2
        await conn.execute(
            "UPDATE stewards SET tickets=tickets+? WHERE id=?",
            (back, founder["id"]),
        )
        refund_note = f"发起人旧船按半价退 {back} 票。"
    await conn.execute(
        "UPDATE stewards SET boat_key=?, boat_damaged=0 WHERE id=?",
        (boat_key, founder["id"]),
    )
    names = "、".join(m["name"] for m in members)
    await db.add_chronicle(
        "sea",
        f"{names} 合伙买下 {name}",
        founder["id"],
        conn=conn,
    )
    return (
        f"{name} 下水了。{names} 各付 {each} 票。{refund_note}"
        f"谁出航谁收渔获，同伴分票；修船费用平摊。"
        f"登记在 {founder['name']} 名下，不是借船。"
    )
