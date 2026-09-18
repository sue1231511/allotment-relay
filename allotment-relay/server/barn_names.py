"""牲畜命名与纪事 — §二十七（简版）。"""
from __future__ import annotations

import re

from . import db


async def ensure_column(conn) -> None:
    try:
        await conn.execute(
            "ALTER TABLE barn_animals ADD COLUMN custom_name TEXT NOT NULL DEFAULT ''"
        )
    except Exception:
        pass


def _valid(name: str) -> str:
    n = (name or "").strip()
    if not n or len(n) > 12:
        raise ValueError("名字 1～12 字")
    if not re.match(r"^[\u4e00-\u9fffA-Za-z0-9·]+$", n):
        raise ValueError("名字只用中文、字母、数字或中点")
    return n


async def rename(conn, steward: dict, slot: int, name: str) -> str:
    await ensure_column(conn)
    nm = _valid(name)
    cur = await conn.execute(
        """
        SELECT species FROM barn_animals
        WHERE steward_id=? AND slot=? AND species IS NOT NULL AND species != ''
        """,
        (steward["id"], slot),
    )
    row = await cur.fetchone()
    if not row:
        raise ValueError(f"#{slot} 空栏")
    await conn.execute(
        "UPDATE barn_animals SET custom_name=? WHERE steward_id=? AND slot=?",
        (nm, steward["id"], slot),
    )
    await db.add_chronicle("barn", f"{steward['name']} 给 #{slot} 起名「{nm}」", steward["id"], conn=conn)
    return f"#{slot} 现在叫「{nm}」。"


def display_name(animal: dict, spec: dict) -> str:
    custom = (animal.get("custom_name") or "").strip()
    if custom:
        return custom
    return spec.get("name") or animal.get("species") or "?"
