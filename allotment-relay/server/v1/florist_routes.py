"""默语花房手游接口；消费与重试结果由花房事务共同落账。"""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .. import db, florist, game
from ..florist_catalog import TEAS
from . import farm_service
from .auth import extract_api_key, require_enrolled
from .errors import ApiError, classify, humanize

router = APIRouter(prefix="/api/v1/florist", tags=["island-florist"])

class FloristActBody(BaseModel):
    kind: str = Field(max_length=24)
    target: str = Field(default="", max_length=80)

def _command(kind: str, target: str) -> str:
    if kind in ("visit", "language", "stamp", "look", "bye"):
        if target:
            raise ApiError("BAD_REQUEST", "这一下不需要另填名字。")
        return {"visit": "visit", "language": "花语", "stamp": "记名", "look": "scan", "bye": "告别"}[kind]
    if kind in ("buy", "dry"):
        if not target or any(c.isspace() for c in target):
            raise ApiError("BAD_REQUEST", "先点要买或做干花的那一枝。")
        return ("买花 " if kind == "buy" else "干花 ") + target
    if kind in ("tea", "pack", "brew") and target in TEAS:
        name = TEAS[target]["name"]
        return "花茶 " + ("冲泡 " + name + "包" if kind == "brew" else name + ("包" if kind == "pack" else ""))
    raise ApiError("BAD_REQUEST", "花房没有这一下。")

async def _snapshot(key: str, s: dict) -> dict:
    async with db.connect() as conn:
        shelf = await florist.player_view(conn, s)
    snap = await farm_service.snapshot(key, s["id"])
    snap["florist"] = shelf
    return snap

@router.get("")
async def status(request: Request):
    try:
        key = extract_api_key(request)
        _, s = await require_enrolled(key)
        return JSONResponse(await _snapshot(key, s), headers={"Cache-Control": "no-store"})
    except ApiError as exc:
        return JSONResponse(exc.as_dict(), status_code=exc.status)

@router.post("/act")
async def act(request: Request, body: FloristActBody):
    try:
        key = extract_api_key(request)
        row, _ = await require_enrolled(key)
        command = _command(body.kind, body.target)
        s = await game.require_steward(row["id"], exempt_duty=True)
        idem = request.headers.get("Idempotency-Key", "").strip()
        if len(idem) > 128:
            raise ApiError("BAD_REQUEST", "请求编号过长。")
        narrative = await florist.command(s["id"], command, idem=idem)
        snap = await _snapshot(key, s)
        narrative = humanize(narrative).replace("默默 help 看真指令。", "点对话框查看选项。")
        snap["event"] = {"kind": "florist", "speaker": "默默", "title": "默语花房", "narrative": narrative}
        return JSONResponse(snap, headers={"Cache-Control": "no-store"})
    except ValueError as exc:
        error = classify(exc)
        return JSONResponse(error.as_dict(), status_code=error.status)
    except ApiError as exc:
        return JSONResponse(exc.as_dict(), status_code=exc.status)
