"""广场聊天。直接复用 lounge.human_*，不经过 command 解析。"""
from __future__ import annotations

from typing import Any

from .. import events, lounge
from .errors import classify


async def notices() -> list[dict[str, Any]]:
    from .. import db

    items: list[dict[str, Any]] = []
    pulse = await events.public_pulse_snapshot()
    if pulse:
        items.append({
            "id": "pulse",
            "kind": "pulse",
            "title": pulse.get("title") or pulse.get("label") or "岛上动静",
            "body": pulse.get("detail") or pulse.get("line") or pulse.get("text") or "",
        })
    async with db.connect() as conn:
        rows = await (await conn.execute(
            """
            SELECT id, tag, body FROM hui_notices
            WHERE retracted=0
            ORDER BY created_at DESC LIMIT 5
            """
        )).fetchall()
    for row in rows:
        items.append({
            "id": f"hui-{row[0]}",
            "kind": "notice",
            "title": row[1] or "潮生会告示",
            "body": row[2] or "",
        })
    return items


def _message_view(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "who": row.get("who") or row.get("name") or "",
        "kind": row.get("kind") or "",
        "text": row.get("text") or row.get("body") or "",
        "created_at": row.get("created_at"),
        "source": row.get("source") or "",
    }


async def list_messages(api_key: str, *, since: int = 0, limit: int = 30) -> dict[str, Any]:
    try:
        data = await lounge.human_list_messages(
            api_key, since_id=max(0, since), limit=min(50, max(1, limit)),
        )
    except ValueError as exc:
        raise classify(exc) from exc
    msgs = [_message_view(m) for m in (data.get("messages") or [])]
    return {
        "ok": True,
        "messages": msgs,
        "who": data.get("who") or "",
        "human_name": data.get("human_name") or "",
        "in_booth": bool(data.get("in_booth")),
        "booth_label": data.get("booth_label") or "",
        "pinned": lounge.pinned_notice(""),
        "notices": await notices(),
        "cooldown_sec": lounge.LOUNGE_COOLDOWN_SEC,
        "max_len": lounge.LOUNGE_MAX_LEN,
    }


async def post_message(api_key: str, text: str) -> dict[str, Any]:
    try:
        posted = await lounge.human_post(api_key, text)
    except ValueError as exc:
        raise classify(exc) from exc
    listed = await list_messages(api_key)
    listed["posted"] = _message_view(posted)
    return listed
