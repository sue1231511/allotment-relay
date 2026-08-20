"""潮下 Undertide — 全部数值参数。天天侧维护，独立于地面 config.py。"""

from __future__ import annotations

# ── 入口链 ────────────────────────────────────────────────
UT_UNLOCK_DRINKS = 3          # 单杯≥UT_UNLOCK_DRINK_PRICE 的酒计数
UT_UNLOCK_DRINK_PRICE = 30    # 计数门槛（30 票档以上的酒都算；30x3=90 票≈五天低保）
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

# ══ 二期 ═══════════════════════════════════════════════════

# ── 深坑 ──
UT_PIT_MIN_BODY = 40
UT_PIT_LADDER = [  # (级, 入场费, 胜奖, 战力底盘, 重伤率)
    (1, 20, 60, 30, 0.05), (2, 35, 110, 45, 0.15), (3, 60, 200, 60, 0.30),
    (4, 90, 320, 78, 0.45), (5, 140, 520, 100, 0.60),
]
UT_PIT_MEDIC = {"ring_shock": (60, 90), "pit_trauma": (80, 120)}
UT_PIT_WIN_REP = 2
UT_PIT_DEATH_CHANCE = 0.15   # NPC 惨败死亡概率(差值≥15)

# ── 死人抽牌 ──
UT_DICE_PAY = {"small": 2, "big": 2, "black": 5}      # 全部 EV 0.833
UT_LANTERN_LADDER = [1.5, 2, 4, 8]
UT_LANTERN_SURVIVE = [0.65, 0.55, 0.45, 0.35]
UT_LANTERN_TIMEOUT = 7200
UT_DRAW_DEALER_STAND = 17
UT_BET_CAP = [(0, 15), (5, 15), (15, 30), (40, 60), (70, 120), (90, 200)]  # (rep_floor, cap)
UT_CASINO_HIGHLIGHT = 150   # 单日净赢触发后屋事件
UT_CASINO_LOSE_STREAK = 3   # 连输停发

# ── 劫持 ──
UT_HIJACK_DAILY = 1
UT_HIJACK_OUTCOMES = {"clean": 0.40, "hurt_npc": 0.25, "hurt_self": 0.20, "fail": 0.15}
UT_HIJACK_LOOT = (20, 50)
UT_HIJACK_REP = {"clean": -4, "hurt_npc": -8, "hurt_self": -4, "fail": -10}
UT_HIJACK_BODY_SELF = (-10, -20)
UT_HIJACK_CAT_BODY = (30, 45)    # 劫猫猫 body 损耗（正数，用时取负）
UT_HIJACK_LIZHI_BODY = (15, 25)  # 劫荔栀 body 损耗（正数，用时取负）
UT_HIJACK_LIZHI_CASH = 0.25
UT_HIJACK_BAN_COUNT = 3
UT_SURGERY_FEE = 60
UT_CAT_MARK_DEBUFF = 48     # 小时

# ── 胁迫经济 ──
UT_MUSCLE_DAILY = 1
UT_PUSH_DAILY = 1
UT_NPC_POOL_DAILY = (3, 5)
UT_NPC_TIERS = {"soft": 15, "norm": 30, "hard": 50, "danger": 70}
UT_NPC_GRUDGE = {"soft": 0.20, "norm": 0.40, "hard": 0.60, "danger": 0.90}
UT_MUSCLE_PAY = 0.20
UT_NPC_RARE_CHANCE = 0.10
UT_PUSH_GAIN = (1.3, 1.8)
UT_FENCE_NORMAL = 0.9
UT_GRUDGE_MAX = 3
UT_GRUDGE_CHANCE_DAILY = 0.08
UT_GRUDGE_PAYOFF = 2.0
UT_TAG_SHIFT_CHANCE = 0.15

# ══ 三期 ═══════════════════════════════════════════════════

# ── 凯斯酒馆 / 耳语人 ──
UT_WHISPER_PRICE = (10, 100)     # 世界情报价区间
UT_WHISPER_FAKE_CHANCE = 0.15
UT_WHISPER_SPY_COST = 50         # 查悬赏雇主
UT_WHISPER_AI_COST = 30          # AI 社交情报

# ── 悬赏墙 ──
UT_BOUNTY_TIERS = {"steal": 60, "beat": 150}
UT_BOUNTY_FEE = 0.20
UT_BOUNTY_COOLDOWN = 48 * 3600
UT_BOUNTY_NPC_TIMEOUT = 72 * 3600
UT_BOUNTY_EXEC_REP = -2
UT_BOUNTY_NPC_EXEC_REP = 2
UT_BOUNTY_STEAL_PLOT = True      # 偷=毁一块成熟作物

# ── K室 ──
UT_K_ROOM_PENALTY = 1.2
UT_K_ROOM_RESET_REP = 15
UT_VR_DAYS = 7

# ── 潮汐法则 ──
UT_TIDE_MULT_RANGE = (0.8, 1.5)
UT_TIDE_LADDER = [80, 60, 40, 20]   # 景气分阈值(降序) → 倍率
UT_TIDE_MULTS = [1.5, 1.25, 1.0, 0.9, 0.8]
UT_HIGHLIGHT_BROADCAST = 150

# ── 真人面板密钥（部署后在 Zeabur 改环境变量）──
import os
# 安全默认：不设环境变量 = 面板禁用（线上必须在 Zeabur 配置这三个 key）
UT_OWNER_KEY = os.environ.get("UT_OWNER_KEY", "")
UT_GATE_KEY = os.environ.get("UT_GATE_KEY", "")
LIZHI_KEY = os.environ.get("LIZHI_KEY", "")
UT_LIZHI_MOOD_PRICE = {"great": 0.8, "good": 0.95, "normal": 1.0, "bad": 1.05, "awful": 1.1}
UT_LIZHI_BOGO_GIFT = "sea_salt_lager"
UT_LIZHI_BOGO_CAP = 30
