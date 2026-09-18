"""潮下麻烦档：井蚀过高时井壁裂隙，三选一（清井 / 绑索 / 硬闯）。"""
from __future__ import annotations

import json
from typing import Any

from . import db, well_corrosion as wc_mod

HAZARD_CRACK = "crack"
TRIGGER_AT = wc_mod.WARN_AT


async def ensure_columns(conn) -> None:
    for ddl in (
        "ALTER TABLE steward_undertide ADD COLUMN well_hazard TEXT",
        "ALTER TABLE steward_undertide ADD COLUMN well_hazard_json TEXT",
    ):
        try:
            await conn.execute(ddl)
        except Exception:
            pass


async def get_hazard(conn, steward_id: int) -> str:
    await ensure_columns(conn)
    cur = await conn.execute(
        "SELECT well_hazard FROM steward_undertide WHERE steward_id=?",
        (steward_id,),
    )
    row = await cur.fetchone()
    return (row[0] or "") if row else ""


async def maybe_after_bump(conn, steward_id: int, *, old: int, new: int) -> str | None:
    if new < TRIGGER_AT or old >= TRIGGER_AT:
        return None
    if await get_hazard(conn, steward_id):
        return None
    await ensure_columns(conn)
    payload = {"corrosion": new}
    await conn.execute(
        """
        UPDATE steward_undertide SET well_hazard=?, well_hazard_json=?
        WHERE steward_id=?
        """,
        (HAZARD_CRACK, json.dumps(payload, ensure_ascii=False), steward_id),
    )
    from . import bad_event_tiers as tiers_mod

    tier = tiers_mod.TIER_FATAL if new >= wc_mod.MAX_CORROSION - 5 else tiers_mod.TIER_HEAVY
    await tiers_mod.record_open(
        conn,
        steward_id,
        "undertide",
        tier,
        f"井壁裂（蚀 {new}）",
        ref_key="well_crack",
    )
    return tiers_mod.tag(
        tier,
        f"井壁裂了道缝（蚀 {new}/{wc_mod.MAX_CORROSION}）！"
        " undertide_ops 井险 清井|绑索|硬闯"
        "（清井=20票大维护；绑索=漂绳×1或10票；硬闯=不花钱但蚀度+6、可能扭伤）"
        + tiers_mod.repair_hint("undertide", tier=tier),
    )


async def assert_not_blocked(conn, steward_id: int) -> None:
    if await get_hazard(conn, steward_id) == HAZARD_CRACK:
        raise ValueError(
            "井壁裂着，先 undertide_ops 井险 清井|绑索|硬闯。"
            "人类 /island 恶猫钱庄对话里也能点。"
        )


def ui_actions(*, tickets: int, stock: dict[str, int]) -> list[dict[str, Any]]:
    twine = int(stock.get("drift_twine") or 0)
    return [
        {
            "action": "清井",
            "label": "清井",
            "hint": "20 票",
            "can": tickets >= 20,
            "disabled_reason": "票不够 20",
        },
        {
            "action": "绑索",
            "label": "绑索",
            "hint": "漂绳×1 或 10 票",
            "can": twine >= 1 or tickets >= 10,
            "disabled_reason": "缺漂绳且票不够 10",
        },
        {"action": "硬闯", "label": "硬闯", "hint": "蚀度+6", "can": True, "disabled_reason": ""},
    ]


async def resolve(conn, steward: dict[str, Any], choice: str) -> str:
    if await get_hazard(conn, steward["id"]) != HAZARD_CRACK:
        raise ValueError("没有井裂待决。undertide_ops status 看井蚀")
    ch = (choice or "").strip().lower()
    norm = None
    for zh, en in (("清井", "clean"), ("绑索", "rope"), ("硬闯", "force")):
        if ch in (zh, en):
            norm = zh
            break
    if not norm:
        raise ValueError("井险处置：清井 · 绑索 · 硬闯（例 undertide_ops 井险 清井）")
    sid = steward["id"]

    if norm == "清井":
        msg = await wc_mod.clean(conn, sid, tickets=20)
        await _clear(conn, sid, flash_summary="潮下井裂：清井处置，井险已结。")
        return msg

    if norm == "绑索":
        paid = ""
        if not await db.take_item(conn, sid, "drift_twine", 1):
            cost = 10
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (sid,))
            have = int((await cur.fetchone())[0])
            if have < cost:
                raise ValueError(f"绑索要漂绳×1 或 {cost} 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (cost, sid),
            )
            paid = f"-{cost} 票"
        else:
            from .catalog import item_label

            paid = f"{item_label('drift_twine')}×1"
        await conn.execute(
            "UPDATE steward_undertide SET well_corrosion=MAX(0, well_corrosion-12) WHERE steward_id=?",
            (sid,),
        )
        await _clear(conn, sid, flash_summary="潮下井裂：绑索加固，井险已结。")
        lvl = await wc_mod.get_level(conn, sid)
        return f"绑索加固，裂口勒住了。（{paid}，井蚀 {lvl}/{wc_mod.MAX_CORROSION}）"

    await conn.execute(
        "UPDATE steward_undertide SET well_corrosion=MIN(?, well_corrosion+6) WHERE steward_id=?",
        (wc_mod.MAX_CORROSION, sid),
    )
    await _clear(conn, sid, flash_summary="潮下井裂：硬闯过关，井险已结。")
    from . import health

    ill = await health.maybe_roll_ailment(
        conn, sid, "undertide", chance=0.32, source="well_crack",
    )
    lvl = await wc_mod.get_level(conn, sid)
    msg = f"硬闯过去了，井壁又啃掉一层（井蚀 {lvl}/{wc_mod.MAX_CORROSION}）。"
    if ill:
        msg += f"\n{ill}\n→ undertide_ops medic 或 visit_ops clinic"
    return msg


async def _clear(
    conn,
    steward_id: int,
    *,
    flash_summary: str = "",
) -> None:
    await ensure_columns(conn)
    await conn.execute(
        """
        UPDATE steward_undertide SET well_hazard=NULL, well_hazard_json=NULL
        WHERE steward_id=?
        """,
        (steward_id,),
    )
    from . import bad_event_tiers as tiers_mod

    await tiers_mod.record_resolved(conn, steward_id, "undertide", ref_key="well_crack")
    if flash_summary:
        from . import hazard_flash as hf

        await hf.on_trouble_cleared(
            conn, steward_id, "undertide", flash_summary, "well_crack",
        )


async def player_snippet(conn, steward: dict[str, Any]) -> dict[str, Any]:
    """给 /island 钱庄对话附加井裂按钮。"""
    hazard = await get_hazard(conn, steward["id"])
    lvl = await wc_mod.get_level(conn, steward["id"])
    stock = await db.get_satchel(steward["id"])
    tickets = int(steward.get("tickets") or 0)
    return {
        "corrosion": lvl,
        "max_corrosion": wc_mod.MAX_CORROSION,
        "hazard": hazard,
        "crack_actions": ui_actions(tickets=tickets, stock=stock) if hazard == HAZARD_CRACK else [],
        "line": (
            f"井壁裂着，先处置再下井（蚀 {lvl}/{wc_mod.MAX_CORROSION}）。"
            if hazard == HAZARD_CRACK
            else f"井蚀 {lvl}/{wc_mod.MAX_CORROSION}"
        ),
    }
