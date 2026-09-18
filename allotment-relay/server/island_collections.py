"""岛收集簿（样板）— 行囊/产业里程碑，只读进度。"""
from __future__ import annotations

from . import db
from .catalog import ITEM_NAMES
from .game import require_steward

# (key, 标题, satchel_item 或 None, 特殊键 hut|boat|barn)
ENTRIES: list[tuple[str, str, str | None, str | None]] = [
    ("kale", "甘蓝入门", "crop_kale", None),
    ("beet", "甜菜一行", "crop_beet", None),
    ("fogpea", "雾豆初收", "crop_fogpea", None),
    ("herring", "鲱鳞闪光", "fish_herring", None),
    ("sardine", "沙丁一串", "fish_sardine", None),
    ("pickles", "腌坛开盖", "pickles", None),
    ("compost", "堆肥上手", "compost", None),
    ("skiff", "第一艘船", None, "boat"),
    ("barn", "畜栏开张", None, "barn"),
    ("hut2", "小屋二档", None, "hut2"),
    ("black_salt_fish", "黑盐炖鱼成", "meal:black_salt_fish", None),
    ("fog_mushroom_soup", "雾菇汤香", "meal:fog_mushroom_soup", None),
]


async def _has_item(conn, steward_id: int, item: str) -> bool:
    if item.startswith("meal:"):
        dish = item.split(":", 1)[1]
        cur = await conn.execute(
            """
            SELECT 1 FROM meal_storage
            WHERE steward_id=? AND dish_key=? AND quantity>0 LIMIT 1
            """,
            (steward_id, dish),
        )
        return (await cur.fetchone()) is not None
    cur = await conn.execute(
        "SELECT 1 FROM satchel WHERE steward_id=? AND item=? AND quantity>0 LIMIT 1",
        (steward_id, item),
    )
    return (await cur.fetchone()) is not None


async def _milestone(conn, steward_id: int, key: str | None) -> bool:
    if key == "boat":
        cur = await conn.execute(
            "SELECT boat_key FROM stewards WHERE id=?", (steward_id,)
        )
        row = await cur.fetchone()
        return bool(row and row[0])
    if key == "barn":
        cur = await conn.execute(
            "SELECT barn_built FROM stewards WHERE id=?", (steward_id,)
        )
        return bool(int((await cur.fetchone())[0] or 0))
    if key == "hut2":
        cur = await conn.execute(
            "SELECT hut_built, hut_level FROM stewards WHERE id=?", (steward_id,)
        )
        row = await cur.fetchone()
        return bool(row and int(row[0]) and int(row[1] or 0) >= 2)
    return False


async def sheet(conn, steward_id: int) -> str:
    lines = [f"岛收集簿（样板 {len(ENTRIES)} 项，只读进度；不是 lore scan）："]
    done = 0
    for key, title, item, mile in ENTRIES:
        ok = False
        if item:
            ok = await _has_item(conn, steward_id, item)
        elif mile:
            ok = await _milestone(conn, steward_id, mile)
        if ok:
            done += 1
        mark = "✓" if ok else "·"
        hint = ITEM_NAMES.get(item, item) if item else mile or ""
        lines.append(f"  {mark} {title}" + (f"（{hint}）" if not ok and hint else ""))
    lines.append(f"进度 {done}/{len(ENTRIES)}。背包曾持有即算点亮。")
    return "\n".join(lines)


async def collection_ops(key_id: int, command: str = "") -> str:
    parts = command.strip().split()
    verb = parts[0].lower() if parts else "status"
    read_ok = verb in ("", "status", "列表", "list", "help", "?", "帮助", "收集")
    s = await require_steward(key_id, exempt_duty=read_ok)
    if verb in ("help", "?", "帮助"):
        return "steward_ops 收集 — 岛收集簿样板进度（只读，不是 lore scan）"
    async with db.connect() as conn:
        return await sheet(conn, s["id"])
