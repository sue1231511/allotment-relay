"""会话与档案。登记走现有 steward_ops，不另做一套身份。"""
from __future__ import annotations

from typing import Any

from .. import db, events, play, steward_dashboard
from . import lounge_service, views
from .auth import key_row
from .errors import ApiError, classify


async def open_session(api_key: str, name: str = "") -> dict[str, Any]:
    row = await key_row(api_key)
    s = await db.get_steward_by_key_id(int(row["id"]))
    enrolled = bool(s and s.get("enrolled"))
    welcome = ""
    if not enrolled and name.strip():
        from .. import mcp_dispatch as mux

        try:
            welcome = await mux._call_ops(mux.steward_ops, int(row["id"]), f"enroll {name.strip()}")
        except ValueError as exc:
            raise classify(exc) from exc
        enrolled = True
    return await full_state(api_key, welcome=welcome)


async def full_state(api_key: str, *, welcome: str = "") -> dict[str, Any]:
    row = await key_row(api_key)
    s = await db.get_steward_by_key_id(int(row["id"]))
    enrolled = bool(s and s.get("enrolled"))
    dash = None
    farm = {"home": [], "parcels": [], "land": {}}
    if enrolled:
        try:
            dash = await steward_dashboard.fetch_dashboard(api_key)
            farm = await views.farm_view(api_key, int(s["id"]))
        except ValueError as exc:
            raise classify(exc) from exc
    pulse = await events.public_pulse_snapshot()
    notice_list = await lounge_service.notices()
    body: dict[str, Any] = {
        "ok": True,
        "enrolled": enrolled,
        "me": views.player_view(dash, enrolled=enrolled),
        "farm": farm,
        "world": views.world_view(play.climate_bits(), notices=notice_list, pulse=pulse),
        "shore": None,
    }
    if enrolled:
        from . import shore_service

        body["shore"] = await shore_service._gear_view(int(s["id"]))
    if welcome:
        body["event"] = {
            "title": "登岛",
            "narrative": views.player_view(dash, enrolled=True).get("name") and welcome.split("\n", 1)[0] or welcome,
            "kind": "session",
        }
        from .errors import humanize
        body["event"]["narrative"] = humanize(welcome)
    return body


async def me(api_key: str) -> dict[str, Any]:
    state = await full_state(api_key)
    if not state["enrolled"]:
        raise ApiError("NOT_ENROLLED", "还没起岛上的名字。", status=403)
    return state
