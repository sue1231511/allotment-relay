#!/usr/bin/env python3
"""集市「我的摊」视图 — 摊主独立查询，不受街摊展示窗口截断。

线上症状：我的摊 0/12 且街摊翻不到自己的单号，market_ops mine 却能读到。
根因是 player_view 从街摊 LIMIT 窗口里筛自己的单，挂单多时老单被截掉。
"""
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


async def _insert_listing(db, seller_id: int, item: str, seq: int, price: int = 9) -> None:
    async with db.connect() as conn:
        await conn.execute(
            """
            INSERT INTO market_listings
            (seller_id, item, quantity, price, suggested, note, created_at)
            VALUES (?,?,?,?,?,?,?)
            """,
            (seller_id, item, 1, price, price, "", f"2026-01-01T00:{seq // 60:02d}:{seq % 60:02d}"),
        )
        await conn.commit()


async def _sell_with_gust(db, market, kid: int, cmd: str) -> None:
    """挂单可能掷中摊险被拦；按玩家路子先稳摊再挂。"""
    for _ in range(6):
        try:
            await market.market_ops(kid, cmd)
            return
        except ValueError as exc:
            if "稳摊" not in str(exc):
                raise
            await market.market_ops(kid, "摊险 压石")
    raise AssertionError(f"摊险循环：{cmd}")


def test_market_mine_view() -> None:
    asyncio.run(_test_market_mine_view())


async def _test_market_mine_view() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="market-mine-view-"))
    db = await _boot(tmp)
    from server import config, game, market

    kid, sid = await _enroll(db, "mine@example.com", "早摊主")
    okid, osid = await _enroll(db, "other@example.com", "夜摊客")
    s = await game.require_steward(kid, exempt_duty=True)

    # 早摊主挂满 12 格（扩到顶），单号落在最前
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET market_extra=? WHERE id=?",
            (config.MARKET_LIST_SLOTS_MAX - config.MARKET_LIST_MAX, sid),
        )
        await db.add_item(conn, sid, "crop_kale", 12)
        await conn.commit()
    for i in range(12):
        await _sell_with_gust(db, market, kid, f"sell 甘蓝 1 {8 + i}")

    # 夜摊客随后挂 70 单，把早摊主全部挤出街摊窗口
    for i in range(70):
        await _insert_listing(db, osid, "grape", 100 + i)

    async with db.connect() as conn:
        view = await market.player_view(conn, s)

    # 我的摊：摊主独立查询，全量 12/12，不受街摊窗口截断
    mine = view["mine"]
    assert mine["used"] == 12, f"mine.used={mine['used']}，应为 12（摊主独立查询）"
    assert len(mine["listings"]) == 12, len(mine["listings"])
    badge = next(t["badge"] for t in view["tabs"] if t["key"] == "mine")
    assert badge == "12/12", badge

    # 街摊窗口 60：只装得下最新的 60 单，早摊主的老单沉底不可见（符合窗口语义）
    listings = view["listings"]
    assert len(listings) == 60, len(listings)

    # 挂得再多，我的摊也不丢单
    for i in range(40):
        await _insert_listing(db, osid, "turmeric", 200 + i)
    async with db.connect() as conn:
        view = await market.player_view(conn, s)
    assert view["mine"]["used"] == 12, view["mine"]["used"]

    # 摊主名：票不够买的格子也要写摊主名，玩家不用猜
    async with db.connect() as conn:
        await conn.execute("UPDATE stewards SET tickets=0 WHERE id=?", (sid,))
        await conn.commit()
    s = await game.require_steward(kid, exempt_duty=True)
    async with db.connect() as conn:
        view = await market.player_view(conn, s)
    affordable = [r for r in view["listings"] if r["can_buy"]]
    locked = [r for r in view["listings"] if not r["can_buy"] and not r["mine"]]
    assert not affordable, "票已清零，不该有买得起的单"
    for row in locked:
        assert row["seller"] in row["note"], (
            f"#{row['id']} 票不够的格子没写摊主名：{row['note']}"
        )


if __name__ == "__main__":
    test_market_mine_view()
    print("ok")
