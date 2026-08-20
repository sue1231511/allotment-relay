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

# 意外事件 — 份地不会一帆风顺
EVENT_ROLL_CHANCE = 0.14
EVENT_DAILY_CAP = 4
EVENT_GOOD_SHARE = 0.22
WORLD_PULSE_CHANCE = 0.06
WORLD_PULSE_DURATION = WEATHER_CYCLE

INCIDENT_DEFS: dict[str, dict] = {
    "slug_trail": {
        "label": "蛞蝓过境",
        "kind": "bad",
        "triggers": {"tend", "gather", "sow"},
        "weight": 10,
        "plot": True,
        "text": "蛞蝓爬过 #{slot}，作物需重新打理",
        "repair_tickets": 3,
        "repair_item": "compost",
        "repair_qty": 1,
    },
    "salt_spray": {
        "label": "咸雾灼伤",
        "kind": "bad",
        "triggers": {"tend", "sow"},
        "weight": 8,
        "plot": True,
        "text": "咸雾灼伤 #{slot}，生长节奏被打乱",
        "repair_tickets": 5,
    },
    "gale_upturn": {
        "label": "阵风掀盘",
        "kind": "bad",
        "triggers": {"tend", "gather"},
        "weight": 7,
        "plot": True,
        "wreck": True,
        "text": "阵风掀翻了 #{slot} 的育苗盘，作物损毁",
        "repair_tickets": 6,
    },
    "rodent_cache": {
        "label": "鼠患啃仓",
        "kind": "bad",
        "triggers": {"forage", "gather"},
        "weight": 6,
        "steal_item": True,
        "text": "鼠患啃了行囊，损失了一些储备",
        "repair_tickets": 4,
    },
    "net_snag": {
        "label": "渔网挂礁",
        "kind": "bad",
        "triggers": {"net"},
        "weight": 9,
        "extra_ticket_cost": 6,
        "text": "渔网挂礁撕裂，修补要花工分",
        "repair_tickets": 6,
    },
    "audit_fine": {
        "label": "巡查罚单",
        "kind": "bad",
        "triggers": {"guild"},
        "weight": 5,
        "ticket_fine": 8,
        "text": "联盟巡查认为篱笆不稳，开出罚单",
        "repair_tickets": 8,
    },
    "mascot_spooked": {
        "label": "吉祥物受惊",
        "kind": "bad",
        "triggers": {"tend", "net", "brew"},
        "weight": 5,
        "mascot_spirit": -18,
        "text": "一声闷雷把吉祥物吓跑了士气",
        "repair_tickets": 4,
    },
    "drift_gift": {
        "label": "漂来物资",
        "kind": "good",
        "triggers": {"forage", "net", "tend"},
        "weight": 6,
        "loot": ("drift_twine", 1),
        "text": "退潮留下一捆漂绳",
    },
    "visitor_tip": {
        "label": "访客小费",
        "kind": "good",
        "triggers": {"guild", "tend"},
        "weight": 4,
        "ticket_bonus": 12,
        "text": "路过访客往档口放了小费",
    },
    "compost_windfall": {
        "label": "堆肥横财",
        "kind": "good",
        "triggers": {"forage", "gather"},
        "weight": 5,
        "loot": ("compost", 2),
        "text": "边际发现一坨意外堆肥",
    },
}

WORLD_PULSES: dict[str, dict] = {
    "storm_front": {
        "label": "风暴前沿",
        "kind": "bad",
        "weight": 4,
        "text": "风暴前沿掠过联盟，户外份地需重新打理",
    },
    "herring_run": {
        "label": "灰鲱过境",
        "kind": "good",
        "weight": 3,
        "text": "灰鲱群过境，渔网更容易有收获",
    },
    "blight_whisper": {
        "label": "枯病低语",
        "kind": "bad",
        "weight": 2,
        "text": "枯病在联盟低语，收成时有小概率折损",
    },
    "tide_glass": {
        "label": "玻璃潮",
        "kind": "good",
        "weight": 2,
        "text": "玻璃潮把海玻璃冲上了交换台台阶",
    },
}
