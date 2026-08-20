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

# 逾篱摘取 scrump — 份地题材里的「偷菜」，规则自成一套
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
