import secrets
import time
from typing import Any

import aiosqlite

from .catalog import STARTER_STOCK
from .config import DATA_DIR, DB_PATH, KEY_PREFIX, START_PARCELS, START_TICKETS

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
"""


async def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
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
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO api_keys (api_key, email, created_at) VALUES (?, ?, ?)",
            (api_key, email, now()),
        )
        await db.commit()
    return api_key


async def recover_api_key(email: str) -> str | None:
    email = email.strip().lower()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT api_key FROM api_keys WHERE email = ? ORDER BY id DESC LIMIT 1",
            (email,),
        )
        row = await cur.fetchone()
        return row["api_key"] if row else None


async def get_key_row(api_key: str) -> dict[str, Any] | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM api_keys WHERE api_key = ?", (api_key,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_steward_by_key_id(key_id: int) -> dict[str, Any] | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM stewards WHERE key_id = ?", (key_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_steward_by_name(name: str) -> dict[str, Any] | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM stewards WHERE name = ? COLLATE NOCASE", (name.strip(),)
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_steward_by_id(steward_id: int) -> dict[str, Any] | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM stewards WHERE id = ?", (steward_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def touch_steward(steward_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE stewards SET last_active_at = ? WHERE id = ?",
            (now(), steward_id),
        )
        await db.commit()


async def add_chronicle(action: str, text: str, actor_id: int | None = None, target_id: int | None = None) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO chronicle (action, actor_id, target_id, text, created_at) VALUES (?, ?, ?, ?, ?)",
            (action, actor_id, target_id, text, now()),
        )
        await db.commit()


async def get_satchel(steward_id: int) -> dict[str, int]:
    async with aiosqlite.connect(DB_PATH) as db:
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
    async with aiosqlite.connect(DB_PATH) as db:
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
    if len(name) < 2 or len(name) > 24:
        raise ValueError("名字长度需在 2~24 之间")
    ts = now()
    async with aiosqlite.connect(DB_PATH) as db:
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
                key_id, name, motto, badge, portrait, tickets, parcel_count,
                enrolled, last_active_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (key_id, name, motto.strip()[:200], badge.strip()[:32], portrait.strip()[:120],
             START_TICKETS, START_PARCELS, ts, ts),
        )
        sid = (await (await db.execute("SELECT last_insert_rowid()")).fetchone())[0]
        await ensure_parcels(db, sid, START_PARCELS)
        for item, qty in STARTER_STOCK.items():
            await add_item(db, sid, item, qty)
        await db.execute(
            "INSERT INTO chronicle (action, actor_id, text, created_at) VALUES ('enroll', ?, ?, ?)",
            (sid, f"{name} 加入了 Allotment Relay 份地联盟", ts),
        )
        await db.commit()
    steward = await get_steward_by_id(sid)
    assert steward
    return steward


async def public_stats() -> dict[str, Any]:
    from . import world
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        stewards = (await (await db.execute(
            "SELECT COUNT(*) c FROM stewards WHERE enrolled = 1"
        )).fetchone())["c"]
        online = (await (await db.execute(
            "SELECT COUNT(*) c FROM stewards WHERE enrolled = 1 AND last_active_at > ?",
            (now() - 900,),
        )).fetchone())["c"]
        swaps = (await (await db.execute(
            "SELECT COUNT(*) c FROM swap_lots WHERE claimed_by IS NULL"
        )).fetchone())["c"]
        recipes = (await (await db.execute(
            "SELECT COUNT(*) c FROM hearth_discoveries"
        )).fetchone())["c"]
        scrumps = (await (await db.execute(
            "SELECT COUNT(*) c FROM chronicle WHERE action IN ('scrump', 'scrump_busted')"
        )).fetchone())["c"]
        w, t = world.current_weather(), world.current_tide()
        return {
            "stewards": stewards,
            "online": online,
            "open_swaps": swaps,
            "hearth_recipes": recipes,
            "total_scrumps": scrumps,
            "weather": w,
            "tide": t,
        }


async def public_chronicle(limit: int = 40) -> list[dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
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
    from .catalog import ITEM_NAMES
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM stewards WHERE enrolled = 1 ORDER BY last_active_at DESC LIMIT 100"
        )
        result = []
        for p in [dict(r) for r in await cur.fetchall()]:
            inv = await get_satchel(p["id"])
            parcels = await get_parcels(p["id"])
            latest = await (await db.execute(
                "SELECT text FROM chronicle WHERE actor_id = ? OR target_id = ? ORDER BY created_at DESC LIMIT 1",
                (p["id"], p["id"]),
            )).fetchone()
            result.append({
                "id": p["id"],
                "name": p["name"],
                "motto": p["motto"],
                "badge": p["badge"],
                "portrait": p["portrait"],
                "tickets": p["tickets"],
                "parcel_count": p["parcel_count"],
                "greenhouse": bool(p["greenhouse"]),
                "greenhouse_label": p["greenhouse_label"],
                "mascot_name": p["mascot_name"],
                "mascot_trait": p["mascot_trait"],
                "last_active_at": p["last_active_at"],
                "parcels": parcels,
                "stock": [{"item": k, "name": ITEM_NAMES.get(k, k), "quantity": v} for k, v in list(inv.items())[:10]],
                "latest": latest[0] if latest else "",
            })
        return result
