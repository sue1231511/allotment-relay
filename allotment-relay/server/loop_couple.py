"""生产→消耗→损耗→维修→加工→交易→事件→再生产 强耦合。

不另开玩法：读现有库存/耐久/待选，把下一步写进看屋；灶旧掉星、柜旧压生鱼价。
"""
from __future__ import annotations

import random
from typing import Any

from . import durability as dura_mod

LOOP_STEPS = ("生产", "消耗", "损耗", "维修", "加工", "交易", "事件", "再生产")


async def fridge_price_mult(conn, steward_id: int, item: str) -> float:
    """柜旧/没柜：生鱼回收压一档。加工过的不受。"""
    if not str(item or "").startswith("fish_"):
        return 1.0
    from . import hut_appliances as appl_mod

    if not await appl_mod.has_appliance(conn, steward_id, "fridge"):
        return 0.88
    dur, mx = await appl_mod.get_durability(conn, steward_id, "fridge")
    return 1.0 if dura_mod.efficiency(dur, mx) >= 0.75 else 0.88


async def adjust_cook_stars(conn, steward_id: int, stars: int) -> tuple[int, str]:
    """灶旧或硬烧：星级可能掉一档，材料不退。"""
    from . import hut_appliances as appl_mod
    from . import light_bad_events as light_mod

    note = ""
    if await light_mod.has_flag(conn, steward_id, "stove_hard"):
        await light_mod.take_flag(conn, steward_id, "stove_hard")
        if stars > 1 and random.random() < 0.55:
            stars = max(1, stars - 1)
            note = "硬烧，星级掉一档"
    if await appl_mod.has_appliance(conn, steward_id, "stove"):
        dur, mx = await appl_mod.get_durability(conn, steward_id, "stove")
        bonus = dura_mod.fail_bonus(dur, mx)
        if bonus and stars > 1 and random.random() < bonus:
            stars = max(1, stars - 1)
            note = note or "灶旧，这锅只到下一档"
        await appl_mod.wear_stove(conn, steward_id)
    return stars, note


async def hint(conn, steward: dict[str, Any]) -> str | None:
    """八步闭环：每步读另一系统，指出卡住的下一环。"""
    sid = steward["id"]
    cur = await conn.execute(
        "SELECT item, quantity FROM satchel WHERE steward_id=? AND quantity>0",
        (sid,),
    )
    stock = {r[0]: int(r[1]) for r in await cur.fetchall()}
    fish = [k for k in stock if k.startswith("fish_")]
    crops = [k for k in stock if k.startswith("crop_")]
    seeds = [k for k in stock if k.startswith("seed_")]
    meals = [k for k in stock if k.startswith("dish_") or k.startswith("meal_")]
    pickled = int(stock.get("proc_pickled_fish") or 0) + int(stock.get("pickles") or 0)
    tickets = int(steward.get("tickets") or 0)

    from . import hut_appliances as appl_mod
    from . import boat_parts as boat_mod
    from . import event_choice as choice_mod

    fridge_on = await appl_mod.has_appliance(conn, sid, "fridge")
    fridge_dur, fridge_mx = (100, 100)
    if fridge_on:
        fridge_dur, fridge_mx = await appl_mod.get_durability(conn, sid, "fridge")
    stove_on = await appl_mod.has_appliance(conn, sid, "stove")
    stove_dur, stove_mx = (100, 100)
    if stove_on:
        stove_dur, stove_mx = await appl_mod.get_durability(conn, sid, "stove")
    parts = await boat_mod.get_all(conn, sid)
    sail, sail_mx = parts.get("sail", (100, 100))
    pending = await choice_mod.list_open(conn, sid)
    snap = await dura_mod.snapshot(conn, sid)
    worn = [r for r in snap if r["dur"] / max(1, r["max"]) < 0.45]

    bits: list[str] = []
    if not crops and not fish and seeds:
        bits.append("生产：种还在袋里，份地点空地播种")
    if worn:
        bits.append(f"损耗：{worn[0]['label']}旧了，可硬用（效率降）→ {worn[0]['fix']}")
    if worn and tickets >= worn[0]["repair_cost"]:
        bits.append(f"维修：票够修{worn[0]['label']}（约{worn[0]['repair_cost']}票）")
    elif worn:
        bits.append("维修：票不够，先卖加工货或下馆")
    if fish and pickled <= 0 and not meals:
        bits.append("加工：鱼可腌/晒/打刺身再卖，生鱼柜旧压价")
    if crops and not meals and stove_on and stove_dur / max(1, stove_mx) < 0.45:
        bits.append("加工：灶旧了，先小屋点修灶再出菜，硬烧可能掉星")
    if meals or pickled:
        bits.append("交易：熟菜/腌货去行囊卖票，票再回头修")
    if fish and fridge_on and fridge_dur / max(1, fridge_mx) < 0.45:
        bits.append("交易：冰箱旧，生鱼回收会少一截 → 小屋点修冰箱")
    elif fish and not fridge_on:
        bits.append("消耗：钓上来了，小屋买冰箱再装，生鱼才扛得住")
    if pending:
        bits.append(f"事件：{pending[0]['via']}待选 {'｜'.join(pending[0]['opts'][:3])}")
    if sail / max(1, sail_mx) < 0.45:
        bits.append("损耗：帆旧了，出航前港口修帆舵灯，或硬撑")
    if tickets >= 8 and not seeds and (meals or pickled or not crops):
        bits.append("再生产：卖完了去杂货铺买种，份地再播")
    if not bits:
        return None
    return "闭环：" + " · ".join(bits[:4])


def couple_ok() -> bool:
    return len(LOOP_STEPS) == 8 and callable(hint) and callable(adjust_cook_stars)
