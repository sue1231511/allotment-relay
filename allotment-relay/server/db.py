import asyncio
import contextvars
import re
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import aiosqlite

from .catalog import STARTER_STOCK
from .config import (
    DATA_DIR,
    DB_PATH,
    FORAGE_COOLDOWN_DAY,
    KEY_PREFIX,
    START_ENERGY,
    START_ORCHARDS,
    START_PARCELS,
    START_TICKETS,
    WEEK_SECONDS,
)

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
    orchard_count INTEGER NOT NULL DEFAULT 3,
    greenhouse INTEGER NOT NULL DEFAULT 0,
    greenhouse_count INTEGER NOT NULL DEFAULT 0,
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
    orchard INTEGER NOT NULL DEFAULT 0,
    UNIQUE(steward_id, slot, orchard)
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

CREATE TABLE IF NOT EXISTS hui_notices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tag TEXT NOT NULL DEFAULT '厅示',
    body TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    retracted INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS marriages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    partner_type TEXT NOT NULL DEFAULT 'human',
    partner_name TEXT NOT NULL,
    status TEXT NOT NULL,
    proposal_text TEXT NOT NULL DEFAULT '',
    proposal_item TEXT NOT NULL DEFAULT '',
    proposal_location TEXT NOT NULL DEFAULT '',
    preferred_wedding_date INTEGER,
    note TEXT NOT NULL DEFAULT '',
    token_hash TEXT,
    token_expires_at INTEGER,
    token_used_at INTEGER,
    confirmed_at INTEGER,
    rejected_at INTEGER,
    reject_seen INTEGER NOT NULL DEFAULT 0,
    wedding_at INTEGER,
    wedding_location TEXT NOT NULL DEFAULT '',
    vow_ai TEXT NOT NULL DEFAULT '',
    vow_human TEXT NOT NULL DEFAULT '',
    ring_ready INTEGER NOT NULL DEFAULT 0,
    attire_ready INTEGER NOT NULL DEFAULT 0,
    feast_note TEXT NOT NULL DEFAULT '',
    home_hut INTEGER NOT NULL DEFAULT 0,
    public_slug TEXT,
    charter_json TEXT NOT NULL DEFAULT '',
    filing_kind TEXT NOT NULL DEFAULT '',
    private_notice TEXT NOT NULL DEFAULT '',
    human_notice TEXT NOT NULL DEFAULT '',
    divorce_rejected_at INTEGER,
    bride_price INTEGER NOT NULL DEFAULT 0,
    bride_frozen INTEGER NOT NULL DEFAULT 0,
    gold_three INTEGER NOT NULL DEFAULT 0,
    gold_five INTEGER NOT NULL DEFAULT 0,
    feast_tier TEXT NOT NULL DEFAULT '',
    feast_ready INTEGER NOT NULL DEFAULT 0,
    attire_source TEXT NOT NULL DEFAULT '',
    betrothal_done INTEGER NOT NULL DEFAULT 0,
    betrothal_gift INTEGER NOT NULL DEFAULT 0,
    betrothal_token INTEGER NOT NULL DEFAULT 0,
    betrothal_feast INTEGER NOT NULL DEFAULT 0,
    betrothal_bouquet INTEGER NOT NULL DEFAULT 0,
    betrothal_attire INTEGER NOT NULL DEFAULT 0,
    betrothal_photo INTEGER NOT NULL DEFAULT 0,
    betrothal_confirm_hash TEXT,
    betrothal_confirm_expires_at INTEGER,
    betrothal_confirm_used_at INTEGER,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_marriages_steward ON marriages(steward_id, status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_marriages_token_hash ON marriages(token_hash) WHERE token_hash IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_marriages_slug ON marriages(public_slug) WHERE public_slug IS NOT NULL;
-- idx_marriages_betrothal_confirm_hash 必须等 ALTER ADD COLUMN 之后再建。
-- 旧库 marriages 没有 betrothal_confirm_hash；写在 SCHEMA 里会让 executescript 整段失败，启动崩掉。

CREATE TABLE IF NOT EXISTS marriage_guests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    marriage_id INTEGER NOT NULL REFERENCES marriages(id),
    guest_kind TEXT NOT NULL,
    guest_name TEXT NOT NULL,
    guest_id INTEGER,
    attended INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    UNIQUE(marriage_id, guest_kind, guest_name)
);

CREATE TABLE IF NOT EXISTS marriage_gifts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    marriage_id INTEGER NOT NULL REFERENCES marriages(id),
    giver_id INTEGER NOT NULL REFERENCES stewards(id),
    giver_name TEXT NOT NULL,
    item_code TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS marriage_blessings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    marriage_id INTEGER NOT NULL REFERENCES marriages(id),
    author_id INTEGER,
    author_name TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS marriage_displays (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    marriage_id INTEGER NOT NULL REFERENCES marriages(id),
    kind TEXT NOT NULL,
    ref TEXT NOT NULL DEFAULT '',
    label TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS marriage_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    marriage_id INTEGER NOT NULL REFERENCES marriages(id),
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    game_day INTEGER NOT NULL
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

CREATE TABLE IF NOT EXISTS world_flags (
    flag_key TEXT PRIMARY KEY,
    applied_at INTEGER NOT NULL,
    detail TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS hut_compost_bin (
    steward_id INTEGER PRIMARY KEY REFERENCES stewards(id),
    fill INTEGER NOT NULL DEFAULT 0,
    ready INTEGER NOT NULL DEFAULT 0
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
    mix_count INTEGER NOT NULL DEFAULT 0,
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

CREATE TABLE IF NOT EXISTS musong_sendoffs (
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    day INTEGER NOT NULL,
    target_name TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (steward_id, day)
);

CREATE TABLE IF NOT EXISTS steward_jingshan (
    steward_id INTEGER PRIMARY KEY REFERENCES stewards(id),
    stage INTEGER NOT NULL DEFAULT 0,
    ordered_at INTEGER NOT NULL DEFAULT 0,
    delivered_day INTEGER NOT NULL DEFAULT -1,
    updated_at INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS steward_buxing (
    steward_id INTEGER PRIMARY KEY REFERENCES stewards(id),
    tide_count INTEGER NOT NULL DEFAULT 0,
    tea_day INTEGER NOT NULL DEFAULT -1,
    wicks INTEGER NOT NULL DEFAULT 0,
    updated_at INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS buxing_lights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    label TEXT NOT NULL,
    wish TEXT NOT NULL,
    fulfilled INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS buxing_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    kind TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at INTEGER NOT NULL
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
    passive_rolled INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (steward_id, day)
);

CREATE TABLE IF NOT EXISTS gugu_dove_rolls (
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    day INTEGER NOT NULL,
    rolled INTEGER NOT NULL DEFAULT 0,
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

CREATE TABLE IF NOT EXISTS steward_stories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    story_key TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    minutes_left INTEGER NOT NULL DEFAULT 60,
    flags_json TEXT NOT NULL DEFAULT '[]',
    outcome TEXT NOT NULL DEFAULT '',
    reward_granted INTEGER NOT NULL DEFAULT 0,
    started_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    completed_at INTEGER,
    UNIQUE(steward_id, story_key)
);

CREATE TABLE IF NOT EXISTS steward_story_outcomes (
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    story_key TEXT NOT NULL,
    outcome TEXT NOT NULL,
    completed_at INTEGER NOT NULL,
    PRIMARY KEY (steward_id, story_key, outcome)
);

CREATE TABLE IF NOT EXISTS steward_story_stage_rewards (
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    story_key TEXT NOT NULL,
    stage_key TEXT NOT NULL,
    rewarded_at INTEGER NOT NULL,
    PRIMARY KEY (steward_id, story_key, stage_key)
);

CREATE TABLE IF NOT EXISTS steward_story_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    steward_id INTEGER NOT NULL REFERENCES stewards(id),
    story_key TEXT NOT NULL,
    outcome TEXT NOT NULL,
    flags_json TEXT NOT NULL DEFAULT '[]',
    completed_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_story_runs_steward
ON steward_story_runs(steward_id, story_key, completed_at DESC);
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
            "ALTER TABLE stewards ADD COLUMN dine_buff_until INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE stewards ADD COLUMN bath_soak_at INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE stewards ADD COLUMN book_read_day INTEGER NOT NULL DEFAULT 0",
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
            CREATE TABLE IF NOT EXISTS ut_dead_wall (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                cause TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL
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
            "ALTER TABLE steward_undertide ADD COLUMN gear_key TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE steward_undertide ADD COLUMN gear_durability INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE steward_undertide ADD COLUMN gear_max INTEGER NOT NULL DEFAULT 0",

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
            "ALTER TABLE stewards ADD COLUMN satchel_stack_extra INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE stewards ADD COLUMN clinic_dove_day INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE stewards ADD COLUMN clinic_dove_affinity INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE stewards ADD COLUMN clinic_tonic_day INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE stewards ADD COLUMN clinic_tonic_count INTEGER NOT NULL DEFAULT 0",
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
            "ALTER TABLE star_state ADD COLUMN welfare_spent INTEGER NOT NULL DEFAULT 0",
            """
            CREATE TABLE IF NOT EXISTS star_welfare (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                steward_id INTEGER NOT NULL REFERENCES stewards(id),
                amount INTEGER NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL DEFAULT 0
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS star_theater_affinity (
                steward_id INTEGER PRIMARY KEY REFERENCES stewards(id),
                score INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL DEFAULT 0
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS star_theater_runs (
                steward_id INTEGER NOT NULL REFERENCES stewards(id),
                day INTEGER NOT NULL,
                role_key TEXT NOT NULL DEFAULT '',
                role_label TEXT NOT NULL DEFAULT '',
                play_title TEXT NOT NULL DEFAULT '',
                rehearsed INTEGER NOT NULL DEFAULT 0,
                rehearsal_affinity INTEGER NOT NULL DEFAULT 0,
                head_fan INTEGER NOT NULL DEFAULT 0,
                outcome TEXT NOT NULL DEFAULT '',
                payout INTEGER NOT NULL DEFAULT 0,
                standing_gain INTEGER NOT NULL DEFAULT 0,
                mist_wit_gain INTEGER NOT NULL DEFAULT 0,
                performance_affinity INTEGER NOT NULL DEFAULT 0,
                claimed INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (steward_id, day)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS star_theater_weekly (
                steward_id INTEGER NOT NULL REFERENCES stewards(id),
                week INTEGER NOT NULL,
                PRIMARY KEY (steward_id, week)
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
            CREATE TABLE IF NOT EXISTS steward_stories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                steward_id INTEGER NOT NULL REFERENCES stewards(id),
                story_key TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                minutes_left INTEGER NOT NULL DEFAULT 60,
                flags_json TEXT NOT NULL DEFAULT '[]',
                outcome TEXT NOT NULL DEFAULT '',
                reward_granted INTEGER NOT NULL DEFAULT 0,
                started_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                completed_at INTEGER,
                UNIQUE(steward_id, story_key)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS steward_story_outcomes (
                steward_id INTEGER NOT NULL REFERENCES stewards(id),
                story_key TEXT NOT NULL,
                outcome TEXT NOT NULL,
                completed_at INTEGER NOT NULL,
                PRIMARY KEY (steward_id, story_key, outcome)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS steward_story_stage_rewards (
                steward_id INTEGER NOT NULL REFERENCES stewards(id),
                story_key TEXT NOT NULL,
                stage_key TEXT NOT NULL,
                rewarded_at INTEGER NOT NULL,
                PRIMARY KEY (steward_id, story_key, stage_key)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS steward_story_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                steward_id INTEGER NOT NULL REFERENCES stewards(id),
                story_key TEXT NOT NULL,
                outcome TEXT NOT NULL,
                flags_json TEXT NOT NULL DEFAULT '[]',
                completed_at INTEGER NOT NULL
            )
            """,
            """CREATE INDEX IF NOT EXISTS idx_story_runs_steward
               ON steward_story_runs(steward_id, story_key, completed_at DESC)""",
            """
            INSERT INTO steward_story_runs
                (steward_id, story_key, outcome, flags_json, completed_at)
            SELECT s.steward_id, s.story_key, s.outcome, s.flags_json,
                   COALESCE(s.completed_at, s.updated_at)
            FROM steward_stories s
            WHERE s.status='completed'
              AND NOT EXISTS (
                  SELECT 1 FROM steward_story_runs r
                  WHERE r.steward_id=s.steward_id
                    AND r.story_key=s.story_key
                    AND r.outcome=s.outcome
                    AND r.completed_at=COALESCE(s.completed_at, s.updated_at)
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
            "ALTER TABLE kitchen_rolls ADD COLUMN mix_count INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE shiye_rolls ADD COLUMN passive_rolled INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE steward_stories ADD COLUMN reward_granted INTEGER NOT NULL DEFAULT 0",
            """
            CREATE TABLE IF NOT EXISTS gugu_dove_rolls (
                steward_id INTEGER NOT NULL REFERENCES stewards(id),
                day INTEGER NOT NULL,
                 rolled INTEGER NOT NULL DEFAULT 0,
                 PRIMARY KEY (steward_id, day)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS musong_sendoffs (
                steward_id INTEGER NOT NULL REFERENCES stewards(id),
                day INTEGER NOT NULL,
                target_name TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                PRIMARY KEY (steward_id, day)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS steward_jingshan (
                steward_id INTEGER PRIMARY KEY REFERENCES stewards(id),
                stage INTEGER NOT NULL DEFAULT 0,
                ordered_at INTEGER NOT NULL DEFAULT 0,
                delivered_day INTEGER NOT NULL DEFAULT -1,
                updated_at INTEGER NOT NULL DEFAULT 0
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS steward_buxing (
                steward_id INTEGER PRIMARY KEY REFERENCES stewards(id),
                tide_count INTEGER NOT NULL DEFAULT 0,
                tea_day INTEGER NOT NULL DEFAULT -1,
                wicks INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL DEFAULT 0
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS buxing_lights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                steward_id INTEGER NOT NULL REFERENCES stewards(id),
                label TEXT NOT NULL,
                wish TEXT NOT NULL,
                fulfilled INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS buxing_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                steward_id INTEGER NOT NULL REFERENCES stewards(id),
                kind TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
            """,
            "ALTER TABLE parcels ADD COLUMN tree_harvests INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE parcels ADD COLUMN tree_harvest_max INTEGER NOT NULL DEFAULT 0",
            """
            CREATE TABLE IF NOT EXISTS ut_daily_actions (
                steward_id INTEGER NOT NULL REFERENCES stewards(id),
                day_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (steward_id, day_id, action)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS world_flags (
                flag_key TEXT PRIMARY KEY,
                applied_at INTEGER NOT NULL,
                detail TEXT NOT NULL DEFAULT ''
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS hut_compost_bin (
                steward_id INTEGER PRIMARY KEY REFERENCES stewards(id),
                fill INTEGER NOT NULL DEFAULT 0,
                ready INTEGER NOT NULL DEFAULT 0
            )
            """,
            "ALTER TABLE parcels ADD COLUMN orchard INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE stewards ADD COLUMN orchard_count INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE stewards ADD COLUMN greenhouse_count INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE stewards ADD COLUMN island_bond INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE stewards ADD COLUMN island_bond_labor INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE stewards ADD COLUMN island_bond_people INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE stewards ADD COLUMN island_bond_story INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE stewards ADD COLUMN island_bond_life INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE stewards ADD COLUMN island_bond_give INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE stewards ADD COLUMN island_bond_well INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE stewards ADD COLUMN island_bond_backfill INTEGER NOT NULL DEFAULT 0",
            """
            CREATE TABLE IF NOT EXISTS island_bond_flags (
                steward_id INTEGER NOT NULL REFERENCES stewards(id),
                flag_key TEXT NOT NULL,
                PRIMARY KEY (steward_id, flag_key)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS island_bond_daily (
                steward_id INTEGER NOT NULL REFERENCES stewards(id),
                day INTEGER NOT NULL,
                flag_key TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (steward_id, day, flag_key)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS steward_quarry (
                steward_id INTEGER PRIMARY KEY REFERENCES stewards(id),
                pick_tier INTEGER NOT NULL DEFAULT 0,
                claim_count INTEGER NOT NULL DEFAULT 1,
                last_prospect_at INTEGER NOT NULL DEFAULT 0,
                last_hew_at INTEGER NOT NULL DEFAULT 0,
                hews_total INTEGER NOT NULL DEFAULT 0
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS quarry_claims (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                steward_id INTEGER NOT NULL REFERENCES stewards(id),
                slot INTEGER NOT NULL,
                vein TEXT NOT NULL DEFAULT '',
                strikes_left INTEGER NOT NULL DEFAULT 0,
                ready_at INTEGER NOT NULL DEFAULT 0,
                last_hew_at INTEGER NOT NULL DEFAULT 0,
                UNIQUE(steward_id, slot)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS quarry_rolls (
                steward_id INTEGER NOT NULL REFERENCES stewards(id),
                day INTEGER NOT NULL,
                last_at INTEGER NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (steward_id, day)
            )
            """,
            "ALTER TABLE steward_quarry ADD COLUMN last_hew_at INTEGER NOT NULL DEFAULT 0",
            """
            CREATE TABLE IF NOT EXISTS steward_craft (
                steward_id INTEGER PRIMARY KEY REFERENCES stewards(id),
                job_key TEXT NOT NULL DEFAULT '',
                job_ready_at INTEGER NOT NULL DEFAULT 0,
                job_qty INTEGER NOT NULL DEFAULT 0,
                pan_count INTEGER NOT NULL DEFAULT 1,
                last_salvage_at INTEGER NOT NULL DEFAULT 0,
                salvages_total INTEGER NOT NULL DEFAULT 0,
                crafts_total INTEGER NOT NULL DEFAULT 0,
                net_patch_until INTEGER NOT NULL DEFAULT 0,
                net_patch_empty REAL NOT NULL DEFAULT 0
            )
            """,
            "ALTER TABLE steward_craft ADD COLUMN net_patch_empty REAL NOT NULL DEFAULT 0",
            """
            CREATE TABLE IF NOT EXISTS craft_pans (
                steward_id INTEGER NOT NULL REFERENCES stewards(id),
                slot INTEGER NOT NULL,
                brine_at INTEGER NOT NULL DEFAULT 0,
                UNIQUE(steward_id, slot)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS craft_rolls (
                steward_id INTEGER NOT NULL REFERENCES stewards(id),
                day INTEGER NOT NULL,
                last_at INTEGER NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (steward_id, day)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS steward_exhibits (
                steward_id INTEGER NOT NULL REFERENCES stewards(id),
                set_key TEXT NOT NULL,
                done_at INTEGER NOT NULL,
                PRIMARY KEY (steward_id, set_key)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS tide_fund (
                id INTEGER PRIMARY KEY CHECK (id=1),
                tickets INTEGER NOT NULL DEFAULT 0,
                donated_total INTEGER NOT NULL DEFAULT 0,
                paid_total INTEGER NOT NULL DEFAULT 0,
                taxed_total INTEGER NOT NULL DEFAULT 0
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS tide_fund_claims (
                steward_id INTEGER NOT NULL REFERENCES stewards(id),
                day INTEGER NOT NULL,
                amount INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (steward_id, day)
            )
            """,
            "ALTER TABLE stewards ADD COLUMN tax_arrears INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE tide_fund ADD COLUMN taxed_total INTEGER NOT NULL DEFAULT 0",
            """
            CREATE TABLE IF NOT EXISTS shore_tax_bills (
                steward_id INTEGER NOT NULL REFERENCES stewards(id),
                week_id TEXT NOT NULL,
                assessed INTEGER NOT NULL DEFAULT 0,
                paid INTEGER NOT NULL DEFAULT 0,
                tickets_at INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (steward_id, week_id)
            )
            """,
            "ALTER TABLE stewards ADD COLUMN invite_code TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE stewards ADD COLUMN invited_by INTEGER",
            "ALTER TABLE stewards ADD COLUMN invite_bound_at INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE stewards ADD COLUMN invite_status TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE stewards ADD COLUMN invite_lantern INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE api_keys ADD COLUMN pending_invite_code TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE api_keys ADD COLUMN register_device_id TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE api_keys ADD COLUMN register_ip_hash TEXT NOT NULL DEFAULT ''",
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_stewards_invite_code
            ON stewards(invite_code) WHERE invite_code != ''
            """,
            """
            CREATE TABLE IF NOT EXISTS invite_devices (
                device_id TEXT NOT NULL,
                key_id INTEGER NOT NULL,
                first_seen_at INTEGER NOT NULL,
                last_seen_at INTEGER NOT NULL,
                PRIMARY KEY (device_id, key_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS invite_ip_log (
                ip_hash TEXT NOT NULL,
                key_id INTEGER NOT NULL,
                first_seen_at INTEGER NOT NULL,
                last_seen_at INTEGER NOT NULL,
                hops INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (ip_hash, key_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS invite_activity (
                steward_id INTEGER NOT NULL,
                activity_type TEXT NOT NULL,
                first_at INTEGER NOT NULL,
                count INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (steward_id, activity_type)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS invite_rewards (
                invitee_id INTEGER NOT NULL,
                tier TEXT NOT NULL,
                granted_at INTEGER NOT NULL,
                PRIMARY KEY (invitee_id, tier)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS invite_keepsakes (
                steward_id INTEGER NOT NULL,
                item_key TEXT NOT NULL,
                granted_at INTEGER NOT NULL,
                PRIMARY KEY (steward_id, item_key)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS invite_risk_log (
                invitee_id INTEGER PRIMARY KEY,
                inviter_id INTEGER NOT NULL,
                bound_at INTEGER NOT NULL,
                island_bond INTEGER NOT NULL DEFAULT 0,
                active_days INTEGER NOT NULL DEFAULT 0,
                activity_types INTEGER NOT NULL DEFAULT 0,
                device_account_count INTEGER NOT NULL DEFAULT 0,
                risk_score INTEGER NOT NULL DEFAULT 0,
                hit_rules TEXT NOT NULL DEFAULT '[]',
                invite_status TEXT NOT NULL DEFAULT 'pending',
                rewards_json TEXT NOT NULL DEFAULT '[]',
                note TEXT NOT NULL DEFAULT '',
                cleared_at INTEGER NOT NULL DEFAULT 0,
                updated_at INTEGER NOT NULL
            )
            """,
            "ALTER TABLE stewards ADD COLUMN upkeep_arrears INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE tide_fund ADD COLUMN upkeep_total INTEGER NOT NULL DEFAULT 0",
            # week_id 存东八区日期 YYYY-MM-DD（每天一张单；旧的 ISO 周键仍可共存）
            """
            CREATE TABLE IF NOT EXISTS shore_upkeep_bills (
                steward_id INTEGER NOT NULL REFERENCES stewards(id),
                week_id TEXT NOT NULL,
                assessed INTEGER NOT NULL DEFAULT 0,
                paid INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (steward_id, week_id)
            )
            """,
            # 小橘小剧场编剧社：玩家投稿潮闻/故事，后台采纳发稿费
            """
            CREATE TABLE IF NOT EXISTS star_scripts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                steward_id INTEGER NOT NULL REFERENCES stewards(id),
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                pitch TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                accepted_as TEXT NOT NULL DEFAULT '',
                payout INTEGER NOT NULL DEFAULT 0,
                note TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL DEFAULT 0,
                decided_at INTEGER NOT NULL DEFAULT 0
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_star_scripts_status ON star_scripts(status, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_star_scripts_steward ON star_scripts(steward_id, created_at)",
            # 衣泊坊：剧院侧厅裁衣。成衣进衣橱，不占行囊。
            """
            CREATE TABLE IF NOT EXISTS steward_atelier (
                steward_id INTEGER PRIMARY KEY REFERENCES stewards(id),
                job_cut TEXT NOT NULL DEFAULT '',
                job_color TEXT NOT NULL DEFAULT '',
                job_motif TEXT NOT NULL DEFAULT '',
                job_fabric TEXT NOT NULL DEFAULT '',
                job_dye TEXT NOT NULL DEFAULT '',
                job_story TEXT NOT NULL DEFAULT '',
                job_name TEXT NOT NULL DEFAULT '',
                job_ready_at INTEGER NOT NULL DEFAULT 0,
                worn_id INTEGER NOT NULL DEFAULT 0,
                sews_total INTEGER NOT NULL DEFAULT 0
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS steward_wardrobe (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                steward_id INTEGER NOT NULL REFERENCES stewards(id),
                cut_key TEXT NOT NULL,
                color_key TEXT NOT NULL,
                motif_key TEXT NOT NULL DEFAULT 'plain',
                fabric_key TEXT NOT NULL,
                story_key TEXT NOT NULL DEFAULT '',
                name TEXT NOT NULL,
                origin TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL DEFAULT 0
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_wardrobe_steward ON steward_wardrobe(steward_id, id)",
            """
            CREATE TABLE IF NOT EXISTS steward_cloth_echo (
                steward_id INTEGER NOT NULL REFERENCES stewards(id),
                story_key TEXT NOT NULL,
                place TEXT NOT NULL,
                text TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (steward_id, story_key, place)
            )
            """,
            "ALTER TABLE lounge_messages ADD COLUMN booth_key TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE stewards ADD COLUMN lounge_booth_key TEXT NOT NULL DEFAULT ''",
            "CREATE INDEX IF NOT EXISTS idx_lounge_booth ON lounge_messages(booth_key, id)",
            "CREATE INDEX IF NOT EXISTS idx_stewards_lounge_booth ON stewards(lounge_booth_key)",
            """
            CREATE TABLE IF NOT EXISTS lounge_packets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                steward_id INTEGER NOT NULL REFERENCES stewards(id),
                message_id INTEGER NOT NULL REFERENCES lounge_messages(id),
                total INTEGER NOT NULL,
                shares INTEGER NOT NULL,
                remain_tickets INTEGER NOT NULL,
                remain_shares INTEGER NOT NULL,
                blessing TEXT NOT NULL DEFAULT '',
                booth_key TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                refunded INTEGER NOT NULL DEFAULT 0
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_lounge_packets_msg ON lounge_packets(message_id)",
            "CREATE INDEX IF NOT EXISTS idx_lounge_packets_open ON lounge_packets(refunded, remain_shares, expires_at)",
            """
            CREATE TABLE IF NOT EXISTS lounge_packet_grabs (
                packet_id INTEGER NOT NULL REFERENCES lounge_packets(id),
                steward_id INTEGER NOT NULL REFERENCES stewards(id),
                amount INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                PRIMARY KEY (packet_id, steward_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS hui_notices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tag TEXT NOT NULL DEFAULT '厅示',
                body TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                retracted INTEGER NOT NULL DEFAULT 0
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS marriages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                steward_id INTEGER NOT NULL REFERENCES stewards(id),
                partner_type TEXT NOT NULL DEFAULT 'human',
                partner_name TEXT NOT NULL,
                status TEXT NOT NULL,
                proposal_text TEXT NOT NULL DEFAULT '',
                proposal_item TEXT NOT NULL DEFAULT '',
                proposal_location TEXT NOT NULL DEFAULT '',
                preferred_wedding_date INTEGER,
                note TEXT NOT NULL DEFAULT '',
                token_hash TEXT,
                token_expires_at INTEGER,
                token_used_at INTEGER,
                confirmed_at INTEGER,
                rejected_at INTEGER,
                reject_seen INTEGER NOT NULL DEFAULT 0,
                wedding_at INTEGER,
                wedding_location TEXT NOT NULL DEFAULT '',
                vow_ai TEXT NOT NULL DEFAULT '',
                vow_human TEXT NOT NULL DEFAULT '',
                ring_ready INTEGER NOT NULL DEFAULT 0,
                attire_ready INTEGER NOT NULL DEFAULT 0,
                feast_note TEXT NOT NULL DEFAULT '',
                home_hut INTEGER NOT NULL DEFAULT 0,
                public_slug TEXT,
                charter_json TEXT NOT NULL DEFAULT '',
                filing_kind TEXT NOT NULL DEFAULT '',
                private_notice TEXT NOT NULL DEFAULT '',
                human_notice TEXT NOT NULL DEFAULT '',
                divorce_rejected_at INTEGER,
                bride_price INTEGER NOT NULL DEFAULT 0,
                bride_frozen INTEGER NOT NULL DEFAULT 0,
                gold_three INTEGER NOT NULL DEFAULT 0,
                gold_five INTEGER NOT NULL DEFAULT 0,
                feast_tier TEXT NOT NULL DEFAULT '',
                feast_ready INTEGER NOT NULL DEFAULT 0,
                attire_source TEXT NOT NULL DEFAULT '',
                betrothal_done INTEGER NOT NULL DEFAULT 0,
                betrothal_gift INTEGER NOT NULL DEFAULT 0,
                betrothal_token INTEGER NOT NULL DEFAULT 0,
                betrothal_feast INTEGER NOT NULL DEFAULT 0,
                betrothal_bouquet INTEGER NOT NULL DEFAULT 0,
                betrothal_attire INTEGER NOT NULL DEFAULT 0,
                betrothal_photo INTEGER NOT NULL DEFAULT 0,
                betrothal_confirm_hash TEXT,
                betrothal_confirm_expires_at INTEGER,
                betrothal_confirm_used_at INTEGER,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_marriages_steward ON marriages(steward_id, status)",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_marriages_token_hash ON marriages(token_hash) WHERE token_hash IS NOT NULL",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_marriages_slug ON marriages(public_slug) WHERE public_slug IS NOT NULL",
            """
            CREATE TABLE IF NOT EXISTS marriage_guests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                marriage_id INTEGER NOT NULL REFERENCES marriages(id),
                guest_kind TEXT NOT NULL,
                guest_name TEXT NOT NULL,
                guest_id INTEGER,
                attended INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,
                UNIQUE(marriage_id, guest_kind, guest_name)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS marriage_gifts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                marriage_id INTEGER NOT NULL REFERENCES marriages(id),
                giver_id INTEGER NOT NULL REFERENCES stewards(id),
                giver_name TEXT NOT NULL,
                item_code TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS marriage_blessings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                marriage_id INTEGER NOT NULL REFERENCES marriages(id),
                author_id INTEGER,
                author_name TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS marriage_displays (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                marriage_id INTEGER NOT NULL REFERENCES marriages(id),
                kind TEXT NOT NULL,
                ref TEXT NOT NULL DEFAULT '',
                label TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS marriage_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                marriage_id INTEGER NOT NULL REFERENCES marriages(id),
                kind TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                game_day INTEGER NOT NULL
            )
            """,
            "ALTER TABLE marriages ADD COLUMN filing_kind TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE marriages ADD COLUMN private_notice TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE marriages ADD COLUMN human_notice TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE marriages ADD COLUMN divorce_rejected_at INTEGER",
            "ALTER TABLE marriages ADD COLUMN bride_price INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE marriages ADD COLUMN bride_frozen INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE marriages ADD COLUMN gold_three INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE marriages ADD COLUMN gold_five INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE marriages ADD COLUMN feast_tier TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE marriages ADD COLUMN feast_ready INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE marriages ADD COLUMN attire_source TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE marriages ADD COLUMN betrothal_done INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE marriages ADD COLUMN betrothal_gift INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE marriages ADD COLUMN betrothal_token INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE marriages ADD COLUMN betrothal_feast INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE marriages ADD COLUMN betrothal_bouquet INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE marriages ADD COLUMN betrothal_attire INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE marriages ADD COLUMN betrothal_photo INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE marriages ADD COLUMN betrothal_confirm_hash TEXT",
            "ALTER TABLE marriages ADD COLUMN betrothal_confirm_expires_at INTEGER",
            "ALTER TABLE marriages ADD COLUMN betrothal_confirm_used_at INTEGER",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_marriages_betrothal_confirm_hash ON marriages(betrothal_confirm_hash) WHERE betrothal_confirm_hash IS NOT NULL",
        ):
            try:
                await db.execute(ddl)
            except aiosqlite.OperationalError:
                pass
        await _rebuild_parcels_orchard_unique(db)
        await _rebuild_parcels_kind_unique(db)
        await _migrate_greenhouse_slots(db)
        await _grant_starting_orchards(db)
        from . import ranks as ranks_mod
        from . import disaster as disaster_mod
        from . import chaoshen as chaoshen_mod
        from . import tax as tax_mod
        from . import bond as bond_mod
        await ranks_mod.seed_xp(db)
        await disaster_mod.ensure_weekly_tide(db)
        await tax_mod.ensure_shore_tax(db)
        from . import upkeep as upkeep_mod
        await upkeep_mod.ensure_shore_upkeep(db)
        await chaoshen_mod.ensure_fund_payout(db)
        await bond_mod.backfill_all(db)
        from . import invite as invite_mod
        await invite_mod.backfill_invite_codes(db)
        await db.commit()


async def _parcels_has_orchard_unique(db: aiosqlite.Connection) -> bool:
    indexes = await (await db.execute("PRAGMA index_list(parcels)")).fetchall()
    for idx in indexes:
        if not idx[2]:
            continue
        cols = await (await db.execute(f"PRAGMA index_info('{idx[1]}')")).fetchall()
        names = [c[2] for c in cols]
        if names == ["steward_id", "slot", "orchard"]:
            return True
        if names == ["steward_id", "slot", "orchard", "greenhouse"]:
            return True
    return False


async def _rebuild_parcels_orchard_unique(db: aiosqlite.Connection) -> None:
    """份地和果园可以同号：UNIQUE(steward_id, slot, orchard)。"""
    if await _parcels_has_orchard_unique(db):
        return
    info = await (await db.execute("PRAGMA table_info(parcels)")).fetchall()
    if not info:
        return
    await db.execute("PRAGMA foreign_keys=OFF")
    await db.execute(
        """
        CREATE TABLE parcels__orchard_u (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            steward_id INTEGER NOT NULL REFERENCES stewards(id),
            slot INTEGER NOT NULL,
            crop TEXT,
            planted_at INTEGER,
            tended INTEGER NOT NULL DEFAULT 0,
            greenhouse INTEGER NOT NULL DEFAULT 0,
            ready_at INTEGER NOT NULL DEFAULT 0,
            grow_target INTEGER NOT NULL DEFAULT 0,
            grow_pace TEXT NOT NULL DEFAULT '',
            fertilized INTEGER NOT NULL DEFAULT 0,
            scarecrow INTEGER NOT NULL DEFAULT 0,
            dove_yield_mult REAL NOT NULL DEFAULT 1.0,
            harvest_left INTEGER NOT NULL DEFAULT 0,
            watered INTEGER NOT NULL DEFAULT 0,
            camera INTEGER NOT NULL DEFAULT 0,
            tree_harvests INTEGER NOT NULL DEFAULT 0,
            tree_harvest_max INTEGER NOT NULL DEFAULT 0,
            orchard INTEGER NOT NULL DEFAULT 0,
            UNIQUE(steward_id, slot, orchard)
        )
        """
    )
    src_cols = {r[1] for r in info}
    dest = [
        "id", "steward_id", "slot", "crop", "planted_at", "tended", "greenhouse",
        "ready_at", "grow_target", "grow_pace", "fertilized", "scarecrow",
        "dove_yield_mult", "harvest_left", "watered", "camera",
        "tree_harvests", "tree_harvest_max", "orchard",
    ]
    select_bits = [c if c in src_cols else "0" for c in dest]
    await db.execute(
        f"INSERT INTO parcels__orchard_u ({', '.join(dest)}) "
        f"SELECT {', '.join(select_bits)} FROM parcels"
    )
    await db.execute("DROP TABLE parcels")
    await db.execute("ALTER TABLE parcels__orchard_u RENAME TO parcels")
    await db.execute("PRAGMA foreign_keys=ON")


async def _parcels_has_kind_unique(db: aiosqlite.Connection) -> bool:
    indexes = await (await db.execute("PRAGMA index_list(parcels)")).fetchall()
    for idx in indexes:
        if not idx[2]:
            continue
        cols = await (await db.execute(f"PRAGMA index_info('{idx[1]}')")).fetchall()
        names = [c[2] for c in cols]
        if names == ["steward_id", "slot", "orchard", "greenhouse"]:
            return True
    return False


async def _rebuild_parcels_kind_unique(db: aiosqlite.Connection) -> None:
    """份地 / 果园 / 温室可以同号：UNIQUE(steward_id, slot, orchard, greenhouse)。"""
    if await _parcels_has_kind_unique(db):
        return
    info = await (await db.execute("PRAGMA table_info(parcels)")).fetchall()
    if not info:
        return
    await db.execute("PRAGMA foreign_keys=OFF")
    await db.execute(
        """
        CREATE TABLE parcels__kind_u (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            steward_id INTEGER NOT NULL REFERENCES stewards(id),
            slot INTEGER NOT NULL,
            crop TEXT,
            planted_at INTEGER,
            tended INTEGER NOT NULL DEFAULT 0,
            greenhouse INTEGER NOT NULL DEFAULT 0,
            ready_at INTEGER NOT NULL DEFAULT 0,
            grow_target INTEGER NOT NULL DEFAULT 0,
            grow_pace TEXT NOT NULL DEFAULT '',
            fertilized INTEGER NOT NULL DEFAULT 0,
            scarecrow INTEGER NOT NULL DEFAULT 0,
            dove_yield_mult REAL NOT NULL DEFAULT 1.0,
            harvest_left INTEGER NOT NULL DEFAULT 0,
            watered INTEGER NOT NULL DEFAULT 0,
            camera INTEGER NOT NULL DEFAULT 0,
            tree_harvests INTEGER NOT NULL DEFAULT 0,
            tree_harvest_max INTEGER NOT NULL DEFAULT 0,
            orchard INTEGER NOT NULL DEFAULT 0,
            UNIQUE(steward_id, slot, orchard, greenhouse)
        )
        """
    )
    src_cols = {r[1] for r in info}
    dest = [
        "id", "steward_id", "slot", "crop", "planted_at", "tended", "greenhouse",
        "ready_at", "grow_target", "grow_pace", "fertilized", "scarecrow",
        "dove_yield_mult", "harvest_left", "watered", "camera",
        "tree_harvests", "tree_harvest_max", "orchard",
    ]
    select_bits = [c if c in src_cols else "0" for c in dest]
    await db.execute(
        f"INSERT INTO parcels__kind_u ({', '.join(dest)}) "
        f"SELECT {', '.join(select_bits)} FROM parcels"
    )
    await db.execute("DROP TABLE parcels")
    await db.execute("ALTER TABLE parcels__kind_u RENAME TO parcels")
    await db.execute("PRAGMA foreign_keys=ON")


async def _migrate_greenhouse_slots(db: aiosqlite.Connection) -> None:
    """旧温室 #99 迁到 棚1；补 greenhouse_count。"""
    await db.execute(
        """
        UPDATE parcels SET slot=1
        WHERE COALESCE(greenhouse,0)=1 AND COALESCE(orchard,0)=0 AND slot=99
          AND NOT EXISTS (
            SELECT 1 FROM parcels AS p2
            WHERE p2.steward_id = parcels.steward_id
              AND p2.slot = 1
              AND COALESCE(p2.orchard,0)=0
              AND COALESCE(p2.greenhouse,0)=1
          )
        """
    )
    await db.execute(
        """
        UPDATE stewards SET greenhouse_count = (
            SELECT COUNT(*) FROM parcels
            WHERE parcels.steward_id = stewards.id AND COALESCE(parcels.greenhouse,0)=1
        )
        """
    )
    await db.execute(
        """
        UPDATE stewards SET greenhouse=1
        WHERE COALESCE(greenhouse_count, 0) > 0 AND COALESCE(greenhouse, 0)=0
        """
    )


async def _grant_starting_orchards(db: aiosqlite.Connection) -> None:
    rows = await (await db.execute(
        "SELECT id, COALESCE(orchard_count, 0) FROM stewards"
    )).fetchall()
    for sid, count in rows:
        n = int(count or 0)
        if n < START_ORCHARDS:
            n = START_ORCHARDS
            await db.execute(
                "UPDATE stewards SET orchard_count=? WHERE id=?", (n, sid),
            )
        await ensure_orchard_parcels(db, sid, n)


def now() -> int:
    return int(time.time())


def day_id(ts: int | None = None) -> int:
    """游戏日序号（UTC 午夜换班，与 FORAGE_COOLDOWN_DAY 对齐）。"""
    t = now() if ts is None else ts
    return t // FORAGE_COOLDOWN_DAY


def day_start(day: int | None = None) -> int:
    """某日 0 点的 Unix 时间戳；默认今天。"""
    d = day_id() if day is None else day
    return d * FORAGE_COOLDOWN_DAY


def next_day_start(ts: int | None = None) -> int:
    """下一次游戏日换班的 Unix 时间戳。"""
    t = now() if ts is None else ts
    return (t // FORAGE_COOLDOWN_DAY + 1) * FORAGE_COOLDOWN_DAY


def seconds_until_next_day(ts: int | None = None) -> int:
    """距离下一次游戏日换班还剩多少秒。"""
    t = now() if ts is None else ts
    return max(0, next_day_start(t) - t)


def week_id(ts: int | None = None) -> int:
    """游戏周序号（与 WEEK_SECONDS 对齐）。"""
    t = now() if ts is None else ts
    return t // WEEK_SECONDS


def make_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(24)


async def create_api_key(
    email: str,
    *,
    invite_code: str = "",
    device_id: str = "",
    ip: str = "",
    hops: int = 1,
) -> str:
    email = email.strip().lower()
    if not email or "@" not in email:
        raise ValueError("邮箱格式无效")
    api_key = make_key()
    async with connect() as db:
        await db.execute(
            "INSERT INTO api_keys (api_key, email, created_at) VALUES (?, ?, ?)",
            (api_key, email, now()),
        )
        key_id = (await (await db.execute("SELECT last_insert_rowid()")).fetchone())[0]
        from . import invite as invite_mod
        await invite_mod.set_pending_invite(db, int(key_id), invite_code, device_id, ip)
        await invite_mod.observe(int(key_id), device_id, ip, hops, conn=db)
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


async def add_item(
    db: aiosqlite.Connection,
    steward_id: int,
    item: str,
    qty: int,
    *,
    over_cap: bool = False,
) -> None:
    if qty <= 0:
        return
    if not over_cap:
        from .catalog import item_stack_cap, satchel_full_message
        cur = await db.execute(
            "SELECT satchel_stack_extra FROM stewards WHERE id=?", (steward_id,)
        )
        tier_row = await cur.fetchone()
        stack_tier = int(tier_row[0] or 0) if tier_row else 0
        cap = item_stack_cap(item, stack_tier=stack_tier)
        cur = await db.execute(
            "SELECT quantity FROM satchel WHERE steward_id = ? AND item = ?",
            (steward_id, item),
        )
        row = await cur.fetchone()
        have = int(row[0] if row else 0)
        if have + qty > cap:
            raise ValueError(satchel_full_message(item, have, qty, cap))
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


async def get_parcels(
    steward_id: int, *, orchard: int | None = None, greenhouse: int | None = None
) -> list[dict[str, Any]]:
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        sql = "SELECT * FROM parcels WHERE steward_id = ?"
        args: list[Any] = [steward_id]
        if orchard is not None:
            sql += " AND COALESCE(orchard,0) = ?"
            args.append(int(orchard))
        if greenhouse is not None:
            sql += " AND COALESCE(greenhouse,0) = ?"
            args.append(int(greenhouse))
        sql += " ORDER BY greenhouse, orchard, slot"
        cur = await db.execute(sql, args)
        return [dict(r) for r in await cur.fetchall()]


async def ensure_parcels(db: aiosqlite.Connection, steward_id: int, count: int) -> None:
    for slot in range(1, count + 1):
        await db.execute(
            """
            INSERT OR IGNORE INTO parcels (steward_id, slot, orchard, crop, planted_at, tended)
            VALUES (?, ?, 0, NULL, NULL, 0)
            """,
            (steward_id, slot),
        )


async def ensure_orchard_parcels(db: aiosqlite.Connection, steward_id: int, count: int) -> None:
    for slot in range(1, count + 1):
        await db.execute(
            """
            INSERT OR IGNORE INTO parcels (steward_id, slot, orchard, crop, planted_at, tended)
            VALUES (?, ?, 1, NULL, NULL, 0)
            """,
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
                orchard_count,
                enrolled, last_active_at, created_at, energy, last_bar_shift_at,
                reward_level, invite_code
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?)
            """,
            (key_id, name, motto.strip()[:200], badge.strip()[:32], portrait.strip()[:120],
             START_TICKETS, START_TICKETS, START_PARCELS, START_ORCHARDS, ts, ts, START_ENERGY, ts,
             start_level, ""),
        )
        sid = (await (await db.execute("SELECT last_insert_rowid()")).fetchone())[0]
        from . import invite as invite_mod
        await invite_mod.assign_invite_code(db, int(sid))
        await ensure_parcels(db, sid, START_PARCELS)
        await ensure_orchard_parcels(db, sid, START_ORCHARDS)
        for item, qty in STARTER_STOCK.items():
            await add_item(db, sid, item, qty)
        await db.execute(
            "INSERT INTO chronicle (action, actor_id, text, created_at) VALUES ('enroll', ?, ?, ?)",
            (sid, f"{name} 加入了潮汐岛份地联盟", ts),
        )
        row = await (await db.execute("SELECT * FROM stewards WHERE id=?", (sid,))).fetchone()
        steward_row = dict(row) if row else {"id": sid, "key_id": key_id, "invited_by": 0}
        await invite_mod.bind_from_pending(db, steward_row)
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
        from . import season as season_mod
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
            SELECT body, tag FROM hui_notices
            WHERE retracted=0
            ORDER BY created_at DESC LIMIT 5
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
                "season": season_mod.month_line(),
            },
            "season": season_mod.current_season(),
            "season_label": season_mod.season_name(),
            "month": season_mod.current_season_index(),
            "month_label": season_mod.season_name(),
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
            "beacons": [{"author": "潮生会", "tag": r[1], "body": r[0][:80]} for r in beacons],
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


_GIFT_LINE_RE = re.compile(r"^(.+?) 送礼给 (.+?)：(.+)$", re.S)


def gift_kind_label(action: str) -> str:
    if action == "bar_tip":
        return "打赏"
    if action == "handoff":
        return "台阶"
    return "礼物"


def gift_display_text(
    text: str,
    *,
    viewer_name: str | None = None,
    action: str = "gift",
) -> str:
    raw = (text or "").strip()
    if action == "gift_inbox":
        return raw
    if action == "bar_tip":
        return raw
    m = _GIFT_LINE_RE.match(raw)
    if m and viewer_name and m.group(2).strip() == viewer_name.strip():
        return m.group(3).strip()
    return raw


async def _repair_gift_targets(
    conn: aiosqlite.Connection,
    steward_id: int,
    steward_name: str,
) -> None:
    """旧纪事若漏写 target_id，按正文「送礼给 名字」补回收礼人。"""
    needle = f"送礼给 {steward_name}："
    await conn.execute(
        """
        UPDATE chronicle
        SET target_id=?
        WHERE action IN ('gift', 'gift_inbox')
          AND target_id IS NULL
          AND text LIKE ?
        """,
        (steward_id, f"%{needle}%"),
    )


async def list_received_gifts(steward_id: int, limit: int = 20) -> list[dict[str, Any]]:
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        name_row = await (
            await db.execute("SELECT name FROM stewards WHERE id=?", (steward_id,))
        ).fetchone()
        steward_name = str(name_row[0] or "") if name_row else ""
        if steward_name:
            await _repair_gift_targets(db, steward_id, steward_name)
            await db.commit()
        cur = await db.execute(
            """
            SELECT c.text, c.created_at, c.action, a.name AS actor_name
            FROM chronicle c
            LEFT JOIN stewards a ON a.id = c.actor_id
            WHERE c.target_id=? AND c.action IN ('gift', 'gift_inbox', 'bar_tip', 'handoff')
            ORDER BY c.created_at DESC LIMIT ?
            """,
            (steward_id, limit),
        )
        rows = [dict(r) for r in await cur.fetchall()]
        for r in rows:
            r["summary"] = gift_display_text(
                r.get("text") or "",
                viewer_name=steward_name,
                action=str(r.get("action") or "gift"),
            )
        return rows


async def list_sent_gifts(steward_id: int, limit: int = 20) -> list[dict[str, Any]]:
    async with connect() as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT c.text, c.created_at, c.action, t.name AS target_name
            FROM chronicle c
            LEFT JOIN stewards t ON t.id = c.target_id
            WHERE c.actor_id=? AND c.action IN ('gift', 'gift_inbox')
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
                    parcel_views.append({
                        "slot": pl["slot"], "crop": None, "state": "开垦中",
                        "orchard": bool(pl.get("orchard")),
                        "greenhouse": bool(pl.get("greenhouse")),
                    })
                elif not pl.get("crop"):
                    parcel_views.append({
                        "slot": pl["slot"], "crop": None, "state": "休耕",
                        "orchard": bool(pl.get("orchard")),
                        "greenhouse": bool(pl.get("greenhouse")),
                    })
                else:
                    meta = CROPS.get(pl["crop"], {"name": pl["crop"], "emoji": "🌱"})
                    parcel_views.append({
                        "slot": pl["slot"],
                        "crop": pl["crop"],
                        "emoji": meta.get("emoji", "🌱"),
                        "state": farming.parcel_status(pl),
                        "orchard": bool(pl.get("orchard")),
                        "greenhouse": bool(pl.get("greenhouse")),
                    })
            summary = " · ".join(
                f"#{v['slot']}{v.get('emoji', '')}{v['state'][:2] if v.get('state') else '休'}"
                for v in parcel_views[:5]
            )
            latest_rows = await (await db.execute(
                """
                SELECT text, created_at FROM chronicle
                WHERE actor_id = ? OR target_id = ?
                ORDER BY created_at DESC LIMIT 3
                """,
                (p["id"], p["id"]),
            )).fetchall()
            ranked = ranks_mod.attach_level(p)
            ready_count = sum(
                1 for v in parcel_views
                if str(v.get("state") or "") in ("可收", "过熟", "ready", "overripe")
            )
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
                "ready_count": ready_count,
                "orchard_count": p.get("orchard_count") or 0,
                "greenhouse": bool(p["greenhouse"]),
                "greenhouse_count": int(p.get("greenhouse_count") or 0) or (1 if p.get("greenhouse") else 0),
                "greenhouse_label": p["greenhouse_label"],
                "mascot_name": p["mascot_name"],
                "mascot_trait": p["mascot_trait"],
                "last_active_at": p["last_active_at"],
                "parcels": parcel_views,
                "parcel_summary": summary,
                "stock": [{"item": k, "name": ITEM_NAMES.get(k, k), "quantity": v} for k, v in list(inv.items())[:10]],
                "latest": latest_rows[0]["text"] if latest_rows else "",
                "recent": [
                    {"text": r["text"], "created_at": r["created_at"]}
                    for r in latest_rows
                ],
            })
        result.sort(key=lambda row: (-int(row.get("parcel_count") or 0), -int(row.get("tickets") or 0)))
        return result
