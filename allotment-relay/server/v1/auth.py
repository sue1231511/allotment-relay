"""凭证校验。密钥只走请求头或 POST 体，不写 URL、不写日志。"""
from __future__ import annotations

from typing import Any

from fastapi import Request

from .. import db
from .errors import ApiError


def extract_api_key(request: Request, body_key: str = "") -> str:
    header = (request.headers.get("authorization") or "").strip()
    if header.lower().startswith("bearer "):
        token = header[7:].strip()
        if token:
            return token
    alt = (request.headers.get("x-api-key") or "").strip()
    if alt:
        return alt
    return (body_key or "").strip()


async def key_row(api_key: str) -> dict[str, Any]:
    key = (api_key or "").strip()
    if not key:
        raise ApiError("INVALID_KEY", "请先贴上凭证。", status=401)
    row = await db.get_key_row(key)
    if not row:
        raise ApiError("INVALID_KEY", "凭证无效。回上手页重新贴一次。", status=401)
    return row


async def require_enrolled(api_key: str) -> tuple[dict[str, Any], dict[str, Any]]:
    row = await key_row(api_key)
    s = await db.get_steward_by_key_id(int(row["id"]))
    if not s or not s.get("enrolled"):
        raise ApiError("NOT_ENROLLED", "还没起岛上的名字。", status=403)
    return row, s
