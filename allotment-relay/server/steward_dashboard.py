"""管家私有状态面板 — 供 /steward 网页用 API key 查询。"""

from __future__ import annotations

import aiosqlite
from typing import Any

from . import bar, db, energy, events, farming, health, land, ranks, survival, world
from . import undertide
from .catalog import CROPS, ITEM_NAMES
from .config import ONLINE_WINDOW
from . import market as market_mod
from .undertide_copy import REP_TIER_DESC


async def fetch_dashboard(api_key: str) -> dict[str, Any]:
    row = await db.get_key_row(api_key.strip())
    if not row:
        raise ValueError("凭证无效")
    s = await db.get_steward_by_key_id(row["id"])
    if not s or not s["enrolled"]:
        raise ValueError("请先 steward_ops enroll 登记管理员")

    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        await energy.soft_regen(conn, s["id"])
        ailments = await health.list_ailments(conn, s["id"])
        open_incidents = await events.list_open_incidents_on(conn, s["id"])
        extra = await market_mod._market_extra(conn, s["id"])
        cap = market_mod.market_list_cap(extra)
        used = (await (await conn.execute(
            "SELECT COUNT(*) FROM market_listings WHERE seller_id=? AND buyer_id IS NULL",
            (s["id"],),
        )).fetchone())[0]
        voyage = await (await conn.execute(
            """
            SELECT route, returns_at, status FROM voyages
            WHERE steward_id=? AND status IN ('sailing','hailed','fish_encounter')
            """,
            (s["id"],),
        )).fetchone()
        ut = await (await conn.execute(
            """
            SELECT shadow_rep, access, jail_state, jail_until, k_room, busted_count
            FROM steward_undertide WHERE steward_id=?
            """,
            (s["id"],),
        )).fetchone()
        await conn.commit()

    gifts = await db.list_received_gifts(s["id"], 8)
    pulse = await events.public_pulse_snapshot()

    s = await db.get_steward_by_id(s["id"]) or s
    ranked = ranks.attach_level(s)
    parcels = await db.get_parcels(s["id"])
    stock = await db.get_satchel(s["id"])

    parcel_views = []
    for p in parcels:
        gh = bool(p.get("greenhouse"))
        left = land.clear_left(p)
        if left > 0:
            parcel_views.append({
                "slot": p["slot"],
                "greenhouse": gh,
                "state": "clearing",
                "crop": None,
                "emoji": "🚧",
                "name": "开垦中",
                "detail": farming.format_grow_eta(left),
                "label": f"开垦中（{farming.format_grow_eta(left)}）",
            })
        elif not p.get("crop"):
            parcel_views.append({
                "slot": p["slot"],
                "greenhouse": gh,
                "state": "fallow",
                "crop": None,
                "emoji": "🟫",
                "name": "休耕",
                "detail": "可播种",
                "label": "休耕",
            })
        else:
            meta = CROPS.get(p["crop"], {"name": p["crop"], "emoji": "🌱"})
            status = farming.parcel_status(p)
            extra_p = farming.parcel_extra(p)
            if status == "过熟":
                state = "overripe"
            elif status == "可收":
                state = "ready"
            elif status == "生长":
                state = "growing"
            else:
                state = "tending"
            _, _, grow_left = farming.grow_progress(p)
            detail = (
                farming.format_grow_eta(grow_left) if grow_left > 0 and state in ("growing", "tending")
                else f"{status}{extra_p}"
            )
            parcel_views.append({
                "slot": p["slot"],
                "greenhouse": gh,
                "state": state,
                "crop": p["crop"],
                "emoji": meta.get("emoji", "🌱"),
                "name": meta["name"],
                "detail": detail,
                "label": f"{meta['emoji']}{meta['name']}（{status}{extra_p}）",
            })

    stock_items = [
        {"item": k, "name": ITEM_NAMES.get(k, k), "qty": q}
        for k, q in sorted(stock.items(), key=lambda x: (-x[1], x[0]))[:48]
    ]

    incident_views = [
        {
            "id": r["id"],
            "label": r.get("label") or r["incident_key"],
            "repair_tickets": r.get("repair_tickets") or 0,
        }
        for r in open_incidents[:8]
    ]

    gift_views = [
        {
            "who": g.get("actor_name") or "某人",
            "kind": "打赏" if g.get("action") == "bar_tip" else "礼物",
            "text": g["text"],
            "created_at": g["created_at"],
        }
        for g in gifts
    ]

    voyage_view = None
    if voyage:
        from .config import VOYAGE_ROUTES
        route = VOYAGE_ROUTES.get(voyage[0], {}).get("label", voyage[0])
        if voyage[2] == "hailed":
            voyage_view = f"{route} · 黑旗截停"
        elif voyage[2] == "fish_encounter":
            voyage_view = f"{route} · 未命名小鱼"
        else:
            left = max(0, voyage[1] - db.now())
            voyage_view = f"{route} · {left // 60} 分后归港"

    now = db.now()
    last_active = int(s.get("last_active_at") or 0)
    online = last_active > 0 and (now - last_active) <= ONLINE_WINDOW
    bar_locked = bar.is_shift_overdue(s)
    ut_row = dict(ut) if ut else {}
    shadow_rep = int(ut_row.get("shadow_rep") or 10)
    ut_access = bool(ut_row.get("access"))
    jail_on = (ut_row.get("jail_state") or "") == "serving"
    jail_left = max(0, int(ut_row.get("jail_until") or 0) - now) if jail_on else 0
    k_room = bool(ut_row.get("k_room"))
    busted_count = int(ut_row.get("busted_count") or 0)
    tier, _, _ = undertide._rep_tier(shadow_rep)

    ailment_views = [
        {
            "name": a.get("name") or a.get("key") or "病症",
            "emoji": a.get("emoji") or "🩹",
            "stage_name": a.get("stage_name") or "",
        }
        for a in ailments
    ]
    status_flags = []
    if bar_locked:
        status_flags.append("考勤锁定")
    if jail_on:
        status_flags.append("潮下服刑")
    if k_room:
        status_flags.append("K室")
    if ailment_views:
        status_flags.append(f"病症 {len(ailment_views)}")

    return {
        "name": s["name"],
        "badge": s["badge"],
        "motto": s["motto"],
        "portrait": s["portrait"],
        "tickets": s["tickets"],
        "level": ranked.get("level", 1),
        "title": ranked.get("title", ""),
        "xp": ranked.get("xp", 0),
        "status": {
            "online": online,
            "label": "在档口" if online else "离线",
            "last_active_at": last_active,
            "bar_locked": bar_locked,
            "flags": status_flags,
            "ailments": ailment_views,
            "undertide": {
                "access": ut_access,
                "jail": jail_on,
                "jail_left": jail_left,
                "k_room": k_room,
                "busted_count": busted_count,
            },
        },
        "shadow": {
            "value": shadow_rep,
            "tier": tier,
            "desc": REP_TIER_DESC.get(tier, ""),
        },
        "meters": {
            "satiety": int(s.get("satiety") or 0),
            "mist_wit": int(s.get("mist_wit") or 0),
            "standing": int(s.get("standing") or 0),
            "shadow_rep": shadow_rep,
            "health": int(s.get("health") or 0),
            "energy": int(s.get("energy") or 0),
            "energy_max": 100,
        },
        "meter_lines": {
            "survival": survival.meter_line(s),
            "health": health.meter_line(s, ailments),
            "energy": energy.meter_line(s, ailments),
            "bar_duty": bar.duty_line(s),
        },
        "climate": world.climate_line(),
        "pulse": pulse,
        "parcels": parcel_views,
        "stock_count": len(stock),
        "stock": stock_items,
        "incidents": incident_views,
        "gifts": gift_views,
        "market": {"used": used, "cap": cap},
        "voyage": voyage_view,
        "flags": {
            "greenhouse": bool(s.get("greenhouse")),
            "hut_built": bool(s.get("hut_built")),
            "barn_built": bool(s.get("barn_built")),
            "eatery_open": bool(s.get("eatery_open")),
            "boat": bool(s.get("boat_key")),
        },
        "updated_at": db.now(),
    }
