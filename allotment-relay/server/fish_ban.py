"""潮生会禁捕 — 第三批：每周禁 1～2 种鱼。"""
from __future__ import annotations

import hashlib
import random

from . import db
from .catalog import SEA_CATCH


def _week_id() -> int:
    return int(db.day_id()) // 7


def banned_species(week_id: int | None = None) -> list[str]:
    wk = week_id if week_id is not None else _week_id()
    seed = int(hashlib.sha256(f"fish-ban-{wk}".encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    pool = [
        k for k, m in SEA_CATCH.items()
        if not m.get("cast_only") and int(m.get("rarity") or 1) <= 4
    ]
    if not pool:
        return []
    n = 2 if wk % 2 == 0 else 1
    return rng.sample(pool, k=min(n, len(pool)))


def is_banned(species: str, week_id: int | None = None) -> bool:
    return species in banned_species(week_id)


def brief_ban(week_id: int | None = None) -> str:
    """给 /island 会厅列表一行摘要（不含 MCP 子命令）。"""
    banned = banned_species(week_id)
    if not banned:
        return "本周无禁捞种"
    names = [SEA_CATCH[k]["name"] for k in banned if k in SEA_CATCH]
    return f"禁捞：{'、'.join(names)}（网/钓碰上罚 15 票放生）"


def notice_text(week_id: int | None = None) -> str:
    banned = banned_species(week_id)
    if not banned:
        return "本周未设禁捕种。"
    names = [SEA_CATCH[k]["name"] for k in banned if k in SEA_CATCH]
    return f"本周禁捕：{'、'.join(names)}（网/钓碰上会罚 15 票并放生，visit_ops 潮生会 禁捕 查）"


async def enforce(conn, steward_id: int, species: str) -> str | None:
    if not is_banned(species):
        return None
    fine = 15
    cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (steward_id,))
    have = int((await cur.fetchone())[0])
    if have < fine:
        raise ValueError(
            f"禁捕种 {SEA_CATCH.get(species, {}).get('name', species)}，票不够交罚 {fine}，先别捞"
        )
    await conn.execute(
        "UPDATE stewards SET tickets=tickets-? WHERE id=?",
        (fine, steward_id),
    )
    name = SEA_CATCH.get(species, {}).get("name", species)
    return f"禁捕：{name}已放生（-{fine} 票）"
