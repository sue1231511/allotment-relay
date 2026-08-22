#!/usr/bin/env python3
"""SQLite 并发与嵌套 connect 回归。"""
from __future__ import annotations

import asyncio
import os
import sqlite3
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


def test_nested_connect_reuses_connection() -> None:
    asyncio.run(_test_nested_connect_reuses_connection())


async def _test_nested_connect_reuses_connection() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="db-nested-"))
    db = await _boot(tmp)
    outer_id = inner_id = None
    async with db.connect() as outer:
        outer_id = id(outer)
        async with db.connect() as inner:
            inner_id = id(inner)
    assert outer_id is not None and inner_id == outer_id


def test_concurrent_connect_serializes() -> None:
    asyncio.run(_test_concurrent_connect_serializes())


async def _test_concurrent_connect_serializes() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="db-conc-"))
    db = await _boot(tmp)
    key = await db.create_api_key("busy@example.com")
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], "并发测试", "", "naturalist", "")

    async def touch() -> int:
        async with db.connect() as conn:
            cur = await conn.execute("SELECT tickets FROM stewards WHERE key_id=?", (row["id"],))
            return (await cur.fetchone())[0]

    results = await asyncio.gather(*[touch() for _ in range(24)])
    assert all(r == 120 for r in results), results


def test_call_ops_retries_locked() -> None:
    from server import db, mcp_dispatch

    assert db.is_db_locked_error(sqlite3.OperationalError("database is locked"))
    assert not db.is_db_locked_error(ValueError("nope"))

    async def _boom() -> str:
        raise sqlite3.OperationalError("database is locked")

    async def _run() -> None:
        try:
            await mcp_dispatch._call_ops(_boom)
            raise AssertionError("should raise")
        except ValueError as exc:
            assert "数据库正忙" in str(exc), exc

    asyncio.run(_run())
