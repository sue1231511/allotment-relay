"""船改装槽 — 文档六类船上的可选改装（玩法轻量加成）。"""
from __future__ import annotations

from . import db
from .catalog import ITEM_NAMES, resolve_item_key

MAX_MODS = 2

MODS: dict[str, dict] = {
    "copper_bell": {
        "name": "铜雾钟",
        "emoji": "🔔",
        "cost": 35,
        "need": [("craft_copper_nails", 2)],
        "fail_reduce": 0.02,
        "hint": "归港失败率略降",
    },
    "fog_paint": {
        "name": "雾纹漆",
        "emoji": "🎨",
        "cost": 28,
        "need": [("quarry_fog_lead", 1)],
        "cargo_bonus": 0,
        "hint": "外观收藏向，无战力",
    },
    "lantern_figure": {
        "name": "灯笼首",
        "emoji": "🏮",
        "cost": 42,
        "need": [("craft_timber", 3), ("fish_lanternfish", 1)],
        "fail_reduce": 0.03,
        "hint": "夜航略稳",
    },
    "salt_rail": {
        "name": "盐边栏",
        "emoji": "⚓",
        "cost": 30,
        "need": [("quarry_salt", 2), ("craft_copper_nails", 1)],
        "parley_bonus": 0.05,
        "hint": "海上谈和略易",
    },
}


async def ensure_table(conn) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS steward_boat_mod (
            steward_id INTEGER NOT NULL REFERENCES stewards(id),
            slot INTEGER NOT NULL,
            mod_key TEXT NOT NULL,
            installed_at INTEGER NOT NULL,
            PRIMARY KEY (steward_id, slot)
        )
        """
    )


async def list_installed(conn, steward_id: int) -> list[tuple[int, str]]:
    await ensure_table(conn)
    cur = await conn.execute(
        "SELECT slot, mod_key FROM steward_boat_mod WHERE steward_id=? ORDER BY slot",
        (steward_id,),
    )
    return [(int(r[0]), r[1]) for r in await cur.fetchall()]


async def bonuses(conn, steward_id: int) -> dict[str, float]:
    installed = await list_installed(conn, steward_id)
    fail_reduce = 0.0
    parley = 0.0
    for _slot, key in installed:
        meta = MODS.get(key) or {}
        fail_reduce += float(meta.get("fail_reduce") or 0)
        parley += float(meta.get("parley_bonus") or 0)
    return {"fail_reduce": fail_reduce, "parley_bonus": parley}


async def status_line(conn, steward_id: int) -> str:
    rows = await list_installed(conn, steward_id)
    if not rows:
        return f"改装槽 0/{MAX_MODS} 空。tide_ops voyage 改装 list"
    bits = []
    for slot, key in rows:
        m = MODS.get(key, {})
        bits.append(f"{slot}:{m.get('emoji', '')}{m.get('name', key)}")
    return f"改装 [{', '.join(bits)}]（最多 {MAX_MODS}）"


async def install(conn, steward: dict, mod_token: str) -> str:
    if not steward.get("boat_key"):
        raise ValueError("先 tide_ops voyage buy 购船")
    key = mod_token.strip().lower().replace(" ", "_")
    if key not in MODS:
        for mk, meta in MODS.items():
            if meta["name"] == mod_token:
                key = mk
                break
    if key not in MODS:
        raise ValueError("tide_ops voyage 改装 list 看可选")
    meta = MODS[key]
    rows = await list_installed(conn, steward["id"])
    if any(k == key for _, k in rows):
        raise ValueError("已经装过这件改装")
    if len(rows) >= MAX_MODS:
        raise ValueError(f"改装槽已满（{MAX_MODS}），先 改装 卸 槽位")
    slot = 1 if not any(s == 1 for s, _ in rows) else 2
    cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (steward["id"],))
    tickets = int((await cur.fetchone())[0])
    if tickets < meta["cost"]:
        raise ValueError(f"需要 {meta['cost']} 票")
    for item, qty in meta["need"]:
        if not await db.take_item(conn, steward["id"], item, qty):
            raise ValueError(f"缺 {ITEM_NAMES.get(item, item)}×{qty}")
    await conn.execute(
        "UPDATE stewards SET tickets=tickets-? WHERE id=?",
        (meta["cost"], steward["id"]),
    )
    await conn.execute(
        """
        INSERT INTO steward_boat_mod (steward_id, slot, mod_key, installed_at)
        VALUES (?,?,?,?)
        """,
        (steward["id"], slot, key, db.now()),
    )
    return f"槽{slot} 装上 {meta['emoji']}{meta['name']}（-{meta['cost']}票）。{meta['hint']}"


async def uninstall(conn, steward: dict, slot: int) -> str:
    await ensure_table(conn)
    cur = await conn.execute(
        "DELETE FROM steward_boat_mod WHERE steward_id=? AND slot=? RETURNING mod_key",
        (steward["id"], slot),
    )
    row = await cur.fetchone()
    if not row:
        raise ValueError(f"槽{slot} 没有改装")
    m = MODS.get(row[0], {})
    return f"已卸下槽{slot} {m.get('name', row[0])}（材料不退）"


async def dispatch(conn, steward: dict, parts: list[str]) -> str:
    await ensure_table(conn)
    if not parts or parts[0].lower() in ("list", "列表", "help"):
        lines = [f"船改装（最多 {MAX_MODS} 槽，tide_ops voyage 改装 装 名 / 卸 槽位）："]
        for key, meta in MODS.items():
            need = " + ".join(f"{ITEM_NAMES.get(i, i)}×{q}" for i, q in meta["need"])
            lines.append(
                f"  {meta['emoji']}{meta['name']} ({key}) — {need} + {meta['cost']}票 · {meta['hint']}"
            )
        lines.append(await status_line(conn, steward["id"]))
        return "\n".join(lines)
    sub = parts[0].lower()
    if sub in ("装", "install") and len(parts) >= 2:
        return await install(conn, steward, " ".join(parts[1:]))
    if sub in ("卸", "remove") and len(parts) >= 2:
        return await uninstall(conn, steward, int(parts[1]))
    raise ValueError("改装 list · 改装 装 铜雾钟 · 改装 卸 1")
