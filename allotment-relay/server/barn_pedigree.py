"""动物履历 — 第三批。"""
from __future__ import annotations

from . import db
from .catalog import LIVESTOCK


async def ensure_table(conn) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS barn_pedigree (
            steward_id INTEGER NOT NULL,
            species TEXT NOT NULL,
            generation INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (steward_id, species)
        )
        """
    )
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS barn_animal_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            steward_id INTEGER NOT NULL,
            slot INTEGER NOT NULL,
            text TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
        """
    )


async def next_generation(conn, steward_id: int, species: str) -> tuple[int, str]:
    await ensure_table(conn)
    cur = await conn.execute(
        "SELECT generation FROM barn_pedigree WHERE steward_id=? AND species=?",
        (steward_id, species),
    )
    row = await cur.fetchone()
    gen = int(row[0]) + 1 if row else 1
    await conn.execute(
        """
        INSERT INTO barn_pedigree (steward_id, species, generation)
        VALUES (?, ?, ?)
        ON CONFLICT(steward_id, species) DO UPDATE SET generation=excluded.generation
        """,
        (steward_id, species, gen),
    )
    name = LIVESTOCK.get(species, {}).get("name", species)
    label = f"第{gen}栏{name}"
    return gen, label


async def log(conn, steward_id: int, slot: int, text: str) -> None:
    await ensure_table(conn)
    await conn.execute(
        "INSERT INTO barn_animal_log (steward_id, slot, text, created_at) VALUES (?,?,?,?)",
        (steward_id, slot, text[:120], db.now()),
    )


async def status(conn, steward_id: int) -> str:
    await ensure_table(conn)
    cur = await conn.execute(
        """
        SELECT species, generation FROM barn_pedigree
        WHERE steward_id=? ORDER BY generation DESC
        """,
        (steward_id,),
    )
    gens = await cur.fetchall()
    cur2 = await conn.execute(
        """
        SELECT text FROM barn_animal_log
        WHERE steward_id=? ORDER BY id DESC LIMIT 6
        """,
        (steward_id,),
    )
    logs = [r[0] for r in await cur2.fetchall()]
    if not gens and not logs:
        return "还没有畜栏履历。购入/治病/收产会自动记。barn_ops 履历"
    lines = ["畜栏血统/履历："]
    for sp, gen in gens:
        name = LIVESTOCK.get(sp, {}).get("name", sp)
        lines.append(f"  {name} 累计第{gen}批入栏")
    for t in logs:
        lines.append(f"  · {t}")
    return "\n".join(lines)
