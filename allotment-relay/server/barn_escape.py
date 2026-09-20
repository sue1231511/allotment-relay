"""畜栏惊逃 — 麻烦档事件：寻回。"""
from __future__ import annotations

import random

from . import db
from .catalog import LIVESTOCK, ITEM_NAMES


async def tick_escape(conn, steward_id: int, animal: dict) -> str | None:
    if not animal.get("species") or animal.get("guard"):
        return None
    if int(animal.get("escaped_at") or 0) > 0:
        return None
    if not animal.get("fed"):
        return None
    from . import barn_temper as temper_mod

    animal = await temper_mod.ensure_temper(conn, animal)
    if random.random() > temper_mod.escape_chance(animal):
        return None
    await conn.execute(
        "UPDATE barn_animals SET escaped_at=? WHERE id=?",
        (db.now(), animal["id"]),
    )
    meta = LIVESTOCK[animal["species"]]
    return (
        f"#{animal['slot']} {meta['name']}受惊跑了（性格{temper_mod.label(animal)}）"
        f" → hut_ops barn 寻回 {animal['slot']}"
    )


async def recover(conn, steward: dict, slot: int) -> str:
    cur = await conn.execute(
        "SELECT * FROM barn_animals WHERE steward_id=? AND slot=?",
        (steward["id"], slot),
    )
    row = await cur.fetchone()
    if not row:
        raise ValueError("空栏")
    animal = dict(row)
    if not int(animal.get("escaped_at") or 0):
        raise ValueError("这栏没跑丢")
    cost = 8
    cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (steward["id"],))
    if int((await cur.fetchone())[0]) < cost:
        raise ValueError(f"寻回要 {cost} 票")
    from . import energy as energy_mod

    await energy_mod.spend(conn, steward["id"], 6, action="寻回牲口")
    await conn.execute(
        "UPDATE stewards SET tickets=tickets-? WHERE id=?",
        (cost, steward["id"]),
    )
    await conn.execute(
        "UPDATE barn_animals SET escaped_at=0, fed=0 WHERE steward_id=? AND slot=?",
        (steward["id"], slot),
    )
    meta = LIVESTOCK[animal["species"]]
    return f"#{slot} {meta['name']}找回来了（-{cost} 票，6 精力，今天得再喂）"
