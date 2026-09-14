#!/usr/bin/env python3
"""plot_ops claim 编号 应落到 commons，而不是未知 plot 指令。"""
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
        await conn.execute(
            "UPDATE stewards SET tickets=400, last_bar_shift_at=? WHERE id=?",
            (db.now(), sid),
        )
        await conn.commit()
    return row["id"], sid


async def _run() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="plot-claim-"))
    db = await _boot(tmp)
    from server import mcp_dispatch as mux

    kid, _sid = await _enroll(db, "plot-claim@example.com", "拾票人")
    now = db.now()
    async with db.connect() as conn:
        cur = await conn.execute(
            """
            INSERT INTO commons_spawns (
                spawn_key, label, domain, reward_item, reward_qty,
                reward_tickets, detail, appears_at, expires_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                "test:ticket-stub",
                "档口遗票",
                "market",
                None,
                0,
                12,
                "测试领取路由",
                now - 1,
                now + 3600,
            ),
        )
        spawn_id = cur.lastrowid
        await conn.commit()

    scanned = await mux.plot_bundle(kid, "commons scan")
    assert f"#{spawn_id}" in scanned and "档口遗票" in scanned, scanned
    assert f"claim {spawn_id}" in scanned, scanned

    claimed = await mux.plot_bundle(kid, f"claim {spawn_id}")
    assert "未知 plot" not in claimed, claimed
    assert "档口遗票" in claimed or "12" in claimed or "票" in claimed, claimed

    async with db.connect() as conn:
        cur = await conn.execute(
            """
            INSERT INTO commons_spawns (
                spawn_key, label, domain, reward_item, reward_qty,
                reward_tickets, detail, appears_at, expires_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                "test:ticket-stub-2",
                "第二张遗票",
                "market",
                None,
                0,
                8,
                "测试 commons claim 路由",
                now - 1,
                now + 3600,
            ),
        )
        spawn2 = cur.lastrowid
        await conn.commit()

    claimed2 = await mux.plot_bundle(kid, f"commons claim {spawn2}")
    assert "未知 plot" not in claimed2, claimed2
    assert "第二张" in claimed2 or "8" in claimed2 or "票" in claimed2, claimed2


def test_plot_claim_route() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    test_plot_claim_route()
    print("ok")
