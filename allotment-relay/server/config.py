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
