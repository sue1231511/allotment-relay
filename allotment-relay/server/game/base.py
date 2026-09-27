import random
import re
from typing import Any

import aiosqlite

from .. import config, db, events, flavor, farming, health, survival, world
from .. import commons
from ..catalog import (
    CROPS,
    resolve_crop_key,
    resolve_item_key,
    unknown_crop_message,
    unknown_item_message,
    FORAGE_LOOT,
    ITEM_NAMES,
    ITEM_PRICES,
    SEA_CATCH,
    item_label,
    item_stack_cap,
    suggested_price,
    weighted_fish_pick,
)
from ..config import (
    BADGES,
    BOATS,
    GUILD_SHIFT_DAILY,
    GUILD_TICKETS,
    MARKET_LIST_MAX,
    MARKET_LIST_SLOTS_MAX,
    MARKET_SLOT_COST,
    SWAP_CLAIM_FEE,
    BAR_MANDATORY_DAYS,
)




def _parse_int(token: str, label: str = "数量") -> int:
    cleaned = token.strip().rstrip(";,").lstrip("#")
    if cleaned.lower().startswith("x") and len(cleaned) > 1:
        cleaned = cleaned[1:]
    try:
        return int(cleaned)
    except ValueError:
        raise ValueError(f"{label}须为整数，收到: {token!r}") from None



def _parcel_line(plot: dict) -> str:
    from .. import land as land_mod
    label = land_mod.slot_label(plot)
    gh = "🪴" if plot.get("greenhouse") else ""
    left = land_mod.clear_left(plot)
    if left > 0:
        return f"  {label}{gh}: 开垦中（{farming.format_grow_eta(left)}）"
    if not plot.get("crop"):
        from .. import soil as soil_mod
        rest = soil_mod.status_suffix(plot)
        return f"  {label}{gh}: 休耕{rest}"
    meta = CROPS.get(plot["crop"], {"name": plot["crop"], "emoji": "🌱"})
    state = farming.parcel_status(plot)
    extra = farming.parcel_extra(plot)
    return f"  {label}{gh}: {meta['emoji']}{meta['name']}（{state}{extra}）"



async def _load_named_plot(
    conn,
    steward_id: int,
    token: str,
    *,
    orchard_ctx: bool = False,
    greenhouse_ctx: bool = False,
    fallback_other: bool = False,
) -> dict:
    from .. import land as land_mod
    slot, orchard_flag, gh_flag = land_mod.parse_slot_ref(
        token, orchard_ctx=orchard_ctx, greenhouse_ctx=greenhouse_ctx
    )
    plot = await land_mod.fetch_plot(conn, steward_id, slot, orchard_flag, gh_flag)
    if not plot and fallback_other:
        if gh_flag:
            plot = await land_mod.fetch_plot(conn, steward_id, slot, 0, 0)
        elif orchard_flag:
            plot = await land_mod.fetch_plot(conn, steward_id, slot, 0, 0) or (
                await land_mod.fetch_plot(conn, steward_id, slot, 0, 1)
            )
        else:
            plot = await land_mod.fetch_plot(conn, steward_id, slot, 1, 0) or (
                await land_mod.fetch_plot(conn, steward_id, slot, 0, 1)
            )
    if not plot:
        raise ValueError(land_mod.missing_slot_msg(slot, orchard_flag, gh_flag))
    return plot



async def require_steward(key_id: int, *, exempt_duty: bool = False) -> dict[str, Any]:
    s = await db.get_steward_by_key_id(key_id)
    if not s or not s["enrolled"]:
        raise ValueError("请先调用 steward_ops enroll 登记管理员身份")
    if not exempt_duty:
        from .. import bar
        await bar.assert_bar_duty(s)
    from .. import undertide
    await undertide.assert_not_jailed(s["id"])
    # 包宿行动锁：在后厨洗碗的人哪儿也去不了
    from .. import bar as bar_mod
    if bar_mod.is_lodging(s):
        hours = (int(s["lodge_until"]) - __import__("time").time()) // 3600
        if hours > 0:
            raise ValueError(
                "你还在后厨。碗没洗完，水汽糊在脸上。\n\n"
                f"（包宿中——约 {hours} 小时后结账走人。bar_ops lodge 查你的状态。）"
            )
    await db.touch_steward(s["id"])
    async with db.connect() as conn:
        from .. import health as health_mod
        from .. import disaster as disaster_mod
        await health_mod.tick_chronic(conn, s["id"])
        await disaster_mod.ensure_weekly_tide(conn)
        await disaster_mod.ensure_season_climate(conn)
        from .. import farming as farming_mod
        from .. import barn as barn_mod
        life_notes = await farming_mod.tick_tree_age(conn, s["id"])
        life_notes.extend(await barn_mod.tick_animal_age(conn, s["id"]))
        from .. import barn_disease as barn_disease_mod
        life_notes.extend(await barn_disease_mod.tick_barn_disease(conn, s["id"]))
        from .. import tax as tax_mod
        await tax_mod.ensure_shore_tax(conn)
        await tax_mod.collect_steward(conn, s["id"])
        from .. import upkeep as upkeep_mod
        await upkeep_mod.ensure_shore_upkeep(conn)
        await upkeep_mod.collect_steward(conn, s["id"])
        from .. import chaoshen as chaoshen_mod
        await chaoshen_mod.ensure_fund_payout(conn)
        from .. import bond as bond_mod
        await bond_mod.ensure_backfill(conn, s["id"])
        from .. import invite as invite_mod
        await invite_mod.evaluate_and_settle(conn, s["id"])
        await conn.commit()
    s = await db.get_steward_by_id(s["id"]) or s
    if life_notes:
        s = dict(s)
        s["_life_notes"] = life_notes
    from .. import progress as progress_mod
    await progress_mod.sync_steward(s)
    return s

