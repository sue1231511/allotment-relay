#!/usr/bin/env python3
"""过熟果树清理后应重新结果，不应把树清死。"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def _boot(tmp: Path):
    os.environ["DATA_DIR"] = str(tmp)
    from server import config, db

    config.DATA_DIR = tmp
    config.DB_PATH = tmp / "relay.db"
    db.DATA_DIR = tmp
    db.DB_PATH = tmp / "relay.db"
    await db.init_db()
    return db


async def _enroll(db, email: str, name: str) -> tuple[int, int]:
    key = await db.create_api_key(email)
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], name, "", "naturalist", "")
    async with db.connect() as conn:
        sid = (await (await conn.execute(
            "SELECT id FROM stewards WHERE key_id=?", (row["id"],)
        )).fetchone())[0]
    return row["id"], sid


def test_overripe_tree_compost_keeps_tree() -> None:
    asyncio.run(_test_overripe_tree_compost_keeps_tree())


async def _test_overripe_tree_compost_keeps_tree() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="tree-compost-"))
    db = await _boot(tmp)
    from server import game, farming

    kid, sid = await _enroll(db, "tree@example.com", "果农")
    async with db.connect() as conn:
        await conn.execute(
            """
            UPDATE parcels SET crop='mango', planted_at=?, tended=1, greenhouse=0,
            grow_target=260, grow_pace='中茬', harvest_left=0
            WHERE steward_id=? AND slot=1
            """,
            (db.now() - 10_000, sid),
        )
        await conn.commit()

    async with db.connect() as conn:
        conn.row_factory = __import__("aiosqlite").Row
        plot = dict(await (await conn.execute(
            "SELECT * FROM parcels WHERE steward_id=? AND slot=1", (sid,)
        )).fetchone())
    assert farming.plot_overripe(plot), plot

    msg = await game.plot_ops(kid, "compost 1")
    assert "树还在" in msg, msg

    async with db.connect() as conn:
        row = await (await conn.execute(
            "SELECT crop, planted_at FROM parcels WHERE steward_id=? AND slot=1", (sid,)
        )).fetchone()
    assert row[0] == "mango", row
    assert row[1] > 0, row
    assert not farming.plot_overripe({"crop": row[0], "planted_at": row[1], "grow_target": 260})


if __name__ == "__main__":
    asyncio.run(_test_overripe_tree_compost_keeps_tree())
    print("ok")
