"""岸工坊麻烦档：金属件打好了淬火烫手，三选一（泼水 / 戴胚 / 硬取）。"""
from __future__ import annotations

import json
import random
from typing import Any

from . import db, energy
from .catalog import CRAFT_RECIPES, item_label

HAZARD_QUENCH = "quench"

METAL_JOB_KEYS = frozenset(
    key
    for key, meta in CRAFT_RECIPES.items()
    if any(
        need in meta.get("need", {})
        for need in (
            "quarry_copper_bar",
            "quarry_iron_bar",
            "quarry_fog_lead",
            "quarry_marrow",
            "quarry_tide_stone",
            "quarry_gold_sand",
        )
    )
)

CHOICES = (
    ("泼水", "splash", "water"),
    ("戴胚", "glove", "mitt"),
    ("硬取", "grab", "bare"),
)


async def ensure_columns(conn) -> None:
    for ddl in (
        "ALTER TABLE steward_craft ADD COLUMN anvil_hazard TEXT",
        "ALTER TABLE steward_craft ADD COLUMN anvil_hazard_json TEXT",
    ):
        try:
            await conn.execute(ddl)
        except Exception:
            pass


async def get_hazard(conn, steward_id: int) -> str:
    await ensure_columns(conn)
    cur = await conn.execute(
        "SELECT anvil_hazard FROM steward_craft WHERE steward_id=?",
        (steward_id,),
    )
    row = await cur.fetchone()
    return (row[0] or "") if row else ""


async def maybe_when_ready(
    conn,
    steward_id: int,
    *,
    job_key: str,
    ready_at: int,
    now: int,
) -> str | None:
    if not job_key or ready_at > now:
        return None
    if job_key not in METAL_JOB_KEYS:
        return None
    if await get_hazard(conn, steward_id):
        return None
    if random.random() > 0.17:
        return None
    meta = CRAFT_RECIPES.get(job_key, {})
    payload = {"job_key": job_key, "name": meta.get("name", job_key)}
    await ensure_columns(conn)
    await conn.execute(
        """
        UPDATE steward_craft SET anvil_hazard=?, anvil_hazard_json=?
        WHERE steward_id=?
        """,
        (HAZARD_QUENCH, json.dumps(payload, ensure_ascii=False), steward_id),
    )
    name = meta.get("name", job_key)
    return (
        f"{name} 还在白烟里烫手！"
        " craft_ops 淬火 泼水|戴胚|硬取"
        "（泼水=盐×1或6票；戴胚=羊毛×1或8票；硬取=10精力可能烫伤）"
    )


async def assert_not_blocked(conn, steward_id: int) -> None:
    if await get_hazard(conn, steward_id) == HAZARD_QUENCH:
        raise ValueError(
            "件还烫着，先 craft_ops 淬火 泼水|戴胚|硬取。"
            "人类 /island 岸工坊砧上栏也能点。"
        )


def ui_actions(*, tickets: int, stock: dict[str, int], energy_now: int) -> list[dict[str, Any]]:
    salt = int(stock.get("quarry_salt") or 0)
    wool = int(stock.get("wool") or 0)
    return [
        {
            "action": "泼水",
            "label": "泼水",
            "hint": "盐×1 或 6 票",
            "can": salt >= 1 or tickets >= 6,
            "disabled_reason": "缺盐且票不够 6",
        },
        {
            "action": "戴胚",
            "label": "戴胚",
            "hint": "羊毛×1 或 8 票",
            "can": wool >= 1 or tickets >= 8,
            "disabled_reason": "缺羊毛且票不够 8",
        },
        {
            "action": "硬取",
            "label": "硬取",
            "hint": "10 精力",
            "can": energy_now >= 10,
            "disabled_reason": "精力不够 10",
        },
    ]


async def resolve(conn, steward: dict[str, Any], choice: str) -> str:
    cur = await conn.execute(
        """
        SELECT anvil_hazard, anvil_hazard_json
        FROM steward_craft WHERE steward_id=?
        """,
        (steward["id"],),
    )
    row = await cur.fetchone()
    if not row or (row[0] or "") != HAZARD_QUENCH:
        raise ValueError("砧上没有淬火待决。craft_ops status 看砧")
    ch = (choice or "").strip().lower()
    norm = None
    for zh, en, _ in CHOICES:
        if ch in (zh, en):
            norm = zh
            break
    if not norm:
        raise ValueError("淬火处置：泼水 · 戴胚 · 硬取（例 craft_ops 淬火 泼水）")
    sid = steward["id"]

    if norm == "泼水":
        paid = ""
        if not await db.take_item(conn, sid, "quarry_salt", 1):
            cost = 6
            have = int((await (await conn.execute(
                "SELECT tickets FROM stewards WHERE id=?", (sid,)
            )).fetchone())[0])
            if have < cost:
                raise ValueError(f"泼水要{item_label('quarry_salt')}×1 或 {cost} 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (cost, sid),
            )
            paid = f"-{cost} 票"
        else:
            paid = f"{item_label('quarry_salt')}×1"
        await _clear(conn, sid)
        return f"泼盐雾，白烟散了，可以取了。（{paid}）"

    if norm == "戴胚":
        paid = ""
        if not await db.take_item(conn, sid, "wool", 1):
            cost = 8
            have = int((await (await conn.execute(
                "SELECT tickets FROM stewards WHERE id=?", (sid,)
            )).fetchone())[0])
            if have < cost:
                raise ValueError(f"戴胚要羊毛×1 或 {cost} 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (cost, sid),
            )
            paid = f"-{cost} 票"
        else:
            paid = "羊毛×1"
        await _clear(conn, sid)
        return f"垫羊毛把件夹出来了。（{paid}）"

    await energy.spend(conn, sid, 10, action="淬火硬取")
    await _clear(conn, sid)
    from . import health

    ill = await health.maybe_roll_ailment(
        conn, sid, "craft", chance=0.28, source="anvil_quench",
    )
    msg = "徒手拎下来，指尖还在跳。"
    if ill:
        msg += f"\n{ill}\n→ visit_ops clinic treat"
    return msg


async def _clear(conn, steward_id: int) -> None:
    await ensure_columns(conn)
    await conn.execute(
        """
        UPDATE steward_craft SET anvil_hazard=NULL, anvil_hazard_json=NULL
        WHERE steward_id=?
        """,
        (steward_id,),
    )
