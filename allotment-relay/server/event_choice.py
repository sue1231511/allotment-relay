"""每事件多选 — 点名册里每条至少两路，不全是扣票。

已有入口（帆撕/虫害/惊逃/杂务/塌方等）只登记；缺档的事记待选，steward_ops 灾选 处理。
"""
from __future__ import annotations

import json
from typing import Any

from . import bad_event_tiers as tiers_mod
from . import db

CHOICES: dict[str, dict[str, Any]] = {}
TICKET_COSTS: dict[str, int] = {}


async def ensure_table(conn) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS steward_event_choices (
            steward_id INTEGER NOT NULL REFERENCES stewards(id),
            event_key TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at INTEGER NOT NULL,
            PRIMARY KEY (steward_id, event_key)
        )
        """
    )


def spec_for(event_key: str) -> dict[str, Any] | None:
    return CHOICES.get(event_key)


def cover_ok() -> bool:
    from . import event_catalog

    for ev in event_catalog.NAMED_EVENTS:
        spec = CHOICES.get(ev["key"])
        if not spec or len(spec.get("opts") or ()) < 2:
            return False
    return True


def covered_count() -> int:
    return sum(1 for spec in CHOICES.values() if len(spec.get("opts") or ()) >= 2)


def catalog_line(event_key: str) -> str:
    spec = CHOICES.get(event_key) or {}
    opts = "｜".join(spec.get("opts") or ())
    via = spec.get("via") or "管家档灾选"
    return f"{event_key}：{opts}（{via}）"


async def offer(conn, steward_id: int, event_key: str, **payload: Any) -> str | None:
    spec = CHOICES.get(event_key)
    if not spec:
        return None
    if spec.get("owned"):
        return None
    await ensure_table(conn)
    now = db.now()
    blob = json.dumps(payload, ensure_ascii=False)
    await conn.execute(
        """
        INSERT OR REPLACE INTO steward_event_choices
        (steward_id, event_key, payload_json, created_at)
        VALUES (?,?,?,?)
        """,
        (int(steward_id), event_key, blob, now),
    )
    opts = "｜".join(spec["opts"])
    return f"待选 {spec.get('via') or event_key}：{opts}（上手页管家档点灾选）"
