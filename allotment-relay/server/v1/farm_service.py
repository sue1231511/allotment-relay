"""份地写操作。

MIGRATION BOUNDARY
------------------
播种 / 打理 / 浇水 / 施肥 / 收获 / 堆肥 / 摇树 / 开垦的数值与副作用仍走 `game._plot_one`（与 MCP `plot_ops` 同一条路径）。
本模块只做：结构化入参、地块预检、稳定错误码、结构化回包。
下一步应把 `_plot_one` 里的 sow/water/gather 抽成 `farm_actions.py`，
让 MCP 解析器和本服务一起调用，而不是让 REST 长期拼命令字符串。
"""
from __future__ import annotations

from typing import Any

from .. import db, farming, game, land as land_mod
from ..catalog import CROPS, resolve_crop_key
from .errors import ApiError, classify
from . import views


def _slot_token(slot: int | str) -> str:
    raw = str(slot).strip()
    if not raw:
        raise ApiError("BAD_REQUEST", "请先点一块地。")
    return raw


async def _prepare(key_id: int) -> dict[str, Any]:
    # 与 game.plot_ops 开场一致：考勤、开垦结算、公共物资。
    from .. import commons, events

    s = await game.require_steward(key_id)
    await events.maybe_world_pulse(s)
    async with db.connect() as conn:
        await commons.maybe_spawn_commons(conn, steward_id=s["id"])
        await db.heal_parcels_for(conn, s["id"])
        finished = await land_mod.settle(conn, s["id"])
        await conn.commit()
    if finished:
        s = await db.get_steward_by_id(s["id"]) or s
    return s


async def _load_home_plot(steward_id: int, slot_token: str) -> dict[str, Any]:
    try:
        slot, orchard, gh = land_mod.parse_slot_ref(slot_token)
    except ValueError as exc:
        raise ApiError("BAD_REQUEST", "没有这块地。", status=404, detail=str(exc)) from exc
    async with db.connect() as conn:
        conn.row_factory = __import__("aiosqlite").Row
        plot = await land_mod.fetch_plot(conn, steward_id, slot, orchard, gh)
    if not plot:
        raise ApiError("BAD_REQUEST", "没有这块地。", status=404)
    return dict(plot)


async def snapshot(api_key: str, steward_id: int) -> dict[str, Any]:
    from .. import play, steward_dashboard

    dash = await steward_dashboard.fetch_dashboard(api_key)
    farm = await views.farm_view(api_key, steward_id)
    return {
        "ok": True,
        "me": views.player_view(dash, enrolled=True),
        "farm": farm,
        "world": views.world_view(play.climate_bits()),
    }


async def buy(api_key: str, key_id: int, crop: str, qty: int = 1) -> dict[str, Any]:
    try:
        s = await _prepare(key_id)
    except ValueError as exc:
        raise classify(exc) from exc
    crop_key = resolve_crop_key((crop or "").strip())
    if not crop_key:
        raise ApiError("BAD_REQUEST", "没有这种作物。")
    n = max(1, min(24, int(qty or 1)))
    sow_name = (CROPS[crop_key].get("aliases") or [CROPS[crop_key]["name"]])[0]
    try:
        narrative = await game._plot_one(s, f"buy {n} {sow_name}")
    except ValueError as exc:
        raise classify(exc) from exc
    snap = await snapshot(api_key, s["id"])
    snap["event"] = {
        "title": "买种",
        "narrative": views_human(narrative),
        "kind": "farm",
    }
    return snap


_EXPAND_CMD = {
    "home": ("买地 确认", "开垦"),
    "plots": ("买地 确认", "开垦"),
    "orchard": ("买园 确认", "买园"),
    "greenhouse": ("买棚 确认", "买棚"),
}


async def expand(api_key: str, key_id: int, kind: str = "home") -> dict[str, Any]:
    try:
        s = await _prepare(key_id)
    except ValueError as exc:
        raise classify(exc) from exc
    key = (kind or "home").strip().lower()
    if key in ("plot", "plots", "yard", "land"):
        key = "home"
    if key in ("shed", "棚", "温室"):
        key = "greenhouse"
    if key in ("园", "grove", "tree"):
        key = "orchard"
    pair = _EXPAND_CMD.get(key)
    if not pair:
        raise ApiError("BAD_REQUEST", "没有这一类地。切菜地、果园或温室再点草地。")
    cmd, title = pair
    try:
        narrative = await game._plot_one(s, cmd)
    except ValueError as exc:
        raise classify(exc) from exc
    snap = await snapshot(api_key, s["id"])
    snap["event"] = {
        "title": title,
        "narrative": views_human(narrative),
        "kind": "farm",
    }
    return snap


async def sow(api_key: str, key_id: int, slot: int | str, crop: str) -> dict[str, Any]:
    try:
        s = await _prepare(key_id)
    except ValueError as exc:
        raise classify(exc) from exc
    token = _slot_token(slot)
    crop_key = resolve_crop_key((crop or "").strip())
    if not crop_key:
        raise ApiError("BAD_REQUEST", "没有这种作物。")
    sow_name = (CROPS[crop_key].get("aliases") or [CROPS[crop_key]["name"]])[0]
    plot = await _load_home_plot(s["id"], token)
    try:
        land_mod.assert_ready(plot)
    except ValueError as exc:
        raise classify(exc) from exc
    if plot.get("crop"):
        raise ApiError("PLOT_BUSY", "这块地已经种着东西。", status=409)
    seed = f"seed_{crop_key}"
    stock = await db.get_satchel(s["id"])
    if int(stock.get(seed) or 0) <= 0:
        raise ApiError("ITEM_REQUIRED", f"行囊里没有{CROPS[crop_key]['name']}种。", status=409)

    # MIGRATION BOUNDARY: 拼给 _plot_one 的命令不得泄漏到客户端。
    try:
        narrative = await game._plot_one(s, f"sow {token} {sow_name}")
    except ValueError as exc:
        raise classify(exc) from exc
    snap = await snapshot(api_key, s["id"])
    snap["event"] = {
        "title": "播种",
        "narrative": views_human(narrative),
        "kind": "farm",
    }
    return snap


async def water(api_key: str, key_id: int, slot: int | str) -> dict[str, Any]:
    try:
        s = await _prepare(key_id)
    except ValueError as exc:
        raise classify(exc) from exc
    token = _slot_token(slot)
    plot = await _load_home_plot(s["id"], token)
    try:
        land_mod.assert_ready(plot)
    except ValueError as exc:
        raise classify(exc) from exc
    if not plot.get("crop"):
        raise ApiError("NOT_READY", "这块地还是空的。", status=409)
    if farming.plot_ready(plot) or farming.plot_overripe(plot):
        raise ApiError("NOT_READY", "已经熟了，浇也赶不上。直接收吧。", status=409)
    if plot.get("watered"):
        raise ApiError("ALREADY_DONE", "这一茬已经浇过水了。", status=409)

    try:
        narrative = await game._plot_one(s, f"浇水 {token}")
    except ValueError as exc:
        raise classify(exc) from exc
    snap = await snapshot(api_key, s["id"])
    snap["event"] = {
        "title": "浇水",
        "narrative": views_human(narrative),
        "kind": "farm",
    }
    return snap


async def tend(api_key: str, key_id: int, slot: int | str) -> dict[str, Any]:
    try:
        s = await _prepare(key_id)
    except ValueError as exc:
        raise classify(exc) from exc
    token = _slot_token(slot)
    plot = await _load_home_plot(s["id"], token)
    try:
        land_mod.assert_ready(plot)
    except ValueError as exc:
        raise classify(exc) from exc
    if not plot.get("crop"):
        raise ApiError("NOT_READY", "这块地还是空的。", status=409)
    if farming.plot_ready(plot) or farming.plot_overripe(plot):
        raise ApiError("NOT_READY", "已经熟了，直接收吧。", status=409)
    if plot.get("tended"):
        raise ApiError("ALREADY_DONE", "这一茬已经打理过了。", status=409)

    try:
        narrative = await game._plot_one(s, f"tend {token}")
    except ValueError as exc:
        raise classify(exc) from exc
    snap = await snapshot(api_key, s["id"])
    snap["event"] = {
        "title": "打理",
        "narrative": views_human(narrative),
        "kind": "farm",
    }
    return snap


async def fertilize(api_key: str, key_id: int, slot: int | str) -> dict[str, Any]:
    try:
        s = await _prepare(key_id)
    except ValueError as exc:
        raise classify(exc) from exc
    token = _slot_token(slot)
    plot = await _load_home_plot(s["id"], token)
    try:
        land_mod.assert_ready(plot)
    except ValueError as exc:
        raise classify(exc) from exc
    if not plot.get("crop"):
        raise ApiError("NOT_READY", "这块地还是空的。", status=409)
    if farming.plot_ready(plot) or farming.plot_overripe(plot):
        raise ApiError("NOT_READY", "已经熟了，肥料留给下一茬。", status=409)
    if plot.get("fertilized"):
        raise ApiError("ALREADY_DONE", "这一茬已经施过肥了。", status=409)

    try:
        narrative = await game._plot_one(s, f"施肥 {token}")
    except ValueError as exc:
        raise classify(exc) from exc
    snap = await snapshot(api_key, s["id"])
    snap["event"] = {
        "title": "施肥",
        "narrative": views_human(narrative),
        "kind": "farm",
    }
    return snap


async def compost(api_key: str, key_id: int, slot: int | str) -> dict[str, Any]:
    try:
        s = await _prepare(key_id)
    except ValueError as exc:
        raise classify(exc) from exc
    token = _slot_token(slot)
    plot = await _load_home_plot(s["id"], token)
    try:
        land_mod.assert_ready(plot)
    except ValueError as exc:
        raise classify(exc) from exc
    if not plot.get("crop"):
        raise ApiError("NOT_READY", "这块地是空的。", status=409)
    if not farming.plot_overripe(plot) and not farming.plot_ready(plot):
        raise ApiError("NOT_READY", "只有过熟或枯了才能进堆肥桶。", status=409)

    try:
        narrative = await game._plot_one(s, f"compost {token}")
    except ValueError as exc:
        raise classify(exc) from exc
    snap = await snapshot(api_key, s["id"])
    snap["event"] = {
        "title": "堆肥",
        "narrative": views_human(narrative),
        "kind": "farm",
    }
    return snap


async def shake(api_key: str, key_id: int, slot: int | str) -> dict[str, Any]:
    try:
        s = await _prepare(key_id)
    except ValueError as exc:
        raise classify(exc) from exc
    token = _slot_token(slot)
    plot = await _load_home_plot(s["id"], token)
    try:
        land_mod.assert_ready(plot)
    except ValueError as exc:
        raise classify(exc) from exc
    if not plot.get("crop"):
        raise ApiError("NOT_READY", "这块地没有能摇的树。", status=409)
    meta = CROPS.get(plot["crop"], {})
    if not meta.get("shake"):
        raise ApiError("NOT_READY", f"{meta.get('name', plot['crop'])} 不能摇，直接收吧。", status=409)
    if not farming.plot_ready(plot):
        raise ApiError("NOT_READY", "还没熟，等等再摇。", status=409)

    try:
        narrative = await game._plot_one(s, f"shake {token}")
    except ValueError as exc:
        raise classify(exc) from exc
    snap = await snapshot(api_key, s["id"])
    snap["event"] = {
        "title": "摇一摇",
        "narrative": views_human(narrative),
        "kind": "farm",
    }
    return snap


async def harvest(api_key: str, key_id: int, slot: int | str) -> dict[str, Any]:
    try:
        s = await _prepare(key_id)
    except ValueError as exc:
        raise classify(exc) from exc
    token = _slot_token(slot)
    plot = await _load_home_plot(s["id"], token)
    try:
        land_mod.assert_ready(plot)
    except ValueError as exc:
        raise classify(exc) from exc
    if not plot.get("crop"):
        raise ApiError("NOT_READY", "这块地是空的，没有能收的。", status=409)
    if not farming.plot_ready(plot) and not farming.plot_overripe(plot):
        _, _, left = farming.grow_progress(plot)
        eta = farming.format_grow_eta(left) or "再等一会儿"
        raise ApiError("NOT_READY", f"还没熟，还需 {eta}。", status=409)

    try:
        narrative = await game._plot_one(s, f"gather {token}")
    except ValueError as exc:
        raise classify(exc) from exc
    snap = await snapshot(api_key, s["id"])
    snap["event"] = {
        "title": "收获",
        "narrative": views_human(narrative),
        "kind": "farm",
    }
    return snap


def views_human(text: str) -> str:
    from .errors import humanize

    return humanize(text)


async def event_snapshot(steward_id: int) -> dict[str, Any]:
    """Read stored events only: no attendance, random roll, or settlement on refresh."""
    import aiosqlite
    from ..catalog import ITEM_NAMES

    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        owner = await (await conn.execute("SELECT tickets FROM stewards WHERE id=?", (steward_id,))).fetchone()
        tickets = int(owner["tickets"] or 0)
        stock_rows = await (await conn.execute("SELECT item, quantity FROM satchel WHERE steward_id=?", (steward_id,))).fetchall()
        stock = {r["item"]: r["quantity"] for r in stock_rows}
        rows = await (await conn.execute(
            "SELECT * FROM steward_incidents WHERE steward_id=? AND resolved=0 ORDER BY created_at DESC, id DESC",
            (steward_id,),
        )).fetchall()
        history = await (await conn.execute(
            "SELECT id, text, created_at FROM chronicle WHERE actor_id=? AND action IN ('incident', 'incident_fix', 'farm_event') ORDER BY created_at DESC, id DESC LIMIT 20",
            (steward_id,),
        )).fetchall()
    incidents = []
    for row in rows:
        cost = int(row["repair_tickets"] or 0)
        item = row["repair_item"] or ""
        qty = int(row["repair_qty"] or 1) if item else 0
        incidents.append({
            "id": row["id"], "label": row["label"] or "意外",
            "detail": views_human(row["detail"] or ""),
            "repair_tickets": cost, "repair_item": item,
            "repair_item_label": ITEM_NAMES.get(item, item), "repair_qty": qty,
            "can_pay_tickets": tickets >= cost,
            "can_pay_item": bool(item) and stock.get(item, 0) >= qty,
        })
    return {"ok": True, "tickets": tickets, "incidents": incidents,
            "history": [{"id": r["id"], "text": views_human(r["text"]), "created_at": r["created_at"]} for r in history]}


async def repair_event(api_key: str, key_id: int, incident_id: int, payment: str) -> dict[str, Any]:
    from .. import events

    if incident_id <= 0 or payment not in {"tickets", "item"}:
        raise ApiError("BAD_REQUEST", "请选择事件和处理方式。")
    try:
        # Same ownership, costs, repair effects and resolved flag as MCP.
        narrative = await events.incident_ops(key_id, f"repair {incident_id}" + (" item" if payment == "item" else ""))
    except ValueError as exc:
        raise ApiError("ACTION_FAILED", str(exc).replace("repair 需要", "处理需要"), status=409) from exc
    s = await db.get_steward_by_key_id(key_id)
    result = await snapshot(api_key, s["id"])
    result.update(await event_snapshot(s["id"]))
    result["event"] = {"title": "田间事件", "narrative": views_human(narrative), "kind": "farm"}
    return result
