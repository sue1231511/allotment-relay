"""统一坏事件档位（轻/中/重/绝）— 扩展方案四档标签，供各系统复用。"""
from __future__ import annotations

import random

TIER_LIGHT = "light"
TIER_MID = "mid"
TIER_HEAVY = "heavy"
TIER_FATAL = "fatal"

TIER_LABEL: dict[str, str] = {
    TIER_LIGHT: "轻",
    TIER_MID: "中",
    TIER_HEAVY: "重",
    TIER_FATAL: "绝",
}

DEFAULT_WEIGHTS = (0.52, 0.30, 0.14, 0.04)


def roll_tier(*, weights: tuple[float, float, float, float] = DEFAULT_WEIGHTS) -> str:
    r = random.random()
    acc = 0.0
    keys = (TIER_LIGHT, TIER_MID, TIER_HEAVY, TIER_FATAL)
    for w, key in zip(weights, keys):
        acc += w
        if r < acc:
            return key
    return TIER_LIGHT


def tag(tier: str, message: str) -> str:
    label = TIER_LABEL.get(tier, TIER_LABEL[TIER_LIGHT])
    return f"【{label}】{message}"


def sleep_penalty_for_tier(tier: str) -> int:
    """杂务/潮气类忽略惩罚：档位越高，下次睡觉少回越多精力。"""
    return {TIER_LIGHT: 2, TIER_MID: 3, TIER_HEAVY: 5, TIER_FATAL: 8}.get(tier, 2)


REPAIR_HINTS: dict[str, str] = {
    "quarry": "→ visit_ops clinic treat 岩尘入肺 · quarry_ops 塌方 撑柱|撤人|硬挖",
    "voyage": "→ voyage_ops repair · 部件 tide_ops 船件 status",
    "hut": "→ hut_ops 杂务 · hut_ops 家维 交 · visit_ops clinic 调理",
    "undertide": "→ undertide_ops medic · visit_ops clinic treat 斗场震伤",
    "beach": "→ 再动一次同动作消 debuff · visit_ops clinic 调理 小",
}


def repair_hint(system: str, *, tier: str | None = None) -> str:
    base = REPAIR_HINTS.get(system, "")
    if not base:
        return ""
    if tier == TIER_FATAL:
        return base + "（档位绝：优先处理再扩产/出海）"
    return base
