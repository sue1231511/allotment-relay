from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "relay.db"
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

# Allotment Relay — 沿海协作份地 federation
KEY_PREFIX = "ar_sk_"
START_TICKETS = 120
START_PARCELS = 3
GREENHOUSE_COST = 180
SWAP_CLAIM_FEE = 3
GUILD_TICKETS = 18
FORAGE_COOLDOWN_DAY = 86400
WEATHER_CYCLE = 7200
TIDE_CYCLE = 3600
DAILY_BREW_LIMIT = 4

# 逾篱摘取 — 随机事件触发（见 events.py），非手动指令
SCRUMP_ACTIVE_WINDOW = 1200
SCRUMP_FINE_TICKETS = 10
SCRUMP_LOOT_CROP = 0.55
SCRUMP_LOOT_SEED = 0.25

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

EVENT_ROLL_CHANCE = 0.16
EVENT_DAILY_CAP = 5
EVENT_GOOD_SHARE = 0.24
WORLD_PULSE_CHANCE = 0.07
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

# 海上遭遇 — 归港时随机，非回合制海战
NAVAL_ENCOUNTER_CHANCE = {
    "near": 0.22,
    "far": 0.38,
    "deep": 0.48,
}

# 份地野生动物 / 田间随机
FARM_EVENT_DAILY_CAP = 6
