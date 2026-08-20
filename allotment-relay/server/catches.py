"""渔获 / 赶海图鉴收集。"""

from __future__ import annotations

import aiosqlite

from . import db
from .catalog import BEACH_LOOT, ITEM_NAMES, SEA_CATCH


async def record_catch(conn: aiosqlite.Connection, steward_id: int, item_key: str) -> None:
    if not item_key.startswith(("fish_", "beach_", "shell_")):
        return
    await conn.execute(
        """
        INSERT INTO steward_catches (steward_id, catch_key, first_at, catch_count)
        VALUES (?,?,?,1)
        ON CONFLICT(steward_id, catch_key) DO UPDATE SET catch_count = catch_count + 1
        """,
        (steward_id, item_key, db.now()),
    )


async def fish_catalog(conn: aiosqlite.Connection, steward_id: int) -> str:
    conn.row_factory = aiosqlite.Row
    rows = await (await conn.execute(
        "SELECT catch_key, catch_count, first_at FROM steward_catches WHERE steward_id=?",
        (steward_id,),
    )).fetchall()
    caught = {r["catch_key"]: dict(r) for r in rows}
    all_keys = [f"fish_{k}" for k in SEA_CATCH]
    lines = [f"渔获图鉴 {len([k for k in all_keys if k in caught])}/{len(all_keys)}", ""]
    for key, meta in SEA_CATCH.items():
        item = f"fish_{key}"
        if item in caught:
            c = caught[item]["catch_count"]
            lines.append(f"  ✓ {meta['emoji']}{meta['name']} ×{c}")
        else:
            lines.append(f"  · {meta['name']}（未钓到）")
    return "\n".join(lines)


async def beach_catalog(conn: aiosqlite.Connection, steward_id: int) -> str:
    conn.row_factory = aiosqlite.Row
    rows = await (await conn.execute(
        """
        SELECT catch_key, catch_count FROM steward_catches
        WHERE steward_id=? AND (catch_key LIKE 'shell_%' OR catch_key LIKE 'beach_%' OR catch_key LIKE 'curio_%')
        """,
        (steward_id,),
    )).fetchall()
    caught = {r["catch_key"]: r["catch_count"] for r in rows}
    beach_keys = sorted({row[0] for row in BEACH_LOOT})
    got = sum(1 for k in beach_keys if k in caught)
    lines = [f"赶海图鉴 {got}/{len(beach_keys)}", ""]
    for key in beach_keys:
        name = ITEM_NAMES.get(key, key)
        if key in caught:
            lines.append(f"  ✓ {name} ×{caught[key]}")
        else:
            lines.append(f"  · {name}")
    return "\n".join(lines)
