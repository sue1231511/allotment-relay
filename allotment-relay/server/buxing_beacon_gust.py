"""灯塔麻烦档：守夜后阵风晃灯，三选一（压窗 / 避风 / 硬守）。"""
from __future__ import annotations

import json
import random
from typing import Any

from . import db, energy


HAZARD_GALE = "gale"


async def ensure_columns(conn) -> None:
    for ddl in (
        "ALTER TABLE steward_buxing ADD COLUMN beacon_hazard TEXT",
        "ALTER TABLE steward_buxing ADD COLUMN beacon_hazard_json TEXT",
    ):
        try:
            await conn.execute(ddl)
        except Exception:
            pass


async def get_hazard(conn, steward_id: int) -> str:
    await ensure_columns(conn)
    cur = await conn.execute(
        "SELECT beacon_hazard FROM steward_buxing WHERE steward_id=?",
        (steward_id,),
    )
    row = await cur.fetchone()
    return (row[0] or "") if row else ""


def _chance() -> float:
    from . import world

    w = world.current_weather()
    base = 0.10
    if w in ("gale", "storm", "windy"):
        base = 0.24
    elif w == "rain":
        base = 0.14
    return base


async def maybe_after_watch(conn, steward_id: int) -> str | None:
    if await get_hazard(conn, steward_id):
        return None
    if random.random() > _chance():
        return None
    await ensure_columns(conn)
    await conn.execute(
        """
        INSERT INTO steward_buxing (steward_id, updated_at, beacon_hazard, beacon_hazard_json)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(steward_id) DO UPDATE SET
            beacon_hazard=excluded.beacon_hazard,
            beacon_hazard_json=excluded.beacon_hazard_json,
            updated_at=excluded.updated_at
        """,
        (
            steward_id,
            db.now(),
            HAZARD_GALE,
            json.dumps({"kind": "beacon_gust"}, ensure_ascii=False),
        ),
    )
    return (
        "塔窗被风拍得直响，灯芯乱跳！"
        " visit_ops buxing 灯险 压窗|避风|硬守"
        "（压窗=砖×1或10票；避风=8精力；硬守=12精力）"
        "人类 /island 灯塔也能点。"
    )


async def assert_not_blocked(conn, steward_id: int) -> None:
    if await get_hazard(conn, steward_id) == HAZARD_GALE:
        raise ValueError(
            "塔上还在晃，先 visit_ops buxing 灯险 压窗|避风|硬守。"
            "人类 /island 灯塔也能点。"
        )


def ui_actions(*, tickets: int, stock: dict[str, int], energy_now: int) -> list[dict[str, Any]]:
    brick = int(stock.get("quarry_brick") or 0)
    return [
        {
            "action": "压窗",
            "label": "压窗",
            "hint": "砖×1 或 10 票",
            "can": brick >= 1 or tickets >= 10,
            "disabled_reason": "缺砖且票不够 10",
        },
        {
            "action": "避风",
            "label": "避风",
            "hint": "8 精力",
            "can": energy_now >= 8,
            "disabled_reason": "精力不够 8",
        },
        {
            "action": "硬守",
            "label": "硬守",
            "hint": "12 精力",
            "can": energy_now >= 12,
            "disabled_reason": "精力不够 12",
        },
    ]


async def resolve(conn, steward: dict[str, Any], choice: str) -> str:
    if await get_hazard(conn, steward["id"]) != HAZARD_GALE:
        raise ValueError("没有塔窗待决。visit_ops buxing visit 上塔")
    ch = (choice or "").strip().lower()
    norm = None
    for zh, en in (("压窗", "bar"), ("避风", "shelter"), ("硬守", "hold")):
        if ch in (zh, en):
            norm = zh
            break
    if not norm:
        raise ValueError("灯险处置：压窗 · 避风 · 硬守（例 visit_ops buxing 灯险 压窗）")
    sid = steward["id"]

    if norm == "压窗":
        paid = ""
        if not await db.take_item(conn, sid, "quarry_brick", 1):
            cost = 10
            have = int((await (await conn.execute(
                "SELECT tickets FROM stewards WHERE id=?", (sid,)
            )).fetchone())[0])
            if have < cost:
                raise ValueError("压窗要页岩砖×1 或 10 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (cost, sid),
            )
            paid = f"-{cost} 票"
        else:
            paid = "页岩砖×1"
        await _clear(conn, sid, flash_summary="灯塔灯险：压窗稳灯，灯险已结。")
        return f"压好窗闩，灯芯稳了。（{paid}）"

    if norm == "避风":
        await energy.spend(conn, sid, 8, action="灯塔避风")
        await _clear(conn, sid, flash_summary="灯塔灯险：避风守灯，灯险已结。")
        return "躲进塔心一圈，风过再点灯。"

    await energy.spend(conn, sid, 12, action="灯塔硬守")
    lost = ""
    if random.random() < 0.2:
        await conn.execute(
            "UPDATE stewards SET tickets=MAX(0, tickets-5) WHERE id=?",
            (sid,),
        )
        lost = "风刮走一点灯油（−5 票）。"
    await _clear(conn, sid, flash_summary="灯塔灯险：硬守过关，灯险已结。")
    return f"硬顶住窗框，守住了。{lost}"


async def _clear(
    conn,
    steward_id: int,
    *,
    flash_summary: str = "",
) -> None:
    await ensure_columns(conn)
    await conn.execute(
        """
        UPDATE steward_buxing
        SET beacon_hazard=NULL, beacon_hazard_json=NULL, updated_at=?
        WHERE steward_id=?
        """,
        (db.now(), steward_id),
    )
    if flash_summary:
        from . import hazard_flash as hf

        await hf.on_trouble_cleared(
            conn, steward_id, "lighthouse", flash_summary, "beacon_gust",
        )
