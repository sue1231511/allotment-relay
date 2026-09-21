"""潮生会禁捕 — 第三批：每周禁 1～2 种鱼。"""
from __future__ import annotations

import hashlib
import random

from . import db
from .catalog import SEA_CATCH

FINE = 15
BAN_SCOPE = "岸边网钓、出海归港、渔排收碰上"


def _week_id(ts: int | None = None) -> int:
    """和岸税/周潮同一套「本周」：东八区周一换班，不是 UTC 日序号。"""
    from .disaster import cst_week_ordinal
    return cst_week_ordinal(ts)


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


def species_from_item(item: str) -> str | None:
    """fish_glassshrimp / glassshrimp → glassshrimp；非渔获返回 None。"""
    key = (item or "").strip()
    if key.startswith("fish_"):
        key = key[5:]
    if key in SEA_CATCH:
        return key
    return None


def brief_ban(week_id: int | None = None) -> str:
    """给 /island 会厅列表一行摘要（不含 MCP 子命令）。"""
    banned = banned_species(week_id)
    if not banned:
        return "本周无禁捞种"
    names = [SEA_CATCH[k]["name"] for k in banned if k in SEA_CATCH]
    return f"禁捞：{'、'.join(names)}（{BAN_SCOPE}罚 {FINE} 票放生，不能卖）"


def notice_text(week_id: int | None = None) -> str:
    banned = banned_species(week_id)
    if not banned:
        return "本周未设禁捕种。"
    names = [SEA_CATCH[k]["name"] for k in banned if k in SEA_CATCH]
    return (
        f"本周禁捕：{'、'.join(names)}"
        f"（{BAN_SCOPE}会罚 {FINE} 票并放生，不能进袋也不能卖；"
        f"visit_ops 潮生会 禁捕 查）"
    )


def refuse_trade(item: str, week_id: int | None = None) -> str | None:
    """本周禁捞种不能 vend / 挂摊。"""
    species = species_from_item(item)
    if not species or not is_banned(species, week_id):
        return None
    name = SEA_CATCH.get(species, {}).get("name", species)
    return f"本周禁捞 {name}，不能卖。潮生会要的是当场放生，不是进集市。"


async def enforce(
    conn,
    steward_id: int,
    species: str,
    *,
    must_release: bool = False,
) -> str | None:
    """碰上禁捞种：扣罚并放生，不进袋。

    岸边网/钓票不够会拦住（先别捞）。出海归港已经发生，用
    must_release=True：票不够也放生，能扣多少扣多少。
    """
    if not is_banned(species):
        return None
    cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (steward_id,))
    have = int((await cur.fetchone())[0])
    if have < FINE and not must_release:
        raise ValueError(
            f"禁捕种 {SEA_CATCH.get(species, {}).get('name', species)}，"
            f"票不够交罚 {FINE}，先别捞"
        )
    paid = min(FINE, have)
    if paid:
        await conn.execute(
            "UPDATE stewards SET tickets=tickets-? WHERE id=?",
            (paid, steward_id),
        )
    name = SEA_CATCH.get(species, {}).get("name", species)
    from . import voyage_chronicle as vlog_mod
    await vlog_mod.append(conn, steward_id, f"禁捕放生 {name}（-{paid}票）")
    if paid < FINE:
        return f"禁捕：{name}已放生（票不足，扣 {paid} 票）"
    return f"禁捕：{name}已放生（-{paid} 票）"


async def maybe_release_item(
    conn,
    steward_id: int,
    item: str,
    *,
    must_release: bool = True,
) -> str | None:
    """物品是本周禁捞渔获则放生；否则 None（调用方照常入库）。"""
    species = species_from_item(item)
    if not species:
        return None
    return await enforce(conn, steward_id, species, must_release=must_release)
