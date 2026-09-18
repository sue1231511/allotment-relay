"""岸工坊麻烦档：打捞后缆绳缠脚，三选一（割绳 / 弃货 / 硬拽）。"""
from __future__ import annotations

import json
import random
from typing import Any

from . import db, energy
from .catalog import item_label

HAZARD_SNAG = "snag"

CHOICES = (
    ("割绳", "cut", "knife"),
    ("弃货", "drop", "leave"),
    ("硬拽", "pull", "yank"),
)


def _chance(*, weather: str) -> float:
    base = 0.11
    if weather in ("gale", "storm", "rain"):
        base += 0.07
    return min(0.24, base)


async def maybe_after_salvage(conn, steward_id: int, *, got_loot: bool) -> str | None:
    if not got_loot:
        return None
    from . import world

    if random.random() > _chance(weather=world.current_weather()):
        return None
    cur = await conn.execute(
        "SELECT salvage_hazard FROM steward_craft WHERE steward_id=?",
        (steward_id,),
    )
    row = await cur.fetchone()
    if row and row[0]:
        return None
    payload = {"kind": "rope_tangle"}
    await conn.execute(
        """
        UPDATE steward_craft SET salvage_hazard=?, salvage_hazard_json=?
        WHERE steward_id=?
        """,
        (HAZARD_SNAG, json.dumps(payload, ensure_ascii=False), steward_id),
    )
    return (
        "缆绳缠住脚踝，货还压在绳圈里！"
        " craft_ops 捞险 割绳|弃货|硬拽"
        "（割绳=漂绳×1或8票；弃货=刚捞的货各减1；硬拽=12精力，可能咸痰）"
    )


def ui_actions(*, tickets: int, stock: dict[str, int], energy: int) -> list[dict[str, Any]]:
    twine = int(stock.get("drift_twine") or 0)
    return [
        {
            "action": "割绳",
            "label": "割绳",
            "hint": "漂绳×1 或 8 票",
            "can": twine >= 1 or tickets >= 8,
            "disabled_reason": "缺漂绳且票不够 8",
        },
        {"action": "弃货", "label": "弃货", "hint": "货各减 1", "can": True, "disabled_reason": ""},
        {
            "action": "硬拽",
            "label": "硬拽",
            "hint": "12 精力",
            "can": energy >= 12,
            "disabled_reason": "精力不够 12",
        },
    ]


async def resolve(conn, steward: dict[str, Any], choice: str) -> str:
    cur = await conn.execute(
        """
        SELECT salvage_hazard, salvage_hazard_json
        FROM steward_craft WHERE steward_id=?
        """,
        (steward["id"],),
    )
    row = await cur.fetchone()
    if not row or (row[0] or "") != HAZARD_SNAG:
        raise ValueError("没有缠网待决。craft_ops status 看打捞栏")
    ch = (choice or "").strip().lower()
    norm = None
    for zh, en, _ in CHOICES:
        if ch in (zh, en, _):
            norm = zh
            break
    if not norm:
        raise ValueError("捞险处置：割绳 · 弃货 · 硬拽（例 craft_ops 捞险 割绳）")
    sid = steward["id"]

    if norm == "割绳":
        paid = ""
        if not await db.take_item(conn, sid, "drift_twine", 1):
            cost = 8
            cur2 = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (sid,))
            have = int((await cur2.fetchone())[0])
            if have < cost:
                raise ValueError(f"割绳要漂绳×1 或 {cost} 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (cost, sid),
            )
            paid = f"-{cost} 票"
        else:
            paid = f"{item_label('drift_twine')}×1"
        await _clear(conn, sid)
        return f"割断绳圈，脚出来了，货还在。（{paid}）"

    if norm == "弃货":
        stock = await db.get_satchel(sid)
        lost: list[str] = []
        for key, qty in list(stock.items()):
            if qty <= 0:
                continue
            if key.startswith("fish_") or key in (
                "drift_twine", "craft_timber", "craft_rusty_nail", "sea_glass",
                "wet_note", "bait_worm", "quarry_shale", "shell_rough_catseye",
            ):
                await db.take_item(conn, sid, key, 1)
                lost.append(item_label(key))
        await _clear(conn, sid)
        if lost:
            return f"弃货脱身：{'、'.join(lost[:4])} 各少了 1（缠绳里泡坏了）。"
        return "弃货脱身：绳圈里没剩什么，人先上来了。"

    await energy.spend(conn, sid, 12, action="硬拽")
    await _clear(conn, sid)
    from . import health

    ill = await health.maybe_roll_ailment(
        conn, sid, "salvage", chance=0.28, source="salvage_snag",
    )
    msg = "硬拽把绳拽开了，货还在，人磕在礁上。"
    if ill:
        msg += f"\n{ill}\n→ visit_ops clinic treat 咸痰"
    return msg


async def _clear(conn, steward_id: int) -> None:
    await conn.execute(
        """
        UPDATE steward_craft SET salvage_hazard=NULL, salvage_hazard_json=NULL
        WHERE steward_id=?
        """,
        (steward_id,),
    )
