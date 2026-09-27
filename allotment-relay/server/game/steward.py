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


from .base import _parse_int, _parcel_line, _load_named_plot, require_steward
from .tide import _collect_bottle_replies, _collect_handoffs


async def steward_sheet(key_id: int) -> str:
    s = await require_steward(key_id, exempt_duty=True)
    async with db.connect() as conn:
        from .. import energy as energy_mod
        from .. import health as health_mod
        await energy_mod.soft_regen(conn, s["id"])
        ailments = await health_mod.list_ailments(conn, s["id"])
        from .. import lili as lili_mod
        from .. import hut as hut_mod
        await lili_mod.maybe_spawn_visit(conn)
        lili_hint = await lili_mod.active_visit_hint(conn)
        hut_summary = (await hut_mod.get_bonuses(conn, s["id"])).summary()
        handoff_notes = await _collect_handoffs(conn, s["id"])
        from .. import neighbor_links as nlink_mod
        loan_notes = await nlink_mod.loan_reminder_notices(conn, s["id"])
        bottle_notes = await _collect_bottle_replies(conn, s["id"])
        open_incidents = await events.list_open_incidents_on(conn, s["id"])
        dove_pending = await farming.get_gugu_dove_pending(conn, s["id"])
        from .. import land as land_mod
        finished = await land_mod.settle(conn, s["id"])
        await conn.commit()
    s = await db.get_steward_by_id(s["id"]) or s
    from .. import progress as progress_mod
    await progress_mod.sync_steward(s, rewards=True)
    parcels = await db.get_parcels(s["id"])
    stock = await db.get_satchel(s["id"])
    from .. import energy as energy_mod
    from .. import ranks as ranks_mod
    from .. import progress as progress_mod
    from .. import bar as bar_mod
    from .. import health as health_mod
    from .. import land as land_mod
    from .. import bond as bond_mod
    from .. import invite as invite_mod
    ranked = ranks_mod.attach_level(s)
    invite_line = invite_mod.sheet_line(s)
    lines = [
        f"管理员: {s['name']} ({s['badge']})",
        f"座右铭: {s['motto']}",
        f"肖像: {s['portrait']}",
        f"工分票: {s['tickets']}",
        ranks_mod.sheet_level_line(ranked),
        progress_mod.sheet_title_line(ranked),
        *bond_mod.sheet_lines(s),
        *([invite_line] if invite_line else []),
        survival.meter_line(s),
        health_mod.meter_line(s, ailments),
        energy_mod.meter_line(s, ailments),
        bar_mod.duty_line(s),
        land_mod.sheet_note(s, parcels, orchard=False),
        land_mod.sheet_note(s, parcels, orchard=True),
        land_mod.sheet_note(s, parcels, greenhouse=True),
        world.climate_line(),
        "岛务: 潮生会（值事阿簿）→ visit_ops 潮生会 · 岸税 税 · 岸维 维 · 潮汐基金 基金 捐 50（票数自填；补贴周二四六自动发）",
    ]
    for note in s.get("_life_notes") or []:
        lines.append(note)
    from .. import disaster as disaster_mod
    climate_line = await disaster_mod.climate_sheet_line()
    if climate_line:
        lines.append(climate_line)
    from .. import cloth as cloth_mod
    async with db.connect() as cloth_conn:
        cloth_line = await cloth_mod.sheet_line(cloth_conn, s["id"])
    if cloth_line:
        lines.append(cloth_line)
    from .. import tax as tax_mod
    tax_line = await tax_mod.sheet_line(s)
    if tax_line:
        lines.append(tax_line)
    from .. import upkeep as upkeep_mod
    upkeep_line = await upkeep_mod.sheet_line(s)
    if upkeep_line:
        lines.append(upkeep_line)
    pulse_snap = await events.public_pulse_snapshot()
    if pulse_snap:
        mins = pulse_snap["remaining"] // 60
        kind = "凶" if pulse_snap["kind"] == "bad" else "吉"
        lines.append(
            f"全服脉冲：{pulse_snap['label']}（{kind}，约 {mins} 分钟）→ plot_ops incident scan"
        )
        if pulse_snap.get("detail"):
            lines.append(f"  {pulse_snap['detail']}")
    from .. import disaster as disaster_mod
    hit_line = await disaster_mod.recent_hit_line(s["id"])
    if hit_line:
        lines.append(hit_line)
    for done in finished:
        lines.append(done)
    hint = survival.low_meter_hint(s)
    if hint:
        lines.append(hint)
    clinic_nag = health_mod.clinic_hint(ailments)
    if clinic_nag:
        lines.append(clinic_nag)
    if open_incidents:
        lines.append(
            f"未处理意外 {len(open_incidents)} 条 → plot_ops incident / repair 编号"
        )
        for r in open_incidents[:4]:
            label = r.get("label") or r["incident_key"]
            cost = r.get("repair_tickets") or 0
            lines.append(f"  编号 #{r['id']} {label}（repair {cost} 票）")
    if dove_pending:
        lines.append("🕊️ 斑鸠盯梢中 → plot_ops dove 忽略|驱赶")
    if lili_hint:
        lines.append(lili_hint)
    from .. import tt as tt_mod
    lines.append(tt_mod.shopfront_line() + " → visit_ops tt")
    for note in handoff_notes:
        lines.append(note)
    for note in loan_notes:
        lines.append(note)
    for note in bottle_notes:
        lines.append(note)
    gh_n = int(s.get("greenhouse_count") or 0) or (1 if s.get("greenhouse") else 0)
    if gh_n:
        label = s.get("greenhouse_label") or "未命名"
        lines.append(f"温室: {gh_n} 座 · {label}（sow 棚1 / sow 99）")
    if s.get("boat_key"):
        boat = BOATS.get(s["boat_key"], {})
        dmg = " ⚠待修" if s.get("boat_damaged") else ""
        lines.append(f"船: {boat.get('name', s['boat_key'])}{dmg}")
    if s.get("hut_built"):
        from ..catalog import HUT_LEVELS
        lvl = s.get("hut_level") or 1
        hname = s.get("hut_label") or HUT_LEVELS[lvl]["name"]
        lines.append(f"小屋: {hname}（Lv{lvl}）")
        if hut_summary:
            lines.append(hut_summary)
    if s.get("barn_built"):
        lines.append("畜栏: 已建")
    if s.get("eatery_open"):
        lines.append(
            f"小馆: {s.get('eatery_label') or s['name']+'的馆'}"
            f"（kitchen_ops shop menu · 不想开了 shop 卖掉）"
        )
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        from .. import marine as marine_mod
        pens = await marine_mod._list_pens(conn, s["id"])
        voyage = await (await conn.execute(
            """
            SELECT route, returns_at, status FROM voyages
            WHERE steward_id=? AND status IN ('sailing','hailed','fish_encounter')
            """,
            (s["id"],),
        )).fetchone()
        from .. import tale as tale_mod
        tale_line = await tale_mod.snapshot_line(key_id)
    if pens:
        lines.append("渔排:")
        for pen in pens:
            lines.append(marine_mod._pen_line(pen))
    if voyage:
        from ..config import VOYAGE_ROUTES
        if voyage["status"] == "hailed":
            lines.append(
                f"出海: {VOYAGE_ROUTES[voyage['route']]['label']} 🏴 黑旗截停 — "
                "tide_ops fight|flee|parley|bribe"
            )
        elif voyage["status"] == "fish_encounter":
            lines.append(
                f"出海: {VOYAGE_ROUTES[voyage['route']]['label']} 🐟 未命名小鱼 — "
                "tide_ops compliment|release|catch|grab"
            )
        else:
            left = max(0, voyage["returns_at"] - db.now())
            lines.append(f"出海: {VOYAGE_ROUTES[voyage['route']]['label']}（{left // 60} 分后归港）")
    if s["mascot_name"]:
        from .. import social as social_mod
        lines.append(f"吉祥物: {s['mascot_name']}（{s['mascot_trait']}，士气 {s['mascot_spirit']}）")
        mhint = social_mod.mascot_spirit_hint(s.get("mascot_spirit", 70))
        if mhint:
            lines.append(mhint)
    if tale_line:
        lines.append(tale_line)
    plots = [p for p in parcels if not p.get("orchard")]
    trees = [p for p in parcels if p.get("orchard")]
    lines.append("份地状态:")
    lines.extend(_parcel_line(p) for p in plots)
    lines.append("果园:")
    lines.extend(_parcel_line(p) for p in trees)
    if stock:
        lines.append("行囊:")
        for item, qty in stock.items():
            lines.append(f"  {ITEM_NAMES.get(item, item)} x{qty} · {item}")
    recent_gifts = await db.list_received_gifts(s["id"], 1)
    if recent_gifts:
        lines.append("最近有人送礼/酒吧打赏 → tote_ops gifts 查看详情")
    async with db.connect() as conn:
        from .. import market as market_mod
        extra = await market_mod._market_extra(conn, s["id"])
        cap = market_mod.market_list_cap(extra)
        used = (await (await conn.execute(
            "SELECT COUNT(*) FROM market_listings WHERE seller_id=? AND buyer_id IS NULL",
            (s["id"],),
        )).fetchone())[0]
        if used or cap > MARKET_LIST_MAX:
            expand = ""
            if cap < MARKET_LIST_SLOTS_MAX:
                expand = f"；满了可 market_ops 扩（{MARKET_SLOT_COST}票/格）"
            lines.append(f"集市摊格 {used}/{cap}{expand} → market_ops mine")
    # 濒死提示：钱包见底+精力见底时，把包宿的门指给他
    if int(s.get("tickets") or 0) < 20 and int(s.get("energy") or 100) < 30:
        lines.append(
            "\n⚠ 混不下去了？bar_ops lodge — 酒馆包宿：管饭+工钱 15，"
            "干一整天（当晚还要帮忙陪酒）。荔栀的后门只救人，不养人。"
        )
    return "\n".join(lines)



async def steward_revise(key_id: int, motto: str = "", portrait: str = "") -> str:
    s = await require_steward(key_id, exempt_duty=True)
    async with db.connect() as conn:
        if motto.strip():
            await conn.execute("UPDATE stewards SET motto = ? WHERE id = ?", (motto.strip()[:200], s["id"]))
        if portrait.strip():
            await conn.execute("UPDATE stewards SET portrait = ? WHERE id = ?", (portrait.strip()[:120], s["id"]))
        await conn.commit()
    s = await db.get_steward_by_id(s["id"]) or s
    return (
        "资料已修订\n"
        f"座右铭: {s['motto'] or '（空）'}\n"
        f"肖像: {s['portrait'] or '（空）'}"
    )



async def peer_sheet(name: str, *, viewer_id: int | None = None) -> str:
    s = await db.get_steward_by_name(name)
    if not s or not s["enrolled"]:
        raise ValueError(f"未找到管理员: {name}")
    parcels = await db.get_parcels(s["id"])
    from .. import ranks as ranks_mod
    from .. import progress as progress_mod
    from .. import bond as bond_mod
    ranked = ranks_mod.attach_level(s)
    rapport_line = ""
    if viewer_id and int(viewer_id) != int(s["id"]):
        from .. import social as social_mod

        score = await social_mod.get_rapport(int(viewer_id), int(s["id"]))
        rapport_line = social_mod.rapport_peer_blurb(score)
    lines = [
        f"管理员: {s['name']} ({s['badge']})",
    ]
    if rapport_line:
        lines.append(rapport_line)
    lines.extend([
        f"座右铭: {s['motto']}",
        f"肖像: {s['portrait']}",
        f"工分票: {s['tickets']}",
        ranks_mod.sheet_level_line(ranked),
        progress_mod.sheet_title_line(ranked),
        *bond_mod.sheet_lines(s),
        f"温室: {int(s.get('greenhouse_count') or 0) or (1 if s.get('greenhouse') else 0)} 座"
        + (f" · {s['greenhouse_label']}" if s.get("greenhouse_label") else ""),
        "公开份地:",
        *(_parcel_line(p) for p in parcels if not p.get("orchard") and not p.get("greenhouse")),
        "公开果园:",
        *(_parcel_line(p) for p in parcels if p.get("orchard")),
        "公开温室:",
        *(_parcel_line(p) for p in parcels if p.get("greenhouse")),
        f"岛务: 潮生会（值事阿簿）→ visit_ops 潮生会 · 岸税 税 · 岸维 维 · 潮汐基金 基金 捐 50（票数自填；补贴周二四六自动发）",
        f"串门: plot_ops 偷菜 {s['name']} · alliance_ops assist {s['name']}",
    ])
    return "\n".join(lines)



async def guild_shift(key_id: int) -> str:
    s = await require_steward(key_id)
    day = db.day_id()
    mult, note = survival.guild_ticket_multiplier(s)
    caravan = await events.guild_pulse_multiplier()
    gain = max(1, int(GUILD_TICKETS * mult * caravan))
    async with db.connect() as conn:
        cur = await conn.execute(
            "SELECT count FROM guild_shifts WHERE steward_id=? AND day=?",
            (s["id"], day),
        )
        row = await cur.fetchone()
        used = row[0] if row else 0
        if used >= GUILD_SHIFT_DAILY:
            raise ValueError(
                f"今日 guild 轮值已领取（每日 {GUILD_SHIFT_DAILY} 次，明天再来）"
            )
        from .. import hut as hut_mod
        hut_b = await hut_mod.get_bonuses(conn, s["id"])
        await conn.execute(
            "UPDATE stewards SET tickets = tickets + ? WHERE id = ?",
            (gain, s["id"]),
        )
        await conn.execute(
            """
            INSERT INTO guild_shifts (steward_id, day, count) VALUES (?,?,1)
            ON CONFLICT(steward_id, day) DO UPDATE SET count = count + 1
            """,
            (s["id"], day),
        )
        await survival.bump(conn, s["id"], standing=4 + hut_b.guild_standing, mist_wit=2)
        from .. import bond as bond_mod
        await bond_mod.grant(conn, s["id"], bond_mod.GUILD, "labor")
        extra = await events.roll_after_action(s, "guild", conn)
        await conn.commit()
    await db.add_chronicle("guild", f"{s['name']} 完成一轮 guild 轮值，+{gain} 票", s["id"])
    msg = f"获得 {gain} 工分票（今日 guild {used + 1}/{GUILD_SHIFT_DAILY}）"
    if note:
        msg += f"（{note}）"
    msg += flavor.maybe_suffix(flavor.GUILD_SUFFIX)
    return f"{msg}\n{extra}" if extra else msg

