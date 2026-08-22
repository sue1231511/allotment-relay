#!/usr/bin/env python3
"""undertide_ops racket — 收账鬼阿标强买强卖。"""
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


def test_undertide_racket_flow() -> None:
    asyncio.run(_test_undertide_racket_flow())


async def _test_undertide_racket_flow() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="ut-racket-"))
    db = await _boot(tmp)
    from server import undertide, undertide_racket as ur

    kid, sid = await _enroll(db, "racket@example.com", "被收账的")
    async with db.connect() as conn:
        from server import undertide as ut_mod
        await ut_mod._ensure_ut(conn, sid)
        await conn.execute(
            "UPDATE steward_undertide SET access=1, well_hint=1 WHERE steward_id=?",
            (sid,),
        )
        await conn.execute("UPDATE stewards SET tickets=200 WHERE id=?", (sid,))
        await conn.commit()

    scan = await undertide.undertide_ops(kid, "racket")
    assert ur.ENFORCER_NAME in scan or "放过" in scan, scan

    async with db.connect() as conn:
        deal = await ur.ensure_racket_deal(conn, sid, force=True)
        await conn.commit()
    assert deal and deal.get("kind") in ("buy", "sell"), deal

    detail = await undertide.undertide_ops(kid, "racket")
    assert "accept" in detail and "refuse" in detail, detail

    market = await undertide.undertide_ops(kid, "market")
    assert ur.ENFORCER_NAME in market or "没盯上" in market, market

    accept = await undertide.undertide_ops(kid, "racket accept")
    assert "票" in accept or "货" in accept or "罚" in accept, accept

    again = await undertide.undertide_ops(kid, "racket")
    assert "没找你" in again or "结清" in again or "放过" in again, again


if __name__ == "__main__":
    asyncio.run(_test_undertide_racket_flow())
    print("ok")
