"""潮下 Undertide — 全部数值参数。天天侧维护，独立于地面 config.py。"""

from __future__ import annotations

# ── 入口链 ────────────────────────────────────────────────
UT_UNLOCK_DRINKS = 3          # 单杯≥UT_UNLOCK_DRINK_PRICE 的酒计数
UT_UNLOCK_DRINK_PRICE = 40    # 计数门槛（最贵常规酒「老板娘心情」45 在此之上）
UT_DESCEND_COST = 3           # 枯井门票

# ── 影信 shadow_rep ───────────────────────────────────────
UT_START_SHADOW_REP = 10
UT_REP_TIERS = [              # (下限, 档名, 黑市系数, 真货加成)
    (0, "烂账鬼", 1.50, -0.05),
    (5, "生面孔", 1.25, -0.05),
    (15, "能打交道", 1.00, 0.00),
    (40, "熟客", 0.95, 0.10),
    (70, "自己人", 0.90, 0.18),
    (90, "被看见", 0.90, 0.18),
]
UT_K_ROOM_REP = 5             # 低于此 + 逾期债 → K室（一期仅文案预警，K室三期）

# ── 随机事件 ──────────────────────────────────────────────
UT_EVENT_CHANCE = 0.08
UT_EVENT_DAILY_CAP = 3

# ── 后室铺（黑市）─────────────────────────────────────────
UT_QUALITY_BASE = (0.60, 0.25, 0.15)   # 真货/次品/假货 基线
UT_SHELF = {                # 层: (最少种数, 最多种数, 单种库存min, max)
    "common": (8, 12, 3, 8),
    "linked": (3, 5, 2, 4),
    "rare": (0, 1, 1, 1),
}

# ── 恶猫钱庄 ──────────────────────────────────────────────
UT_RATE_BASE = 0.10          # 基准日利率（猫猫面板可调 5%~25%）
UT_RATE_MIN = 0.05
UT_RATE_MAX = 0.25
UT_LOAN_MAX_DAYS = 7
UT_LOAN_CAP = 200            # min(200, shadow_rep × 3)
UT_LOAN_CONCURRENT = 2

# ── 地下监牢 ──────────────────────────────────────────────
UT_JAIL_BUSTED_TRIGGER = 5   # 案底触发线
UT_JAIL_RANSOM_PER_COUNT = 15
UT_JAIL_RANSOM_RELIEF = 0.5  # 赎身后案底减半
UT_JAIL_TERM_HOURS = 48
UT_JAIL_WORK_PAY = 2
UT_JAIL_WORK_BODY = -2
UT_JAIL_WORK_PER_DAY = 6
UT_JAIL_REDUCE_HOURS = 12    # 搬满减刑
UT_JAIL_SERVE_REP = 3
UT_JAIL_RANSOM_REP = 1

# ── 哄猫猫（提议队列，一期收数据）────────────────────────
UT_CHEER_DAILY = 1
UT_CHEER_CAT_RATE_CUT = 0.02 # 采纳后当日利率 -2pp（面板二期）
UT_CHEER_EXPIRE_HOURS = 24
