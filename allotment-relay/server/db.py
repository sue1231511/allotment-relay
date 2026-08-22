import asyncio
import contextvars
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import aiosqlite

from .catalog import STARTER_STOCK
from .config import DATA_DIR, DB_PATH, KEY_PREFIX, START_ENERGY, START_PARCELS, START_TICKETS

# 单进程内串行化 SQLite 访问，避免多云端 Agent 并发时 database is locked
_DB_MUTEX = asyncio.Lock()
_DB_CONN: contextvars.ContextVar[aiosqlite.Connection | None] = contextvars.ContextVar(
    "_db_conn", default=None,
)
_DB_PRAGMAS_READY = False

DB_BUSY_MSG = (
    "数据库正忙（岛上同时操作的人太多）。等 10～30 秒再发同一条指令，不要连点。"
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    api_key TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_api_keys_email ON api_keys(email);

CREATE TABLE IF NOT EXISTS stewards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_id INTEGER NOT NULL UNIQUE REFERENCES api_keys(id),
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    motto TEXT NOT NULL DEFAULT '',
    badge TEXT NOT NULL DEFAULT 'naturalist',
    portrait TEXT NOT NULL DEFAULT '',
    tickets INTEGER NOT NULL DEFAULT 0,
    xp INTEGER NOT NULL DEFAULT 0,
    parcel_count INTEGER NOT NULL DEFAULT 3,
    greenhouse INTEGER NOT NULL DEFAULT 0,
    greenhouse_label TEXT NOT NULL DEFAULT '',
    mascot_name TEXT NOT NULL DEFAULT '',
    mascot_trait TEXT NOT NULL DEFAULT '',
    mascot_spirit INTEGER NOT NULL DEFAULT 70,
    forage_at INTEGER NOT NULL DEFAULT 0,
    brews_today INTEGER NOT NULL DEFAULT 0,
    brew_day INTEGER NOT NULL DEFAULT 0,
    enrolled INTEGER NOT NULL DEFAULT 0,
    last_active_at INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS parcels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    slot INTEGER NOT NULL,
    crop TEXT,
    planted_at INTEGER,
    tended INTEGER NOT NULL DEFAULT 0,
    greenhouse INTEGER NOT NULL DEFAULT 0,
    ready_at INTEGER NOT NULL DEFAULT 0,
    UNIQUE(steward_id, slot)
);

CREATE TABLE IF NOT EXISTS satchel (
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    item TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (steward_id, item)
);

CREATE TABLE IF NOT EXISTS chronicle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    actor_id INTEGER,
    target_id INTEGER,
    text TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS beacons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    author_id INTEGER NOT NULL REFERENCES stewards(id),
    tag TEXT NOT NULL DEFAULT 'general',
    body TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS beacon_replies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    beacon_id INTEGER NOT NULL REFERENCES beacons(id),
    author_id INTEGER NOT NULL REFERENCES stewards(id),
    body TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS swap_lots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    depositor_id INTEGER NOT NULL REFERENCES stewards(id),
    item TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    claimed_by INTEGER,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS hearth_discoveries (
    signature TEXT NOT NULL UNIQUE,
    meal_key TEXT NOT NULL,
    discoverer_id INTEGER NOT NULL REFERENCES stewards(id),
    discovered_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS handoffs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_id INTEGER NOT NULL REFERENCES stewards(id),
    to_id INTEGER NOT NULL REFERENCES stewards(id),
    item TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    picked_up INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS assist_log (
    helper_id INTEGER NOT NULL REFERENCES stewards(id),
    target_id INTEGER NOT NULL REFERENCES stewards(id),
    day INTEGER NOT NULL,
    PRIMARY KEY (helper_id, target_id, day)
);
CREATE TABLE IF NOT EXISTS scrump_log (
    thief_id INTEGER NOT NULL REFERENCES stewards(id),
    target_id INTEGER NOT NULL REFERENCES stewards(id),
    day INTEGER NOT NULL,
    PRIMARY KEY (thief_id, target_id, day)
);

CREATE TABLE IF NOT EXISTS rapport (
    steward_a INTEGER NOT NULL REFERENCES stewards(id),
    steward_b INTEGER NOT NULL REFERENCES stewards(id),
    score INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (steward_a, steward_b)
);

CREATE TABLE IF NOT EXISTS larder (
    item TEXT PRIMARY KEY,
    quantity INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS larder_draws (
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    day INTEGER NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (steward_id, day)
);

CREATE TABLE IF NOT EXISTS contracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    poster_id INTEGER NOT NULL REFERENCES stewards(id),
    want_item TEXT NOT NULL,
    want_qty INTEGER NOT NULL,
    reward_tickets INTEGER NOT NULL,
    filler_id INTEGER,
    status TEXT NOT NULL DEFAULT 'open',
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS league_week (
    week_id INTEGER PRIMARY KEY,
    goal_key TEXT NOT NULL,
    target INTEGER NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0,
    completed INTEGER NOT NULL DEFAULT 0,
    completed_at INTEGER
);

CREATE TABLE IF NOT EXISTS league_contrib (
    week_id INTEGER NOT NULL,
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    amount INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (week_id, steward_id)
);

CREATE TABLE IF NOT EXISTS steward_incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    incident_key TEXT NOT NULL,
    plot_id INTEGER,
    detail TEXT NOT NULL DEFAULT '',
    label TEXT NOT NULL DEFAULT '',
    repair_tickets INTEGER NOT NULL DEFAULT 0,
    repair_item TEXT,
    repair_qty INTEGER NOT NULL DEFAULT 0,
    resolved INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS event_rolls (
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    day INTEGER NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (steward_id, day)
);

CREATE TABLE IF NOT EXISTS world_pulse (
    pulse_key TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'bad',
    effect_type TEXT NOT NULL DEFAULT '',
    fish_focus TEXT,
    detail TEXT NOT NULL DEFAULT '',
    started_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS fish_pens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    slot INTEGER NOT NULL DEFAULT 1,
    species TEXT,
    stocked_at INTEGER,
    fed INTEGER NOT NULL DEFAULT 0,
    pen_label TEXT NOT NULL DEFAULT '',
    UNIQUE(steward_id, slot)
);

CREATE TABLE IF NOT EXISTS voyages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    steward_id INTEGER NOT NULL UNIQUE REFERENCES stewards(id),
    route TEXT NOT NULL,
    departed_at INTEGER NOT NULL,
    returns_at INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'sailing',
    encounter TEXT
);

CREATE TABLE IF NOT EXISTS farm_rolls (
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    day INTEGER NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (steward_id, day)
);

CREATE TABLE IF NOT EXISTS gugu_dove_pending (
    steward_id INTEGER PRIMARY KEY REFERENCES stewards(id),
    plot_id INTEGER NOT NULL REFERENCES parcels(id),
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS commons_spawns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spawn_key TEXT NOT NULL,
    label TEXT NOT NULL,
    domain TEXT NOT NULL DEFAULT 'shore',
    reward_item TEXT,
    reward_qty INTEGER NOT NULL DEFAULT 0,
    reward_tickets INTEGER NOT NULL DEFAULT 0,
    detail TEXT NOT NULL DEFAULT '',
    appears_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    claimed_by INTEGER REFERENCES stewards(id),
    claimed_at INTEGER
);

CREATE TABLE IF NOT EXISTS discovery_rolls (
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    day INTEGER NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (steward_id, day)
);

CREATE TABLE IF NOT EXISTS hut_fittings (
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    slot TEXT NOT NULL,
    item_key TEXT NOT NULL,
    installed_at INTEGER NOT NULL,
    PRIMARY KEY (steward_id, slot)
);

CREATE TABLE IF NOT EXISTS market_listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_id INTEGER NOT NULL REFERENCES stewards(id),
    item TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    price INTEGER NOT NULL,
    suggested INTEGER NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '',
    buyer_id INTEGER REFERENCES stewards(id),
    sold_at INTEGER,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS steward_catches (
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    catch_key TEXT NOT NULL,
    first_at INTEGER NOT NULL,
    catch_count INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (steward_id, catch_key)
);

CREATE TABLE IF NOT EXISTS drift_bottles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    author_id INTEGER NOT NULL REFERENCES stewards(id),
    body TEXT NOT NULL,
    signature TEXT NOT NULL DEFAULT '',
    found_by INTEGER REFERENCES stewards(id),
    found_at INTEGER,
    reply_body TEXT NOT NULL DEFAULT '',
    reply_by INTEGER REFERENCES stewards(id),
    reply_at INTEGER,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS world_boss (
    boss_key TEXT PRIMARY KEY,
    hp INTEGER NOT NULL,
    max_hp INTEGER NOT NULL,
    defeated_at INTEGER,
    respawn_at INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS boss_attacks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    boss_key TEXT NOT NULL,
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    damage INTEGER NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS barn_animals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    slot INTEGER NOT NULL,
    species TEXT,
    stocked_at INTEGER,
    fed INTEGER NOT NULL DEFAULT 0,
    guard INTEGER NOT NULL DEFAULT 0,
    UNIQUE(steward_id, slot)
);

CREATE TABLE IF NOT EXISTS meal_storage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    dish_key TEXT NOT NULL,
    stars INTEGER NOT NULL DEFAULT 3,
    quantity INTEGER NOT NULL DEFAULT 1,
    stored_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS kitchen_rolls (
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    day INTEGER NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (steward_id, day)
);

CREATE TABLE IF NOT EXISTS beach_rolls (
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    day INTEGER NOT NULL,
    last_at INTEGER NOT NULL DEFAULT 0,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (steward_id, day)
);

CREATE TABLE IF NOT EXISTS beach_probe_rolls (
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    day INTEGER NOT NULL,
    last_at INTEGER NOT NULL DEFAULT 0,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (steward_id, day)
);

CREATE TABLE IF NOT EXISTS barn_daily_collect (
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    slot INTEGER NOT NULL,
    day INTEGER NOT NULL,
    PRIMARY KEY (steward_id, slot, day)
);

CREATE TABLE IF NOT EXISTS steward_ailments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    ailment_key TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'event',
    inflicted_at INTEGER NOT NULL,
    stage INTEGER NOT NULL DEFAULT 0,
    last_tick_at INTEGER NOT NULL DEFAULT 0,
    last_treat_at INTEGER NOT NULL DEFAULT 0,
    UNIQUE(steward_id, ailment_key)
);

CREATE TABLE IF NOT EXISTS boss_rolls (
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    day INTEGER NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (steward_id, day)
);

CREATE TABLE IF NOT EXISTS bottle_rolls (
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    day INTEGER NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (steward_id, day)
);

CREATE TABLE IF NOT EXISTS steward_gear (
    steward_id INTEGER PRIMARY KEY REFERENCES stewards(id),
    bait_tier INTEGER NOT NULL DEFAULT 1,
    rod_tier INTEGER NOT NULL DEFAULT 0,
    net_tier INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS bar_rolls (
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    day INTEGER NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (steward_id, day)
);

CREATE TABLE IF NOT EXISTS bar_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patron_id INTEGER NOT NULL REFERENCES stewards(id),
    host_id INTEGER REFERENCES stewards(id),
    service TEXT NOT NULL,
    cost INTEGER NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS bar_skills (
    steward_id INTEGER PRIMARY KEY REFERENCES stewards(id),
    support_xp INTEGER NOT NULL DEFAULT 0,
    service_xp INTEGER NOT NULL DEFAULT 0,
    bar_xp INTEGER NOT NULL DEFAULT 0,
    host_xp INTEGER NOT NULL DEFAULT 0,
    shift_count INTEGER NOT NULL DEFAULT 0,
    total_wages INTEGER NOT NULL DEFAULT 0,
    total_tips INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS bar_shifts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    day INTEGER NOT NULL,
    job TEXT NOT NULL,
    period TEXT NOT NULL,
    wage INTEGER NOT NULL DEFAULT 0,
    tips INTEGER NOT NULL DEFAULT 0,
    event_id TEXT,
    event_text TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS bar_drink_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patron_id INTEGER NOT NULL REFERENCES stewards(id),
    drink_key TEXT NOT NULL,
    cost INTEGER NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS bar_tips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_id INTEGER NOT NULL REFERENCES stewards(id),
    to_id INTEGER NOT NULL REFERENCES stewards(id),
    amount INTEGER NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    day INTEGER NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS bar_daily_state (
    day INTEGER PRIMARY KEY,
    owner_mood TEXT NOT NULL DEFAULT 'normal',
    auto_mood TEXT NOT NULL DEFAULT 'normal',
    manual_mood_level TEXT NOT NULL DEFAULT '',
    manual_mood_text TEXT NOT NULL DEFAULT '',
    manual_mood_date INTEGER NOT NULL DEFAULT 0,
    revenue_tickets INTEGER NOT NULL DEFAULT 0,
    owner_event_text TEXT NOT NULL DEFAULT '',
    owner_event_date INTEGER NOT NULL DEFAULT 0,
    owner_event_enabled INTEGER NOT NULL DEFAULT 0,
    special_drink TEXT NOT NULL DEFAULT '',
    activity_key TEXT,
    global_event TEXT NOT NULL DEFAULT '',
    duo_nudge TEXT NOT NULL DEFAULT '',
    duo_steward_a INTEGER NOT NULL DEFAULT 0,
    duo_steward_b INTEGER NOT NULL DEFAULT 0,
    duo_activated_at INTEGER NOT NULL DEFAULT 0,
    singer_state TEXT NOT NULL DEFAULT '',
    playlist_json TEXT NOT NULL DEFAULT '[]',
    song_queue_json TEXT NOT NULL DEFAULT '[]',
    first_order_free INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS bar_unlocks (
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    unlock_key TEXT NOT NULL,
    PRIMARY KEY (steward_id, unlock_key)
);

CREATE TABLE IF NOT EXISTS lili_visits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    day_id INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS lili_offers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    visit_id INTEGER NOT NULL REFERENCES lili_visits(id),
    trade_key TEXT NOT NULL,
    give_json TEXT NOT NULL,
    get_item TEXT NOT NULL,
    get_qty INTEGER NOT NULL DEFAULT 1,
    ticket_cost INTEGER NOT NULL DEFAULT 0,
    stock INTEGER NOT NULL DEFAULT 1,
    sold INTEGER NOT NULL DEFAULT 0,
    day_id INTEGER NOT NULL DEFAULT 0,
    domains_json TEXT NOT NULL DEFAULT '[]',
    offer_tier INTEGER NOT NULL DEFAULT 1,
    value_total INTEGER NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS steward_lili (
    steward_id INTEGER PRIMARY KEY REFERENCES stewards(id),
    stars_until INTEGER NOT NULL DEFAULT 0,
    fool_visit_id INTEGER NOT NULL DEFAULT 0,
    fool_count INTEGER NOT NULL DEFAULT 0,
    favored_visit_id INTEGER NOT NULL DEFAULT 0,
    pet_day INTEGER NOT NULL DEFAULT 0,
    pet_visit_id INTEGER NOT NULL DEFAULT 0,
    dog_fur INTEGER NOT NULL DEFAULT 0,
    bell_hint_day INTEGER NOT NULL DEFAULT 0,
    blessing_key TEXT NOT NULL DEFAULT '',
    blessing_uses INTEGER NOT NULL DEFAULT 0,
    summon_chance INTEGER NOT NULL DEFAULT 30,
    summon_done INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS npc_visits (
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    npc_key TEXT NOT NULL,
    day INTEGER NOT NULL,
    PRIMARY KEY (steward_id, npc_key, day)
);

CREATE TABLE IF NOT EXISTS tt_affinity (
    steward_id INTEGER PRIMARY KEY REFERENCES stewards(id),
    score INTEGER NOT NULL DEFAULT 0,
    updated_at INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tt_daily (
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    day INTEGER NOT NULL,
    visit_done INTEGER NOT NULL DEFAULT 0,
    mood_gift INTEGER NOT NULL DEFAULT 0,
    gifts INTEGER NOT NULL DEFAULT 0,
    bumps INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (steward_id, day)
);

CREATE TABLE IF NOT EXISTS eatery_menu (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    item TEXT NOT NULL,
    price INTEGER NOT NULL,
    listed_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS eatery_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shop_id INTEGER NOT NULL REFERENCES stewards(id),
    patron_id INTEGER NOT NULL REFERENCES stewards(id),
    item TEXT NOT NULL,
    price INTEGER NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS eatery_rolls (
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    day INTEGER NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (steward_id, day)
);

CREATE TABLE IF NOT EXISTS shiye_rolls (
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    day INTEGER NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (steward_id, day)
);

CREATE TABLE IF NOT EXISTS shaonian_daily (
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    day INTEGER NOT NULL,
    fortune TEXT NOT NULL DEFAULT '',
    fortune_casts INTEGER NOT NULL DEFAULT 0,
    transfer_done INTEGER NOT NULL DEFAULT 0,
    transfer_failed INTEGER NOT NULL DEFAULT 0,
    visit_done INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (steward_id, day)
);

CREATE TABLE IF NOT EXISTS shaonian_charms (
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    day INTEGER NOT NULL,
    charm_key TEXT NOT NULL,
    purchased_at INTEGER NOT NULL,
    PRIMARY KEY (steward_id, day, charm_key)
);

CREATE TABLE IF NOT EXISTS guild_shifts (
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    day INTEGER NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (steward_id, day)
);

CREATE TABLE IF NOT EXISTS tale_catalog (
    tale_key TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    intro TEXT NOT NULL,
    min_level INTEGER NOT NULL DEFAULT 1,
    min_standing INTEGER NOT NULL DEFAULT 0,
    domain TEXT NOT NULL DEFAULT 'shore',
    stages_json TEXT NOT NULL,
    rewards_json TEXT NOT NULL,
    repeatable INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS steward_tales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    tale_key TEXT NOT NULL,
    stage_idx INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    accepted_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    choices_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(steward_id, tale_key)
);

CREATE TABLE IF NOT EXISTS steward_tales_done (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    tale_key TEXT NOT NULL,
    outcome TEXT NOT NULL DEFAULT 'completed',
    completed_at INTEGER NOT NULL,
    times INTEGER NOT NULL DEFAULT 1,
    UNIQUE(steward_id, tale_key, outcome)
);

CREATE TABLE IF NOT EXISTS tale_explore_rolls (
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    day INTEGER NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (steward_id, day)
);
"""


@asynccontextmanager
async def connect() -> AsyncIterator[aiosqlite.Connection]:
    """Open DB with busy wait — use as `async with connect() as conn:`."""
    global _DB_PRAGMAS_READY
    existing = _DB_CONN.get()
    if existing is not None:
        yield existing
        return
    async with _DB_MUTEX:
        async with aiosqlite.connect(DB_PATH, timeout=60.0) as conn:
            await conn.execute("PRAGMA busy_timeout=30000")
            if not _DB_PRAGMAS_READY:
                await conn.execute("PRAGMA journal_mode=WAL")
                await conn.execute("PRAGMA synchronous=NORMAL")
                await conn.execute("PRAGMA wal_autocheckpoint=1000")
                _DB_PRAGMAS_READY = True
            token = _DB_CONN.set(conn)
            try:
                yield conn
            finally:
                _DB_CONN.reset(token)


def is_db_locked_error(exc: BaseException) -> bool:
    if isinstance(exc, (aiosqlite.OperationalError, sqlite3.OperationalError)):
        return "locked" in str(exc).lower()
    return False


async def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    probe = DATA_DIR / ".write_probe"
    try:
        probe.write_text("ok")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        raise RuntimeError(
            f"数据库目录不可写: {DATA_DIR} ({exc}). "
            "请检查 Zeabur 持久卷是否挂载到 /app/server/data"
        ) from exc
    async with aiosqlite.connect(DB_PATH, timeout=30.0) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")
        await db.execute("PRAGMA busy_timeout=10000")
        await db.executescript(SCHEMA)
        for ddl in (
            "ALTER TABLE stewards ADD COLUMN boat_key TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE stewards ADD COLUMN boat_damaged INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE steward_incidents ADD COLUMN label TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE steward_incidents ADD COLUMN repair_tickets INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE steward_incidents ADD COLUMN repair_item TEXT",
            "ALTER TABLE steward_incidents ADD COLUMN repair_qty INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE world_pulse ADD COLUMN effect_type TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE world_pulse ADD COLUMN fish_focus TEXT",
            "ALTER TABLE world_pulse ADD COLUMN detail TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE stewards ADD COLUMN satiety INTEGER NOT NULL DEFAULT 72",
            "ALTER TABLE stewards ADD COLUMN mist_wit INTEGER NOT NULL DEFAULT 78",
            "ALTER TABLE stewards ADD COLUMN standing INTEGER NOT NULL DEFAULT 88",
            "ALTER TABLE parcels ADD COLUMN grow_target INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE parcels ADD COLUMN grow_pace TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE stewards ADD COLUMN hut_built INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE stewards ADD COLUMN hut_level INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE stewards ADD COLUMN hut_label TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE stewards ADD COLUMN energy INTEGER NOT NULL DEFAULT 80",
            "ALTER TABLE stewards ADD COLUMN barn_built INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE stewards ADD COLUMN beach_at INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE parcels ADD COLUMN fertilized INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE parcels ADD COLUMN scarecrow INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE stewards ADD COLUMN last_bar_shift_at INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE stewards ADD COLUMN health INTEGER NOT NULL DEFAULT 100",
            "ALTER TABLE stewards ADD COLUMN eatery_open INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE stewards ADD COLUMN eatery_label TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE stewards ADD COLUMN eatery_opened_at INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE stewards ADD COLUMN fruit_streak INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE stewards ADD COLUMN bed_rest_at INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE voyages ADD COLUMN encounter TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE bar_daily_state ADD COLUMN auto_mood TEXT NOT NULL DEFAULT 'normal'",
            "ALTER TABLE bar_daily_state ADD COLUMN manual_mood_level TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE bar_daily_state ADD COLUMN manual_mood_text TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE bar_daily_state ADD COLUMN manual_mood_date INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE bar_daily_state ADD COLUMN revenue_tickets INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE bar_daily_state ADD COLUMN owner_event_text TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE bar_daily_state ADD COLUMN owner_event_date INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE bar_daily_state ADD COLUMN owner_event_enabled INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE bar_daily_state ADD COLUMN first_order_free INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE bar_daily_state ADD COLUMN duo_nudge TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE bar_daily_state ADD COLUMN duo_steward_a INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE bar_daily_state ADD COLUMN duo_steward_b INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE bar_daily_state ADD COLUMN duo_activated_at INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE drift_bottles ADD COLUMN reply_body TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE drift_bottles ADD COLUMN reply_by INTEGER REFERENCES stewards(id)",
            "ALTER TABLE drift_bottles ADD COLUMN reply_at INTEGER",
            "ALTER TABLE lili_visits ADD COLUMN day_id INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE lili_offers ADD COLUMN day_id INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE lili_offers ADD COLUMN domains_json TEXT NOT NULL DEFAULT '[]'",
            "ALTER TABLE lili_offers ADD COLUMN offer_tier INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE lili_offers ADD COLUMN value_total INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE lili_offers ADD COLUMN note TEXT NOT NULL DEFAULT ''",
            """
            CREATE TABLE IF NOT EXISTS steward_lili (
                steward_id INTEGER PRIMARY KEY REFERENCES stewards(id),
                stars_until INTEGER NOT NULL DEFAULT 0,
                fool_visit_id INTEGER NOT NULL DEFAULT 0,
                fool_count INTEGER NOT NULL DEFAULT 0,
                favored_visit_id INTEGER NOT NULL DEFAULT 0,
                pet_day INTEGER NOT NULL DEFAULT 0,
                pet_visit_id INTEGER NOT NULL DEFAULT 0,
                dog_fur INTEGER NOT NULL DEFAULT 0,
                bell_hint_day INTEGER NOT NULL DEFAULT 0,
                blessing_key TEXT NOT NULL DEFAULT '',
                blessing_uses INTEGER NOT NULL DEFAULT 0,
                summon_chance INTEGER NOT NULL DEFAULT 30,
                summon_done INTEGER NOT NULL DEFAULT 0
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS gugu_dove_pending (
                steward_id INTEGER PRIMARY KEY REFERENCES stewards(id),
                plot_id INTEGER NOT NULL REFERENCES parcels(id),
                created_at INTEGER NOT NULL
            )
            """,
            "ALTER TABLE parcels ADD COLUMN dove_yield_mult REAL NOT NULL DEFAULT 1.0",
            "ALTER TABLE parcels ADD COLUMN harvest_left INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE parcels ADD COLUMN watered INTEGER NOT NULL DEFAULT 0",
            """
            CREATE TABLE IF NOT EXISTS hut_cabinet (
                steward_id INTEGER NOT NULL REFERENCES stewards(id),
                item TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                stored_at INTEGER NOT NULL,
                PRIMARY KEY (steward_id, item)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS steward_undertide (
                steward_id INTEGER PRIMARY KEY REFERENCES stewards(id),
                shadow_rep INTEGER NOT NULL DEFAULT 10,
                access INTEGER NOT NULL DEFAULT 0,
                well_hint INTEGER NOT NULL DEFAULT 0,
                pricey_count INTEGER NOT NULL DEFAULT 0,
                busted_count INTEGER NOT NULL DEFAULT 0,
                jail_state TEXT NOT NULL DEFAULT '',
                jail_until INTEGER NOT NULL DEFAULT 0,
                jail_work_today INTEGER NOT NULL DEFAULT 0,
                jail_work_day INTEGER NOT NULL DEFAULT 0,
                seen_events TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL DEFAULT 0
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS ut_market_shelf (
                day_id INTEGER NOT NULL,
                slot INTEGER NOT NULL,
                layer TEXT NOT NULL,
                item_key TEXT NOT NULL,
                stock INTEGER NOT NULL,
                price_mult REAL NOT NULL DEFAULT 1.0,
                PRIMARY KEY (day_id, slot)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS ut_market_log (
                steward_id INTEGER NOT NULL,
                day_id INTEGER NOT NULL,
                item_key TEXT NOT NULL,
                quality TEXT NOT NULL,
                price INTEGER NOT NULL,
                created_at INTEGER NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS ut_debts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                steward_id INTEGER NOT NULL,
                principal INTEGER NOT NULL,
                due_day INTEGER NOT NULL,
                source TEXT NOT NULL DEFAULT 'bank',
                status TEXT NOT NULL DEFAULT 'open',
                created_day INTEGER NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS ut_event_log (
                steward_id INTEGER NOT NULL,
                day_id INTEGER NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (steward_id, day_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS ut_owner_state (
                id INTEGER PRIMARY KEY CHECK (id=1),
                rate_today REAL NOT NULL DEFAULT 0,
                rate_reason TEXT NOT NULL DEFAULT '',
                rate_day INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL DEFAULT 0
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS ut_pit_fighters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                level INTEGER NOT NULL,
                power INTEGER NOT NULL,
                wins INTEGER NOT NULL DEFAULT 0,
                losses INTEGER NOT NULL DEFAULT 0,
                alive INTEGER NOT NULL DEFAULT 1,
                flavor TEXT NOT NULL DEFAULT ''
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS ut_lantern (
                steward_id INTEGER PRIMARY KEY,
                bet INTEGER NOT NULL,
                stage INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS ut_street_npc (
                day_id INTEGER NOT NULL,
                slot INTEGER NOT NULL,
                name TEXT NOT NULL,
                tier TEXT NOT NULL,
                stock_json TEXT NOT NULL DEFAULT '[]',
                PRIMARY KEY (day_id, slot)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS ut_grudge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                steward_id INTEGER NOT NULL,
                npc_name TEXT NOT NULL,
                tier TEXT NOT NULL,
                item_value INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'active',
                created_at INTEGER NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS ut_hijack_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                steward_id INTEGER NOT NULL,
                day_id INTEGER NOT NULL,
                target TEXT NOT NULL,
                outcome TEXT NOT NULL
            )
            """,
            "ALTER TABLE steward_undertide ADD COLUMN hijack_fails INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE steward_undertide ADD COLUMN ban_until INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE steward_undertide ADD COLUMN mark_sewn TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE steward_undertide ADD COLUMN pit_banned INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE steward_undertide ADD COLUMN casino_net INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE steward_undertide ADD COLUMN casino_lose INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE steward_undertide ADD COLUMN casino_day INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE steward_undertide ADD COLUMN pending_grudge INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE steward_undertide ADD COLUMN k_room INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE steward_undertide ADD COLUMN vr_until INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE steward_undertide ADD COLUMN vr_target INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE steward_undertide ADD COLUMN highlight_done INTEGER NOT NULL DEFAULT 0",

            "ALTER TABLE ut_market_log ADD COLUMN net INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE ut_debts ADD COLUMN penalty INTEGER NOT NULL DEFAULT 0",
            """
            CREATE TABLE IF NOT EXISTS ut_bounty (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                poster TEXT NOT NULL,
                poster_id INTEGER,
                target_name TEXT NOT NULL,
                target_id INTEGER,
                tier TEXT NOT NULL,
                bounty INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                expires_at INTEGER NOT NULL,
                created_at INTEGER NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS ut_tide_state (
                id INTEGER PRIMARY KEY CHECK (id=1),
                week INTEGER NOT NULL DEFAULT 0,
                score INTEGER NOT NULL DEFAULT 50,
                mult REAL NOT NULL DEFAULT 1.0,
                reason TEXT NOT NULL DEFAULT '',
                manual_mult REAL,
                updated_at INTEGER NOT NULL DEFAULT 0
            )
            """,
            "ALTER TABLE bar_daily_state ADD COLUMN owner_bogo INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE bar_daily_state ADD COLUMN owner_bogo_count INTEGER NOT NULL DEFAULT 0",
            """
            CREATE TABLE IF NOT EXISTS ut_avatar_bind (
                steward_id INTEGER PRIMARY KEY REFERENCES stewards(id),
                npc_key TEXT NOT NULL,
                bound_at INTEGER NOT NULL DEFAULT 0
            )
            """,
            "ALTER TABLE steward_undertide ADD COLUMN spouse_free_day INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE steward_undertide ADD COLUMN unread_hits TEXT NOT NULL DEFAULT '[]'",
            "ALTER TABLE steward_undertide ADD COLUMN drug_buff INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE steward_undertide ADD COLUMN drug_until INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE steward_undertide ADD COLUMN drug_crash INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE steward_undertide ADD COLUMN spouse_allow_week INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE steward_undertide ADD COLUMN guide_seen INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE steward_undertide ADD COLUMN last_rep_recover_day INTEGER NOT NULL DEFAULT 0",
            "DELETE FROM ut_bounty WHERE poster='__quest__' AND id NOT IN (SELECT MIN(id) FROM ut_bounty WHERE poster='__quest__' GROUP BY target_name, created_at)",
            "ALTER TABLE steward_undertide ADD COLUMN savings INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE stewards ADD COLUMN lodge_until INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE stewards ADD COLUMN lodge_count INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE stewards ADD COLUMN lodge_cooldown INTEGER NOT NULL DEFAULT 0",
            """
            CREATE TABLE IF NOT EXISTS pit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                steward_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                outcome TEXT NOT NULL,
                opponent TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL
            )
            """,
            "ALTER TABLE steward_undertide ADD COLUMN savings_day INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE ut_owner_state ADD COLUMN save_rate REAL NOT NULL DEFAULT 0.02",
            "ALTER TABLE ut_owner_state ADD COLUMN an_happy_day INTEGER NOT NULL DEFAULT 0",
            """
            CREATE TABLE IF NOT EXISTS ut_cheer_discount (
                steward_id INTEGER PRIMARY KEY REFERENCES stewards(id),
                day INTEGER NOT NULL,
                created_at INTEGER NOT NULL DEFAULT 0
            )
            """,
            "ALTER TABLE ut_tide_state ADD COLUMN gate_drinks INTEGER NOT NULL DEFAULT 3",
            "ALTER TABLE ut_tide_state ADD COLUMN event_mult REAL NOT NULL DEFAULT 1.0",
            "ALTER TABLE ut_tide_state ADD COLUMN highlight INTEGER NOT NULL DEFAULT 150",
            """
            CREATE TABLE IF NOT EXISTS ut_mood_proposals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                steward_id INTEGER NOT NULL,
                target_mood TEXT NOT NULL,
                reason TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at INTEGER NOT NULL
            )
            """,
            "ALTER TABLE ut_mood_proposals ADD COLUMN target TEXT NOT NULL DEFAULT 'cat'",
            "ALTER TABLE stewards ADD COLUMN xp INTEGER NOT NULL DEFAULT 0",
            """
            CREATE TABLE IF NOT EXISTS tt_affinity (
                steward_id INTEGER PRIMARY KEY REFERENCES stewards(id),
                score INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL DEFAULT 0
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS tt_daily (
                steward_id INTEGER NOT NULL REFERENCES stewards(id),
                day INTEGER NOT NULL,
                visit_done INTEGER NOT NULL DEFAULT 0,
                mood_gift INTEGER NOT NULL DEFAULT 0,
                gifts INTEGER NOT NULL DEFAULT 0,
                bumps INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (steward_id, day)
            )
            """,
            "ALTER TABLE steward_lili ADD COLUMN summon_chance INTEGER NOT NULL DEFAULT 30",
            "ALTER TABLE steward_lili ADD COLUMN summon_done INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE steward_ailments ADD COLUMN stage INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE steward_ailments ADD COLUMN last_tick_at INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE steward_ailments ADD COLUMN last_treat_at INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE parcels ADD COLUMN ready_at INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE stewards ADD COLUMN cabinet_extra INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE stewards ADD COLUMN worn_title TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE stewards ADD COLUMN reward_level INTEGER NOT NULL DEFAULT 0",
            """
            CREATE TABLE IF NOT EXISTS steward_achievements (
                steward_id INTEGER NOT NULL REFERENCES stewards(id),
                ach_key TEXT NOT NULL,
                unlocked_at INTEGER NOT NULL,
                PRIMARY KEY (steward_id, ach_key)
            )
            """,
            "ALTER TABLE stewards ADD COLUMN market_extra INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE steward_undertide ADD COLUMN racket_day INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE steward_undertide ADD COLUMN racket_json TEXT NOT NULL DEFAULT ''",
            # 小橘 — 真人扮演的女明星（酒馆驻场 + 小剧场专场）
            """
            CREATE TABLE IF NOT EXISTS star_state (
                id INTEGER PRIMARY KEY CHECK (id=1),
                name TEXT NOT NULL DEFAULT '小橘',
                heat INTEGER NOT NULL DEFAULT 20,
                venue TEXT NOT NULL DEFAULT 'bar',
                mood TEXT NOT NULL DEFAULT 'normal',
                mood_text TEXT NOT NULL DEFAULT '',
                setlist TEXT NOT NULL DEFAULT '',
                outfit TEXT NOT NULL DEFAULT '',
                note TEXT NOT NULL DEFAULT '',
                venue_date INTEGER NOT NULL DEFAULT 0,
                total_tips INTEGER NOT NULL DEFAULT 0,
                fans_count INTEGER NOT NULL DEFAULT 0,
                tips_today INTEGER NOT NULL DEFAULT 0,
                tips_day INTEGER NOT NULL DEFAULT 0,
                heat_tips_today INTEGER NOT NULL DEFAULT 0,
                posts_today INTEGER NOT NULL DEFAULT 0,
                post_day INTEGER NOT NULL DEFAULT 0,
                last_settle_day INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL DEFAULT 0
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS star_proposals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                steward_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                content TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at INTEGER NOT NULL DEFAULT 0
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS star_fans (
                steward_id INTEGER PRIMARY KEY REFERENCES stewards(id),
                cheers INTEGER NOT NULL DEFAULT 0,
                tip_total INTEGER NOT NULL DEFAULT 0,
                joined_at INTEGER NOT NULL DEFAULT 0
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS star_tips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                steward_id INTEGER,
                source TEXT NOT NULL DEFAULT 'ai',
                amount INTEGER NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL DEFAULT 0
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS star_watches (
                steward_id INTEGER NOT NULL,
                day INTEGER NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (steward_id, day)
            )
            """,
            # 监控 — 份地装摄像头防偷菜（协作者侧）
            "ALTER TABLE parcels ADD COLUMN camera INTEGER NOT NULL DEFAULT 0",
            """
            CREATE TABLE IF NOT EXISTS scrump_theft_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL REFERENCES stewards(id),
                thief_id INTEGER REFERENCES stewards(id),
                thief_name TEXT NOT NULL,
                plot_slot INTEGER NOT NULL,
                crop_name TEXT NOT NULL,
                qty INTEGER NOT NULL DEFAULT 0,
                caught INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL
            )
            """,
            """
            CREATE TRIGGER IF NOT EXISTS trg_steward_xp_gain
            AFTER UPDATE OF tickets ON stewards
            WHEN NEW.tickets > OLD.tickets
            BEGIN
                UPDATE stewards
                SET xp = COALESCE(xp, 0) + (NEW.tickets - OLD.tickets)
                WHERE id = NEW.id;
            END
            """,
            """
            CREATE TABLE IF NOT EXISTS tale_catalog (
                tale_key TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                intro TEXT NOT NULL,
                min_level INTEGER NOT NULL DEFAULT 1,
                min_standing INTEGER NOT NULL DEFAULT 0,
                domain TEXT NOT NULL DEFAULT 'shore',
                stages_json TEXT NOT NULL,
                rewards_json TEXT NOT NULL,
                repeatable INTEGER NOT NULL DEFAULT 0,
                sort_order INTEGER NOT NULL DEFAULT 0
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS steward_tales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                steward_id INTEGER NOT NULL REFERENCES stewards(id),
                tale_key TEXT NOT NULL,
                stage_idx INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'active',
                accepted_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                choices_json TEXT NOT NULL DEFAULT '{}',
                UNIQUE(steward_id, tale_key)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS steward_tales_done (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                steward_id INTEGER NOT NULL REFERENCES stewards(id),
                tale_key TEXT NOT NULL,
                outcome TEXT NOT NULL DEFAULT 'completed',
                completed_at INTEGER NOT NULL,
                times INTEGER NOT NULL DEFAULT 1,
                UNIQUE(steward_id, tale_key, outcome)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS tale_explore_rolls (
                steward_id INTEGER NOT NULL REFERENCES stewards(id),
                day INTEGER NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (steward_id, day)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS lounge_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                steward_id INTEGER NOT NULL REFERENCES stewards(id),
                body TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'mcp',
                created_at INTEGER NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_lounge_created ON lounge_messages(created_at DESC)",
            "ALTER TABLE stewards ADD COLUMN lounge_human_name TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE stewards ADD COLUMN lounge_muted_until INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE stewards ADD COLUMN lounge_banned INTEGER NOT NULL DEFAULT 0",
        ):
            try:
                await db.execute(ddl)
            except aiosqlite.OperationalError:
                pass
        from . import ranks as ranks_mod
        await ranks_mod.seed_xp(db)
        await db.commit()


def now() -> int:
    return int(time.time())


def make_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(24)


async def create_api_key(email: str) -> str:
    email = email.strip().lower()
    if not email or "@" not in email:
        raise ValueError("邮箱格式无效")
    api_key = make_key()
    async with connect() as db:
        await db.execute(
            "INSERT INTO api_keys (api_key, email, created_at) VALUES (?, ?, ?)",
            (api_key, email, now()),
        )
        await db.commit()
    return api_key


async def recover_api_key(email: str) -> str | None:
    email = email.strip().lower()
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT api_key FROM api_keys WHERE email = ? ORDER BY id DESC LIMIT 1",
            (email,),
        )
        row = await cur.fetchone()
        return row["api_key"] if row else None


async def get_key_row(api_key: str) -> dict[str, Any] | None:
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM api_keys WHERE api_key = ?", (api_key,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_steward_by_key_id(key_id: int) -> dict[str, Any] | None:
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM stewards WHERE key_id = ?", (key_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_steward_by_name(name: str) -> dict[str, Any] | None:
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM stewards WHERE name = ? COLLATE NOCASE", (name.strip(),)
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_steward_by_id(steward_id: int) -> dict[str, Any] | None:
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM stewards WHERE id = ?", (steward_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def touch_steward(steward_id: int) -> None:
    async with connect() as db:
        await db.execute(
            "UPDATE stewards SET last_active_at = ? WHERE id = ?",
            (now(), steward_id),
        )
        await db.commit()


async def add_chronicle(
    action: str,
    text: str,
    actor_id: int | None = None,
    target_id: int | None = None,
    *,
    conn: aiosqlite.Connection | None = None,
) -> None:
    sql = (
        "INSERT INTO chronicle (action, actor_id, target_id, text, created_at) "
        "VALUES (?, ?, ?, ?, ?)"
    )
    args = (action, actor_id, target_id, text, now())
    if conn is not None:
        await conn.execute(sql, args)
        return
    async with connect() as db:
        await db.execute(sql, args)
        await db.commit()


async def get_satchel(steward_id: int) -> dict[str, int]:
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT item, quantity FROM satchel WHERE steward_id = ? AND quantity > 0 ORDER BY item",
            (steward_id,),
        )
        return {r["item"]: r["quantity"] for r in await cur.fetchall()}


async def add_item(db: aiosqlite.Connection, steward_id: int, item: str, qty: int) -> None:
    await db.execute(
        """
        INSERT INTO satchel (steward_id, item, quantity) VALUES (?, ?, ?)
        ON CONFLICT(steward_id, item) DO UPDATE SET quantity = quantity + excluded.quantity
        """,
        (steward_id, item, qty),
    )


async def take_item(db: aiosqlite.Connection, steward_id: int, item: str, qty: int) -> bool:
    cur = await db.execute(
        "SELECT quantity FROM satchel WHERE steward_id = ? AND item = ?",
        (steward_id, item),
    )
    row = await cur.fetchone()
    if not row or row[0] < qty:
        return False
    new_qty = row[0] - qty
    if new_qty <= 0:
        await db.execute(
            "DELETE FROM satchel WHERE steward_id = ? AND item = ?",
            (steward_id, item),
        )
    else:
        await db.execute(
            "UPDATE satchel SET quantity = ? WHERE steward_id = ? AND item = ?",
            (new_qty, steward_id, item),
        )
    return True


async def get_parcels(steward_id: int) -> list[dict[str, Any]]:
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM parcels WHERE steward_id = ? ORDER BY slot",
            (steward_id,),
        )
        return [dict(r) for r in await cur.fetchall()]


async def ensure_parcels(db: aiosqlite.Connection, steward_id: int, count: int) -> None:
    for slot in range(1, count + 1):
        await db.execute(
            "INSERT OR IGNORE INTO parcels (steward_id, slot, crop, planted_at, tended) VALUES (?, ?, NULL, NULL, 0)",
            (steward_id, slot),
        )


async def enroll_steward(key_id: int, name: str, motto: str, badge: str, portrait: str) -> dict[str, Any]:
    name = name.strip()
    badge = badge.strip().lower() or "naturalist"
    from .config import BADGES
    if badge not in BADGES:
        raise ValueError(f"徽章须为: {', '.join(BADGES)}")
    if len(name) < 2 or len(name) > 24:
        raise ValueError("名字长度需在 2~24 之间")
    ts = now()
    from . import ranks as ranks_mod
    start_level = ranks_mod.level_from_xp(START_TICKETS)
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        if await (await db.execute(
            "SELECT id FROM stewards WHERE name = ? COLLATE NOCASE", (name,)
        )).fetchone():
            raise ValueError("该名字已被登记")
        if await (await db.execute(
            "SELECT id FROM stewards WHERE key_id = ?", (key_id,)
        )).fetchone():
            raise ValueError("此凭证已登记过管理员")
        await db.execute(
            """
            INSERT INTO stewards (
                key_id, name, motto, badge, portrait, tickets, xp, parcel_count,
                enrolled, last_active_at, created_at, energy, last_bar_shift_at,
                reward_level
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
            """,
            (key_id, name, motto.strip()[:200], badge.strip()[:32], portrait.strip()[:120],
             START_TICKETS, START_TICKETS, START_PARCELS, ts, ts, START_ENERGY, ts,
             start_level),
        )
        sid = (await (await db.execute("SELECT last_insert_rowid()")).fetchone())[0]
        await ensure_parcels(db, sid, START_PARCELS)
        for item, qty in STARTER_STOCK.items():
            await add_item(db, sid, item, qty)
        await db.execute(
            "INSERT INTO chronicle (action, actor_id, text, created_at) VALUES ('enroll', ?, ?, ?)",
            (sid, f"{name} 加入了潮汐岛份地联盟", ts),
        )
        await db.commit()
    steward = await get_steward_by_id(sid)
    assert steward
    return steward


async def public_stats() -> dict[str, Any]:
    from . import world
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        stewards = (await (await db.execute(
            "SELECT COUNT(*) c FROM stewards WHERE enrolled = 1"
        )).fetchone())["c"]
        from .config import ONLINE_WINDOW
        from . import ranks as ranks_mod
        online_cut = now() - ONLINE_WINDOW
        online_rows = await (await db.execute(
            """
            SELECT id, name, badge, tickets, COALESCE(xp, 0) AS xp, last_active_at,
                   COALESCE(worn_title, '') AS worn_title
            FROM stewards
            WHERE enrolled = 1 AND last_active_at > ?
            ORDER BY last_active_at DESC LIMIT 40
            """,
            (online_cut,),
        )).fetchall()
        online_people = []
        for raw in online_rows:
            ranked = ranks_mod.attach_level(dict(raw))
            online_people.append({
                "id": ranked["id"],
                "name": ranked["name"],
                "badge": ranked["badge"],
                "tickets": ranked["tickets"],
                "level": ranked["level"],
                "title": ranked.get("display_title") or ranked["title"],
                "last_active_at": ranked["last_active_at"],
            })
        online = len(online_people)
        swaps = (await (await db.execute(
            "SELECT COUNT(*) c FROM swap_lots WHERE claimed_by IS NULL"
        )).fetchone())["c"]
        recipes = (await (await db.execute(
            "SELECT COUNT(*) c FROM hearth_discoveries"
        )).fetchone())["c"]
        scrumps = (await (await db.execute(
            "SELECT COUNT(*) c FROM chronicle WHERE action IN ('scrump', 'scrump_busted')"
        )).fetchone())["c"]
        open_contracts = (await (await db.execute(
            "SELECT COUNT(*) c FROM contracts WHERE status='open'"
        )).fetchone())["c"]
        w, t = world.current_weather(), world.current_tide()
        p = world.current_day_phase()
        from . import multi
        from . import events
        from . import lili as lili_mod
        from .catalog import ITEM_NAMES, WORLD_BOSS
        league = await multi.league_snapshot()
        pulse = await events.public_pulse_snapshot()
        lili_hint = await lili_mod.active_visit_hint(db)
        from . import tt as tt_mod
        tt_hint = tt_mod.shopfront_line()
        boss_row = await (await db.execute(
            "SELECT hp, max_hp, respawn_at FROM world_boss WHERE boss_key=?",
            (WORLD_BOSS["key"],),
        )).fetchone()
        boss = None
        if boss_row:
            hp, max_hp, respawn = boss_row[0], boss_row[1], boss_row[2]
            boss = {
                "name": WORLD_BOSS["name"],
                "hp": hp,
                "max_hp": max_hp,
                "pct": int(hp / max_hp * 100) if max_hp else 0,
                "alive": hp > 0,
            }
        beacons = await (await db.execute(
            """
            SELECT b.body, a.name FROM beacons b
            JOIN stewards a ON a.id=b.author_id
            ORDER BY b.created_at DESC LIMIT 5
            """
        )).fetchall()
        swap_rows = await (await db.execute(
            """
            SELECT l.item, l.quantity, d.name
            FROM swap_lots l JOIN stewards d ON d.id=l.depositor_id
            WHERE l.claimed_by IS NULL ORDER BY l.created_at DESC LIMIT 5
            """
        )).fetchall()
        from . import lore as lore_mod
        lore_tip = lore_mod.daily_lore_tip()
        return {
            "stewards": stewards,
            "online": online,
            "online_people": online_people,
            "climate": world.climate_line(),
            "climate_notes": {
                "weather": world.WEATHER_NOW.get(w, ""),
                "tide": world.TIDE_NOW.get(t, ""),
                "phase": world.PHASE_NOW.get(p, ""),
            },
            "open_swaps": swaps,
            "hearth_recipes": recipes,
            "total_scrumps": scrumps,
            "open_contracts": open_contracts,
            "league": league,
            "pulse": pulse,
            "weather": w,
            "tide": t,
            "day_phase": p,
            "day_phase_label": world.day_phase_label(p),
            "lili": lili_hint,
            "tt": tt_hint,
            "boss": boss,
            "beacons": [{"author": r[1], "body": r[0][:80]} for r in beacons],
            "swap_preview": [
                {
                    "item": r[0],
                    "name": ITEM_NAMES.get(r[0], r[0]),
                    "qty": r[1],
                    "from": r[2],
                }
                for r in swap_rows
            ],
            "lore_tip": lore_tip,
        }


async def list_received_gifts(steward_id: int, limit: int = 20) -> list[dict[str, Any]]:
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT c.text, c.created_at, c.action, a.name AS actor_name
            FROM chronicle c
            LEFT JOIN stewards a ON a.id = c.actor_id
            WHERE c.action IN ('gift', 'bar_tip') AND c.target_id=?
            ORDER BY c.created_at DESC LIMIT ?
            """,
            (steward_id, limit),
        )
        return [dict(r) for r in await cur.fetchall()]


async def public_chronicle(limit: int = 40) -> list[dict[str, Any]]:
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT c.*, a.name AS actor_name, t.name AS target_name
            FROM chronicle c
            LEFT JOIN stewards a ON a.id = c.actor_id
            LEFT JOIN stewards t ON t.id = c.target_id
            ORDER BY c.created_at DESC LIMIT ?
            """,
            (limit,),
        )
        return [
            {
                "id": r["id"],
                "action": r["action"],
                "actor": r["actor_name"] or "系统",
                "target": r["target_name"] or "",
                "text": r["text"],
                "created_at": r["created_at"],
            }
            for r in await cur.fetchall()
        ]


async def public_allotments() -> list[dict[str, Any]]:
    from .catalog import CROPS, ITEM_NAMES
    from . import farming
    from . import land as land_mod
    from . import ranks as ranks_mod
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM stewards WHERE enrolled = 1 ORDER BY last_active_at DESC LIMIT 100"
        )
        result = []
        for p in [dict(r) for r in await cur.fetchall()]:
            inv = await get_satchel(p["id"])
            parcels = await get_parcels(p["id"])
            parcel_views = []
            for pl in parcels:
                if land_mod.clear_left(pl) > 0:
                    parcel_views.append({"slot": pl["slot"], "crop": None, "state": "开垦中"})
                elif not pl.get("crop"):
                    parcel_views.append({"slot": pl["slot"], "crop": None, "state": "休耕"})
                else:
                    meta = CROPS.get(pl["crop"], {"name": pl["crop"], "emoji": "🌱"})
                    parcel_views.append({
                        "slot": pl["slot"],
                        "crop": pl["crop"],
                        "emoji": meta.get("emoji", "🌱"),
                        "state": farming.parcel_status(pl),
                    })
            summary = " · ".join(
                f"#{v['slot']}{v.get('emoji', '')}{v['state'][:2] if v.get('state') else '休'}"
                for v in parcel_views[:5]
            )
            latest = await (await db.execute(
                "SELECT text FROM chronicle WHERE actor_id = ? OR target_id = ? ORDER BY created_at DESC LIMIT 1",
                (p["id"], p["id"]),
            )).fetchone()
            ranked = ranks_mod.attach_level(p)
            result.append({
                "id": p["id"],
                "name": p["name"],
                "motto": p["motto"],
                "badge": p["badge"],
                "portrait": p["portrait"],
                "tickets": p["tickets"],
                "xp": ranked["xp"],
                "level": ranked["level"],
                "title": ranked.get("display_title") or ranked["title"],
                "parcel_count": p["parcel_count"],
                "greenhouse": bool(p["greenhouse"]),
                "greenhouse_label": p["greenhouse_label"],
                "mascot_name": p["mascot_name"],
                "mascot_trait": p["mascot_trait"],
                "last_active_at": p["last_active_at"],
                "parcels": parcel_views,
                "parcel_summary": summary,
                "stock": [{"item": k, "name": ITEM_NAMES.get(k, k), "quantity": v} for k, v in list(inv.items())[:10]],
                "latest": latest[0] if latest else "",
            })
        return result
