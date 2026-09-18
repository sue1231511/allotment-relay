"""出海麻烦档：帆撕裂，三选一（补/返航/硬撑）。"""
from __future__ import annotations

import json
import random

from . import db
from .catalog import ITEM_NAMES


async def maybe_on_depart(conn, steward_id: int, voyage_id: int, route_key: str) -> str | None:
    from . import boat_parts as parts_mod

    parts = await parts_mod.get_all(conn, steward_id)
    sail_d, sail_mx = parts["sail"]
    ratio = sail_d / max(1, sail_mx)
    chance = 0.06
    if ratio < 0.45:
        chance = 0.22
    elif ratio < 0.65:
        chance = 0.12
    if world_storm():
        chance += 0.08
    if random.random() > chance:
        return None
    payload = {
        "type": "sail_tear",
        "route": route_key,
        "hard_sail": False,
    }
    await conn.execute(
        "UPDATE voyages SET status='sail_tear', encounter=? WHERE id=?",
        (json.dumps(payload, ensure_ascii=False), voyage_id),
    )
    return (
        "出航不久帆撕了口子！"
        " tide_ops 帆撕 补（漂绳×2 或 15 票）· 帆撕 返航（提前归港少货）· 帆撕 硬撑（不花钱，事故率↑）"
    )


def world_storm() -> bool:
    from . import world

    return world.current_weather() in ("gale", "storm", "rain")


async def resolve(conn, steward: dict, voyage: dict, choice: str) -> str:
    if voyage.get("status") != "sail_tear":
        raise ValueError("没有帆撕待决。出海 status 会写。")
    ch = choice.lower()
    payload = {}
    try:
        payload = json.loads(voyage.get("encounter") or "{}")
    except json.JSONDecodeError:
        payload = {}
    route = payload.get("route") or voyage.get("route") or "near"

    if ch in ("补", "patch", "修"):
        if not await db.take_item(conn, steward["id"], "drift_twine", 2):
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (steward["id"],))
            have = int((await cur.fetchone())[0])
            cost = 15
            if have < cost:
                raise ValueError(f"补帆要漂绳×2 或 {cost} 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (cost, steward["id"]),
            )
            paid = f"-{cost} 票"
        else:
            paid = f"{ITEM_NAMES.get('drift_twine', '漂绳')}×2"
        from . import boat_parts as parts_mod

        parts = await parts_mod.get_all(conn, steward["id"])
        d, mx = parts["sail"]
        new = min(mx, d + 25)
        await conn.execute(
            """
            UPDATE steward_boat_parts SET durability=? WHERE steward_id=? AND part_key='sail'
            """,
            (new, steward["id"]),
        )
        await _resume_sailing(conn, voyage["id"])
        return f"补好帆（{paid}），继续 {route} 航程"

    if ch in ("返航", "return", "back"):
        await conn.execute(
            "UPDATE voyages SET returns_at=?, encounter=? WHERE id=?",
            (
                db.now() + 60,
                json.dumps({**payload, "early_return": True}, ensure_ascii=False),
                voyage["id"],
            ),
        )
        await _resume_sailing(conn, voyage["id"])
        return "收帆返航，约 1 分钟后靠岸（货会少一截）"

    if ch in ("硬撑", "continue", "go"):
        payload["hard_sail"] = True
        await conn.execute(
            "UPDATE voyages SET encounter=? WHERE id=?",
            (json.dumps(payload, ensure_ascii=False), voyage["id"]),
        )
        await _resume_sailing(conn, voyage["id"])
        from . import boat_parts as parts_mod

        parts = await parts_mod.get_all(conn, steward["id"])
        d, mx = parts["sail"]
        await conn.execute(
            """
            UPDATE steward_boat_parts SET durability=? WHERE steward_id=? AND part_key='sail'
            """,
            (max(0, d - 12), steward["id"]),
        )
        return "硬撑继续航。帆再损，归港更容易出事"

    raise ValueError("帆撕：补 · 返航 · 硬撑（例 tide_ops 帆撕 补）")


async def _resume_sailing(conn, voyage_id: int) -> None:
    await conn.execute(
        "UPDATE voyages SET status='sailing' WHERE id=? AND status='sail_tear'",
        (voyage_id,),
    )


def fail_bonus_from_encounter(voyage: dict | None) -> float:
    if not voyage:
        return 0.0
    try:
        payload = json.loads(voyage.get("encounter") or "{}")
    except json.JSONDecodeError:
        return 0.0
    if payload.get("hard_sail"):
        return 0.14
    if payload.get("early_return"):
        return 0.05
    return 0.0
