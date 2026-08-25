"""管家私有状态面板 — 供 /play 上手页用 API key 查询。"""

from __future__ import annotations

import aiosqlite
from typing import Any

from . import bar, db, energy, events, farming, health, land, memory_archive, ranks, survival, world
from . import undertide as undertide_mod
from . import undertide_config as utcfg
from .catalog import CROPS, ITEM_NAMES
from . import market as market_mod
from .config import ONLINE_WINDOW


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
        ut = await undertide_mod._ensure_ut(conn, s["id"])
        memories = await memory_archive.list_memories(conn, s["id"])
        from . import quarry as quarry_mod
        from . import craft as craft_mod
        quarry_view = await quarry_mod.dashboard_view(conn, s["id"])
        craft_view = await craft_mod.dashboard_view(conn, s["id"])
        await conn.commit()

    gifts = await db.list_received_gifts(s["id"], 20)
    pulse = await events.public_pulse_snapshot()

    s = await db.get_steward_by_id(s["id"]) or s
    ranked = ranks.attach_level(s)
    last_active = int(s.get("last_active_at") or 0)
    online = bool(last_active and (db.now() - last_active) <= ONLINE_WINDOW)
    shadow_rep = int(ut.get("shadow_rep") or utcfg.UT_START_SHADOW_REP)
    rep_tier, _, _ = undertide_mod._rep_tier(shadow_rep)
    status_flags: list[str] = []
    if ut.get("jail_state") == "serving":
        status_flags.append("服刑中")
    if ut.get("k_room"):
        status_flags.append("K 室待见")
    if int(ut.get("busted_count") or 0):
        status_flags.append(f"案底 {ut['busted_count']}")
    if not ut.get("access"):
        status_flags.append("未入潮下")
    parcels = await db.get_parcels(s["id"])
    stock = await db.get_satchel(s["id"])
    async with db.connect() as land_conn:
        land_conn.row_factory = aiosqlite.Row
        land_plots = await land.expansion_snapshot(land_conn, s, orchard=False)
        land_orchard = await land.expansion_snapshot(land_conn, s, orchard=True)
        land_shed = await land.expansion_snapshot(land_conn, s, greenhouse=True)

    parcel_views = []
    for p in parcels:
        gh = bool(p.get("greenhouse"))
        orchard = bool(p.get("orchard"))
        if gh:
            token = f"棚{p['slot']}"
        elif orchard:
            token = f"园{p['slot']}"
        else:
            token = str(p["slot"])
        base = {
            "slot": p["slot"],
            "greenhouse": gh,
            "orchard": orchard,
            "token": token,
            "watered": bool(p.get("watered")),
            "fertilized": bool(p.get("fertilized")),
            "tended": bool(p.get("tended")),
            "shake": False,
        }
        left = land.clear_left(p)
        if left > 0:
            parcel_views.append({
                **base,
                "state": "clearing",
                "crop": None,
                "emoji": "🚧",
                "name": "开垦中",
                "detail": farming.format_grow_eta(left),
                "label": f"开垦中（{farming.format_grow_eta(left)}）",
            })
        elif not p.get("crop"):
            parcel_views.append({
                **base,
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
                **base,
                "state": state,
                "crop": p["crop"],
                "emoji": meta.get("emoji", "🌱"),
                "name": meta["name"],
                "detail": detail,
                "label": f"{meta['emoji']}{meta['name']}（{status}{extra_p}）",
                "shake": bool(meta.get("shake")) and state == "ready",
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
            "kind": db.gift_kind_label(str(g.get("action") or "gift")),
            "text": g.get("summary") or g["text"],
            "created_at": g["created_at"],
            "incoming": bool(g.get("incoming", True)),
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

    result = {
        "name": s["name"],
        "badge": s["badge"],
        "motto": s["motto"],
        "portrait": s["portrait"],
        "tickets": s["tickets"],
        "level": ranked.get("level", 1),
        "title": ranked.get("title", ""),
        "xp": ranked.get("xp", 0),
        "island_bond": int(ranked.get("island_bond") or 0),
        "bond_flavor": ranked.get("bond_flavor") or "",
        "meters": {
            "satiety": int(s.get("satiety") or 0),
            "mist_wit": int(s.get("mist_wit") or 0),
            "standing": int(s.get("standing") or 0),
            "health": int(s.get("health") or 0),
            "energy": int(s.get("energy") or 0),
            "energy_max": 100,
            "shadow_rep": shadow_rep,
            "island_bond": int(ranked.get("island_bond") or 0),
        },
        "meter_lines": {
            "survival": survival.meter_line(s),
            "health": health.meter_line(s, ailments),
            "energy": energy.meter_line(s, ailments),
            "bar_duty": bar.duty_line(s),
        },
        "status": {
            "online": online,
            "label": "在线" if online else "离线",
            "last_active_at": last_active,
            "flags": status_flags,
        },
        "shadow": {
            "rep": shadow_rep,
            "tier": rep_tier,
        },
        "climate": world.climate_line(),
        "pulse": pulse,
        "parcels": parcel_views,
        "land": {
            "plots": land_plots,
            "orchard": land_orchard,
            "greenhouse": land_shed,
        },
        "stock_count": len(stock),
        "stock": stock_items,
        "incidents": incident_views,
        "gifts": gift_views,
        "market": {"used": used, "cap": cap},
        "voyage": voyage_view,
        "quarry": quarry_view,
        "craft": craft_view,
        "memories": memories,
        "flags": {
            "greenhouse": bool(s.get("greenhouse")),
            "hut_built": bool(s.get("hut_built")),
            "barn_built": bool(s.get("barn_built")),
            "eatery_open": bool(s.get("eatery_open")),
            "boat": bool(s.get("boat_key")),
        },
        "dues": {
            "tax_arrears": int(s.get("tax_arrears") or 0),
            "upkeep_arrears": int(s.get("upkeep_arrears") or 0),
        },
        "updated_at": db.now(),
    }
    from . import invite as invite_mod
    result["invite"] = await invite_mod.player_view(s)
    return result
