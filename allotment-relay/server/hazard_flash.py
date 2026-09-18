"""瞬时坏事件结案 — trouble 档处置后写入 steward 灾档「近日已结」。"""
from __future__ import annotations

from . import bad_event_tiers as tiers_mod


async def on_trouble_cleared(
    conn,
    steward_id: int,
    system_key: str,
    summary: str,
    ref: str,
    *,
    tier: str | None = None,
) -> None:
    await tiers_mod.record_flash(
        conn,
        steward_id,
        system_key,
        tier or tiers_mod.TIER_LIGHT,
        summary,
        ref_key=f"flash:{ref}",
    )
