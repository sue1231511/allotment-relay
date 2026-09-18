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


RAPPORT_PERKS: list[tuple[int, str]] = [
    (RAPPORT_SWAP_DISCOUNT, "交换台 claim 手续费 2 票（默认 3）"),
    (RAPPORT_PARLEY_BONUS, "海上被黑旗截停时，谈和成功率 +10%"),
    (RAPPORT_ASSIST_BONUS, "alliance_ops assist 对方额外 +2 票"),
    (RAPPORT_TIP_BONUS, "bar_ops 打赏该岛民，对方实收 +15%"),
]


def perks_for_score(score: int) -> list[str]:
    return [text for need, text in RAPPORT_PERKS if score >= need]


def next_perk_hint(score: int) -> str:
    for need, text in RAPPORT_PERKS:
        if score < need:
            return f"再 +{need - score} 到 {need}：{text}"
    return "档位已全开（赠礼 +3、assist、打赏等仍会涨分）"


async def list_rapports(steward_id: int, *, limit: int = 15) -> list[tuple[str, int]]:
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            """
            SELECT score,
                   CASE WHEN steward_a=? THEN steward_b ELSE steward_a END AS other_id
            FROM rapport
            WHERE steward_a=? OR steward_b=?
            ORDER BY score DESC
            LIMIT ?
            """,
            (steward_id, steward_id, steward_id, limit),
        )).fetchall()
        out: list[tuple[str, int]] = []
        for row in rows:
            cur = await conn.execute(
                "SELECT name FROM stewards WHERE id=?", (int(row["other_id"]),),
            )
            name_row = await cur.fetchone()
            if name_row:
                out.append((name_row[0], int(row["score"])))
        return out


async def rapport_sheet(steward_id: int) -> str:
    rows = await list_rapports(steward_id)
    top = await max_rapport(steward_id)
    lines = [
        "«协作度（和某岛民一对一分，送礼/assist/打赏/酒吧互动等会涨）",
        "档位（对应该岛民的分）：",
        f"  ≥{RAPPORT_SWAP_DISCOUNT} 交换台 claim 2 票 · "
        f"≥{RAPPORT_PARLEY_BONUS} 谈和 +10% · "
        f"≥{RAPPORT_ASSIST_BONUS} assist +2 票 · "
        f"≥{RAPPORT_TIP_BONUS} 打赏 +15%",
        f"你目前最高协作：{top}",
    ]
    if rows:
        lines.append("和你最熟：")
        for name, score in rows:
            perks = perks_for_score(score)
            tag = f"（{' · '.join(perks)}）" if perks else ""
            lines.append(f"  · {name} {score}{tag}")
    else:
        lines.append("还没有记录。tote_ops 赠礼 / alliance_ops assist / bar_ops 打赏 都会 +协作。")
    lines.append("看某人：steward_ops peer 名字 · 赠礼：tote_ops 赠礼 名字 票 数量")
    lines.append("»")
    return "\n".join(lines)


def rapport_peer_blurb(score: int) -> str:
    if score <= 0:
        return "协作度：0（还不熟）"
    perks = perks_for_score(score)
    base = f"协作度：{score}"
    if perks:
        return base + " · " + " · ".join(perks)
    return base + " · " + next_perk_hint(score)
