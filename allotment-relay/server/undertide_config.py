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

# ── 收账鬼阿标（强买强卖）──────────────────────────────────
UT_RACKET_CHANCE = 0.55       # 每日触发概率（未触发则当日无单）
UT_RACKET_BUY_MULT = 2.2      # 强卖价 = vend × mult
UT_RACKET_SELL_MULT = 0.45    # 强收价 = vend × mult
UT_RACKET_POWER = 68          # 阿标战力底盘（refuse 判定）

# ── 恶猫钱庄 ──────────────────────────────────────────────
UT_RATE_BASE = 0.10          # 基准日利率（猫猫面板可调 5%~25%）
UT_RATE_MIN = 0.05
UT_RATE_MAX = 0.25
UT_LOAN_MAX_DAYS = 7
UT_LOAN_CAP = 200            # min(200, shadow_rep × 3)
UT_LOAN_CONCURRENT = 2

# ── 存款（黑心银行：借 10% 存 2%）──
UT_SAVE_RATE_BASE = 0.02     # 基准日利率（猫猫面板可调 1%~5%）
UT_SAVE_RATE_MIN = 0.01
UT_SAVE_RATE_MAX = 0.05
UT_SAVE_CAP = 500            # 硬上限
UT_SAVE_CAP_PER_REP = 5      # 影信 × 5

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
UT_JAIL_RANSOM_REP = 2

# ── 哄猫猫（提议队列，一期收数据）────────────────────────
UT_CHEER_DAILY = 1
UT_CHEER_CAT_RATE_CUT = 0.02 # 采纳后当日利率 -2pp（面板二期）
UT_CHEER_EXPIRE_HOURS = 24

# ══ 二期 ═══════════════════════════════════════════════════

# ── 深坑 ──
UT_PIT_MIN_BODY = 40
UT_PIT_LADDER = [  # (级, 入场费, 胜奖, 战力底盘, 重伤率)
    (1, 20, 60, 58, 0.05), (2, 35, 110, 64, 0.15), (3, 60, 200, 70, 0.30),
    (4, 90, 320, 77, 0.45), (5, 140, 520, 88, 0.60),
]
UT_PIT_MEDIC = {
    "ring_shock": (60, 90),
    "pit_trauma": (80, 120),
    "sprain": (25, 40),
    "backache": (30, 45),
}
UT_PIT_WIN_REP = 4
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
# 口味 B：干成就是本事（潮下不管你怎么弄到本钱），赌输了就是废物；劫特例 NPC 依旧重罚
UT_HIJACK_REP = {"clean": 2, "hurt_npc": -2, "hurt_self": -2, "fail": -8}
UT_HIJACK_BODY_SELF = (-10, -20)
UT_HIJACK_CAT_BODY = (30, 45)    # 劫猫猫 body 损耗（正数，用时取负）
UT_HIJACK_LIZHI_BODY = (15, 25)  # 劫荔栀 body 损耗（正数，用时取负）
UT_HIJACK_LIZHI_CASH = 0.35
UT_HIJACK_BAN_COUNT = 3
UT_SURGERY_FEE = 90
UT_CAT_MARK_DEBUFF = 48     # 小时

# ── 胁迫经济 ──
UT_MUSCLE_DAILY = 1
UT_PUSH_DAILY = 1
UT_NPC_POOL_DAILY = (3, 5)
# 街头四档（v2 重标定：软柿子随便捏，danger 连满练老手都忌惮）
UT_NPC_TIERS = {"soft": 42, "norm": 55, "hard": 70, "danger": 88}
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

# ── 凯斯酒馆·红宝石 / 卖血 ──
# 身价定价：价随口袋票走，穷人喝得起、富人肉疼
UT_RUBY_PRICE_RATE = 0.05        # 价 = 口袋票 × 5%
UT_RUBY_PRICE_MIN = 45
UT_RUBY_PRICE_MAX = 600
UT_RUBY_HEAL = 35                # 健康 +35（封顶 100）
UT_RUBY_MIST_COST = 12           # 雾智 -12
UT_RUBY_DAILY = 1                # 每日 1 杯
UT_RUBY_MIST_FLOOR = 30          # 雾智低于此不卖（凯斯不做把客人喝废的生意）

UT_BLOOD_PAY_RATE = 0.04         # 收入 = 口袋票 × 4%
UT_BLOOD_PAY_MIN = 30
UT_BLOOD_PAY_MAX = 400
UT_BLOOD_HEALTH_COST = 20        # 抽血 -20 健康
UT_BLOOD_DAILY = 1               # 每日 1 次
UT_BLOOD_HEALTH_FLOOR = 35       # 健康低于此不抽

# ── 黑市装备（加战力、有损耗度）──
UT_GEAR_REPAIR_RATE = 0.5        # 修理费 = 装备价 × 损耗比例 × 此系数
UT_GEAR_DRUG_PENALTY = 0.5       # 装备与体质药同时生效时，装备加成减半
UT_GEAR_WEAR_WIN = 1             # 每赢一场耐久 -1
UT_GEAR_WEAR_LOSE = 2            # 每输一场耐久 -2
UT_GEAR_WEAR_BOSS = 1            # Boss 战额外 -1

# ── 影信平衡 v2（涨多降少 + 高影信正循环拉力）──
UT_LOYAL_REP = 70                     # 「自己人」门槛（免费彩票/深坑折扣/悬赏减成共用）
UT_LOTTERY_FREE_REP = UT_LOYAL_REP    # 影信≥此 每天首张彩票免费（Jester 认得自己人）
UT_PIT_ENTRY_REP_DISCOUNT = 0.10      # 自己人 深坑入场 -10%
UT_BOUNTY_FEE_REP_CUT = 0.05          # 自己人 挂单抽成 20%→15%
UT_WHISPER_FAKE_REP_CUT = {40: 0.05, 70: 0.10}   # 影信档 → 假情报率减成
UT_BLOOD_REP_BONUS = {40: 0.05, 70: 0.10}        # 影信档 → 卖血收入加成

# ── 悬赏墙 ──
UT_BOUNTY_TIERS = {"steal": 60, "beat": 150}
UT_BOUNTY_FEE = 0.20
UT_BOUNTY_COOLDOWN = 48 * 3600
UT_BOUNTY_NPC_TIMEOUT = 72 * 3600
UT_BOUNTY_EXEC_REP = -2
UT_BOUNTY_NPC_EXEC_REP = 3
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
STAR_KEY = os.environ.get("STAR_KEY", "")
UT_LIZHI_MOOD_PRICE = {"great": 0.8, "good": 0.95, "normal": 1.0, "bad": 1.05, "awful": 1.1}
UT_LIZHI_BOGO_GIFT = "sea_salt_lager"
UT_LIZHI_BOGO_CAP = 30

# ── 滨海酒吧·包宿救济（社会兜底）──
LODGE_WALLET_LINE = 20      # 钱包低于此线可进
LODGE_DURATION_H = 6        # 真实小时（一个"整天"）
LODGE_PAY = 15              # 救济工钱（<洗碗18）
LODGE_ENERGY = 65           # 管饭回的精力
LODGE_MAX_STREAK = 3        # 连续3次后荔栀翻脸
LODGE_COOLDOWN_H = 24       # 翻脸冷却

# ── 井壁胜场榜（公开榜，≥门槛才上榜）──
PIT_BOARD_MIN_FIGHTS = 5
PIT_BOARD_LIMIT = 15
PIT_BOARD_MCP_LIMIT = 12

# ── 深坑战绩等级（长期成长轴，小加成不碾压）──
PIT_RANKS = [
    (10, "打过几场的人", 6),
    (30, "手上有了记性的人", 12),
    (50, "墙上名字的候补", 18),
    (100, "墙上留了位置的人", 25),
]

# ── 战力判定（v2：骰子按差距说话）──
UT_COMBAT_SIGMOID_K = 8   # 战力差 → 胜率的陡峭度（差8≈73% / 差16≈88% / 差25≈96%）

# ── 影信自然恢复（保底防死亡螺旋）──
REP_RECOVER_PER_DAY = 1
REP_RECOVER_CAP = 20        # 到"能打交道"档内停，再上要靠本事

# ── 潮汐博彩（Jester 的旧机器，穷人翻盘幻想）──
LOTTERY_COST = 5
LOTTERY_TIERS = [
    # (概率, 奖金区间, 档名)
    (0.0015, (300, 600), "头奖"),
    (0.012,  (60, 150),  "大奖"),
    (0.12,   (8, 20),    "小奖"),
]
