#!/usr/bin/env python3
"""alliance contract fill resolves Chinese item names like 石蟹王."""
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
        await conn.execute("UPDATE stewards SET tickets=500 WHERE id=?", (sid,))
        await conn.commit()
    return row["id"], sid


def test_contract_fill_resolves_kingcrab() -> None:
    asyncio.run(_test_contract_fill_resolves_kingcrab())


async def _test_contract_fill_resolves_kingcrab() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="contract-resolve-"))
    db = await _boot(tmp)
    from server import multi

    poster_kid, poster_sid = await _enroll(db, "poster@example.com", "丘名山")
    filler_kid, filler_sid = await _enroll(db, "filler@example.com", "Grayson")

    posted = await multi.contract_ops(poster_kid, "post 石蟹王 1 75")
    assert "石蟹王" in posted and "托管" in posted, posted

    async with db.connect() as conn:
        row = await (await conn.execute(
            "SELECT id, want_item FROM contracts WHERE poster_id=? AND status='open'",
            (poster_sid,),
        )).fetchone()
        assert row is not None
        cid, want = row[0], row[1]
        assert want == "fish_kingcrab", want
        await db.add_item(conn, filler_sid, "fish_kingcrab", 2)
        await conn.commit()

    filled = await multi.contract_ops(filler_kid, f"fill {cid}")
    assert "完成" in filled and "75" in filled, filled

    async with db.connect() as conn:
        have = await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item=?",
            (filler_sid, "fish_kingcrab"),
        )).fetchone()
        assert have and have[0] == 1, have
        got = await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item=?",
            (poster_sid, "fish_kingcrab"),
        )).fetchone()
        assert got and got[0] == 1, got

    # Legacy open contract stored as Chinese name still fills
    async with db.connect() as conn:
        await conn.execute(
            """
            INSERT INTO contracts (poster_id, want_item, want_qty, reward_tickets, status, created_at)
            VALUES (?,?,?,?, 'open', ?)
            """,
            (poster_sid, "石蟹王", 1, 40, db.now()),
        )
        await db.add_item(conn, filler_sid, "fish_kingcrab", 1)
        await conn.execute(
            "UPDATE stewards SET tickets = tickets - 40 WHERE id=?", (poster_sid,)
        )
        await conn.commit()
        legacy = (await (await conn.execute(
            "SELECT id FROM contracts WHERE want_item='石蟹王' AND status='open'"
        )).fetchone())[0]

    legacy_fill = await multi.contract_ops(filler_kid, f"fill {legacy}")
    assert "完成" in legacy_fill, legacy_fill


if __name__ == "__main__":
    test_contract_fill_resolves_kingcrab()
