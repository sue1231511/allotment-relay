"""写操作防重复。同一 steward + 路由 + Idempotency-Key 在窗口内返回首次结果。"""
from __future__ import annotations

import json
from typing import Any

from .. import db
from .errors import ApiError

IDEMPOTENCY_TTL_SEC = 15 * 60
RAPID_LOCK_MS = 800


async def _purge(conn, now: int) -> None:
    await conn.execute(
        "DELETE FROM v1_idempotency WHERE created_at < ?",
        (now - IDEMPOTENCY_TTL_SEC,),
    )


async def recall(steward_id: int, route: str, idem_key: str) -> dict[str, Any] | None:
    key = (idem_key or "").strip()
    if not key:
        return None
    now = db.now()
    async with db.connect() as conn:
        await _purge(conn, now)
        row = await (await conn.execute(
            """
            SELECT status, body FROM v1_idempotency
            WHERE idem_key=? AND steward_id=? AND route=?
            """,
            (key, steward_id, route),
        )).fetchone()
        await conn.commit()
    if not row:
        return None
    return {"status": int(row[0]), "body": json.loads(row[1])}


async def store(
    steward_id: int,
    route: str,
    idem_key: str,
    status: int,
    body: dict[str, Any],
) -> None:
    key = (idem_key or "").strip()
    if not key:
        return
    async with db.connect() as conn:
        await conn.execute(
            """
            INSERT OR REPLACE INTO v1_idempotency
            (idem_key, steward_id, route, status, body, created_at)
            VALUES (?,?,?,?,?,?)
            """,
            (key, steward_id, route, int(status), json.dumps(body, ensure_ascii=False), db.now()),
        )
        await conn.commit()


async def guard_rapid(steward_id: int, route: str) -> None:
    """没有 Idempotency-Key 时，同一路由 800ms 内连点直接拒。"""
    now = db.now()
    stamp = f"rapid:{steward_id}:{route}"
    async with db.connect() as conn:
        await _purge(conn, now)
        row = await (await conn.execute(
            """
            SELECT created_at FROM v1_idempotency
            WHERE idem_key=? AND steward_id=? AND route=?
            """,
            (stamp, steward_id, route),
        )).fetchone()
        if row and (now - int(row[0])) * 1000 < RAPID_LOCK_MS:
            raise ApiError("DUPLICATE", "点得太快，上一次还在落账。", status=409)
        await conn.execute(
            """
            INSERT OR REPLACE INTO v1_idempotency
            (idem_key, steward_id, route, status, body, created_at)
            VALUES (?,?,?,?,?,?)
            """,
            (stamp, steward_id, route, 202, "{}", now),
        )
        await conn.commit()
