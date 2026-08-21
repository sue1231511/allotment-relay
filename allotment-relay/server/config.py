import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
_data_dir = os.environ.get("DATA_DIR")
DATA_DIR = Path(_data_dir) if _data_dir else BASE_DIR / "data"
DB_PATH = DATA_DIR / "relay.db"
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

# 潮汐岛 — 沿海份地 federation
KEY_PREFIX = "ar_sk_"
START_TICKETS = 120
START_PARCELS = 3
GREENHOUSE_COST = 180
SWAP_CLAIM_FEE = 3
GUILD_TICKETS = 18
GUILD_SHIFT_DAILY = 1
FORAGE_COOLDOWN_DAY = 86400
WEATHER_CYCLE = 7200
TIDE_CYCLE = 3600
DAILY_BREW_LIMIT = 4

# 逾篱摘取 — 可手动 plot_ops 偷菜 名字；打理时仍可能随机触发
SCRUMP_ACTIVE_WINDOW = 1200
SCRUMP_FINE_TICKETS = 10
SCRUMP_LOOT_CROP = 0.55
SCRUMP_LOOT_SEED = 0.25
SCRUMP_DAILY = 3
SCRUMP_PER_TARGET = 1

# 多 AI 协作
ASSIST_TICKETS = 8
ASSIST_RAPPORT = 5
LARDER_DRAW_FEE = 2
LARDER_DRAWS_PER_DAY = 3
LEAGUE_BONUS_TICKETS = 25
ONLINE_WINDOW = 900

LEAGUE_GOALS = [
    {"key": "fish_herring", "item": "fish_herring", "target": 12, "label": "灰鲱汛"},
    {"key": "compost", "item": "compost", "target": 20, "label": "堆肥周"},
    {"key": "crop_kale", "item": "crop_kale", "target": 15, "label": "甘蓝丰收"},
    {"key": "assist", "action": "assist", "target": 10, "label": "互助周"},
    {"key": "crop_blueberry", "item": "crop_blueberry", "target": 12, "label": "蓝莓周"},
    {"key": "honey", "item": "honey", "target": 8, "label": "蜂糖周"},
    {"key": "shell_catseye", "item": "shell_catseye", "target": 10, "label": "猫眼螺周"},
    {"key": "egg", "item": "egg", "target": 16, "label": "鲜蛋周"},
]

BADGES = [
    "mariner", "herbalist", "artisan", "naturalist", "archivist", "apiarist", "moorkeeper",
]

WEATHER_LABELS = {
    "clear": "晴朗",
    "misty": "海雾",
    "gale": "阵风",
}

TIDE_LABELS = {
    "ebb": "退潮",
    "slack": "平潮",
    "flood": "涨潮",
}

PEN_ERECT_COST = 140
PEN_EXPAND_COST = 120
MAX_FISH_PENS = 2
MAX_PARCELS = 8
# 第 4～8 块：票价；开垦时长（秒）30 / 45 / 60 / 90 / 120 分钟
PARCEL_EXPAND_COSTS = [80, 120, 180, 260, 360]
PARCEL_CLEAR_SECONDS = [1800, 2700, 3600, 5400, 7200]

BOATS = {
    "skiff": {"name": "小舢板", "cost": 85, "rank": 1, "repair": 12, "cargo": 2},
    "cutter": {"name": "切波艇", "cost": 220, "rank": 2, "repair": 28, "cargo": 4},
    "drifter": {"name": "漂航船", "cost": 420, "rank": 3, "repair": 45, "cargo": 6},
}

VOYAGE_ROUTES = {
    "near": {"label": "近岸", "duration": 480, "fuel": 8, "min_boat": "skiff", "fail": 0.14},
    "far": {"label": "外海", "duration": 1200, "fuel": 18, "min_boat": "cutter", "fail": 0.24},
    "deep": {"label": "深漂", "duration": 2400, "fuel": 35, "min_boat": "drifter", "fail": 0.34},
}

EVENT_ROLL_CHANCE = 0.09
EVENT_DAILY_CAP = 4
EVENT_GOOD_SHARE = 0.24
WORLD_PULSE_CHANCE = 0.05
WORLD_PULSE_DURATION = WEATHER_CYCLE

# 休闲生存感 — 慢衰减、无硬死亡
DAY_PHASE_CYCLE = 2400
START_SATIETY = 72
START_MIST_WIT = 78
START_STANDING = 88
SATIETY_LOW = 35
MIST_WIT_LOW = 30
STANDING_LOW = 28
STANDING_SHUT = 15

# 身体状况 / 诊所
START_HEALTH = 100
HEALTH_LOW = 40
AILMENT_ROLL_CHANCE = 0.12
AILMENT_BAD_EVENT_CHANCE = 0.16

# 海上遭遇 — 归港时随机，非回合制海战
NAVAL_ENCOUNTER_CHANCE = {
    "near": 0.22,
    "far": 0.38,
    "deep": 0.48,
}

# 出海钓鱼 — 未命名小鱼（有腿蓝鱼）随机遭遇
LEGGED_FISH_CHANCE = {
    "near": 0.05,
    "far": 0.07,
    "deep": 0.10,
}
LEGGED_FISH_RARE_GIFT_CHANCE = 0.14
LEGGED_FISH_GRAB_ENERGY = 30

# 份地野生动物 / 田间随机
FARM_EVENT_DAILY_CAP = 4

# 咕咕斑鸠 — sow/tend 昼间盯梢，可忽略或驱赶
GUGU_DOVE_STALK_CHANCE = 0.10
GUGU_DOVE_DRIVE_FAIL_CHANCE = 0.20
GUGU_DOVE_EAT_YIELD = 0.60
GUGU_DOVE_HELP_YIELD = 1.50

# 稀有公共资源 — 随机时间上线，全服争抢
COMMONS_MAX_ACTIVE = 4
COMMONS_SPAWN_CHANCE = 0.09
COMMONS_APPEAR_MIN = 120
COMMONS_APPEAR_MAX = 2400
COMMONS_LIVE_MIN = 480
COMMONS_LIVE_MAX = 3600
COMMONS_CLAIM_FEE = 2

# 意外发现 — 挖到/钓到/翻出
DISCOVERY_DAILY_CAP = 5
DISCOVERY_CHANCE = {
    "tend": 0.11,
    "forage": 0.14,
    "net": 0.13,
    "gather": 0.10,
    "pen_harvest": 0.09,
    "voyage_return": 0.08,
    "beach": 0.12,
}

# 岸畔小屋
HUT_BUILD_COST = 95

# 精力 — 出海/撒网/赶海消耗，吃饭恢复
START_ENERGY = 80
MAX_ENERGY = 100
ENERGY_REGEN_IDLE = 2  # 每次 sheet 查看慢回（软机制）

# 赶海 / 工具
BEACH_COOLDOWN = 1800
BEACH_PROBE_COOLDOWN = 900
BEACH_ENERGY = 8
BEACH_PROBE_ENERGY = 5
SCARECROW_COST = {"drift_twine": 2, "compost": 1}

# 厨房 / 冰箱
KITCHEN_COOK_DAILY = 8
FRIDGE_SLOTS = 12
FRIDGE_DAYS = 7

# 集市 — 玩家互卖，建议价参考 catalog
MARKET_FEE = 2
MARKET_LIST_MAX = 6

# 畜栏
BARN_SLOTS = 6
BARN_ERECT_COST = 75

# 世界 Boss
BOSS_ATTACK_ENERGY = 12
BOSS_ATTACK_DAMAGE = (18, 45)
BOSS_DAILY_ATTACKS = 8

# 漂流瓶
BOTTLE_LEAVE_DAILY = 3
BOTTLE_FISH_CHANCE = 0.12

# 滨海酒吧 — 暮/夜上工，票少补贴厚；每 2 天必须 shift 一次
BAR_SHIFT_DAILY = 4
BAR_SHIFT_ENERGY = 10
BAR_PAY_MIN = 10
BAR_PAY_MAX = 18
BAR_TIP_MAX = 12
BAR_POOR_THRESHOLD = 45
BAR_POOR_PAY_MULT = 1.85
BAR_MANDATORY_DAYS = 2
BAR_MANDATORY_SECONDS = BAR_MANDATORY_DAYS * 86400
BAR_POOR_LABELS = [
    "穷人补贴：荔栀多塞几张",
    "票袋见底，老板按加急算",
    "联盟低保线，上工不丢人",
]
BAR_ROLE_LINES = [
    "陪聊倒酒一轮",
    "牛郎档值班——正经陪聊那种",
    "哄客人开心，票进兜",
    "端盘听故事，故事换小费",
]
BAR_SHIFT_SUFFIX = [
    "下班时荔栀抛来一条毛巾：擦擦汗，票是真的",
    "领班记了你名字，下回优先排班",
    "酒吧灯还亮，你的票袋总算鼓了点",
    "海风吹进来，像给你这班结费鼓掌",
]
BAR_TIP_EVENTS = [
    "客人豪掷小费：「今晚你嘴挺会说的」",
    "荔栀补刀：「这单算你绩效」",
    "角落老水手闷声多了张票：别问，谢就行",
]
BAR_OOPS_EVENTS = [
    "失手打翻杯垫，小费扣一点——杯垫比脸贵",
    "讲冷笑话，全场安静，小费也安静",
]

# 栗栗 — 流动贝壳商人（羊驼商人式随机刷新）
LILI_SPAWN_CHANCE = 0.08
LILI_VISIT_MIN = 2400
LILI_VISIT_MAX = 5400
LILI_OFFERS_MIN = 4
LILI_OFFERS_MAX = 6
# 贝壳引商：献壳唤摊。首次必中，之后按品相改下次成功率
LILI_SUMMON_BASE = 30
LILI_SUMMON_MIN = 10
LILI_SUMMON_MAX = 85
LILI_SUMMON_LIVE = 1800
LILI_SUMMON_JUNK_CUT = 600
LILI_SUMMON_FEE = 1
LILI_SUMMON_RARE_PAY = 1.3
LILI_SUMMON_DELTA = {
    "rare": (15, 25),
    "good": (5, 10),
    "plain": (0, 0),
    "junk": (-15, -15),
}

# 岸畔小馆 — 玩家用熟菜开店，人类网页点餐
EATERY_OPEN_COST = 80
EATERY_MENU_MAX = 8
EATERY_DINE_DAILY = 4

# 黑旗截停 — 坏遭遇需选手，超时当 flee
HAIL_TIMEOUT = 5400
HAIL_BRIBE = {"near": 10, "far": 18, "deep": 28}
HAIL_FIGHT_ENERGY = 12
HAIL_FLEE_ENERGY = 8
HAIL_THREAT = {"near": 38, "far": 54, "deep": 70}

# 拾叶 — 巷口NPC，碰到随机小偷/乞丐/碰瓷/敲诈
SHIYE_BUMP_CHANCE = 0.05
SHIYE_DAILY_MAX = 3
SHIYE_TRIGGERS = {"sow", "tend", "gather", "forage", "guild", "net", "beach"}
SHIYE_BEG_TICKETS = (3, 8)
SHIYE_THIEF_TICKETS = (4, 11)
SHIYE_SCAM_TICKETS = (8, 16)
SHIYE_EXTORT_TICKETS = (12, 22)

# Tt酱杂货店 — 好感 / 进店赠礼 / 路上随机
# 满心 7.5 折很狠，送礼故意慢：每日 3 次、高心衰减、票难换点
TT_AFFINITY_MAX = 100
TT_MOOD_CHANCE = 0.10
TT_GIFT_DAILY_CAP = 3
TT_GIFT_GAIN_CAP = 6
TT_TICKET_GIFT_MIN = 12
TT_TICKET_PER_POINT = 20
TT_TICKET_GAIN_CAP = 3
TT_BUMP_CHANCE = 0.03
TT_BUMP_DAILY_MAX = 1
