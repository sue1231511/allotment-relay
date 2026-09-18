"""大鱼搏斗 — 第二批：稀有鱼上钩后可选硬拉/放走/切线。"""
from __future__ import annotations

import json
import random

from . import db
from .catalog import SEA_CATCH


async def ensure_table(conn) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS steward_fish_fight (
            steward_id INTEGER PRIMARY KEY,
            species TEXT NOT NULL,
            weight_kg REAL NOT NULL DEFAULT 0,
            state TEXT NOT NULL DEFAULT '',
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at INTEGER NOT NULL
        )
        """
    )


async def get_pending(conn, steward_id: int) -> dict | None:
    await ensure_table(conn)
    cur = await conn.execute(
        "SELECT species, weight_kg, state, payload_json FROM steward_fish_fight WHERE steward_id=?",
        (steward_id,),
    )
    row = await cur.fetchone()
    if not row:
        return None
    try:
        payload = json.loads(row[3] or "{}")
    except json.JSONDecodeError:
        payload = {}
    return {
        "species": row[0],
        "weight_kg": float(row[1]),
        "state": row[2],
        "payload": payload,
    }


async def maybe_start(
    conn,
    steward_id: int,
    species: str,
    *,
    weight_kg: float,
    state: str,
    rod_tier: int,
) -> str | None:
    meta = SEA_CATCH.get(species) or {}
    if int(meta.get("rarity") or 1) < 4:
        return None
    if random.random() > 0.52:
        return None
    await ensure_table(conn)
    await conn.execute(
        """
        INSERT INTO steward_fish_fight (steward_id, species, weight_kg, state, payload_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(steward_id) DO UPDATE SET
            species=excluded.species,
            weight_kg=excluded.weight_kg,
            state=excluded.state,
            payload_json=excluded.payload_json,
            created_at=excluded.created_at
        """,
        (
            steward_id, species, weight_kg, state,
            json.dumps({"rod_tier": rod_tier}, ensure_ascii=False),
            db.now(),
        ),
    )
    name = meta.get("name", species)
    return (
        f"大鱼上钩：{name} {weight_kg}kg 还在挣扎！"
        f" tide_ops 搏鱼 硬拉|放走|切线（不切线鱼不进袋）"
    )


async def resolve(conn, steward: dict, action: str) -> str:
    pending = await get_pending(conn, steward["id"])
    if not pending:
        return "没有待搏的大鱼。坐钓稀有鱼可能触发。"
    species = pending["species"]
    meta = SEA_CATCH.get(species) or {}
    name = meta.get("name", species)
    rod_tier = int((pending.get("payload") or {}).get("rod_tier") or 1)
    act = action.lower()

    if act in ("status", "查看", ""):
        return f"待搏：{name} {pending['weight_kg']}kg → 搏鱼 硬拉|放走|切线"

    await conn.execute("DELETE FROM steward_fish_fight WHERE steward_id=?", (steward["id"],))

    if act in ("放走", "release", "放"):
        await db.add_chronicle(
            "tide", f"{steward['name']} 放走大{name}", steward["id"], conn=conn,
        )
        return f"你把 {name} 放归海里。潮线记你一笔。"

    if act in ("切线", "cut", "切"):
        from . import gear_wear as gear_wear_mod
        await gear_wear_mod.wear(conn, steward["id"], "line", amount=20)
        await conn.execute(
            """
            UPDATE steward_fish_parts SET durability=MAX(0, durability-20), snagged=0
            WHERE steward_id=? AND part_key='hook'
            """,
            (steward["id"],),
        )
        return f"切线跑路，{name} 脱钩（线钩大损）"

    if act in ("硬拉", "pull", "拉", "fight"):
        win_p = 0.35 + rod_tier * 0.08
        if random.random() < win_p:
            from . import item_traits as traits_mod
            await traits_mod.grant_satchel(
                conn, steward["id"], f"fish_{species}", 1,
                quality=pending["state"], weight_kg=pending["weight_kg"],
            )
            return f"硬拉上岸！{name} {pending['weight_kg']}kg 进袋"
        await conn.execute(
            """
            UPDATE steward_fish_parts SET durability=MAX(0, durability-8)
            WHERE steward_id=? AND part_key='hook'
            """,
            (steward["id"],),
        )
        await conn.execute(
            """
            INSERT INTO steward_fish_fight (steward_id, species, weight_kg, state, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                steward["id"], species, pending["weight_kg"], pending["state"],
                json.dumps({"rod_tier": rod_tier}, ensure_ascii=False),
                db.now(),
            ),
        )
        return f"{name} 把线再拽出去一截。再试 搏鱼 硬拉，或切线/放走"

    raise ValueError("搏鱼：硬拉 · 放走 · 切线（tide_ops 搏鱼 硬拉）")
