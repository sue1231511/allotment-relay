#!/usr/bin/env python3
"""Tt酱退货：回收价 = 该玩家此刻的买入价 × 0.9。同一个人、同一时刻，买入价恒大于回收价。"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_refund_is_nine_tenths_of_current_buy_price() -> None:
    from server import pricing, tt

    checked = 0
    for item, base, kind in tt.shop_skus():
        if pricing.is_token(item):
            continue
        for h in range(0, 11):
            buy = base if kind == "dowry" else tt.sale_price(base, h * 10)
            refund = pricing.refund_for_player(item, h)
            assert refund == buy * 9 // 10, (item, h, buy, refund)
            assert refund < buy, (item, h, buy, refund)
            checked += 1
    assert checked > 1000


def test_durian_seed_refund_follows_hearts() -> None:
    from server import pricing

    assert pricing.refund_for_player("seed_durian", 0) == 43      # 买 48，退 43
    assert pricing.refund_for_player("seed_durian", 10) == 32     # 满心买 36，退 32


def test_tokens_are_not_refundable() -> None:
    from server import pricing, tt
    from server.catalog import suggested_price

    for token in pricing.TOKEN_ITEMS:
        assert pricing.refund_for_player(token, 10) == 0
        assert suggested_price(token) == 0
        assert tt.refund_price(token, 100) is None


def test_grown_crop_still_sells_full() -> None:
    from server.catalog import CROPS, suggested_price

    assert suggested_price("crop_kale") == CROPS["kale"]["sell"]


async def _boot(tmp: Path):
    os.environ["DATA_DIR"] = str(tmp)
    from server import config, db

    config.DATA_DIR = tmp
    config.DB_PATH = tmp / "relay.db"
    db.DATA_DIR = tmp
    db.DB_PATH = tmp / "relay.db"
    await db.init_db()
    return db


def test_buy_then_return_always_loses() -> None:
    asyncio.run(_test_buy_then_return())


async def _test_buy_then_return() -> None:
    """满心 7.5 折买、再退：每一轮都亏，亏不超过一成+取整。"""
    from server import tt
    from server.game import tote

    db = await _boot(Path(tempfile.mkdtemp(prefix="ttflip-")))
    key = await db.create_api_key("t@x.com")
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], "倒卖号", "", "naturalist", "")
    async with db.connect() as conn:
        sid = (await (await conn.execute("SELECT id FROM stewards WHERE key_id=?", (row["id"],))).fetchone())[0]
        await conn.execute("UPDATE stewards SET tickets=10000, energy=100 WHERE id=?", (sid,))
        await conn.execute(
            "INSERT INTO tt_affinity (steward_id, score, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(steward_id) DO UPDATE SET score=excluded.score", (sid, 100, db.now()))
        await conn.commit()
    for item in ("seed_fogpea", "seed_kale", "tool_milker", "feed_animal", "bait_worm"):
        qty = 1 if item.startswith("tool_") else 40
        for _ in range(3):
            async with db.connect() as conn:
                before = (await (await conn.execute("SELECT tickets FROM stewards WHERE id=?", (sid,))).fetchone())[0]
            await tt.tt_ops(row["id"], f"buy {item} {qty}")
            await tote.tote_ops(row["id"], f"vend {item} {qty}")
            async with db.connect() as conn:
                after = (await (await conn.execute("SELECT tickets FROM stewards WHERE id=?", (sid,))).fetchone())[0]
            assert after < before, (item, before, after)


if __name__ == "__main__":
    test_refund_is_nine_tenths_of_current_buy_price()
    test_durian_seed_refund_follows_hearts()
    test_tokens_are_not_refundable()
    test_grown_crop_still_sells_full()
    test_buy_then_return_always_loses()
    print("ok")
