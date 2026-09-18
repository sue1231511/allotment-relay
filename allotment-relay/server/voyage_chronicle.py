"""船只履历 — 第三批。"""
from __future__ import annotations

from . import db


async def ensure_table(conn) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS steward_boat_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            steward_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
        """
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_boat_log_steward ON steward_boat_log(steward_id, id DESC)"
    )


async def append(conn, steward_id: int, text: str) -> None:
    await ensure_table(conn)
    line = (text or "").strip()[:120]
    if not line:
        return
    await conn.execute(
        "INSERT INTO steward_boat_log (steward_id, text, created_at) VALUES (?,?,?)",
        (int(steward_id), line, db.now()),
    )


async def recent(conn, steward_id: int, limit: int = 8) -> list[str]:
    await ensure_table(conn)
    cur = await conn.execute(
        """
        SELECT text FROM steward_boat_log
        WHERE steward_id=? ORDER BY id DESC LIMIT ?
        """,
        (int(steward_id), limit),
    )
    return [r[0] for r in await cur.fetchall()]


async def status(conn, steward_id: int) -> str:
    rows = await recent(conn, steward_id)
    if not rows:
        return "还没有船事记录。depart/归港/repair 会自动记。voyage_ops 履历"
    lines = ["船只履历（近几条）："]
    for t in rows:
        lines.append(f"  · {t}")
    return "\n".join(lines)
