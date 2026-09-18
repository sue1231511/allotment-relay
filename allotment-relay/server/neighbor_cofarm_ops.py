"""alliance_ops 共耕 入口。"""
from __future__ import annotations

from . import db
from .game import require_steward
from . import neighbor_cofarm as cofarm_mod


async def cofarm_ops(key_id: int, command: str) -> str:
    parts = command.strip().split()
    if parts and parts[0].lower() in ("共耕", "cofarm"):
        parts = parts[1:]
    read_ok = not parts or parts[0].lower() in ("状态", "status", "list")
    s = await require_steward(key_id, exempt_duty=read_ok)
    async with db.connect() as conn:
        msg = await cofarm_mod.dispatch(conn, s, parts)
        await conn.commit()
    return msg
