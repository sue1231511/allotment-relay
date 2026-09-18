"""家庭杂务 — 三选一（自修 / 请匠 / 先不管）§六·5。"""
from __future__ import annotations

import random

from . import db

CHORE_META = {
    "fridge_frost": {
        "name": "冰箱结霜",
        "emoji": "🧊",
        "self": ("除霜", 6, "化霜后冷藏恢复正常。"),
        "npc": (12, "请匠通霜，省心。"),
        "ignore": "霜越积越厚，熟菜保鲜更短。",
    },
    "door_hinge": {
        "name": "门轴响",
        "emoji": "🚪",
        "self": ("上油", 4, "门轴不响了。"),
        "npc": (10, "匠换了铜钉，门顺了。"),
        "ignore": "夜里风一刮门就吱呀，睡略浅。",
    },
    "roof_drip": {
        "name": "屋顶渗水",
        "emoji": "💧",
        "self": ("接盆", 5, "先接住，明天记得 hut_ops 修屋顶。"),
        "npc": (14, "匠补了一处漏点。"),
        "ignore": "潮气进屋，软装发潮概率↑。",
    },
    "stove_clog": {
        "name": "灶台堵塞",
        "emoji": "🔥",
        "self": ("通灶", 5, "火路通了。"),
        "npc": (11, "匠清了烟道。"),
        "ignore": "下次做饭更费神（已记下）。",
    },
}


async def ensure_table(conn) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS steward_hut_chore (
            steward_id INTEGER NOT NULL PRIMARY KEY,
            chore_key TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
        """
    )


async def get_chore(conn, steward_id: int) -> str | None:
    await ensure_table(conn)
    cur = await conn.execute(
        "SELECT chore_key FROM steward_hut_chore WHERE steward_id=?",
        (steward_id,),
    )
    row = await cur.fetchone()
    return row[0] if row else None


async def maybe_roll(conn, steward_id: int, *, hut_built: bool, hut_level: int) -> str | None:
    if not hut_built or hut_level < 2:
        return None
    if await get_chore(conn, steward_id):
        return None
    if random.random() > 0.10:
        return None
    key = random.choice(list(CHORE_META.keys()))
    await conn.execute(
        """
        INSERT OR REPLACE INTO steward_hut_chore (steward_id, chore_key, created_at)
        VALUES (?, ?, ?)
        """,
        (steward_id, key, db.now()),
    )
    meta = CHORE_META[key]
    return (
        f"{meta['emoji']}杂务：{meta['name']}。"
        f"hut_ops 杂务 自修|请匠|不管"
    )


async def resolve(conn, steward: dict, choice: str) -> str:
    key = await get_chore(conn, steward["id"])
    if not key:
        raise ValueError("没有待处理杂务。hut_ops status 看屋")
    meta = CHORE_META[key]
    ch = choice.strip().lower()
    if ch in ("自修", "self", "自己"):
        label, nrg, ok = meta["self"]
        from . import energy as energy_mod
        await energy_mod.spend(conn, steward["id"], nrg, action=f"杂务{label}")
        note = ok
    elif ch in ("请匠", "npc", "匠", "请人"):
        cost, ok = meta["npc"]
        cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (steward["id"],))
        have = int((await cur.fetchone())[0])
        if have < cost:
            raise ValueError(f"请匠要 {cost} 票")
        await conn.execute(
            "UPDATE stewards SET tickets=tickets-? WHERE id=?",
            (cost, steward["id"]),
        )
        note = ok
    elif ch in ("不管", "ignore", "拖"):
        note = meta["ignore"]
        if key == "stove_clog":
            from . import light_bad_events as lb
            await lb.set_flag(conn, steward["id"], "stove_stubborn")
        elif key == "roof_drip":
            from . import light_bad_events as lb
            await lb.set_flag(conn, steward["id"], "humid_soft")
        elif key == "fridge_frost":
            from . import hut_domestic as dom
            day = db.day_id()
            await dom.ensure_table(conn)
            await conn.execute(
                """
                INSERT INTO steward_hut_domestic (steward_id, day_id, paid_mask)
                VALUES (?, ?, 0)
                ON CONFLICT(steward_id, day_id) DO UPDATE SET paid_mask=0
                """,
                (steward["id"], day),
            )
    else:
        raise ValueError("杂务：自修 · 请匠 · 不管")
    await conn.execute("DELETE FROM steward_hut_chore WHERE steward_id=?", (steward["id"],))
    await db.add_chronicle("hut", f"{steward['name']} 处置杂务·{meta['name']}（{choice}）", steward["id"], conn=conn)
    return f"杂务「{meta['name']}」：{note}"


async def status_suffix(conn, steward_id: int) -> str:
    key = await get_chore(conn, steward_id)
    if not key:
        return ""
    meta = CHORE_META[key]
    return f"⚠ 待杂务：{meta['emoji']}{meta['name']}（hut_ops 杂务 自修|请匠|不管）"
