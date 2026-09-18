"""畜栏惊逃处置：三选一（诱回 / 围栏 / 急追）。"""
from __future__ import annotations

from typing import Any

from . import db, energy
from .catalog import LIVESTOCK, item_label


async def ui_actions(
    *,
    tickets: int,
    stock: dict[str, int],
    energy_now: int,
    species: str,
) -> list[dict[str, Any]]:
    meta = LIVESTOCK.get(species, {})
    feed = meta.get("feed") or "crop_wheat"
    timber = int(stock.get("craft_timber") or 0)
    feed_have = int(stock.get(feed) or 0)
    return [
        {
            "action": "诱回",
            "label": "诱回",
            "hint": f"{item_label(feed)}×1 或 8 票",
            "can": feed_have >= 1 or tickets >= 8,
            "disabled_reason": "缺饲料且票不够 8",
        },
        {
            "action": "围栏",
            "label": "围栏",
            "hint": "岸木×1 或 12 票",
            "can": timber >= 1 or tickets >= 12,
            "disabled_reason": "缺岸木且票不够 12",
        },
        {
            "action": "急追",
            "label": "急追",
            "hint": "10 精力",
            "can": energy_now >= 10,
            "disabled_reason": "精力不够 10",
        },
    ]


async def resolve(conn, steward: dict[str, Any], slot: int, choice: str) -> str:
    import aiosqlite

    conn.row_factory = aiosqlite.Row
    cur = await conn.execute(
        "SELECT * FROM barn_animals WHERE steward_id=? AND slot=?",
        (steward["id"], slot),
    )
    row = await cur.fetchone()
    if not row:
        raise ValueError("空栏")
    animal = dict(row)
    if not int(animal.get("escaped_at") or 0):
        raise ValueError(f"#{slot} 没跑丢")
    ch = (choice or "").strip().lower()
    norm = None
    for zh, en in (("诱回", "lure"), ("围栏", "fence"), ("急追", "chase")):
        if ch in (zh, en):
            norm = zh
            break
    if not norm:
        raise ValueError(f"惊逃处置：诱回 · 围栏 · 急追（例 barn_ops 惊逃 {slot} 诱回）")
    sid = steward["id"]
    meta = LIVESTOCK[animal["species"]]
    feed = meta.get("feed") or "crop_wheat"

    if norm == "诱回":
        paid = ""
        if not await db.take_item(conn, sid, feed, 1):
            cost = 8
            have = int((await (await conn.execute(
                "SELECT tickets FROM stewards WHERE id=?", (sid,)
            )).fetchone())[0])
            if have < cost:
                raise ValueError(f"诱回要{item_label(feed)}×1 或 {cost} 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (cost, sid),
            )
            paid = f"-{cost} 票"
        else:
            paid = f"{item_label(feed)}×1"
    elif norm == "围栏":
        paid = ""
        if not await db.take_item(conn, sid, "craft_timber", 1):
            cost = 12
            have = int((await (await conn.execute(
                "SELECT tickets FROM stewards WHERE id=?", (sid,)
            )).fetchone())[0])
            if have < cost:
                raise ValueError(f"围栏要岸木×1 或 {cost} 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (cost, sid),
            )
            paid = f"-{cost} 票"
        else:
            paid = "岸木×1"
    else:
        await energy.spend(conn, sid, 10, action="急追牲口")
        paid = "-10 精力"
        import random

        if random.random() < 0.18:
            await conn.execute(
                "UPDATE barn_animals SET fed=0 WHERE steward_id=? AND slot=?",
                (sid, slot),
            )
            return (
                f"#{slot} {meta['name']}又窜远了，今天得再寻一次。"
                f"（{paid}）"
            )

    await conn.execute(
        "UPDATE barn_animals SET escaped_at=0, fed=0 WHERE steward_id=? AND slot=?",
        (sid, slot),
    )
    return f"#{slot} {meta['name']}回栏了。（{paid}，今天得再喂）"
