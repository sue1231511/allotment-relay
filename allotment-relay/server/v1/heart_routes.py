"""人类拆心意卡 / 回一句 / 回礼。"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .. import heart
from .auth import extract_api_key, require_enrolled
from .errors import ApiError

router = APIRouter(prefix="/api/v1/hearts", tags=["island-hearts"])


class IdBody(BaseModel):
    id: int = Field(gt=0)


class ReplyBody(BaseModel):
    id: int = Field(gt=0)
    text: str = Field(min_length=1, max_length=heart.REPLY_MAX)


class ReturnBody(BaseModel):
    emoji: str = Field(min_length=1, max_length=8)
    title: str = Field(min_length=1, max_length=heart.TITLE_MAX)
    scene: str = Field(min_length=1, max_length=heart.SCENE_MAX)
    tickets: int = Field(ge=heart.MIN_TICKETS, le=heart.MAX_TICKETS)
    note: str = Field(default="", max_length=heart.NOTE_MAX)


def _err(exc: Exception) -> JSONResponse:
    if isinstance(exc, ApiError):
        return JSONResponse(exc.as_dict(), status_code=exc.status)
    return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)


@router.get("")
async def list_hearts(request: Request):
    try:
        _, s = await require_enrolled(extract_api_key(request))
        return JSONResponse(await heart.snapshot(s["id"]), headers={"Cache-Control": "no-store"})
    except Exception as exc:
        return _err(exc)


@router.post("/open")
async def open_heart(request: Request, body: IdBody):
    try:
        _, s = await require_enrolled(extract_api_key(request))
        card = await heart.open_card(s["id"], body.id)
        snap = await heart.snapshot(s["id"])
        snap["card"] = card
        return JSONResponse(snap, headers={"Cache-Control": "no-store"})
    except Exception as exc:
        return _err(exc)


@router.post("/keep")
async def keep_heart(request: Request, body: IdBody):
    try:
        _, s = await require_enrolled(extract_api_key(request))
        card = await heart.keep_card(s["id"], body.id)
        snap = await heart.snapshot(s["id"])
        snap["card"] = card
        return JSONResponse(snap, headers={"Cache-Control": "no-store"})
    except Exception as exc:
        return _err(exc)


@router.post("/reply")
async def reply_heart(request: Request, body: ReplyBody):
    try:
        _, s = await require_enrolled(extract_api_key(request))
        card = await heart.reply_card(s["id"], body.id, body.text)
        snap = await heart.snapshot(s["id"])
        snap["card"] = card
        return JSONResponse(snap, headers={"Cache-Control": "no-store"})
    except Exception as exc:
        return _err(exc)


@router.post("/return")
async def return_heart(request: Request, body: ReturnBody):
    try:
        _, s = await require_enrolled(extract_api_key(request))
        card = await heart.send_as_human(
            s["id"],
            emoji=body.emoji,
            title=body.title,
            scene=body.scene,
            tickets=body.tickets,
            note=body.note,
        )
        snap = await heart.snapshot(s["id"])
        snap["card"] = card
        return JSONResponse(snap, headers={"Cache-Control": "no-store"})
    except Exception as exc:
        return _err(exc)
