#!/usr/bin/env python3
"""集市摊格扩格 — market_ops 扩。"""
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


async def _fill_listings(db, kid: int, sid: int, n: int) -> None:
    from server import market

    async with db.connect() as conn:
        await db.add_item(conn, sid, "crop_kale", n)
        await conn.commit()
    for i in range(n):
        await market.market_ops(kid, f"sell 甘蓝 1 {8 + i}")


def test_market_expand() -> None:
    asyncio.run(_test_market_expand())


async def _test_market_expand() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="market-expand-"))
    db = await _boot(tmp)
    from server import config, market

    kid, sid = await _enroll(db, "seller@example.com", "摊主")

    assert market.market_list_cap(0) == config.MARKET_LIST_MAX
    assert market.market_list_cap(6) == config.MARKET_LIST_SLOTS_MAX

    await _fill_listings(db, kid, sid, config.MARKET_LIST_MAX)
    async with db.connect() as conn:
        await db.add_item(conn, sid, "crop_kale", 1)
        await conn.commit()
    try:
        await market.market_ops(kid, "sell 甘蓝 1 9")
        raise AssertionError("should block at base cap")
    except ValueError as exc:
        assert "已满" in str(exc) and "扩" in str(exc), exc

    expanded = await market.market_ops(kid, "扩")
    assert "摊格 +1" in expanded and "-15 票" in expanded, expanded
    assert market.market_list_cap(1) == config.MARKET_LIST_MAX + 1

    async with db.connect() as conn:
        await db.add_item(conn, sid, "crop_kale", 1)
        await conn.commit()
    await market.market_ops(kid, "sell 甘蓝 1 9")
    mine = await market.market_ops(kid, "mine")
    assert f"/{config.MARKET_LIST_MAX + 1}" in mine, mine

    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET market_extra=? WHERE id=?",
            (config.MARKET_LIST_SLOTS_MAX - config.MARKET_LIST_MAX, sid),
        )
        await conn.commit()
    try:
        await market.market_ops(kid, "扩")
        raise AssertionError("should block at max cap")
    except ValueError as exc:
        assert "扩到顶" in str(exc), exc


if __name__ == "__main__":
    test_market_expand()
    print("ok")
