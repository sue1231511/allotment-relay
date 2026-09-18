"""小屋持续消费 — 灯油 / 冷藏 / 防潮（§六·6）。不缴不封房，只降性能。"""
from __future__ import annotations

from typing import Any

from . import db

FEE_LAMP = 4
FEE_COLD = 6
FEE_MOIST = 3
FLAG_PREFIX = "hut_domestic:"


async def ensure_table(conn) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS steward_hut_domestic (
            steward_id INTEGER NOT NULL,
            day_id INTEGER NOT NULL,
            paid_mask INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (steward_id, day_id)
        )
        """
    )


def _day() -> int:
    return db.day_id()


async def _mask(conn, steward_id: int) -> tuple[int, dict[str, bool]]:
    await ensure_table(conn)
    day = _day()
    cur = await conn.execute(
        """
        SELECT paid_mask FROM steward_hut_domestic
        WHERE steward_id=? AND day_id=?
        """,
        (steward_id, day),
    )
    row = await cur.fetchone()
    mask = int(row[0]) if row else 0
    return mask, {
        "lamp": bool(mask & 1),
        "cold": bool(mask & 2),
        "moist": bool(mask & 4),
    }


async def assess(conn, steward_id: int, *, hut_built: bool, hut_level: int, has_fridge: bool) -> dict[str, Any]:
    """返回今日应缴项与是否已付。"""
    mask, paid = await _mask(conn, steward_id)
    fees: list[dict[str, Any]] = []
    if hut_built and hut_level >= 2:
        fees.append({"key": "lamp", "label": "灯油", "cost": FEE_LAMP, "paid": paid["lamp"]})
    if has_fridge:
        fees.append({"key": "cold", "label": "冷藏", "cost": FEE_COLD, "paid": paid["cold"]})
    if hut_built and hut_level >= 3:
        fees.append({"key": "moist", "label": "防潮", "cost": FEE_MOIST, "paid": paid["moist"]})
    due = sum(f["cost"] for f in fees if not f["paid"])
    return {"fees": fees, "due": due, "mask": mask}


async def pay(conn, steward_id: int, amount: int | None = None) -> str:
    from . import hut as hut_mod

    s_row = await conn.execute("SELECT hut_built, hut_level FROM stewards WHERE id=?", (steward_id,))
    row = await s_row.fetchone()
    if not row or not int(row[0]):
        raise ValueError("先 hut_ops build 小屋，再交家维")
    has_fridge = await hut_mod._has_fitting(conn, steward_id, "fridge")
    view = await assess(
        conn, steward_id,
        hut_built=True, hut_level=int(row[1] or 1), has_fridge=has_fridge,
    )
    if view["due"] <= 0:
        return "今日家维已齐，不用交。"
    pay_all = amount is None
    cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (steward_id,))
    tickets = int((await cur.fetchone())[0])
    target = view["due"] if pay_all else min(int(amount), view["due"])
    if tickets < target:
        raise ValueError(f"票不够。今日家维还差 {view['due']} 票（灯油/冷藏/防潮）")
    mask = view["mask"]
    spent = 0
    for f in view["fees"]:
        if f["paid"]:
            continue
        if spent + f["cost"] > target:
            break
        bit = {"lamp": 1, "cold": 2, "moist": 4}[f["key"]]
        mask |= bit
        spent += f["cost"]
    await conn.execute(
        "UPDATE stewards SET tickets=tickets-? WHERE id=?",
        (spent, steward_id),
    )
    day = _day()
    await conn.execute(
        """
        INSERT INTO steward_hut_domestic (steward_id, day_id, paid_mask)
        VALUES (?, ?, ?)
        ON CONFLICT(steward_id, day_id) DO UPDATE SET paid_mask=excluded.paid_mask
        """,
        (steward_id, day, mask),
    )
    left = view["due"] - spent
    if left > 0:
        return f"家维入了 {spent} 票，还剩 {left} 票项未付（不缴只降性能，不封房）。"
    return f"今日家维交清（-{spent} 票）。灯油/冷藏/防潮正常。"


async def status_line(conn, steward_id: int, *, hut_built: bool, hut_level: int, has_fridge: bool) -> str:
    if not hut_built:
        return ""
    view = await assess(conn, steward_id, hut_built=hut_built, hut_level=hut_level, has_fridge=has_fridge)
    if not view["fees"]:
        return ""
    bits = []
    for f in view["fees"]:
        mark = "✓" if f["paid"] else f"{f['cost']}票"
        bits.append(f"{f['label']}{mark}")
    due = view["due"]
    tail = "已齐" if due <= 0 else f"差{due}票 → hut_ops 家维 交"
    return f"家维（今日）：{' · '.join(bits)}（{tail}）"


def sleep_penalty(unpaid: dict[str, bool]) -> int:
    n = 0
    if not unpaid.get("lamp"):
        n += 2
    if not unpaid.get("moist"):
        n += 2
    return n


def fridge_spoil_mult(unpaid: dict[str, bool]) -> float:
    if unpaid.get("cold"):
        return 1.0
    return 0.72


def stove_extra_energy(unpaid: dict[str, bool]) -> int:
    if unpaid.get("lamp"):
        return 0
    return 1
