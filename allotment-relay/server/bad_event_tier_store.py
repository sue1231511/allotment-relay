"""坏事件档位持久化 — 各系统 open/resolved 记入总表。"""
from __future__ import annotations

from . import bad_event_tiers as tiers_mod
from . import db

SYSTEM_LABEL: dict[str, str] = {
    "quarry": "盐风崖",
    "hail": "黑旗",
    "hut": "小屋杂务",
    "undertide": "潮下井裂",
    "voyage": "出海",
    "beach": "赶海",
    "plot": "份地/打理",
}


async def ensure_table(conn) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS steward_tier_event (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            steward_id INTEGER NOT NULL REFERENCES stewards(id),
            system_key TEXT NOT NULL,
            ref_key TEXT NOT NULL DEFAULT '',
            tier TEXT NOT NULL,
            summary TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            created_at INTEGER NOT NULL,
            resolved_at INTEGER
        )
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_tier_event_open
        ON steward_tier_event(steward_id, status, created_at DESC)
        """
    )


async def open_event(
    conn,
    steward_id: int,
    system_key: str,
    tier: str,
    summary: str,
    *,
    ref_key: str = "",
) -> None:
    await ensure_table(conn)
    await resolve(conn, steward_id, system_key, ref_key=ref_key, quiet=True)
    await conn.execute(
        """
        INSERT INTO steward_tier_event
        (steward_id, system_key, ref_key, tier, summary, status, created_at)
        VALUES (?,?,?,?,?,'open',?)
        """,
        (steward_id, system_key, ref_key or "", tier, summary[:240], db.now()),
    )


async def resolve(
    conn,
    steward_id: int,
    system_key: str,
    *,
    ref_key: str | None = None,
    quiet: bool = False,
) -> int:
    await ensure_table(conn)
    now = db.now()
    if ref_key is not None:
        cur = await conn.execute(
            """
            UPDATE steward_tier_event SET status='resolved', resolved_at=?
            WHERE steward_id=? AND system_key=? AND ref_key=? AND status='open'
            """,
            (now, steward_id, system_key, ref_key or ""),
        )
    else:
        cur = await conn.execute(
            """
            UPDATE steward_tier_event SET status='resolved', resolved_at=?
            WHERE steward_id=? AND system_key=? AND status='open'
            """,
            (now, steward_id, system_key),
        )
    n = cur.rowcount
    return n


async def list_open(conn, steward_id: int, *, limit: int = 12) -> list[dict]:
    await ensure_table(conn)
    conn.row_factory = None
    cur = await conn.execute(
        """
        SELECT system_key, ref_key, tier, summary, created_at
        FROM steward_tier_event
        WHERE steward_id=? AND status='open'
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (steward_id, limit),
    )
    rows = await cur.fetchall()
    out = []
    for sys_k, ref, tier, summary, _ts in rows:
        label = tiers_mod.TIER_LABEL.get(tier, tier)
        sys_nm = SYSTEM_LABEL.get(sys_k, sys_k)
        ref_bit = f" #{ref}" if ref else ""
        out.append(
            {
                "system": sys_k,
                "ref": ref,
                "tier": tier,
                "line": f"【{label}】{sys_nm}{ref_bit} — {summary[:80]}",
            }
        )
    return out


async def format_report(conn, steward_id: int) -> str:
    rows = await list_open(conn, steward_id)
    if not rows:
        return "灾档：当前没有未结案的四档坏事件（轻中重绝）。分散 debuff 仍看各工具 status。"
    lines = ["灾档（未结案坏事件，按最近记录）："]
    for r in rows:
        lines.append(f"  · {r['line']}")
    lines.append("处置后这里会自动结案。总览也可 steward_ops 维修。")
    return "\n".join(lines)
