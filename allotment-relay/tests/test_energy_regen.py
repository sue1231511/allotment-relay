#!/usr/bin/env python3
"""刷新上手页不能刷精力：档口只按时间慢回。"""
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


async def _enroll(db, email: str, name: str) -> tuple[str, int]:
    key = await db.create_api_key(email)
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], name, "", "naturalist", "")
    async with db.connect() as conn:
        sid = (await (await conn.execute(
            "SELECT id FROM stewards WHERE key_id=?", (row["id"],)
        )).fetchone())[0]
        await conn.execute("UPDATE stewards SET energy=40 WHERE id=?", (sid,))
        await conn.commit()
    return key, sid


async def _energy(db, sid: int) -> int:
    async with db.connect() as conn:
        row = await (await conn.execute(
            "SELECT energy FROM stewards WHERE id=?", (sid,)
        )).fetchone()
    return int(row[0])


async def _run() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="energy-regen-"))
    db = await _boot(tmp)
    from server import config, energy, play

    key, sid = await _enroll(db, "refresh@example.com", "刷页")
    real_now = db.now
    t0 = 1_700_000_000
    db.now = lambda: t0
    try:
        snap = await play.snapshot(key)
        assert snap["enrolled"], snap
        assert await _energy(db, sid) == 40

        db.now = lambda: t0 + 30
        await play.snapshot(key)
        await play.snapshot(key)
        await play.snapshot(key)
        assert await _energy(db, sid) == 40, "refreshing /play must not grant energy"

        async with db.connect() as conn:
            await energy.soft_regen(conn, sid)
            await conn.commit()
        assert await _energy(db, sid) == 40

        db.now = lambda: t0 + config.ENERGY_REGEN_IDLE_SEC
        await play.snapshot(key)
        assert await _energy(db, sid) == 42

        await play.snapshot(key)
        assert await _energy(db, sid) == 42

        db.now = lambda: t0 + 3 * config.ENERGY_REGEN_IDLE_SEC
        await play.snapshot(key)
        assert await _energy(db, sid) == 46
    finally:
        db.now = real_now


def main() -> None:
    asyncio.run(_run())
    print("ok")


if __name__ == "__main__":
    main()
