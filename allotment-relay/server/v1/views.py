"""把现有 dashboard / climate 收成移动端 JSON。不重算玩法数值。"""
from __future__ import annotations

from typing import Any

from .. import farming, play, steward_dashboard, world
from ..catalog import CROPS


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
        "dues": dash.get("dues") or {},
        "stock": dash.get("stock") or [],
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
        "tide": bits.get("tide") or "",
        "phase": bits.get("phase") or "",
        "phase_code": bits.get("phase_code") or "",
        "season": bits.get("season") or "",
        "line": bits.get("line") or world.climate_line(),
        "notices": notices or [],
        "pulse": pulse,
    }


def farm_parcel(view: dict[str, Any], raw: dict[str, Any] | None = None) -> dict[str, Any]:
    crop_key = view.get("crop")
    meta = CROPS.get(crop_key or "") or {}
    return {
        "slot": view.get("slot"),
        "token": view.get("token"),
        "orchard": bool(view.get("orchard")),
        "greenhouse": bool(view.get("greenhouse")),
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
        "can_sow": view.get("state") == "fallow",
        "can_water": view.get("state") in ("growing", "tending") and not view.get("watered"),
        "can_harvest": view.get("state") in ("ready", "overripe"),
    }


async def farm_view(api_key: str, steward_id: int | None = None) -> dict[str, Any]:
    dash = await steward_dashboard.fetch_dashboard(api_key)
    raw_rows = await _raw_parcels(steward_id)
    parcels = []
    home = []
    for view in dash.get("parcels") or []:
        raw = raw_rows.get(_parcel_key(view))
        row = farm_parcel(view, raw)
        parcels.append(row)
        if not row["orchard"] and not row["greenhouse"]:
            home.append(row)
    return {
        "home": home,
        "parcels": parcels,
        "land": dash.get("land") or {},
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
