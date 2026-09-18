"""盐风崖麻烦档：挥镐后小概率塌方，三选一（撑柱 / 撤人 / 硬挖）。"""
from __future__ import annotations

import json
import random
from typing import Any

from . import config, db, world
from .catalog import item_label

HAZARD_COLLAPSE = "collapse"

COLLAPSE_CHOICES = (
    ("撑柱", "shore", "prop"),
    ("撤人", "pull", "retreat"),
    ("硬挖", "force", "dig"),
)


def _chance(*, weather: str, tide: str) -> float:
    base = 0.07
    if weather in ("gale", "storm", "rain"):
        base += 0.06
    if tide == "flood":
        base += 0.04
    return min(0.22, base)


async def maybe_after_hew(
    conn,
    steward_id: int,
    slot: int,
    *,
    strikes_left: int,
    vein: str,
) -> str | None:
    if strikes_left <= 0 or not vein:
        return None
    cur = await conn.execute(
        "SELECT hazard FROM quarry_claims WHERE steward_id=? AND slot=?",
        (steward_id, slot),
    )
    row = await cur.fetchone()
    if row and row[0]:
        return None
    tide, weather = world.current_tide(), world.current_weather()
    if random.random() > _chance(weather=weather, tide=tide):
        return None
    payload = {"slot": slot, "vein": vein, "strikes_left": strikes_left}
    await conn.execute(
        """
        UPDATE quarry_claims SET hazard=?, hazard_json=?
        WHERE steward_id=? AND slot=?
        """,
        (HAZARD_COLLAPSE, json.dumps(payload, ensure_ascii=False), steward_id, slot),
    )
    return (
        f"坑{slot}顶上传来碎石滚落——塌方了！"
        f" quarry_ops 塌方 {slot} 撑柱|撤人|硬挖"
        "（撑柱=岸木×2或12票；撤人=这脉作废但人没事；硬挖=不花钱更险，小概率落石后多一块矿）"
    )


def ui_actions(*, tickets: int, stock: dict[str, int]) -> list[dict[str, Any]]:
    have_wood = int(stock.get("craft_timber") or 0)
    return [
        {
            "action": "撑柱",
            "label": "撑柱",
            "hint": "岸木×2 或 12 票",
            "can": have_wood >= 2 or tickets >= 12,
            "disabled_reason": "缺岸木×2 且票不够 12",
        },
        {"action": "撤人", "label": "撤人", "hint": "放弃这脉", "can": True, "disabled_reason": ""},
        {"action": "硬挖", "label": "硬挖", "hint": "不花钱更险", "can": True, "disabled_reason": ""},
    ]


async def resolve(
    conn,
    steward: dict[str, Any],
    slot: int,
    choice: str,
) -> str:
    cur = await conn.execute(
        """
        SELECT hazard, hazard_json, vein, strikes_left
        FROM quarry_claims WHERE steward_id=? AND slot=?
        """,
        (steward["id"], slot),
    )
    row = await cur.fetchone()
    if not row or (row[0] or "") != HAZARD_COLLAPSE:
        raise ValueError(f"坑{slot} 没有塌方待决。quarry_ops status 看坑")
    ch = (choice or "").strip().lower()
    norm = None
    for zh, en, _ in COLLAPSE_CHOICES:
        if ch in (zh, en, _):
            norm = zh
            break
    if not norm:
        raise ValueError("塌方处置：撑柱 · 撤人 · 硬挖（例 quarry_ops 塌方 1 撑柱）")

    label = f"坑{slot}"
    sid = steward["id"]

    if norm == "撑柱":
        paid = ""
        if not await db.take_item(conn, sid, "craft_timber", 2):
            cost = 12
            cur2 = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (sid,))
            have = int((await cur2.fetchone())[0])
            if have < cost:
                raise ValueError(f"撑柱要岸木×2 或 {cost} 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (cost, sid),
            )
            paid = f"-{cost} 票"
        else:
            paid = f"{item_label('craft_timber')}×2"
        await _clear_hazard(conn, sid, slot)
        return f"{label} 撑住落石，脉还在，继续挖。（{paid}）"

    if norm == "撤人":
        await conn.execute(
            """
            UPDATE quarry_claims
            SET vein='', strikes_left=0, hazard=NULL, hazard_json=NULL
            WHERE steward_id=? AND slot=?
            """,
            (sid, slot),
        )
        return f"{label} 撤出来了。这条脉作废，quarry_ops 探脉 {slot} 再找。"

    # 硬挖
    vein_key = row[2] or ""
    await _clear_hazard(conn, sid, slot)
    msg = f"{label} 顶着落石硬挖。"
    from .catalog import QUARRY_VEINS

    if vein_key in QUARRY_VEINS and random.random() < 0.12:
        raw_key = QUARRY_VEINS[vein_key]["raw"]
        await db.add_item(conn, sid, raw_key, 1)
        msg += f" 落石滚开，多捡到一块{item_label(raw_key)}。"
    if random.random() < 0.38:
        await conn.execute(
            """
            UPDATE quarry_claims SET strikes_left=MAX(0, strikes_left-1)
            WHERE steward_id=? AND slot=?
            """,
            (sid, slot),
        )
        msg += " 石屑砸下来，这脉又少了一镐。"
    prof = await conn.execute(
        "SELECT pick_tier FROM steward_quarry WHERE steward_id=?", (sid,),
    )
    pt = int((await prof.fetchone())[0] or 0)
    if pt >= 1 and random.random() < 0.22:
        new_t = max(1, pt - 1)
        if new_t < pt:
            await conn.execute(
                "UPDATE steward_quarry SET pick_tier=? WHERE steward_id=?",
                (new_t, sid),
            )
            msg += f" 镐刃崩了，暂时当 T{new_t} 用（quarry_ops 升镐 可修档）。"
    return msg


async def _clear_hazard(conn, steward_id: int, slot: int) -> None:
    await conn.execute(
        """
        UPDATE quarry_claims SET hazard=NULL, hazard_json=NULL
        WHERE steward_id=? AND slot=?
        """,
        (steward_id, slot),
    )
