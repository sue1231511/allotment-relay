"""土壤肥力与轮作 — 玩法扩展第二批。"""
from __future__ import annotations

from typing import Any

from .catalog import CROPS

DEFAULT_FERTILITY = 70
MIN_FERTILITY = 15
MAX_FERTILITY = 100

# 连作同一作物扣肥；换「族」轮作回肥
FAMILY_ORDER = ("legume", "grain", "root", "leaf", "berry", "fruit", "seasoning", "fiber", "sea", "tropic", "herb")


def crop_family(crop_key: str) -> str:
    tags = tuple(CROPS.get(crop_key, {}).get("tags") or ())
    for fam in FAMILY_ORDER:
        if fam in tags:
            return fam
    return tags[0] if tags else "other"


def fertility_label(value: int) -> str:
    v = int(value or DEFAULT_FERTILITY)
    if v >= 85:
        return "肥"
    if v >= 55:
        return "平"
    if v >= 35:
        return "瘦"
    return "瘠"


def grow_target_mult(fertility: int) -> float:
    f = int(fertility or DEFAULT_FERTILITY)
    if f >= 88:
        return 0.94
    if f >= 70:
        return 1.0
    if f >= 45:
        return 1.06
    return 1.14


async def read_fertility(conn, plot: dict[str, Any]) -> int:
    cur = await conn.execute(
        "SELECT COALESCE(soil_fertility, ?) FROM parcels WHERE id=?",
        (DEFAULT_FERTILITY, plot["id"]),
    )
    row = await cur.fetchone()
    return int(row[0]) if row else DEFAULT_FERTILITY


async def apply_sow_rotation(
    conn,
    plot: dict[str, Any],
    crop: str,
) -> tuple[int, str]:
    """播种前调整肥力，返回 (新肥力, 说明)。"""
    fid = plot["id"]
    cur = await conn.execute(
        "SELECT COALESCE(soil_fertility, ?), last_crop FROM parcels WHERE id=?",
        (DEFAULT_FERTILITY, fid),
    )
    fert, last = await cur.fetchone()
    fert = int(fert or DEFAULT_FERTILITY)
    notes: list[str] = []
    if last:
        if last == crop:
            fert = max(MIN_FERTILITY, fert - 14)
            notes.append("连作同种，肥力略降")
        else:
            lf, nf = crop_family(last), crop_family(crop)
            if lf != nf:
                fert = min(MAX_FERTILITY, fert + 8)
                notes.append("轮作换茬，肥力回升")
            else:
                fert = max(MIN_FERTILITY, fert - 6)
                notes.append("同族连种，肥力略耗")
    if crop == "peanut":
        fert = min(MAX_FERTILITY, fert + 4)
        notes.append("花生固氮，土略肥")
    if crop == "soybean":
        fert = min(MAX_FERTILITY, fert + 3)
        notes.append("黄豆固氮，土略肥")
    await conn.execute(
        "UPDATE parcels SET soil_fertility=? WHERE id=?",
        (fert, fid),
    )
    plot["soil_fertility"] = fert
    note = "；".join(notes) if notes else ""
    return fert, note


async def on_harvest_clear(conn, plot: dict[str, Any], crop: str) -> None:
    cur = await conn.execute(
        "SELECT COALESCE(soil_fertility, ?) FROM parcels WHERE id=?",
        (DEFAULT_FERTILITY, plot["id"]),
    )
    fert = int((await cur.fetchone())[0])
    if crop in ("peanut", "soybean"):
        fert = min(MAX_FERTILITY, fert + 6)
    await conn.execute(
        """
        UPDATE parcels SET last_crop=?, soil_fertility=?
        WHERE id=?
        """,
        (crop, fert, plot["id"]),
    )


def status_suffix(plot: dict[str, Any]) -> str:
    if plot.get("greenhouse"):
        return ""
    f = int(plot.get("soil_fertility") or DEFAULT_FERTILITY)
    bits = [f"土{fertility_label(f)}"]
    last = plot.get("last_crop")
    if last and not plot.get("crop"):
        name = CROPS.get(last, {}).get("name", last)
        bits.append(f"上茬{name}")
    return "·" + "·".join(bits)


async def status_report(conn, steward_id: int) -> str:
    cur = await conn.execute(
        """
        SELECT slot, orchard, greenhouse, COALESCE(soil_fertility, ?), last_crop, crop
        FROM parcels WHERE steward_id=? AND COALESCE(greenhouse,0)=0 AND COALESCE(orchard,0)=0
        ORDER BY slot
        """,
        (DEFAULT_FERTILITY, steward_id),
    )
    rows = await cur.fetchall()
    if not rows:
        return "还没有露天份地。"
    lines = ["露天肥力（连作降、轮作升；花生/黄豆固氮；plot_ops 肥力）："]
    for slot, orch, gh, fert, last, crop in rows:
        if crop:
            continue
        last_n = CROPS.get(last or "", {}).get("name", last or "—")
        lines.append(f"  {slot}号 肥{fert}/{MAX_FERTILITY}({fertility_label(int(fert))}) 上茬{last_n}")
    return "\n".join(lines)
