import json
import secrets
import time
from typing import Any

import aiosqlite

from .config import DATA_DIR, DB_PATH, KEY_PREFIX, START_MOON, START_PLOTS
from .catalog import STARTER_SEEDS

SCHEMA = """
CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    api_key TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_api_keys_email ON api_keys(email);

CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_id INTEGER NOT NULL UNIQUE REFERENCES api_keys(id),
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    bio TEXT NOT NULL DEFAULT '',
    species TEXT NOT NULL DEFAULT 'cat',
    appearance TEXT NOT NULL DEFAULT '',
    moon INTEGER NOT NULL DEFAULT 0,
    plot_count INTEGER NOT NULL DEFAULT 2,
    house_built INTEGER NOT NULL DEFAULT 0,
    house_name TEXT NOT NULL DEFAULT '',
    pet_name TEXT NOT NULL DEFAULT '',
    pet_species TEXT NOT NULL DEFAULT '',
    pet_mood INTEGER NOT NULL DEFAULT 80,
    cooks_today INTEGER NOT NULL DEFAULT 0,
    cook_day INTEGER NOT NULL DEFAULT 0,
    registered INTEGER NOT NULL DEFAULT 0,
    last_active_at INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS plots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL REFERENCES players(id),
    slot INTEGER NOT NULL,
    crop TEXT,
    planted_at INTEGER,
    watered INTEGER NOT NULL DEFAULT 0,
    UNIQUE(player_id, slot)
);

CREATE TABLE IF NOT EXISTS inventory (
    player_id INTEGER NOT NULL REFERENCES players(id),
    item TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (player_id, item)
);

CREATE TABLE IF NOT EXISTS feed (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    actor_id INTEGER,
    target_id INTEGER,
    text TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_player_id INTEGER NOT NULL REFERENCES players(id),
    to_player_id INTEGER NOT NULL REFERENCES players(id),
    text TEXT NOT NULL,
    read_flag INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS bottles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    author_id INTEGER NOT NULL REFERENCES players(id),
    text TEXT NOT NULL,
    mood TEXT NOT NULL DEFAULT '',
    picked_by INTEGER,
    reply TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS recipes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signature TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    inventor_id INTEGER NOT NULL REFERENCES players(id),
    score INTEGER NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS gifts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_player_id INTEGER NOT NULL REFERENCES players(id),
    to_player_id INTEGER NOT NULL REFERENCES players(id),
    item TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    delivered INTEGER NOT NULL DEFAULT 0,
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


async def get_player_by_key_id(key_id: int) -> dict[str, Any] | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM players WHERE key_id = ?", (key_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_player_by_name(name: str) -> dict[str, Any] | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM players WHERE name = ? COLLATE NOCASE", (name.strip(),)
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_player_by_id(player_id: int) -> dict[str, Any] | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM players WHERE id = ?", (player_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def touch_player(player_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE players SET last_active_at = ? WHERE id = ?",
            (now(), player_id),
        )
        await db.commit()


async def add_feed(action: str, text: str, actor_id: int | None = None, target_id: int | None = None) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO feed (action, actor_id, target_id, text, created_at) VALUES (?, ?, ?, ?, ?)",
            (action, actor_id, target_id, text, now()),
        )
        await db.commit()


async def get_inventory(player_id: int) -> dict[str, int]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT item, quantity FROM inventory WHERE player_id = ? AND quantity > 0 ORDER BY item",
            (player_id,),
        )
        rows = await cur.fetchall()
        return {r["item"]: r["quantity"] for r in rows}


async def add_item(db: aiosqlite.Connection, player_id: int, item: str, qty: int) -> None:
    await db.execute(
        """
        INSERT INTO inventory (player_id, item, quantity) VALUES (?, ?, ?)
        ON CONFLICT(player_id, item) DO UPDATE SET quantity = quantity + excluded.quantity
        """,
        (player_id, item, qty),
    )


async def take_item(db: aiosqlite.Connection, player_id: int, item: str, qty: int) -> bool:
    cur = await db.execute(
        "SELECT quantity FROM inventory WHERE player_id = ? AND item = ?",
        (player_id, item),
    )
    row = await cur.fetchone()
    if not row or row[0] < qty:
        return False
    new_qty = row[0] - qty
    if new_qty <= 0:
        await db.execute(
            "DELETE FROM inventory WHERE player_id = ? AND item = ?",
            (player_id, item),
        )
    else:
        await db.execute(
            "UPDATE inventory SET quantity = ? WHERE player_id = ? AND item = ?",
            (new_qty, player_id, item),
        )
    return True


async def get_plots(player_id: int) -> list[dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM plots WHERE player_id = ? ORDER BY slot",
            (player_id,),
        )
        return [dict(r) for r in await cur.fetchall()]


async def ensure_plots(db: aiosqlite.Connection, player_id: int, plot_count: int) -> None:
    for slot in range(1, plot_count + 1):
        await db.execute(
            "INSERT OR IGNORE INTO plots (player_id, slot, crop, planted_at, watered) VALUES (?, ?, NULL, NULL, 0)",
            (player_id, slot),
        )


async def register_player(key_id: int, name: str, bio: str, species: str, appearance: str) -> dict[str, Any]:
    name = name.strip()
    if len(name) < 2 or len(name) > 24:
        raise ValueError("名字长度需在 2~24 之间")
    ts = now()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT id FROM players WHERE name = ? COLLATE NOCASE", (name,))
        if await cur.fetchone():
            raise ValueError("名字已被占用")
        cur = await db.execute("SELECT id FROM players WHERE key_id = ?", (key_id,))
        if await cur.fetchone():
            raise ValueError("该钥匙已注册过角色")
        await db.execute(
            """
            INSERT INTO players (
                key_id, name, bio, species, appearance, moon, plot_count,
                registered, last_active_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (key_id, name, bio.strip()[:200], species.strip()[:32], appearance.strip()[:120], START_MOON, START_PLOTS, ts, ts),
        )
        cur = await db.execute("SELECT last_insert_rowid()")
        player_id = (await cur.fetchone())[0]
        await ensure_plots(db, player_id, START_PLOTS)
        for item, qty in STARTER_SEEDS.items():
            await add_item(db, player_id, item, qty)
        await db.execute(
            "INSERT INTO feed (action, actor_id, text, created_at) VALUES ('join', ?, ?, ?)",
            (player_id, f"{name} 来到了月光农场", ts),
        )
        await db.commit()
    player = await get_player_by_id(player_id)
    assert player
    return player


async def public_stats() -> dict[str, Any]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        players = (await (await db.execute("SELECT COUNT(*) c FROM players WHERE registered = 1")).fetchone())["c"]
        online = (await (await db.execute(
            "SELECT COUNT(*) c FROM players WHERE registered = 1 AND last_active_at > ?",
            (now() - 900,),
        )).fetchone())["c"]
        steals = (await (await db.execute(
            "SELECT COUNT(*) c FROM feed WHERE action IN ('steal', 'caught')"
        )).fetchone())["c"]
        recipes = (await (await db.execute("SELECT COUNT(*) c FROM recipes")).fetchone())["c"]
        bottles = (await (await db.execute(
            "SELECT COUNT(*) c FROM bottles WHERE picked_by IS NULL"
        )).fetchone())["c"]
        return {
            "players": players,
            "online": online,
            "total_steals": steals,
            "recipes": recipes,
            "bottles_floating": bottles,
        }


async def public_feed(limit: int = 40) -> list[dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """
            SELECT f.*, a.name AS actor_name, t.name AS target_name
            FROM feed f
            LEFT JOIN players a ON a.id = f.actor_id
            LEFT JOIN players t ON t.id = f.target_id
            ORDER BY f.created_at DESC LIMIT ?
            """,
            (limit,),
        )
        rows = await cur.fetchall()
        return [
            {
                "id": r["id"],
                "action": r["action"],
                "actor": r["actor_name"] or "系统",
                "owner": r["target_name"] or r["actor_name"] or "系统",
                "text": r["text"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]


async def public_gardens() -> list[dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM players WHERE registered = 1 ORDER BY last_active_at DESC LIMIT 100"
        )
        players = [dict(r) for r in await cur.fetchall()]
        result = []
        for p in players:
            inv = await get_inventory(p["id"])
            plots = await get_plots(p["id"])
            latest_cur = await db.execute(
                "SELECT text FROM feed WHERE actor_id = ? OR target_id = ? ORDER BY created_at DESC LIMIT 1",
                (p["id"], p["id"]),
            )
            latest = await latest_cur.fetchone()
            supplies = []
            for item, qty in inv.items():
                from .catalog import ITEM_NAMES
                supplies.append({
                    "item": item,
                    "name": ITEM_NAMES.get(item, item),
                    "quantity": qty,
                })
            result.append({
                "id": p["id"],
                "name": p["name"],
                "bio": p["bio"],
                "species": p["species"],
                "appearance": p["appearance"],
                "moon": p["moon"],
                "plot_count": p["plot_count"],
                "house_built": bool(p["house_built"]),
                "house_name": p["house_name"],
                "pet_name": p["pet_name"],
                "pet_species": p["pet_species"],
                "last_active_at": p["last_active_at"],
                "plots": plots,
                "supplies": supplies[:12],
                "latest": latest["text"] if latest else "",
            })
        return result
