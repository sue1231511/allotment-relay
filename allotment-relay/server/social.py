"""协作度、徽章被动 — 让 rapport / badge 进入玩法。"""

from __future__ import annotations

from typing import Any

import aiosqlite

from . import config, db

RAPPORT_SWAP_DISCOUNT = 20
RAPPORT_SWAP_FEE = 2
RAPPORT_PARLEY_BONUS = 40
RAPPORT_ASSIST_BONUS = 60
RAPPORT_TIP_BONUS = 80

BADGE_PASSIVES: dict[str, dict[str, float | int]] = {
    "mariner": {"voyage_fail_reduce": 0.03},
    "herbalist": {"brew_mist": 1},
    "artisan": {"cook_star": 0.05},
    "naturalist": {"forage_satiety": 1},
    "archivist": {"brew_mist": 1},
    "apiarist": {"bee_honey": 1},
    "moorkeeper": {"guard_dog": 0.05},
}


def _pair_ids(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


async def get_rapport(
    a: int, b: int, conn: aiosqlite.Connection | None = None,
) -> int:
    sa, sb = _pair_ids(a, b)
    if conn is not None:
        cur = await conn.execute(
            "SELECT score FROM rapport WHERE steward_a=? AND steward_b=?",
            (sa, sb),
        )
        row = await cur.fetchone()
        return row[0] if row else 0
    async with db.connect() as conn:
        cur = await conn.execute(
            "SELECT score FROM rapport WHERE steward_a=? AND steward_b=?",
            (sa, sb),
        )
        row = await cur.fetchone()
        return row[0] if row else 0


async def max_rapport(steward_id: int) -> int:
    async with db.connect() as conn:
        cur = await conn.execute(
            """
            SELECT MAX(score) FROM rapport
            WHERE steward_a=? OR steward_b=?
            """,
            (steward_id, steward_id),
        )
        row = await cur.fetchone()
        return int(row[0] or 0)


def swap_claim_fee(rapport_with_depositor: int) -> int:
    if rapport_with_depositor >= RAPPORT_SWAP_DISCOUNT:
        return RAPPORT_SWAP_FEE
    return config.SWAP_CLAIM_FEE


def parley_bonus_chance(max_r: int) -> float:
    if max_r >= RAPPORT_PARLEY_BONUS:
        return 0.10
    return 0.0


def assist_ticket_bonus(rapport_with_target: int) -> int:
    if rapport_with_target >= RAPPORT_ASSIST_BONUS:
        return 2
    return 0


def tip_amount_bonus(rapport_with_tipper: int, amount: int) -> int:
    if rapport_with_tipper >= RAPPORT_TIP_BONUS:
        return max(1, int(amount * 0.15))
    return 0


def badge_val(steward: dict[str, Any], key: str, default: float = 0.0) -> float:
    badge = (steward.get("badge") or "").lower()
    meta = BADGE_PASSIVES.get(badge, {})
    val = meta.get(key, default)
    return float(val) if val is not None else default


def mascot_trait_mult(spirit: int) -> float:
    if spirit >= 80:
        return 1.05
    if spirit <= 30:
        return 0.85
    return 1.0


def mascot_spirit_hint(spirit: int) -> str | None:
    if spirit <= 30:
        return "吉祥物士气偏低，特质效果打折 — mascot_ops upkeep/train"
    if spirit >= 80:
        return "吉祥物士气高涨，特质略加强"
    return None
