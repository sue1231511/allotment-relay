"""地块病虫害 — 第二批：选手处置，不是纯扣票。"""
from __future__ import annotations

import random
from typing import Any

from . import db
from .catalog import CROPS

PEST_META = {
    "aphid": {"name": "蚜虫", "emoji": "🐛", "yield_penalty": 0.75},
    "root_rot": {"name": "根腐", "emoji": "🫠", "yield_penalty": 0.5},
    "salt_spot": {"name": "盐斑", "emoji": "🧂", "yield_penalty": 0.85},
    "weed": {"name": "杂草", "emoji": "🌾", "yield_penalty": 0.9},
    "blight": {"name": "菌病", "emoji": "🍄", "yield_penalty": 0.6},
    "gh_leak": {"name": "温室漏风", "emoji": "💨", "yield_penalty": 0.88},
    "sinkhole": {"name": "地陷", "emoji": "🕳️", "yield_penalty": 0.35},
}

SINKHOLE_FILL_TICKETS = 12
SINKHOLE_FILL_COMPOST = 2
FENCE_TICKETS = 8

HAND_CLEAR_CHANCE = 0.55
DRUG_TICKETS = 10
DRUG_CLEAR_CHANCE = 0.82


async def maybe_spawn(conn, plot: dict[str, Any]) -> str | None:
    if not plot.get("crop") or plot.get("pest_key"):
        return None
    if plot.get("greenhouse"):
        base = 0.05
        if random.random() < 0.04:
            key = "gh_leak"
            level = 1
            await conn.execute(
                "UPDATE parcels SET pest_key=?, pest_level=? WHERE id=?",
                (key, level, plot["id"]),
            )
            meta = PEST_META[key]
            return (
                f"{meta['emoji']}{meta['name']}上了{plot.get('slot')}号棚"
                f"（plot_ops 虫害 {plot.get('slot')} 补网|通风|不管）"
            )
    else:
        base = 0.09
    fert = int(plot.get("soil_fertility") or 70)
    if fert < 40:
        base += 0.04
    if random.random() > base:
        return None
    key = random.choice(list(PEST_META.keys()))
    level = random.randint(1, 2)
    await conn.execute(
        "UPDATE parcels SET pest_key=?, pest_level=? WHERE id=?",
        (key, level, plot["id"]),
    )
    meta = PEST_META[key]
    return (
        f"{meta['emoji']}{meta['name']}上了{plot.get('slot')}号地"
        f"（plot_ops 虫害 {plot.get('slot')} 手工|施药|拔除）"
    )


def pest_suffix(plot: dict[str, Any]) -> str:
    key = plot.get("pest_key")
    if not key:
        return ""
    meta = PEST_META.get(key, {"name": key, "emoji": "⚠"})
    lv = int(plot.get("pest_level") or 1)
    return f"·{meta['emoji']}{meta['name']}Lv{lv}"


async def list_pests(conn, steward_id: int) -> list[dict[str, Any]]:
    cur = await conn.execute(
        """
        SELECT id, slot, orchard, greenhouse, crop, pest_key, pest_level
        FROM parcels
        WHERE steward_id=? AND pest_key IS NOT NULL AND pest_key != ''
        ORDER BY greenhouse, orchard, slot
        """,
        (steward_id,),
    )
    return [dict(r) for r in await cur.fetchall()]


async def handle(
    conn,
    steward: dict[str, Any],
    plot: dict[str, Any],
    action: str,
) -> str:
    from . import land as land_mod

    key = plot.get("pest_key")
    if not key:
        raise ValueError(f"{land_mod.slot_label(plot)} 没有虫害")
    meta = PEST_META.get(key, {"name": key})
    label = land_mod.slot_label(plot)
    act = action.lower()
    sid = steward["id"]

    if act in ("status", "查看", ""):
        return f"{label} {meta.get('name', key)} Lv{plot.get('pest_level')}"

    if act in ("手工", "hand", "捉", "捉虫"):
        if random.random() < HAND_CLEAR_CHANCE:
            await _clear_pest(conn, plot["id"])
            return f"{label} 手工除虫，{meta['name']}退了"
        await conn.execute(
            "UPDATE parcels SET pest_level=MIN(3, COALESCE(pest_level,1)+1) WHERE id=?",
            (plot["id"],),
        )
        return f"{label} 没捉干净，{meta['name']}更恼了（可施药或拔除）"

    if act in ("施药", "药", "drug", "spray"):
        cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (sid,))
        have = int((await cur.fetchone())[0])
        if have < DRUG_TICKETS:
            raise ValueError(f"施药要 {DRUG_TICKETS} 票，你只有 {have}")
        await conn.execute(
            "UPDATE stewards SET tickets=tickets-? WHERE id=?",
            (DRUG_TICKETS, sid),
        )
        if random.random() < DRUG_CLEAR_CHANCE:
            await _clear_pest(conn, plot["id"])
            return f"{label} 施药 {meta['name']}清了（-{DRUG_TICKETS} 票）"
        return f"{label} 药力不够，{meta['name']}还在（-{DRUG_TICKETS} 票，可再施或拔除）"

    if key == "gh_leak":
        if act in ("补网", "补", "patch", "net"):
            if not await db.take_item(conn, sid, "drift_twine", 1):
                raise ValueError("补棚网要漂绳×1（赶海/工坊可得）")
            await _clear_pest(conn, plot["id"])
            return f"{label} 补了漏缝，{meta['name']}过了"
        if act in ("通风", "vent", "开"):
            lv = max(0, int(plot.get("pest_level") or 1) - 1)
            if lv <= 0:
                await _clear_pest(conn, plot["id"])
                return f"{label} 通风一夜，{meta['name']}散了（这茬长得略慢）"
            await conn.execute(
                "UPDATE parcels SET pest_level=? WHERE id=?",
                (lv, plot["id"]),
            )
            return f"{label} 开了侧窗，{meta['name']}轻了些"
        if act in ("不管", "wait", "ignore", "观望"):
            if random.random() < 0.35:
                await _clear_pest(conn, plot["id"])
                return f"{label} 风自己停了，{meta['name']}好了"
            await conn.execute(
                "UPDATE parcels SET pest_level=MIN(3, COALESCE(pest_level,1)+1) WHERE id=?",
                (plot["id"],),
            )
            return f"{label} 漏风还在，{meta['name']}更恼（可补网或通风）"

    if act in ("不管", "wait", "ignore", "观望"):
        if random.random() < 0.28:
            await _clear_pest(conn, plot["id"])
            return f"{label} {meta['name']}自己退了"
        await conn.execute(
            "UPDATE parcels SET pest_level=MIN(3, COALESCE(pest_level,1)+1) WHERE id=?",
            (plot["id"],),
        )
        return f"{label} 没管它，{meta['name']}蔓延了（可手工/施药/拔除）"

    if act in ("拔除", "拔", "rip", "burn", "烧"):
        crop = plot.get("crop")
        name = CROPS.get(crop or "", {}).get("name", crop or "作物")
        await conn.execute(
            """
            UPDATE parcels SET crop=NULL, planted_at=NULL, tended=0,
            grow_target=0, grow_pace='', fertilized=0, watered=0,
            harvest_left=0, pest_key=NULL, pest_level=0,
            seed_generation=0
            WHERE id=?
            """,
            (plot["id"],),
        )
        if crop:
            from . import soil as soil_mod
            await soil_mod.on_harvest_clear(conn, plot, crop)
            await conn.execute(
                "UPDATE parcels SET soil_fertility=MAX(15, COALESCE(soil_fertility,70)-5) WHERE id=?",
                (plot["id"],),
            )
        return f"{label} 拔除病株，{name}没了，{meta['name']}也断了"

    raise ValueError(
        "虫害处置：手工 · 施药 · 拔除 · 不管"
        "（温室漏风：补网|通风|不管。例 plot_ops 虫害 1 施药）"
    )


async def _clear_pest(conn, plot_id: int) -> None:
    await conn.execute(
        "UPDATE parcels SET pest_key=NULL, pest_level=0 WHERE id=?",
        (plot_id,),
    )


def slot_ref(plot: dict[str, Any]) -> str:
    from . import land as land_mod

    return land_mod.slot_label(plot)


def ui_actions(
    plot: dict[str, Any],
    *,
    tickets: int,
    stock: dict[str, int],
) -> list[dict[str, Any]]:
    """Human /island 虫害按钮；与 handle() 子命令一致。"""
    key = plot.get("pest_key") or ""
    if key == "gh_leak":
        have_twine = int(stock.get("drift_twine") or 0)
        return [
            {
                "action": "补网",
                "label": "补网",
                "hint": "漂绳×1",
                "can": have_twine >= 1,
                "disabled_reason": "背包缺漂绳×1",
            },
            {"action": "通风", "label": "开侧窗通风", "hint": "", "can": True, "disabled_reason": ""},
            {"action": "不管", "label": "先观望", "hint": "", "can": True, "disabled_reason": ""},
        ]
    return [
        {"action": "手工", "label": "手工除虫", "hint": "", "can": True, "disabled_reason": ""},
        {
            "action": "施药",
            "label": f"施药（{DRUG_TICKETS} 票）",
            "hint": "",
            "can": tickets >= DRUG_TICKETS,
            "disabled_reason": f"票不够（要 {DRUG_TICKETS}）",
        },
        {
            "action": "拔除",
            "label": "拔除病株",
            "hint": "清虫但作物没了",
            "can": True,
            "disabled_reason": "",
        },
        {"action": "不管", "label": "先不管", "hint": "", "can": True, "disabled_reason": ""},
    ]


def pest_row_for_api(
    plot: dict[str, Any],
    *,
    tickets: int,
    stock: dict[str, int],
) -> dict[str, Any]:
    key = plot.get("pest_key") or ""
    meta = PEST_META.get(key, {"name": key, "emoji": "⚠"})
    return {
        "slot": slot_ref(plot),
        "label": slot_ref(plot),
        "crop": plot.get("crop") or "",
        "pest_key": key,
        "pest_name": meta.get("name", key),
        "emoji": meta.get("emoji", "⚠"),
        "level": int(plot.get("pest_level") or 1),
        "actions": ui_actions(plot, tickets=tickets, stock=stock),
    }


def yield_mult(plot: dict[str, Any]) -> float:
    key = plot.get("pest_key")
    if not key:
        return 1.0
    meta = PEST_META.get(key, {})
    base = float(meta.get("yield_penalty") or 0.85)
    lv = int(plot.get("pest_level") or 1)
    return max(0.35, base - 0.05 * (lv - 1))
