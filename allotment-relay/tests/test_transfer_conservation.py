#!/usr/bin/env python3
"""玩家之间的渠道（集市、送礼、打赏、合约）只守恒：票只能转移，手续费只能是消耗。"""
from __future__ import annotations

import asyncio
import os
import random
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


async def _enroll(db, email: str, name: str, tickets: int) -> tuple[int, int]:
    key = await db.create_api_key(email)
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], name, "", "naturalist", "")
    async with db.connect() as conn:
        sid = (await (await conn.execute("SELECT id FROM stewards WHERE key_id=?", (row["id"],))).fetchone())[0]
        await conn.execute("UPDATE stewards SET tickets=?, energy=100, health=100 WHERE id=?", (tickets, sid))
        await conn.commit()
    return row["id"], sid


def test_transfers_conserve_tickets(monkeypatch) -> None:
    from server import market_stall_gust

    async def _no_gust(conn, steward_id):
        return ""

    monkeypatch.setattr(market_stall_gust, "maybe_after_sell", _no_gust)
    asyncio.run(_run())


async def _run() -> None:
    from server import bar, config, market, multi
    from server.game import tote

    db = await _boot(Path(tempfile.mkdtemp(prefix="conserve-")))
    names = ["守恒甲", "守恒乙", "守恒丙"]
    keys, sids = [], []
    for i, n in enumerate(names):
        k, s = await _enroll(db, f"c{i}@x.com", n, 2000)
        keys.append(k)
        sids.append(s)
    day = db.day_id()
    async with db.connect() as conn:
        for s in sids:
            await conn.execute(
                "INSERT INTO bar_shifts (steward_id, day, job, period, created_at) VALUES (?,?,?,?,?)",
                (s, day, "dish", "night", db.now()))
            await db.add_item(conn, s, "crop_kale", 30)
        for i in range(3):
            for j in range(i + 1, 3):
                await multi._bump_rapport(conn, sids[i], sids[j], 120)   # 协作度全满：打赏加成、各种福利全开
        await bar._ensure_daily_state(conn)    # 今天营业额池 = 0
        await conn.commit()

    async def pockets() -> int:
        async with db.connect() as conn:
            row = await (await conn.execute(
                "SELECT COALESCE(SUM(tickets),0) FROM stewards WHERE id IN (?,?,?)", tuple(sids))).fetchone()
        return int(row[0])

    async def escrow() -> int:
        async with db.connect() as conn:
            row = await (await conn.execute(
                "SELECT COALESCE(SUM(reward_tickets),0) FROM contracts WHERE status IN ('open','taken')")).fetchone()
        return int(row[0])

    start = await pockets()
    fees = 0
    done = {k: 0 for k in ('gift', 'tip', 'sell', 'buy', 'post', 'fill')}
    rng = random.Random(42)
    for step in range(300):
        i = rng.randrange(3)
        j = (i + 1 + rng.randrange(2)) % 3
        op = rng.choice(["gift", "tip", "sell", "buy", "post", "fill"])
        try:
            if op == "gift":
                await tote.tote_ops(keys[i], f"gift {names[j]} 票 {rng.randint(1, 50)}")
            elif op == "tip":
                await bar.bar_ops(keys[i], f"tip {names[j]} {rng.randint(1, 60)}")
            elif op == "sell":
                await market.market_ops(keys[i], f"sell crop_kale {rng.randint(1, 3)} {rng.randint(1, 30)}")
            elif op == "buy":
                async with db.connect() as conn:
                    rows = await (await conn.execute(
                        "SELECT id FROM market_listings WHERE buyer_id IS NULL AND seller_id!=?", (sids[i],))).fetchall()
                if rows:
                    await market.market_ops(keys[i], f"buy {rng.choice(rows)[0]} 1")
                    fees += config.MARKET_FEE
            elif op == "post":
                await multi.contract_ops(keys[i], f"post crop_kale {rng.randint(1, 3)} {rng.randint(1, 40)}")
            else:
                async with db.connect() as conn:
                    rows = await (await conn.execute(
                        "SELECT id, reward_tickets FROM contracts WHERE status='open' AND kind!='labor' AND poster_id!=?",
                        (sids[i],))).fetchall()
                if rows:
                    await multi.contract_ops(keys[i], f"fill {rng.choice(rows)[0]}")
        except ValueError:
            continue
        done[op] += 1
        # 每一步之后：口袋 + 托管 + 已烧手续费 == 起点（营业额池是 0，打赏没有加成）
        assert await pockets() + await escrow() + fees == start + 0, (step, op)
    assert all(v >= 5 for v in done.values()), done
