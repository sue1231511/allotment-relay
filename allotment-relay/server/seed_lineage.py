"""留种与种子血统 — 第二批。"""
from __future__ import annotations

import random
from typing import Any

from . import db
from .catalog import CROPS


async def ensure_table(conn) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS steward_seed_lineage (
            steward_id INTEGER NOT NULL,
            crop TEXT NOT NULL,
            generation INTEGER NOT NULL DEFAULT 1,
            bias TEXT NOT NULL DEFAULT '',
            label TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (steward_id, crop)
        )
        """
    )


async def get_lineage(conn, steward_id: int, crop: str) -> dict[str, Any] | None:
    await ensure_table(conn)
    cur = await conn.execute(
        """
        SELECT generation, bias, label FROM steward_seed_lineage
        WHERE steward_id=? AND crop=?
        """,
        (steward_id, crop),
    )
    row = await cur.fetchone()
    if not row:
        return None
    return {"generation": int(row[0]), "bias": row[1] or "", "label": row[2] or ""}


async def save_from_crop(conn, steward: dict[str, Any], crop: str) -> str:
    if crop not in CROPS:
        raise ValueError(f"未知作物 {crop}")
    if CROPS[crop].get("tree"):
        raise ValueError("果树留种走果园收成，不支持 plot_ops 留种")
    item = f"crop_{crop}"
    if not await db.take_item(conn, steward["id"], item, 1):
        raise ValueError(f"行囊缺 1 份{CROPS[crop]['name']}（先 gather）")
    await ensure_table(conn)
    prev = await get_lineage(conn, steward["id"], crop)
    gen = 1 if not prev else int(prev["generation"]) + 1
    roll = random.random()
    if roll < 0.12:
        bias = "twisted"
        note = "退化一档"
    elif roll < 0.28:
        bias = "bugbit"
        note = "虫咬倾向"
    elif roll < 0.55:
        bias = "plain"
        note = "血统稳定"
    elif roll < 0.82:
        bias = "tender"
        note = "鲜嫩倾向"
    else:
        bias = "flavor"
        note = "风味倾向"
    label = f"第{gen}代{CROPS[crop]['name']}种"
    await conn.execute(
        """
        INSERT INTO steward_seed_lineage (steward_id, crop, generation, bias, label)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(steward_id, crop) DO UPDATE SET
            generation=excluded.generation,
            bias=excluded.bias,
            label=excluded.label
        """,
        (steward["id"], crop, gen, bias, label),
    )
    seed = f"seed_{crop}"
    await db.add_item(conn, steward["id"], seed, 1)
    if gen >= 2:
        from . import ledger as ledger_mod
        await ledger_mod.birth_story(
            conn,
            steward["id"],
            seed,
            [
                f"{label}由{steward['name']}留种",
                f"倾向{note}，{ledger_mod.calendar_phrase()}",
            ],
            qty=1,
        )
    chron = f"{steward['name']} 留种 {label}（{note}）"
    await db.add_chronicle("plot", chron, steward["id"], conn=conn)
    return f"留种成功：{label}，{note}。已得{CROPS[crop]['name']}种×1（下次 sow 会带上血统）"


def apply_quality_bias(weights: dict[str, int], plot: dict[str, Any]) -> None:
    bias = plot.get("_seed_bias") or ""
    if not bias:
        return
    if bias in weights:
        weights[bias] = weights.get(bias, 1) + 12
    gen = int(plot.get("seed_generation") or 0)
    if gen >= 3:
        weights["flavor"] = weights.get("flavor", 1) + 4
        weights["bugbit"] = max(1, weights.get("bugbit", 1) - 2)
    if gen >= 5:
        weights["plump"] = weights.get("plump", 1) + 3


async def headline(conn, steward_id: int, limit: int = 2) -> str | None:
    """份地 status 一行摘要。"""
    await ensure_table(conn)
    cur = await conn.execute(
        """
        SELECT crop, generation, label FROM steward_seed_lineage
        WHERE steward_id=? ORDER BY generation DESC LIMIT ?
        """,
        (steward_id, limit),
    )
    rows = await cur.fetchall()
    if not rows:
        return None
    bits = []
    for crop, gen, label in rows:
        name = CROPS.get(crop, {}).get("name", crop)
        bits.append(f"{name}{label or f'第{gen}代'}")
    return "留种血统：" + " · ".join(bits) + "（plot_ops 留种 status 全文）"


async def status(conn, steward_id: int) -> str:
    await ensure_table(conn)
    cur = await conn.execute(
        """
        SELECT crop, generation, bias, label FROM steward_seed_lineage
        WHERE steward_id=? ORDER BY generation DESC, crop
        """,
        (steward_id,),
    )
    rows = await cur.fetchall()
    if not rows:
        return "还没有留种血统。收成后 plot_ops 留种 甘蓝（耗 crop 换 seed 并记代）"
    lines = ["种子血统（留种耗 1 份菜；sow 时写入地块）："]
    for crop, gen, bias, label in rows:
        name = CROPS.get(crop, {}).get("name", crop)
        lines.append(f"  {name} {label} 倾向{bias or '—'}")
    return "\n".join(lines)
