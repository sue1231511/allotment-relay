"""海域分层 — 第二批：坐钓/撒网可选水层。"""
from __future__ import annotations

from . import db

LAYER_ZONES = {
    "shore": {"shore"},
    "near": {"shore", "near"},
    "far": {"near", "far"},
    "deep": {"deep", "far"},
}

LAYER_ALIASES = {
    "栈桥": "shore",
    "pier": "shore",
    "岸带": "shore",
    "岸": "shore",
    "礁": "near",
    "reef": "near",
    "船尾": "near",
    "stern": "near",
    "近海": "near",
    "浅湾": "near",
    "外海": "far",
    "深槽": "deep",
    "深": "deep",
}


def resolve_layer(token: str) -> str:
    raw = (token or "").strip()
    low = raw.lower()
    if low in LAYER_ZONES:
        return low
    alias = LAYER_ALIASES.get(raw) or LAYER_ALIASES.get(low)
    if alias:
        return alias
    raise ValueError("水层：岸带/栈桥 · 近海/礁/船尾 · 外海 · 深槽（tide_ops 水层 栈桥）")


async def ensure_table(conn) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS steward_sea_layer (
            steward_id INTEGER PRIMARY KEY,
            layer TEXT NOT NULL DEFAULT 'near'
        )
        """
    )


async def get_layer(conn, steward_id: int) -> str:
    await ensure_table(conn)
    cur = await conn.execute(
        "SELECT layer FROM steward_sea_layer WHERE steward_id=?", (steward_id,),
    )
    row = await cur.fetchone()
    if row:
        return str(row[0])
    await conn.execute(
        "INSERT INTO steward_sea_layer (steward_id, layer) VALUES (?, 'near')",
        (steward_id,),
    )
    return "near"


async def set_layer(conn, steward_id: int, layer: str) -> str:
    layer = resolve_layer(layer)
    await ensure_table(conn)
    await conn.execute(
        """
        INSERT INTO steward_sea_layer (steward_id, layer) VALUES (?, ?)
        ON CONFLICT(steward_id) DO UPDATE SET layer=excluded.layer
        """,
        (steward_id, layer),
    )
    labels = {"shore": "岸带", "near": "近海", "far": "外海", "deep": "深槽"}
    return f"下次网/钓按「{labels[layer]}」选种（fish_ecology 海域）"


def zones_for_layer(layer: str) -> set[str]:
    return set(LAYER_ZONES.get(layer, LAYER_ZONES["near"]))
