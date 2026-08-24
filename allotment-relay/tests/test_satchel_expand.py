#!/usr/bin/env python3
"""行囊扩栈 + 好事件回身体。"""
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
        cur = await conn.execute(
            "SELECT id FROM stewards WHERE key_id=?", (row["id"],)
        )
        sid = (await cur.fetchone())[0]
    return sid, row["id"]


async def test_satchel_stack_expand() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="stack-expand-"))
    db = await _boot(tmp)
    from server import game
    from server.catalog import item_stack_cap

    sid, kid = await _enroll(db, "stack@example.com", "囤货人")
    async with db.connect() as conn:
        await conn.execute("UPDATE stewards SET tickets=200 WHERE id=?", (sid,))
        await conn.commit()

    assert item_stack_cap("crop_kale", stack_tier=0) == 24
    msg = await game.tote_ops(kid, "扩栈")
    assert "32" in msg, msg
    s = await db.get_steward_by_id(sid)
    assert int(s.get("satchel_stack_extra") or 0) == 1

    async with db.connect() as conn:
        await db.add_item(conn, sid, "crop_kale", 30)
        await conn.commit()

    listed = await game.tote_ops(kid, "list")
    assert "x30/32" in listed, listed


async def test_good_event_health_restore() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="health-event-"))
    db = await _boot(tmp)
    from server import events

    sid, _kid = await _enroll(db, "health@example.com", "养生人")
    async with db.connect() as conn:
        await conn.execute("UPDATE stewards SET health=80 WHERE id=?", (sid,))
        await conn.commit()
        steward = await db.get_steward_by_id(sid)
        holder: list[int | None] = [None]
        msgs, ledger = await events._apply_effects(  # noqa: SLF001
            conn, steward, ["health:6"], plot_id_holder=holder,
        )
        await conn.commit()
        cur = await conn.execute("SELECT health FROM stewards WHERE id=?", (sid,))
        row = await cur.fetchone()
    assert ledger.get("health_delta") == 6
    assert row[0] == 86
    assert not msgs


def main() -> None:
    asyncio.run(test_satchel_stack_expand())
    asyncio.run(test_good_event_health_restore())
    print("ok")


if __name__ == "__main__":
    main()
