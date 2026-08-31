"""/api/v1 — 移动端结构化接口。凭证走 Authorization / X-Api-Key / POST 体。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import atelier_service, bar_service, eatery_service, farm_service, hall_service, lighthouse_service, lounge_service, market_service, place_service, quarry_service, session_service, shore_service, shop_service, ting_service, workshop_service, writers_service
from . import idempotency
from .auth import extract_api_key, key_row, require_enrolled
from .errors import ApiError


router = APIRouter(prefix="/api/v1", tags=["island-v1"])


class SessionBody(BaseModel):
    api_key: str = ""
    name: str = ""


class SowBody(BaseModel):
    crop: str = Field(default="", min_length=0)
    api_key: str = ""


class ShoreBody(BaseModel):
    mode: str = "net"
    api_key: str = ""


class LoungePostBody(BaseModel):
    text: str = ""
    message: str = ""
    api_key: str = ""


class BuyBody(BaseModel):
    crop: str = ""
    qty: int = 1
    api_key: str = ""


class ExpandBody(BaseModel):
    kind: str = "home"
    api_key: str = ""


class EatBody(BaseModel):
    item: str = ""
    api_key: str = ""


class PayBody(BaseModel):
    kind: str = ""
    api_key: str = ""


class ShopBuyBody(BaseModel):
    item: str = ""
    qty: int = 1
    api_key: str = ""


class VendBody(BaseModel):
    item: str = ""
    qty: int = 1
    api_key: str = ""


class WorkshopActBody(BaseModel):
    kind: str = ""
    target: str = ""
    api_key: str = ""


class QuarryActBody(BaseModel):
    kind: str = ""
    target: str = ""
    api_key: str = ""


class BarActBody(BaseModel):
    kind: str = ""
    target: str = ""
    api_key: str = ""


class TheaterActBody(BaseModel):
    kind: str = ""
    target: str = ""
    api_key: str = ""


class EateryActBody(BaseModel):
    kind: str = ""
    target: str = ""
    api_key: str = ""


class LighthouseActBody(BaseModel):
    kind: str = ""
    target: str = ""
    api_key: str = ""


class MarketActBody(BaseModel):
    kind: str = ""
    target: str = ""
    api_key: str = ""


class TingActBody(BaseModel):
    kind: str = ""
    target: str = ""
    api_key: str = ""


def _error(exc: ApiError) -> JSONResponse:
    return JSONResponse(exc.as_dict(), status_code=exc.status)


def _idem_key(request: Request) -> str:
    return (request.headers.get("idempotency-key") or "").strip()


async def _write_guard(request: Request, api_key: str, route: str) -> tuple[int, dict[str, Any] | None]:
    row, s = await require_enrolled(api_key)
    sid = int(s["id"])
    key = _idem_key(request)
    if key:
        cached = await idempotency.recall(sid, route, key)
        if cached:
            return sid, cached
    else:
        await idempotency.guard_rapid(sid, route)
    return sid, None


def _cached_response(cached: dict[str, Any]) -> JSONResponse:
    return JSONResponse(cached["body"], status_code=int(cached["status"]))


@router.post("/session")
async def open_session(request: Request, body: SessionBody):
    try:
        key = extract_api_key(request, body.api_key)
        return await session_service.open_session(key, body.name)
    except ApiError as exc:
        return _error(exc)


@router.get("/me")
async def get_me(request: Request):
    try:
        key = extract_api_key(request)
        return await session_service.me(key)
    except ApiError as exc:
        return _error(exc)


@router.get("/world")
async def get_world(request: Request):
    try:
        key = extract_api_key(request)
        await key_row(key)
        state = await session_service.full_state(key)
        return {"ok": True, "world": state["world"], "shore": state.get("shore")}
    except ApiError as exc:
        return _error(exc)


@router.get("/farm")
async def get_farm(request: Request):
    try:
        key = extract_api_key(request)
        await require_enrolled(key)
        state = await session_service.full_state(key)
        return {
            "ok": True,
            "me": state["me"],
            "farm": state["farm"],
            "world": state["world"],
        }
    except ApiError as exc:
        return _error(exc)


@router.post("/farm/parcels/{slot}/sow")
async def sow_parcel(slot: str, request: Request, body: SowBody):
    try:
        key = extract_api_key(request, body.api_key)
        sid, cached = await _write_guard(request, key, f"sow:{slot}")
        if cached:
            return _cached_response(cached)
        row, _ = await require_enrolled(key)
        result = await farm_service.sow(key, int(row["id"]), slot, body.crop)
        await idempotency.store(sid, f"sow:{slot}", _idem_key(request), 200, result)
        return result
    except ApiError as exc:
        return _error(exc)


@router.post("/farm/parcels/{slot}/water")
async def water_parcel(slot: str, request: Request, body: SowBody | None = None):
    try:
        key = extract_api_key(request, (body.api_key if body else ""))
        sid, cached = await _write_guard(request, key, f"water:{slot}")
        if cached:
            return _cached_response(cached)
        row, _ = await require_enrolled(key)
        result = await farm_service.water(key, int(row["id"]), slot)
        await idempotency.store(sid, f"water:{slot}", _idem_key(request), 200, result)
        return result
    except ApiError as exc:
        return _error(exc)


@router.post("/farm/parcels/{slot}/harvest")
async def harvest_parcel(slot: str, request: Request, body: SowBody | None = None):
    try:
        key = extract_api_key(request, (body.api_key if body else ""))
        sid, cached = await _write_guard(request, key, f"harvest:{slot}")
        if cached:
            return _cached_response(cached)
        row, _ = await require_enrolled(key)
        result = await farm_service.harvest(key, int(row["id"]), slot)
        await idempotency.store(sid, f"harvest:{slot}", _idem_key(request), 200, result)
        return result
    except ApiError as exc:
        return _error(exc)


@router.post("/farm/parcels/{slot}/tend")
async def tend_parcel(slot: str, request: Request, body: SowBody | None = None):
    try:
        key = extract_api_key(request, (body.api_key if body else ""))
        sid, cached = await _write_guard(request, key, f"tend:{slot}")
        if cached:
            return _cached_response(cached)
        row, _ = await require_enrolled(key)
        result = await farm_service.tend(key, int(row["id"]), slot)
        await idempotency.store(sid, f"tend:{slot}", _idem_key(request), 200, result)
        return result
    except ApiError as exc:
        return _error(exc)


@router.post("/farm/parcels/{slot}/fertilize")
async def fertilize_parcel(slot: str, request: Request, body: SowBody | None = None):
    try:
        key = extract_api_key(request, (body.api_key if body else ""))
        sid, cached = await _write_guard(request, key, f"fertilize:{slot}")
        if cached:
            return _cached_response(cached)
        row, _ = await require_enrolled(key)
        result = await farm_service.fertilize(key, int(row["id"]), slot)
        await idempotency.store(sid, f"fertilize:{slot}", _idem_key(request), 200, result)
        return result
    except ApiError as exc:
        return _error(exc)


@router.post("/farm/parcels/{slot}/compost")
async def compost_parcel(slot: str, request: Request, body: SowBody | None = None):
    try:
        key = extract_api_key(request, (body.api_key if body else ""))
        sid, cached = await _write_guard(request, key, f"compost:{slot}")
        if cached:
            return _cached_response(cached)
        row, _ = await require_enrolled(key)
        result = await farm_service.compost(key, int(row["id"]), slot)
        await idempotency.store(sid, f"compost:{slot}", _idem_key(request), 200, result)
        return result
    except ApiError as exc:
        return _error(exc)


@router.post("/farm/parcels/{slot}/shake")
async def shake_parcel(slot: str, request: Request, body: SowBody | None = None):
    try:
        key = extract_api_key(request, (body.api_key if body else ""))
        sid, cached = await _write_guard(request, key, f"shake:{slot}")
        if cached:
            return _cached_response(cached)
        row, _ = await require_enrolled(key)
        result = await farm_service.shake(key, int(row["id"]), slot)
        await idempotency.store(sid, f"shake:{slot}", _idem_key(request), 200, result)
        return result
    except ApiError as exc:
        return _error(exc)


@router.post("/farm/expand")
async def expand_land(request: Request, body: ExpandBody):
    try:
        key = extract_api_key(request, body.api_key)
        kind = (body.kind or "home").strip() or "home"
        sid, cached = await _write_guard(request, key, f"expand:{kind}")
        if cached:
            return _cached_response(cached)
        row, _ = await require_enrolled(key)
        result = await farm_service.expand(key, int(row["id"]), kind)
        await idempotency.store(sid, f"expand:{kind}", _idem_key(request), 200, result)
        return result
    except ApiError as exc:
        return _error(exc)


@router.post("/farm/buy")
async def buy_seed(request: Request, body: BuyBody):
    try:
        key = extract_api_key(request, body.api_key)
        sid, cached = await _write_guard(request, key, f"buy:{body.crop}:{body.qty}")
        if cached:
            return _cached_response(cached)
        row, _ = await require_enrolled(key)
        result = await farm_service.buy(key, int(row["id"]), body.crop, body.qty)
        await idempotency.store(sid, f"buy:{body.crop}:{body.qty}", _idem_key(request), 200, result)
        return result
    except ApiError as exc:
        return _error(exc)


@router.post("/hut/sleep")
async def hut_sleep(request: Request, body: SowBody | None = None):
    try:
        key = extract_api_key(request, (body.api_key if body else ""))
        sid, cached = await _write_guard(request, key, "hut:sleep")
        if cached:
            return _cached_response(cached)
        row, _ = await require_enrolled(key)
        result = await place_service.sleep(key, int(row["id"]))
        await idempotency.store(sid, "hut:sleep", _idem_key(request), 200, result)
        return result
    except ApiError as exc:
        return _error(exc)


@router.post("/hut/build")
async def hut_build(request: Request, body: SowBody | None = None):
    try:
        key = extract_api_key(request, (body.api_key if body else ""))
        sid, cached = await _write_guard(request, key, "hut:build")
        if cached:
            return _cached_response(cached)
        row, _ = await require_enrolled(key)
        result = await place_service.build_hut(key, int(row["id"]))
        await idempotency.store(sid, "hut:build", _idem_key(request), 200, result)
        return result
    except ApiError as exc:
        return _error(exc)


@router.get("/bar")
async def bar_status(request: Request):
    try:
        key = extract_api_key(request)
        row, _ = await require_enrolled(key)
        return await bar_service.snapshot(key, int(row["id"]))
    except ApiError as exc:
        return _error(exc)


@router.post("/bar/act")
async def bar_act(request: Request, body: BarActBody):
    try:
        key = extract_api_key(request, body.api_key)
        kind = (body.kind or "").strip()
        target = (body.target or "").strip()
        sid, cached = await _write_guard(request, key, f"bar:{kind}:{target}")
        if cached:
            return _cached_response(cached)
        row, _ = await require_enrolled(key)
        result = await bar_service.act(key, int(row["id"]), kind, target)
        await idempotency.store(sid, f"bar:{kind}:{target}", _idem_key(request), 200, result)
        return result
    except ApiError as exc:
        return _error(exc)


@router.get("/writers")
async def writers_status(request: Request):
    try:
        key = extract_api_key(request)
        row, _ = await require_enrolled(key)
        return await writers_service.snapshot(key, int(row["id"]))
    except ApiError as exc:
        return _error(exc)


@router.post("/writers/act")
async def writers_act(request: Request, body: TheaterActBody):
    try:
        key = extract_api_key(request, body.api_key)
        kind = (body.kind or "").strip()
        target = (body.target or "").strip()
        sid, cached = await _write_guard(request, key, f"writers:{kind}:{target}")
        if cached:
            return _cached_response(cached)
        row, _ = await require_enrolled(key)
        result = await writers_service.act(key, int(row["id"]), kind, target)
        await idempotency.store(sid, f"writers:{kind}:{target}", _idem_key(request), 200, result)
        return result
    except ApiError as exc:
        return _error(exc)


@router.get("/atelier")
async def atelier_status(request: Request):
    try:
        key = extract_api_key(request)
        row, _ = await require_enrolled(key)
        return await atelier_service.snapshot(key, int(row["id"]))
    except ApiError as exc:
        return _error(exc)


@router.post("/atelier/act")
async def atelier_act(request: Request, body: TheaterActBody):
    try:
        key = extract_api_key(request, body.api_key)
        kind = (body.kind or "").strip()
        target = (body.target or "").strip()
        sid, cached = await _write_guard(request, key, f"atelier:{kind}:{target}")
        if cached:
            return _cached_response(cached)
        row, _ = await require_enrolled(key)
        result = await atelier_service.act(key, int(row["id"]), kind, target)
        await idempotency.store(sid, f"atelier:{kind}:{target}", _idem_key(request), 200, result)
        return result
    except ApiError as exc:
        return _error(exc)


@router.get("/hall")
async def hall_status(request: Request):
    try:
        key = extract_api_key(request)
        row, _ = await require_enrolled(key)
        return await hall_service.snapshot(key, int(row["id"]))
    except ApiError as exc:
        return _error(exc)


@router.post("/hall/act")
async def hall_act(request: Request, body: TheaterActBody):
    try:
        key = extract_api_key(request, body.api_key)
        kind = (body.kind or "").strip()
        target = (body.target or "").strip()
        sid, cached = await _write_guard(request, key, f"hall:{kind}:{target}")
        if cached:
            return _cached_response(cached)
        row, _ = await require_enrolled(key)
        result = await hall_service.act(key, int(row["id"]), kind, target)
        await idempotency.store(sid, f"hall:{kind}:{target}", _idem_key(request), 200, result)
        return result
    except ApiError as exc:
        return _error(exc)


@router.get("/eatery")
async def eatery_status(request: Request):
    try:
        key = extract_api_key(request)
        row, _ = await require_enrolled(key)
        return await eatery_service.snapshot(key, int(row["id"]))
    except ApiError as exc:
        return _error(exc)


@router.post("/eatery/act")
async def eatery_act(request: Request, body: EateryActBody):
    try:
        key = extract_api_key(request, body.api_key)
        kind = (body.kind or "").strip()
        target = (body.target or "").strip()
        sid, cached = await _write_guard(request, key, f"eatery:{kind}:{target}")
        if cached:
            return _cached_response(cached)
        row, _ = await require_enrolled(key)
        result = await eatery_service.act(key, int(row["id"]), kind, target)
        await idempotency.store(sid, f"eatery:{kind}:{target}", _idem_key(request), 200, result)
        return result
    except ApiError as exc:
        return _error(exc)


@router.get("/market")
async def market_status(request: Request):
    try:
        key = extract_api_key(request)
        row, _ = await require_enrolled(key)
        return await market_service.snapshot(key, int(row["id"]))
    except ApiError as exc:
        return _error(exc)


@router.post("/market/act")
async def market_act(request: Request, body: MarketActBody):
    try:
        key = extract_api_key(request, body.api_key)
        kind = (body.kind or "").strip()
        target = (body.target or "").strip()
        sid, cached = await _write_guard(request, key, f"market:{kind}:{target}")
        if cached:
            return _cached_response(cached)
        row, _ = await require_enrolled(key)
        result = await market_service.act(key, int(row["id"]), kind, target)
        await idempotency.store(sid, f"market:{kind}:{target}", _idem_key(request), 200, result)
        return result
    except ApiError as exc:
        return _error(exc)


@router.get("/ting")
async def ting_status(request: Request):
    try:
        key = extract_api_key(request)
        row, _ = await require_enrolled(key)
        return await ting_service.snapshot(key, int(row["id"]))
    except ApiError as exc:
        return _error(exc)


@router.post("/ting/act")
async def ting_act(request: Request, body: TingActBody):
    try:
        key = extract_api_key(request, body.api_key)
        kind = (body.kind or "").strip()
        target = (body.target or "").strip()
        sid, cached = await _write_guard(request, key, f"ting:{kind}:{target}")
        if cached:
            return _cached_response(cached)
        row, _ = await require_enrolled(key)
        result = await ting_service.act(key, int(row["id"]), kind, target)
        await idempotency.store(sid, f"ting:{kind}:{target}", _idem_key(request), 200, result)
        return result
    except ApiError as exc:
        return _error(exc)


@router.get("/lighthouse")
async def lighthouse_status(request: Request):
    try:
        key = extract_api_key(request)
        row, _ = await require_enrolled(key)
        return await lighthouse_service.snapshot(key, int(row["id"]))
    except ApiError as exc:
        return _error(exc)


@router.post("/lighthouse/act")
async def lighthouse_act(request: Request, body: LighthouseActBody):
    try:
        key = extract_api_key(request, body.api_key)
        kind = (body.kind or "").strip()
        target = (body.target or "").strip()
        sid, cached = await _write_guard(request, key, f"lighthouse:{kind}:{target}")
        if cached:
            return _cached_response(cached)
        row, _ = await require_enrolled(key)
        result = await lighthouse_service.act(key, int(row["id"]), kind, target)
        await idempotency.store(sid, f"lighthouse:{kind}:{target}", _idem_key(request), 200, result)
        return result
    except ApiError as exc:
        return _error(exc)


@router.post("/bar/work")
async def bar_work(request: Request, body: SowBody | None = None):
    try:
        key = extract_api_key(request, (body.api_key if body else ""))
        sid, cached = await _write_guard(request, key, "bar:work")
        if cached:
            return _cached_response(cached)
        row, _ = await require_enrolled(key)
        result = await place_service.work(key, int(row["id"]))
        await idempotency.store(sid, "bar:work", _idem_key(request), 200, result)
        return result
    except ApiError as exc:
        return _error(exc)


@router.post("/kitchen/eat")
async def kitchen_eat(request: Request, body: EatBody):
    try:
        key = extract_api_key(request, body.api_key)
        sid, cached = await _write_guard(request, key, f"eat:{body.item}")
        if cached:
            return _cached_response(cached)
        row, _ = await require_enrolled(key)
        result = await place_service.eat(key, int(row["id"]), body.item)
        await idempotency.store(sid, f"eat:{body.item}", _idem_key(request), 200, result)
        return result
    except ApiError as exc:
        return _error(exc)


@router.post("/tote/vend")
async def tote_vend(request: Request, body: VendBody):
    try:
        key = extract_api_key(request, body.api_key)
        item = (body.item or "").strip()
        sid, cached = await _write_guard(request, key, f"vend:{item}:{body.qty}")
        if cached:
            return _cached_response(cached)
        row, _ = await require_enrolled(key)
        result = await place_service.vend(key, int(row["id"]), item, body.qty)
        await idempotency.store(sid, f"vend:{item}:{body.qty}", _idem_key(request), 200, result)
        return result
    except ApiError as exc:
        return _error(exc)


@router.get("/shop")
async def shop_catalog(request: Request):
    try:
        key = extract_api_key(request)
        row, _ = await require_enrolled(key)
        return await shop_service.catalog(key, int(row["id"]))
    except ApiError as exc:
        return _error(exc)


@router.post("/shop/buy")
async def shop_buy(request: Request, body: ShopBuyBody):
    try:
        key = extract_api_key(request, body.api_key)
        item = (body.item or "").strip()
        sid, cached = await _write_guard(request, key, f"shop:{item}:{body.qty}")
        if cached:
            return _cached_response(cached)
        row, _ = await require_enrolled(key)
        result = await shop_service.buy(key, int(row["id"]), item, body.qty)
        await idempotency.store(sid, f"shop:{item}:{body.qty}", _idem_key(request), 200, result)
        return result
    except ApiError as exc:
        return _error(exc)


@router.get("/workshop")
async def workshop_status(request: Request):
    try:
        key = extract_api_key(request)
        row, _ = await require_enrolled(key)
        return await workshop_service.snapshot(key, int(row["id"]))
    except ApiError as exc:
        return _error(exc)


@router.post("/workshop/act")
async def workshop_act(request: Request, body: WorkshopActBody):
    try:
        key = extract_api_key(request, body.api_key)
        kind = (body.kind or "").strip()
        target = (body.target or "").strip()
        sid, cached = await _write_guard(request, key, f"workshop:{kind}:{target}")
        if cached:
            return _cached_response(cached)
        row, _ = await require_enrolled(key)
        result = await workshop_service.act(key, int(row["id"]), kind, target)
        await idempotency.store(sid, f"workshop:{kind}:{target}", _idem_key(request), 200, result)
        return result
    except ApiError as exc:
        return _error(exc)


@router.get("/quarry")
async def quarry_status(request: Request):
    try:
        key = extract_api_key(request)
        row, _ = await require_enrolled(key)
        return await quarry_service.snapshot(key, int(row["id"]))
    except ApiError as exc:
        return _error(exc)


@router.post("/quarry/act")
async def quarry_act(request: Request, body: QuarryActBody):
    try:
        key = extract_api_key(request, body.api_key)
        kind = (body.kind or "").strip()
        target = (body.target or "").strip()
        sid, cached = await _write_guard(request, key, f"quarry:{kind}:{target}")
        if cached:
            return _cached_response(cached)
        row, _ = await require_enrolled(key)
        result = await quarry_service.act(key, int(row["id"]), kind, target)
        await idempotency.store(sid, f"quarry:{kind}:{target}", _idem_key(request), 200, result)
        return result
    except ApiError as exc:
        return _error(exc)


@router.post("/hui/pay")
async def hui_pay(request: Request, body: PayBody):
    try:
        key = extract_api_key(request, body.api_key)
        sid, cached = await _write_guard(request, key, f"hui:{body.kind}")
        if cached:
            return _cached_response(cached)
        row, _ = await require_enrolled(key)
        result = await place_service.pay(key, int(row["id"]), body.kind)
        await idempotency.store(sid, f"hui:{body.kind}", _idem_key(request), 200, result)
        return result
    except ApiError as exc:
        return _error(exc)


@router.post("/shore/cast")
async def shore_cast(request: Request, body: ShoreBody):
    try:
        key = extract_api_key(request, body.api_key)
        sid, cached = await _write_guard(request, key, f"shore:{body.mode}")
        if cached:
            return _cached_response(cached)
        row, _ = await require_enrolled(key)
        result = await shore_service.cast(key, int(row["id"]), body.mode)
        await idempotency.store(sid, f"shore:{body.mode}", _idem_key(request), 200, result)
        return result
    except ApiError as exc:
        return _error(exc)


@router.get("/lounge/messages")
async def lounge_get(request: Request, since: int = 0, limit: int = 30):
    try:
        key = extract_api_key(request)
        await require_enrolled(key)
        return await lounge_service.list_messages(key, since=since, limit=limit)
    except ApiError as exc:
        return _error(exc)


@router.post("/lounge/messages")
async def lounge_post(request: Request, body: LoungePostBody):
    try:
        key = extract_api_key(request, body.api_key)
        sid, cached = await _write_guard(request, key, "lounge:say")
        if cached:
            return _cached_response(cached)
        text = (body.text or body.message or "").strip()
        if not text:
            raise ApiError("BAD_REQUEST", "先写下要说的话。")
        result = await lounge_service.post_message(key, text)
        await idempotency.store(sid, "lounge:say", _idem_key(request), 200, result)
        return result
    except ApiError as exc:
        return _error(exc)
