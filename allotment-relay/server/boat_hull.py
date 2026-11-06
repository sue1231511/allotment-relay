"""船体损耗 — 第二批：航程磨 hull，低则 boat_damaged。

船体数值（steward_boat_hull）和「待修」开关（stewards.boat_damaged）是两件事：
航程只磨数值，数值很低时才有概率亮开关。修船看的是两者之一：开关亮着或数值没满都能修。
"""
from __future__ import annotations

import json
import logging
import math
import random
from typing import Any

from . import db

logger = logging.getLogger(__name__)

DEFAULT_HULL = 100


async def ensure_table(conn) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS steward_boat_hull (
            steward_id INTEGER PRIMARY KEY,
            hull INTEGER NOT NULL,
            max_hull INTEGER NOT NULL
        )
        """
    )


async def get_hull(conn, steward_id: int) -> tuple[int, int]:
    await ensure_table(conn)
    cur = await conn.execute(
        "SELECT hull, max_hull FROM steward_boat_hull WHERE steward_id=?",
        (steward_id,),
    )
    row = await cur.fetchone()
    if row:
        return int(row[0]), int(row[1])
    await conn.execute(
        "INSERT INTO steward_boat_hull (steward_id, hull, max_hull) VALUES (?, ?, ?)",
        (steward_id, DEFAULT_HULL, DEFAULT_HULL),
    )
    return DEFAULT_HULL, DEFAULT_HULL


async def wear_after_voyage(conn, steward_id: int, route_key: str, *, storm: bool = False) -> str:
    loss_map = {"near": 4, "far": 7, "deep": 11}
    loss = loss_map.get(route_key, 6)
    if storm:
        loss += 6
    hull, mx = await get_hull(conn, steward_id)
    hull = max(0, hull - loss)
    await conn.execute(
        "UPDATE steward_boat_hull SET hull=? WHERE steward_id=?",
        (hull, steward_id),
    )
    note = f"船体 {hull}/{mx}"
    if hull <= 20:
        if random.random() < 0.45:
            await conn.execute(
                "UPDATE stewards SET boat_damaged=1 WHERE id=?",
                (steward_id,),
            )
            note += "，船体吃不住→待修"
    elif hull <= 35:
        note += "，该保养了"
    return note


async def repair_full(conn, steward_id: int) -> None:
    await get_hull(conn, steward_id)
    await conn.execute(
        "UPDATE steward_boat_hull SET hull=max_hull WHERE steward_id=?",
        (steward_id,),
    )


def repair_cost(base: int, hull: int, max_hull: int, damaged: bool) -> int:
    """船损待修收全价；只是船体没满，按缺的比例收，至少 1 票。"""
    base = max(1, int(base))
    if damaged or max_hull <= 0:
        return base
    missing = max(0, max_hull - hull)
    return max(1, math.ceil(base * missing / max_hull))


def needs_repair(hull: int, max_hull: int, damaged: bool) -> bool:
    return bool(damaged) or hull < max_hull


async def hull_owner(conn, steward: dict[str, Any]) -> tuple[int, str, str]:
    """现在开的这条船，船体记在谁身上。

    和 voyage depart 选船的规则一致：合伙大船（档位不低于自有）→ 发起人；
    自己没船、借了邻居的 → 船主；其余 → 自己。
    返回 (船体主人 id, 这条船的 boat_key, "self" | "share" | "loan")。没船时 boat_key 为空。
    """
    from . import neighbor_boat_share as share_mod
    from . import neighbor_links as nlink_mod

    sid = int(steward["id"])
    boat_key = await nlink_mod.effective_boat_key(conn, steward) or ""
    if not boat_key:
        return sid, "", "self"
    share_key = await share_mod.share_boat_key(conn, sid)
    if share_key and boat_key == share_key:
        founder = await share_mod.share_founder_id(conn, sid)
        if founder:
            return int(founder), boat_key, "share"
    if not steward.get("boat_key"):
        lender = await nlink_mod.boat_loan_lender(conn, sid)
        if lender:
            return int(lender), boat_key, "loan"
    return sid, boat_key, "self"


def voyage_owner_id(steward_id: int, voyage: dict[str, Any] | None) -> int:
    """航行途中船体记在谁身上：出航时写进 encounter 的合伙发起人 / 船主，否则自己。"""
    raw = (voyage or {}).get("encounter") or "{}"
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.exception(
            "voyage_owner_id: encounter 解析失败 steward_id=%s voyage_id=%s encounter=%r",
            steward_id, (voyage or {}).get("id"), raw,
        )
        return steward_id
    if not isinstance(payload, dict):
        return steward_id
    owner = int(payload.get("share_founder_id") or 0) or int(payload.get("loan_lender_id") or 0)
    return owner or steward_id


async def status_line(conn, steward_id: int, *, relation: str = "self") -> str:
    """steward_id 是船体主人（hull_owner 的第一项）。"""
    hull, mx = await get_hull(conn, steward_id)
    pct = int(100 * hull / mx) if mx else 0
    line = f"船体 {hull}/{mx}（{pct}%）"
    if hull >= mx:
        return line
    if relation == "loan":
        return line + "，借来的船由船主 tide_ops voyage repair"
    if relation == "share":
        return line + "，tide_ops voyage repair 补满（合伙平摊）"
    return line + "，tide_ops voyage repair 补满"
