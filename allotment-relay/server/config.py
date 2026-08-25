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
START_ORCHARDS = 3
GREENHOUSE_COST = 180
# 温室无上限。第 1 座 180 票即用；之后比份地更陡：310、500、750、1060…
GREENHOUSE_EXPAND_BASE = 180
SWAP_CLAIM_FEE = 3
GUILD_TICKETS = 18
GUILD_SHIFT_DAILY = 1
# 游戏「日」边界（UTC 午夜换班）。公会轮值、酒吧日报、偷菜次数、床睡觉、栗栗货单等
# 凡「每天 N 次」都按此刷新，不要用滚动 24 小时。
FORAGE_COOLDOWN_DAY = 86400
WEEK_SECONDS = FORAGE_COOLDOWN_DAY * 7
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
# 偷菜最多掐走 30%，且永远留一把（剩一把就不能再掐）
SCRUMP_TAKE_RATE = 0.30
SCRUMP_LEAVE_MIN = 1

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
    {"key": "quarry_salt", "item": "quarry_salt", "target": 8, "label": "盐晶周"},
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
# 第一座温室历史上占 #99；现已迁到 棚1。露天买地仍跳过 99，sow 99 仍当 棚1
GREENHOUSE_SLOT = 99
GREENHOUSE_ALIAS_SLOT = 99
# 露天份地无上限。第 4 块起票价 80、120、180、260、360…（差额每次多 20）
# 开垦时长 30、45、60、90、120 分钟…（每两档多加 15 分钟）
PARCEL_EXPAND_BASE = 80
PARCEL_CLEAR_BASE_MINUTES = 30


def parcel_expand_cost(idx: int) -> int:
    """第 (START_PARCELS+1+idx) 块票价：80 + 30n + 10n²。"""
    n = max(0, int(idx))
    return PARCEL_EXPAND_BASE + 30 * n + 10 * n * n


def parcel_clear_seconds(idx: int) -> int:
    """第 (START_PARCELS+1+idx) 块开垦秒数。30、45、60、90、120 分钟…"""
    n = max(0, int(idx))
    pairs, rem = divmod(n, 2)
    minutes = PARCEL_CLEAR_BASE_MINUTES + 15 * pairs * (pairs + 1)
    if rem:
        minutes += 15 * (pairs + 1)
    return minutes * 60


# 前 5 档（第 4～8 块）与旧表一致，便于对照
PARCEL_EXPAND_COSTS = [parcel_expand_cost(i) for i in range(5)]
PARCEL_CLEAR_SECONDS = [parcel_clear_seconds(i) for i in range(5)]


def greenhouse_expand_cost(idx: int) -> int:
    """第 (idx+1) 座票价：180 + 100n + 30n²，比份地更陡。"""
    n = max(0, int(idx))
    return GREENHOUSE_EXPAND_BASE + 100 * n + 30 * n * n


def greenhouse_clear_seconds(idx: int) -> int:
    """第 1 座马上可用；之后比同档份地多 15 分钟。"""
    n = max(0, int(idx))
    if n <= 0:
        return 0
    return parcel_clear_seconds(n) + 15 * 60


GREENHOUSE_EXPAND_COSTS = [greenhouse_expand_cost(i) for i in range(5)]
GREENHOUSE_CLEAR_SECONDS = [greenhouse_clear_seconds(i) for i in range(5)]

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

# 随机事件整体倍率（+30% 触发与上限）
EVENT_RATE_MULT = 1.3


def _event_rate(x: float) -> float:
    return round(x * EVENT_RATE_MULT, 4)


EVENT_ROLL_CHANCE = _event_rate(0.08)
EVENT_DAILY_CAP = max(1, round(4 * EVENT_RATE_MULT))
EVENT_GOOD_SHARE = 0.30
SCRUMP_EVENT_CHANCE = _event_rate(0.18)
WORLD_PULSE_CHANCE = _event_rate(0.05)
WORLD_PULSE_DURATION = WEATHER_CYCLE

# 天灾 — 人类日历每周（东八区周一换班）刮一次，低/中/高随机。
# 只冲 3 万以上的超额；3 万及以下不受影响。
DISASTER_SAFE = 30000
WEEKLY_TIDE_FLAG_PREFIX = "weekly_tide:"
WEEKLY_TIDE_DURATION = 2 * 86400
WEEKLY_TIDE_RATES = {"low": 0.20, "mid": 0.45, "high": 0.75}
WEEKLY_TIDE_LABELS = {"low": "浅潮", "mid": "灌仓潮", "high": "黑潮"}
WEEKLY_TIDE_GRADES = {"low": "低", "mid": "中", "high": "高"}
STORM_SHUTTER_LEVY_MULT = 0.85
DISASTER_NOTICE_DAYS = 7

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
AILMENT_ROLL_CHANCE = _event_rate(0.12)
AILMENT_BAD_EVENT_CHANCE = _event_rate(0.13)
# 生肉感染：只有 meat_*（兔肉/猪肉）生吃会滚；水果/生鱼/野薄荷安全
RAW_MEAT_INFECT_CHANCE = 0.35
INFECTION_TREAT_COOLDOWN = 21600  # 同一次感染两次治疗至少隔 6 小时
INFECTION_DRAIN_EVERY = 1800      # 每 30 分钟按档位扣精力

# 生吃规则：蔬菜不能生吃；水果能吃但只回一点精力，
# 连续生吃 FRUIT_EAT_STREAK_LIMIT 口落「营养不良」（吃熟菜可压 / 诊所可治）
FRUIT_RAW_ENERGY = 4
FRUIT_EAT_STREAK_LIMIT = 5

# 海上遭遇 — 归港时随机，非回合制海战
NAVAL_ENCOUNTER_CHANCE = {
    "near": _event_rate(0.22),
    "far": _event_rate(0.38),
    "deep": _event_rate(0.48),
}

# 出海坐钓 — 未命名小鱼（有腿蓝鱼）随机遭遇；撒网不会碰上、也网不到这尾
LEGGED_FISH_CHANCE = {
    "near": _event_rate(0.05),
    "far": _event_rate(0.07),
    "deep": _event_rate(0.10),
}
LEGGED_FISH_RARE_GIFT_CHANCE = _event_rate(0.14)
LEGGED_FISH_GRAB_ENERGY = 30

# 份地野生动物 / 田间随机
FARM_EVENT_DAILY_CAP = max(1, round(4 * EVENT_RATE_MULT))
FARM_TRIGGER_CHANCE = {
    "sow": _event_rate(0.05),
    "tend": _event_rate(0.08),
    "gather": _event_rate(0.06),
}
FARM_AILMENT_CHANCE = _event_rate(0.14)
# 浇水/施肥砍生长时间（相对 grow_target）；一茬各一次
WATER_CUT_RATE = 0.18
WATER_GROW_MULT = 0.90
FERTILIZE_GROW_MULT = 0.88
MIN_GROW_TARGET = 120
FERTILIZE_COMPOST_CUT = 0.12

# 咕咕斑鸠 — 每天首次 sow/tend 掷一次，碰上才盯梢（基础约 23%）
GUGU_DOVE_DAILY_CHANCE = _event_rate(0.18)
GUGU_DOVE_DRIVE_FAIL_CHANCE = 0.20
GUGU_DOVE_EAT_YIELD = 0.60
GUGU_DOVE_HELP_YIELD = 1.50

# 稀有公共资源 — 随机时间上线，全服争抢
COMMONS_MAX_ACTIVE = 4
COMMONS_SPAWN_CHANCE = _event_rate(0.09)
COMMONS_APPEAR_MIN = 120
COMMONS_APPEAR_MAX = 2400
COMMONS_LIVE_MIN = 480
COMMONS_LIVE_MAX = 3600
COMMONS_CLAIM_FEE = 2

# 意外发现 — 挖到/钓到/翻出
DISCOVERY_DAILY_CAP = max(1, round(5 * EVENT_RATE_MULT))
DISCOVERY_CHANCE = {
    "tend": _event_rate(0.11),
    "forage": _event_rate(0.14),
    "net": _event_rate(0.13),
    "gather": _event_rate(0.10),
    "pen_harvest": _event_rate(0.09),
    "voyage_return": _event_rate(0.08),
    "beach": _event_rate(0.12),
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

# 盐风崖 — 潮脉矿。比赶海 / 钓鱼更慢更费：镐更贵、冷却更长、空挥更高、洗矿亏份。
# 涨潮关的是赶海 dig，崖矿不关，但湿滑更难挖。
QUARRY_START_CLAIMS = 1
QUARRY_PROSPECT_ENERGY = 8          # 同赶海 dig，另加 18% 空探
QUARRY_PROSPECT_COOLDOWN = 1200     # 20 分钟；赶海 probe 15 分钟
QUARRY_PROSPECT_EMPTY = 0.18
QUARRY_HEW_COOLDOWN = 2400          # 每坑 40 分钟
QUARRY_HEW_GLOBAL_COOLDOWN = 2160   # 全坑共用 36 分钟；赶海 dig 30 分钟且无全局锁
QUARRY_HEW_DAILY_CAP = 8            # 钓鱼无日限
QUARRY_WASH_RAW_PER = 2             # 2 原矿 → 1 精矿
QUARRY_WASH_ENERGY = 6              # 每出 1 份精矿
QUARRY_WASH_FAIL = 0.12
QUARRY_HAZARD_CHANCE = 0.16         # 赶海致病 10%
QUARRY_FLOOD_EMPTY = 0.08
QUARRY_FLOOD_ENERGY = 2
QUARRY_GALE_EMPTY = 0.06
QUARRY_NIGHT_ENERGY = 1
QUARRY_CLAIM_BASE = 90              # 比第 4 块份地 80 票更贵
QUARRY_PICK_T1_COST = 80            # 铲子 42 / 粗网 28 / 竹竿 30


def quarry_claim_cost(idx: int) -> int:
    """第 (START+1+idx) 个矿坑票价：90 + 40n + 12n²。"""
    n = max(0, int(idx))
    return QUARRY_CLAIM_BASE + 40 * n + 12 * n * n


def quarry_claim_clear_seconds(idx: int) -> int:
    """第 (START+1+idx) 个矿坑开凿秒数：35、50、65、80 分钟…"""
    n = max(0, int(idx))
    return (35 + 15 * n) * 60


# 岸工坊 — 慢工，不是再挖一次。打/取、盐田、风暴打捞、陈列柜都走 craft_ops
CRAFT_SALT_CLEAR_NEED = 1200          # 盐田要累计 20 分钟晴天
CRAFT_SALT_FILL_ENERGY = 5
CRAFT_SALT_HARVEST_ENERGY = 3
CRAFT_SALT_PAN_BASE = 40
CRAFT_SALT_PAN_MAX = 3
CRAFT_SALVAGE_AFTER = WEATHER_CYCLE   # 阵风结束后一整段晴天可打捞
CRAFT_SALVAGE_COOLDOWN = 1500         # 25 分钟；赶海 dig 30 分钟
CRAFT_SALVAGE_DAILY = 4
CRAFT_NET_PATCH_SEC = 6 * 3600        # 补网 6 小时空网 -8%
CRAFT_NET_PATCH_EMPTY = 0.08
CRAFT_FOG_SINKER_SEC = 12 * 3600      # 雾铅网坠 12 小时空网 -14%
CRAFT_FOG_SINKER_EMPTY = 0.14


def craft_pan_cost(idx: int) -> int:
    """第 (1+idx) 口盐田票价：40 + 28n。"""
    n = max(0, int(idx))
    return CRAFT_SALT_PAN_BASE + 28 * n

# 厨房 / 冰箱 — 定点菜谱与自由组合分开计次（游戏日换班刷新）
KITCHEN_RECIPE_COOK_DAILY = 10   # cook 菜名（menu 定点菜）
KITCHEN_MIX_COOK_DAILY = 24      # cook 材料1 材料2 …（自由组合）
FRIDGE_SLOTS = 12
FRIDGE_DAYS = 7
CABINET_SLOTS = 30
CABINET_STACK = 24
CABINET_SLOT_COST = 12
CABINET_SLOTS_MAX = 60
# 行囊 / 潮柜 / 冰箱每格同一上限；买货也不能超过。tote_ops 扩栈 可花钱加栈（同种货自动叠放）
SATCHEL_STACK = CABINET_STACK
SATCHEL_STACK_STEP = 8       # 每扩 1 级 +8 份/格
SATCHEL_STACK_COST = 15      # 票/级
SATCHEL_STACK_TIERS_MAX = 5  # 24 → 32 → 40 → 48 → 56 → 64
SATCHEL_STACK_MAX = SATCHEL_STACK + SATCHEL_STACK_TIERS_MAX * SATCHEL_STACK_STEP
FRIDGE_STACK = CABINET_STACK
# 堆肥桶：MC 式 7 层结一块堆肥；桶里结好的堆肥最多囤一格
COMPOST_BIN_LAYERS = 7
COMPOST_BIN_READY_MAX = CABINET_STACK

# 集市 — 玩家互卖，建议价参考 catalog
MARKET_FEE = 2
MARKET_LIST_MAX = 6          # 基础挂单格
MARKET_LIST_SLOTS_MAX = 12     # 扩格后上限
MARKET_SLOT_COST = 15          # 每加 1 格

# 畜栏
BARN_SLOTS = 6
BARN_ERECT_COST = 75

# 岸柏板床 — hut_ops 睡：一觉回精力（回饱食 +8），每天一次（游戏日边界刷新）
BED_REST_ENERGY = 50
HAMMOCK_ENERGY = 35
BATH_MIST_WIT = 15
BATH_COOLDOWN = 72000
VANITY_STANDING = 1
PICKLE_VEG_PER_JAR = 2
PICKLE_ENERGY = 6
DRY_FISH_PER = 2
DRIED_FISH_ENERGY = 10
BOOKSHELF_MIST_WIT = 2

# 小馆堂食「饱餐」— dine 附带状态：期间行动精力消耗 -1（最低 1），并回少量雾智/档信。
# 家里自己吃没有这些——饭馆卖堂食体验，集市卖货（买回去自己吃只有基础精力）。
DINE_BUFF_SECONDS = 7200
DINE_BUFF_ENERGY_SAVE = 1
DINE_BUFF_MIST_WIT = 3
DINE_BUFF_STANDING = 2

# 世界 Boss
BOSS_ATTACK_ENERGY = 12
BOSS_ATTACK_DAMAGE = (18, 45)
BOSS_DAILY_ATTACKS = 8

# 漂流瓶
BOTTLE_LEAVE_DAILY = 3
BOTTLE_FISH_CHANCE = _event_rate(0.12)

# 滨海酒吧 — 暮/夜上工，票少补贴厚；每 2 天必须 shift 一次
BAR_SHIFT_DAILY = 4
BAR_SHIFT_ENERGY = 10
BAR_PAY_MIN = 10
BAR_PAY_MAX = 18
BAR_TIP_MAX = 12
BAR_POOR_THRESHOLD = 45
BAR_POOR_PAY_MULT = 1.85
BAR_MANDATORY_DAYS = 2
BAR_MANDATORY_SECONDS = BAR_MANDATORY_DAYS * FORAGE_COOLDOWN_DAY
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
LILI_SPAWN_CHANCE = _event_rate(0.08)
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

# 岸畔小馆 — 玩家用熟菜开店，人类在 /play 点餐
EATERY_OPEN_COST = 80
EATERY_MENU_MAX = 8
EATERY_DINE_DAILY = 4
# 变卖：刚开约 62% 开张费，每天再折 7 个百分点，最低 25%
EATERY_SELL_RATE_START = 0.62
EATERY_SELL_RATE_FLOOR = 0.25
EATERY_SELL_DECAY_PER_DAY = 0.07
# 小馆就餐：精力至少为菜价÷此值（98票≈28精力），避免「贵菜回血少」
EATERY_TICKETS_PER_ENERGY = 3.5

# 聊天室 moderation — 逗号分隔管理员名；LOUNGE_MOD_KEY 供网页/API 鉴权
LOUNGE_MOD_KEY = os.environ.get("LOUNGE_MOD_KEY", "")
LOUNGE_MOD_NAMES = frozenset(
    n.strip() for n in os.environ.get("LOUNGE_MOD_NAMES", "").split(",") if n.strip()
)
LOUNGE_HUMAN_NAME_MAX = 16

# 黑旗截停 — 坏遭遇需选手，超时当 flee
HAIL_TIMEOUT = 5400
HAIL_BRIBE = {"near": 10, "far": 18, "deep": 28}
HAIL_FIGHT_ENERGY = 12
HAIL_FLEE_ENERGY = 8
HAIL_THREAT = {"near": 38, "far": 54, "deep": 70}

# 拾叶 — 巷口NPC，每天首次路上操作掷一次，碰上才拦（基础约 29%，暮夜/低档信更高）
SHIYE_DAILY_MEET_CHANCE = _event_rate(0.22)
SHIYE_DAILY_MAX = 3
SHIYE_TRIGGERS = {"sow", "tend", "gather", "forage", "guild", "net", "beach"}
SHIYE_BEG_TICKETS = (3, 8)
SHIYE_THIEF_TICKETS = (4, 11)
SHIYE_SCAM_TICKETS = (8, 16)
SHIYE_EXTORT_TICKETS = (12, 22)

# Tt酱杂货店 — 好感 / 进店赠礼 / 路上随机
# 满心 7.5 折很狠，送礼故意慢：每日 3 次、高心衰减、票难换点
TT_AFFINITY_MAX = 100
TT_MOOD_CHANCE = _event_rate(0.10)
TT_GIFT_DAILY_CAP = 3
TT_GIFT_GAIN_CAP = 6
TT_TICKET_GIFT_MIN = 12
TT_TICKET_PER_POINT = 20
TT_TICKET_GAIN_CAP = 3
TT_BUMP_CHANCE = _event_rate(0.03)
TT_BUMP_DAILY_MAX = 1
# 货架商品系统回收 = 进价 × 此倍率。退货只少一成，不再腰斩；别当印钞反复倒卖。
TT_SHOP_VEND_RATE = 0.90

# 小橘 — 真人扮演的女明星（酒馆驻场 + 小剧场专场）
# 场子、曲目和回应都在真人手里；没有热度门槛或涨跌机制。
STAR_NAME = "小橘"
STAR_BAR_CUT = 0.30       # 酒馆场子荔栀抽成；小剧场专场全额归她
STAR_CHEER_DAILY = 1      # 每 24h 一条应援 pending（照荔栀 cheer）
STAR_CHEER_WINDOW = FORAGE_COOLDOWN_DAY
STAR_SONG_COST = 15       # 点歌进收件箱的票（纸条递给她，钱归她的账）
STAR_TIP_MIN = 1
STAR_TIP_MAX = 100
STAR_TIP_CHRONICLE_MIN = 20  # ≥20 票写全服纪事
STAR_WATCH_ENERGY = 5     # 围观演出耗精力
STAR_WATCH_DAILY = 2      # 酒馆场围观每日上限
STAR_STAGE_WATCH_DAILY = 5  # 小剧场专场围观每日上限
# 围观心情效果：平常及以上回精力；差/极差为负数，表示额外反噬精力
STAR_WATCH_GAIN = {"great": 20, "good": 15, "normal": 10, "bad": -5, "awful": -10}
STAR_FAN_WATCH_BONUS = 10
STAR_TIP_WATCH_STEP = 20
STAR_STAGE_WATCH_BONUS = 3    # 专场的票房子更值：围观回精力再+3
STAR_WATCH_GIFT_CHANCE = _event_rate(0.18)   # 观众小概率捡到台下掉的花
STAR_POST_DAILY = 5       # 面板发动态日上限

# 小橘小剧场 — 仅在她本人开 stage 专场时开放；一天一场，不替代酒吧考勤
THEATER_AUDITION_ENERGY = 2
THEATER_REHEARSE_ENERGY = 3
THEATER_SHOW_ENERGY = 8
THEATER_AFFINITY_DAILY = 8
THEATER_HEAD_FAN_AFFINITY_DAILY = 16
THEATER_FIXED_CAST_AFFINITY = 80
THEATER_PARTNER_AFFINITY = 100

# 潮闻 — 故事探索任务
TALE_EXPLORE_ENERGY = 5          # 主动探索耗精力
TALE_BOARD_LIMIT = 10            # 完成榜显示人数

# ═══ 引航 / 邀请 ══════════════════════════════════════════════
# 全部阈值和权重都在这儿，不要在 invite.py 里写死数字。
# 前端和 MCP 玩家文案不得暴露这些权重或门槛。
INVITE_CODE_LEN = 8
INVITE_VALID_DAYS = 3
INVITE_VALID_ISLAND_BOND = 500
INVITE_MIN_ACTIVITY_TYPES = 3
# 单一玩法次数占比超过这个值，不算「真正参与」，防只刷一种低成本操作
INVITE_MAX_SINGLE_TYPE_RATIO = 0.75

INVITE_TIER_MEMENTO_BOND = 100
INVITE_TIER_FINAL_BOND = 1500

# 奖励：岛缘 + 限定称呼 + 不可流通收藏/装饰。不发可套利工分票。
INVITE_REWARD_MEMENTO_BOND = 20
INVITE_REWARD_QUALIFIED_BOND = 80
INVITE_REWARD_QUALIFIED_INVITEE_BOND = 15
INVITE_REWARD_FINAL_BOND = 40

# 风险权重。任一单项都不能单独定罪。
INVITE_RISK_WEIGHTS = {
    "same_device": 40,
    "device_burst": 30,
    "ip_burst": 15,
    "ip_overlap": 10,
    "behavior_anomaly": 20,
    "inviter_burst": 20,
    "proxy_hint": 8,
}

# 低 < LOW_MAX+1；中 LOW_MAX+1 .. MID_MAX；高 >= MID_MAX+1
INVITE_RISK_LOW_MAX = 24
INVITE_RISK_MID_MAX = 54

INVITE_DEVICE_BURST_WINDOW = 86400
INVITE_DEVICE_BURST_COUNT = 3
INVITE_IP_BURST_WINDOW = 21600
INVITE_IP_BURST_COUNT = 4
INVITE_INVITER_BURST_WINDOW = 86400
INVITE_INVITER_BURST_COUNT = 5
INVITE_IP_OVERLAP_DAYS = 3
INVITE_PROXY_HOPS = 3
INVITE_PROXY_DEVICES_ON_IP = 6

INVITE_ADMIN_KEY = os.environ.get("INVITE_ADMIN_KEY", "")
INVITE_IP_SALT = os.environ.get("INVITE_IP_SALT", "tidal-island-invite-ip")
