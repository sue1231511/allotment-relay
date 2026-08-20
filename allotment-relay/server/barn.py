"""畜栏 — 牛羊猪狗兔鸡，喂食产出。"""

from __future__ import annotations

import aiosqlite

from . import config, db, flavor
from .catalog import ITEM_NAMES, LIVESTOCK
from .game import require_steward


def _ready(animal: dict, species: str) -> bool:
    meta = LIVESTOCK[species]
    if meta.get("guard"):
        return False
    if not animal.get("stocked_at"):
        return False
    grow = meta["grow"]
    if animal.get("fed"):
        grow = int(grow * 0.85)
    return db.now() - animal["stocked_at"] >= grow


def _line(animal: dict | None, slot: int) -> str:
    if not animal or not animal.get("species"):
        return f"  #{slot}: 空栏"
    spec = LIVESTOCK[animal["species"]]
    if spec.get("guard"):
        state = "守夜中" if animal.get("guard") else "幼犬"
    elif _ready(animal, animal["species"]):
        state = "可收"
    elif animal.get("fed"):
        state = "放养"
    else:
        state = "待喂"
    return f"  #{slot}: {spec['emoji']}{spec['name']}（{state}）"


async def barn_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    parts = command.strip().split(maxsplit=2)
    verb = parts[0].lower() if parts else "status"

    if verb == "status":
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            rows = await (await conn.execute(
                "SELECT * FROM barn_animals WHERE steward_id=? ORDER BY slot",
                (s["id"],),
            )).fetchall()
        built = s.get("barn_built")
        lines = [
            f"畜栏: {'已建' if built else '未建'}（erect {config.BARN_ERECT_COST} 票）",
            f"槽位 {config.BARN_SLOTS}",
        ]
        by_slot = {r["slot"]: dict(r) for r in rows}
        for slot in range(1, config.BARN_SLOTS + 1):
            lines.append(_line(by_slot.get(slot), slot))
        lines.append(f"可购: {', '.join(LIVESTOCK.keys())}")
        return "\n".join(lines)

    if verb == "erect":
        if s.get("barn_built"):
            return "已有畜栏"
        async with aiosqlite.connect(db.DB_PATH) as conn:
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < config.BARN_ERECT_COST:
                raise ValueError(f"搭建畜栏需要 {config.BARN_ERECT_COST} 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-?, barn_built=1 WHERE id=?",
                (config.BARN_ERECT_COST, s["id"]),
            )
            for slot in range(1, config.BARN_SLOTS + 1):
                await conn.execute(
                    "INSERT OR IGNORE INTO barn_animals (steward_id, slot, species, fed) VALUES (?,?,NULL,0)",
                    (s["id"], slot),
                )
            await conn.commit()
        return f"畜栏就绪（-{config.BARN_ERECT_COST} 票）"

    if verb == "buy" and len(parts) >= 2:
        if not s.get("barn_built"):
            raise ValueError("先 barn_ops erect")
        species = parts[1].lower()
        slot = int(parts[2]) if len(parts) > 2 else 1
        if species not in LIVESTOCK:
            raise ValueError(f"可购: {', '.join(LIVESTOCK.keys())}")
        meta = LIVESTOCK[species]
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                "SELECT * FROM barn_animals WHERE steward_id=? AND slot=?",
                (s["id"], slot),
            )
            row = await cur.fetchone()
            if not row:
                await conn.execute(
                    "INSERT INTO barn_animals (steward_id, slot, species, fed) VALUES (?,?,NULL,0)",
                    (s["id"], slot),
                )
            elif row["species"]:
                raise ValueError(f"#{slot} 已有动物")
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < meta["buy"]:
                raise ValueError(f"需要 {meta['buy']} 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (meta["buy"], s["id"]),
            )
            guard = 1 if meta.get("guard") else 0
            await conn.execute(
                """
                UPDATE barn_animals SET species=?, stocked_at=?, fed=0, guard=?
                WHERE steward_id=? AND slot=?
                """,
                (species, db.now(), guard, s["id"], slot),
            )
            await conn.commit()
        if meta.get("guard"):
            return f"#{slot} 入驻 {meta['name']} — 守夜减偷菜概率"
        return f"#{slot} 购入 {meta['emoji']}{meta['name']}（-{meta['buy']} 票）"

    if verb == "feed":
        slot = int(parts[1]) if len(parts) > 1 else 1
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            row = dict(await (await conn.execute(
                "SELECT * FROM barn_animals WHERE steward_id=? AND slot=?",
                (s["id"], slot),
            )).fetchone() or {})
            if not row.get("species"):
                raise ValueError("空栏")
            meta = LIVESTOCK[row["species"]]
            if meta.get("guard"):
                if not await db.take_item(conn, s["id"], meta["feed"], meta["feed_qty"]):
                    raise ValueError(f"喂狗需要 {ITEM_NAMES.get(meta['feed'], meta['feed'])}")
                await conn.execute(
                    "UPDATE barn_animals SET guard=1, fed=1 WHERE steward_id=? AND slot=?",
                    (s["id"], slot),
                )
            else:
                if row.get("fed"):
                    return f"#{slot} 今日已喂"
                if not await db.take_item(conn, s["id"], meta["feed"], meta["feed_qty"]):
                    raise ValueError(
                        f"需要 {ITEM_NAMES.get(meta['feed'], meta['feed'])} x{meta['feed_qty']}"
                    )
                await conn.execute(
                    "UPDATE barn_animals SET fed=1 WHERE steward_id=? AND slot=?",
                    (s["id"], slot),
                )
            await conn.commit()
        return f"#{slot} 已喂食"

    if verb == "harvest":
        slot = int(parts[1]) if len(parts) > 1 else 1
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            row = dict(await (await conn.execute(
                "SELECT * FROM barn_animals WHERE steward_id=? AND slot=?",
                (s["id"], slot),
            )).fetchone() or {})
            if not row.get("species"):
                raise ValueError("空栏")
            species = row["species"]
            meta = LIVESTOCK[species]
            if meta.get("guard"):
                raise ValueError("狗不产肉，它产安全感")
            if not _ready(row, species):
                raise ValueError("还没长成，继续 feed")
            product = meta["product"]
            qty = meta["product_qty"]
            if not row.get("fed"):
                qty = max(1, qty // 2)
            await db.add_item(conn, s["id"], product, qty)
            await conn.execute(
                """
                UPDATE barn_animals SET species=NULL, stocked_at=NULL, fed=0, guard=0
                WHERE steward_id=? AND slot=?
                """,
                (s["id"], slot),
            )
            await conn.commit()
        msg = f"#{slot} 收获 {ITEM_NAMES.get(product, product)} x{qty}"
        msg += flavor.maybe_suffix(["栏里忙，票里稳", "牲畜：今天也努力了"])
        await db.add_chronicle("barn", f"{s['name']} 畜栏收 {product}", s["id"])
        return msg

    raise ValueError(
        f"未知 barn 指令: {command}（status/erect/buy/feed/harvest）"
    )
