"""手游只应邀和看旁白/进度/失败原因；推进/选项/自定义由 MCP 岛民负责。"""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .. import companion_date
from .auth import extract_api_key, require_enrolled
from .errors import ApiError

router = APIRouter(prefix="/api/v1/dates", tags=["island-dates"])


class ResponseBody(BaseModel):
    date_id: int = Field(gt=0)
    scene: str = Field(max_length=32)
    accept: bool


@router.get("")
async def dates(request: Request):
    try:
        _, s = await require_enrolled(extract_api_key(request))
        result = await companion_date.snapshot(s["id"])
        return JSONResponse(result, headers={"Cache-Control": "no-store"})
    except ApiError as exc:
        return JSONResponse(exc.as_dict(), status_code=exc.status)


@router.post("/respond")
async def respond(request: Request, body: ResponseBody):
    try:
        _, s = await require_enrolled(extract_api_key(request))
        result = await companion_date.respond(s["id"], body.date_id, body.scene, accept=body.accept)
        return JSONResponse(result, headers={"Cache-Control": "no-store"})
    except ApiError as exc:
        return JSONResponse(exc.as_dict(), status_code=exc.status)
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": {"code": "DATE_STATE", "message": str(exc)}}, status_code=409)
