"""船只部件 — 八件：帆 / 舵 / 灯 / 锚 / 缆 / 底泵 / 鱼舱 / 冰舱（§59 第二批 #19）。"""
from __future__ import annotations

from . import db

PARTS = ("sail", "rudder", "lantern", "anchor", "hawser", "bilge", "hold", "ice")
DEFAULT = 100

PART_LABELS: dict[str, str] = {
    "sail": "帆",
    "rudder": "舵",
    "lantern": "灯",
    "anchor": "锚",
    "hawser": "缆",
    "bilge": "泵",
    "hold": "舱",
    "ice": "冰",
}


async def ensure_table(conn) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS steward_boat_parts (
            steward_id INTEGER NOT NULL,
            part_key TEXT NOT NULL,
            durability INTEGER NOT NULL,
            max_dur INTEGER NOT NULL,
            PRIMARY KEY (steward_id, part_key)
        )
        """
    )


async def get_all(conn, steward_id: int) -> dict[str, tuple[int, int]]:
    await ensure_table(conn)
    out: dict[str, tuple[int, int]] = {}
    for p in PARTS:
        cur = await conn.execute(
            "SELECT durability, max_dur FROM steward_boat_parts WHERE steward_id=? AND part_key=?",
            (steward_id, p),
        )
        row = await cur.fetchone()
        if row:
            out[p] = (int(row[0]), int(row[1]))
        else:
            await conn.execute(
                """
                INSERT INTO steward_boat_parts (steward_id, part_key, durability, max_dur)
                VALUES (?, ?, ?, ?)
                """,
                (steward_id, p, DEFAULT, DEFAULT),
            )
            out[p] = (DEFAULT, DEFAULT)
    return out


def _loss_for_part(key: str, route: str, *, storm: bool) -> int:
    base = {"near": 2, "far": 4, "deep": 6}.get(route, 3)
    extra = 0
    if storm:
        extra += 2
        if key == "sail":
            extra += 2
        if key == "bilge":
            extra += 3
        if key == "hawser":
            extra += 1
    if route == "near" and key == "anchor":
        extra += 1
    if route == "deep" and key == "hawser":
        extra += 1
    if key == "lantern" and storm:
        extra += 1
    if key == "hold" and route in ("far", "deep"):
        extra += 1
    if key == "ice" and route == "deep":
        extra += 2
    elif key == "ice" and route == "far":
        extra += 1
    return base + extra


async def wear_voyage(conn, steward_id: int, route: str, *, storm: bool) -> str:
    parts = await get_all(conn, steward_id)
    notes = []
    for key, (dur, mx) in parts.items():
        loss = _loss_for_part(key, route, storm=storm)
        new = max(0, dur - loss)
        await conn.execute(
            "UPDATE steward_boat_parts SET durability=? WHERE steward_id=? AND part_key=?",
            (new, steward_id, key),
        )
        label = PART_LABELS.get(key, key)
        notes.append(f"{label}{new}/{mx}")
    return "部件 " + " · ".join(notes)


def _ratio(parts: dict[str, tuple[int, int]], key: str) -> float:
    d, mx = parts.get(key, (DEFAULT, DEFAULT))
    return d / max(1, mx)


def fail_bonus(parts: dict[str, tuple[int, int]]) -> float:
    extra = 0.0
    sail = _ratio(parts, "sail")
    rudder = _ratio(parts, "rudder")
    if sail < 0.35:
        extra += 0.08
    elif sail < 0.55:
        extra += 0.04
    if rudder < 0.35:
        extra += 0.06
    anchor = _ratio(parts, "anchor")
    if anchor < 0.35:
        extra += 0.05
    elif anchor < 0.55:
        extra += 0.02
    hawser = _ratio(parts, "hawser")
    if hawser < 0.35:
        extra += 0.05
    bilge = _ratio(parts, "bilge")
    if bilge < 0.35:
        extra += 0.04
    lantern = _ratio(parts, "lantern")
    if lantern < 0.35:
        extra += 0.03
    hold = _ratio(parts, "hold")
    if hold < 0.35:
        extra += 0.04
    ice = _ratio(parts, "ice")
    if ice < 0.35:
        extra += 0.03
    return extra


def effective_cargo(cargo: int, parts: dict[str, tuple[int, int]]) -> int:
    hold = _ratio(parts, "hold")
    if hold < 0.35:
        return max(1, cargo - 2)
    if hold < 0.55:
        return max(1, cargo - 1)
    return cargo


def fish_state_for_ice(parts: dict[str, tuple[int, int]], default_state: str) -> str:
    """冰舱低时归港鱼状态偏差。"""
    ice = _ratio(parts, "ice")
    if ice < 0.35:
        return "bruised" if default_state in ("fresh", "firm") else default_state
    if ice < 0.55 and default_state == "fresh":
        return "firm"
    return default_state


async def repair_all(conn, steward_id: int, tickets: int = 22) -> str:
    cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (steward_id,))
    have = int((await cur.fetchone())[0])
    if have < tickets:
        raise ValueError(f"修部件要 {tickets} 票，你只有 {have}")
    nail = await db.take_item(conn, steward_id, "craft_copper_nails", 1)
    cost = tickets if nail else tickets + 6
    if have < cost:
        if nail:
            await db.add_item(conn, steward_id, "craft_copper_nails", 1)
        raise ValueError(f"修部件要 {cost} 票{'（或备铜钉省6票）' if not nail else ''}")
    await conn.execute(
        "UPDATE stewards SET tickets=tickets-? WHERE id=?", (cost, steward_id),
    )
    await conn.execute(
        "UPDATE steward_boat_parts SET durability=max_dur WHERE steward_id=?",
        (steward_id,),
    )
    labels = "/".join(PART_LABELS[k] for k in PARTS)
    return f"{labels}回满（-{cost} 票{'·用钉' if nail else ''}）"


async def status_line(conn, steward_id: int) -> str:
    parts = await get_all(conn, steward_id)
    bits = []
    for key in PARTS:
        d, mx = parts[key]
        bits.append(f"{PART_LABELS[key]}{d}/{mx}")
    return "船部件 " + " · ".join(bits) + " · voyage_ops 部件 修"


def compact_note(parts: dict[str, tuple[int, int]]) -> str:
    """岛端一行简写：帆/舵/灯/锚/缆/泵/舱/冰。"""
    return "".join(
        f"{PART_LABELS[k]}{parts[k][0]}/{parts[k][1]}"
        for k in PARTS
        if k in parts
    )
