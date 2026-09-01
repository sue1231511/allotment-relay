"""把现有 dashboard / climate 收成移动端 JSON。不重算玩法数值。"""
from __future__ import annotations

from typing import Any

from .. import config, farming, play, steward_dashboard, world
from ..catalog import (
    CROPS,
    ITEM_PRICES,
    is_fruit_item,
    is_raw_meat,
    item_vendable,
    suggested_price,
)


def _can_eat(item: str) -> bool:
    key = str(item or "")
    if key.startswith(("dish_", "meal_", "fish_", "dried_")):
        return True
    if key in {"wild_mint", "pickles", "myth_octopus"}:
        return True
    return is_fruit_item(key) or is_raw_meat(key)


def _stock_row(it: dict[str, Any]) -> dict[str, Any]:
    item = str(it.get("item") or "")
    furniture = item.startswith("fit_") or item.startswith("deco_")
    price = int(suggested_price(item) or ITEM_PRICES.get(item, 0) or 0)
    return {
        **it,
        "can_eat": _can_eat(item),
        "can_vend": bool(item_vendable(item) and not furniture),
        "vend_price": price,
    }


def appearance_of(parcel: dict[str, Any]) -> str:
    state = str(parcel.get("state") or "fallow")
    if state in ("fallow", "clearing"):
        return "empty"
    if state in ("ready", "overripe"):
        return "ripe"
    if state == "tending":
        return "seedling"
    return "growing"


def visual_stage(raw_parcel: dict[str, Any] | None, view: dict[str, Any]) -> str:
    """空地 / 幼苗 / 生长中 / 成熟。只用于外观，不改成熟判定。"""
    look = appearance_of(view)
    if look in ("empty", "ripe"):
        return look
    if not raw_parcel or not raw_parcel.get("crop"):
        return "empty"
    elapsed, need, _ = farming.grow_progress(raw_parcel)
    if need <= 0:
        return "growing"
    ratio = elapsed / need
    if ratio < 0.35:
        return "seedling"
    return "growing"


def player_view(dash: dict[str, Any] | None, *, enrolled: bool) -> dict[str, Any]:
    if not dash:
        return {
            "enrolled": enrolled,
            "name": "",
            "level": 1,
            "title": "",
            "tickets": 0,
            "energy": 0,
            "energy_max": 100,
            "island_bond": 0,
            "health": 0,
            "satiety": 0,
            "mist_wit": 0,
            "standing": 0,
            "shadow_rep": 0,
        }
    meters = dash.get("meters") or {}
    return {
        "enrolled": enrolled,
        "name": dash.get("name") or "",
        "level": dash.get("level") or 1,
        "title": dash.get("title") or "",
        "tickets": dash.get("tickets") or 0,
        "energy": meters.get("energy") or 0,
        "energy_max": meters.get("energy_max") or 100,
        "island_bond": dash.get("island_bond") or 0,
        "health": meters.get("health") or 0,
        "satiety": meters.get("satiety") or 0,
        "mist_wit": meters.get("mist_wit") or 0,
        "standing": meters.get("standing") or 0,
        "shadow_rep": meters.get("shadow_rep") or 0,
        "dues": dash.get("dues") or {},
        "duty": (dash.get("meter_lines") or {}).get("bar_duty") or "",
        "flags": dash.get("flags") or {},
        "hut_build_cost": config.HUT_BUILD_COST,
        "stock": [_stock_row(it) for it in (dash.get("stock") or [])],
        "seeds": play.seed_options(dash.get("stock") or []),
    }


def world_view(
    climate: dict[str, Any] | None = None,
    *,
    notices: list[dict[str, Any]] | None = None,
    pulse: dict[str, Any] | None = None,
) -> dict[str, Any]:
    bits = climate or play.climate_bits()
    return {
        "weather": bits.get("weather") or "",
        "weather_code": bits.get("weather_code") or "",
        "tide": bits.get("tide") or "",
        "tide_code": bits.get("tide_code") or "",
        "phase": bits.get("phase") or "",
        "phase_code": bits.get("phase_code") or "",
        "season": bits.get("season") or "",
        "season_left": bits.get("season_left") or "",
        "line": bits.get("line") or world.climate_line(),
        "weather_hint": bits.get("weather_hint") or "",
        "tide_hint": bits.get("tide_hint") or "",
        "phase_hint": bits.get("phase_hint") or "",
        "season_hint": bits.get("season_hint") or "",
        "notices": notices or [],
        "pulse": pulse,
    }


# 家园面板：菜地非果树、果园只果树、温室两种都有。三样起步菜保留界面名。
PANEL_ALIASES = {
    "kale": "白菜",
    "beet": "胡萝卜",
    "fogpea": "番茄",
}


def format_grow_minutes(mins: int) -> str:
    mins = max(0, int(mins or 0))
    if mins < 60:
        return f"{mins}分钟"
    hours, left = divmod(mins, 60)
    if left == 0:
        return f"{hours}小时"
    return f"{hours}小时{left}分"


def remain_seconds(raw: dict[str, Any] | None, view: dict[str, Any]) -> int:
    state = str(view.get("state") or "fallow")
    if state in ("fallow", "clearing", "ready", "overripe"):
        return 0
    if not raw or not raw.get("crop"):
        return 0
    _, _, left = farming.grow_progress(raw)
    return int(left)


def panel_crops(
    stock: list[dict[str, Any]] | None = None, *, kind: str = "home"
) -> list[dict[str, Any]]:
    qty: dict[str, int] = {}
    for item in stock or []:
        qty[str(item.get("item") or "")] = int(item.get("qty") or 0)
    out: list[dict[str, Any]] = []
    for key, meta in CROPS.items():
        is_tree = bool(meta.get("tree"))
        if kind == "home" and is_tree:
            continue
        if kind == "orchard" and not is_tree:
            continue
        aliases = meta.get("aliases") or []
        sow_name = aliases[0] if aliases else (meta.get("name") or key)
        grow_min = int(meta.get("grow") or 0)
        out.append({
            "key": key,
            "label": PANEL_ALIASES.get(key) or (meta.get("name") or sow_name),
            "name": sow_name,
            "full": meta.get("name") or sow_name,
            "emoji": meta.get("emoji") or "🌱",
            "grow_min": grow_min,
            "grow_text": format_grow_minutes(grow_min),
            "yield": int(meta.get("yield") or 0),
            "seed": f"seed_{key}",
            "seed_qty": qty.get(f"seed_{key}", 0),
            "tree": is_tree,
        })
    return out


def farm_parcel(view: dict[str, Any], raw: dict[str, Any] | None = None) -> dict[str, Any]:
    crop_key = view.get("crop")
    meta = CROPS.get(crop_key or "") or {}
    greenhouse = bool(view.get("greenhouse"))
    orchard = bool(view.get("orchard"))
    if greenhouse:
        kind = "greenhouse"
    elif orchard:
        kind = "orchard"
    else:
        kind = "home"
    return {
        "slot": view.get("slot"),
        "token": view.get("token"),
        "kind": kind,
        "orchard": orchard,
        "greenhouse": greenhouse,
        "state": view.get("state"),
        "appearance": visual_stage(raw, view),
        "crop": crop_key,
        "name": view.get("name"),
        "emoji": view.get("emoji") or meta.get("emoji") or "🌱",
        "detail": view.get("detail") or "",
        "label": view.get("label") or "",
        "watered": bool(view.get("watered")),
        "fertilized": bool(view.get("fertilized")),
        "tended": bool(view.get("tended")),
        "remain_sec": remain_seconds(raw, view),
        "can_sow": view.get("state") == "fallow",
        "can_water": view.get("state") in ("growing", "tending") and not view.get("watered"),
        "can_tend": view.get("state") in ("growing", "tending") and not view.get("tended"),
        "can_fertilize": view.get("state") in ("growing", "tending") and not view.get("fertilized"),
        "can_harvest": view.get("state") in ("ready", "overripe"),
        "shake": bool(view.get("shake")),
    }


def _sort_plots(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda p: int(p.get("slot") or 0))


async def farm_view(api_key: str, steward_id: int | None = None) -> dict[str, Any]:
    dash = await steward_dashboard.fetch_dashboard(api_key)
    raw_rows = await _raw_parcels(steward_id)
    parcels = []
    home: list[dict[str, Any]] = []
    orchard: list[dict[str, Any]] = []
    greenhouse: list[dict[str, Any]] = []
    for view in dash.get("parcels") or []:
        raw = raw_rows.get(_parcel_key(view))
        row = farm_parcel(view, raw)
        parcels.append(row)
        if row["kind"] == "greenhouse":
            greenhouse.append(row)
        elif row["kind"] == "orchard":
            orchard.append(row)
        else:
            home.append(row)
    stock = dash.get("stock") or []
    return {
        "home": _sort_plots(home),
        "orchard": _sort_plots(orchard),
        "greenhouse": _sort_plots(greenhouse),
        "parcels": parcels,
        "land": dash.get("land") or {},
        "panel": panel_crops(stock, kind="home"),
        "panels": {
            "home": panel_crops(stock, kind="home"),
            "orchard": panel_crops(stock, kind="orchard"),
            "greenhouse": panel_crops(stock, kind="greenhouse"),
        },
    }


def _parcel_key(view: dict[str, Any]) -> tuple[int, int, int]:
    return (
        int(view.get("slot") or 0),
        1 if view.get("orchard") else 0,
        1 if view.get("greenhouse") else 0,
    )


async def _raw_parcels(steward_id: int | None) -> dict[tuple[int, int, int], dict[str, Any]]:
    if not steward_id:
        return {}
    from .. import db

    parcels = await db.get_parcels(steward_id)
    return {
        (int(p["slot"]), 1 if p.get("orchard") else 0, 1 if p.get("greenhouse") else 0): p
        for p in parcels
    }
