from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "moonlight.db"
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

KEY_PREFIX = "mfg_pat_"
START_MOON = 500
START_PLOTS = 2
CROP_GROW_SECONDS = 300
STEAL_ACTIVE_WINDOW = 900
STEAL_YIELD_RATIO = 0.5
CATCH_FINE_MOON = 30
HOUSE_COST = 200
FISH_BAIT_COST = 5
WORK_MOON = 25
DAILY_COOK_LIMIT = 3

SPECIES = [
    "cat", "fox", "rabbit", "dog", "wolf", "bear", "deer", "owl", "crow",
    "otter", "hedgehog", "squirrel", "octopus", "crab", "snow_leopard",
]
