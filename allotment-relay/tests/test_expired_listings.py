#!/usr/bin/env python3
"""过期挂单不能成交：集市、交换台、公仓、悬赏交付；买家/领取人一分钱不扣，过期的货按变质丢弃规则清掉并写纪事。"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

H = 3600


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
        sid = (await (await conn.execute("SELECT id FROM stewards WHERE key_id=?", (row["id"],))).fetchone())[0]
        await conn.execute(
            "UPDATE stewards SET tickets=1000, energy=100, health=100, last_active_at=?, last_bar_shift_at=? WHERE id=?",
            (db.now(), db.now(), sid),
        )
        await conn.commit()
    return row["id"], sid


def _travel(monkeypatch, db, hours: float) -> None:
    real = db.now
    monkeypatch.setattr(db, "now", lambda: real() + int(hours * H))


async def _duty(db, *sids: int) -> None:
    async with db.connect() as conn:
        for sid in sids:
            await conn.execute(
                "UPDATE stewards SET last_active_at=?, last_bar_shift_at=? WHERE id=?", (db.now(), db.now(), sid))
        await conn.commit()


async def _tickets(db, sid: int) -> int:
    async with db.connect() as conn:
        return int((await (await conn.execute("SELECT tickets FROM stewards WHERE id=?", (sid,))).fetchone())[0])


async def _qty(db, sid: int, item: str) -> int:
    async with db.connect() as conn:
        row = await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item=?", (sid, item))).fetchone()
    return int(row[0]) if row else 0


async def _spoil_log(db, actor: int | None) -> list[str]:
    async with db.connect() as conn:
        if actor is None:
            rows = await (await conn.execute(
                "SELECT text FROM chronicle WHERE action='spoil' AND actor_id IS NULL")).fetchall()
        else:
            rows = await (await conn.execute(
                "SELECT text FROM chronicle WHERE action='spoil' AND actor_id=?", (actor,))).fetchall()
    return [r[0] for r in rows]


@pytest.fixture(autouse=True)
def _no_gust(monkeypatch):
    from server import market_stall_gust

    async def _noop(conn, steward_id):
        return ""

    monkeypatch.setattr(market_stall_gust, "maybe_after_sell", _noop)


ITEM = "fish_herring"      # 鱼 36 小时


def test_expired_market_listing_cannot_be_bought_and_buyer_pays_nothing(monkeypatch) -> None:
    asyncio.run(_market_full(monkeypatch))


async def _market_full(monkeypatch) -> None:
    from server import item_traits, market

    db = await _boot(Path(tempfile.mkdtemp(prefix="exp-mkt-")))
    ka, a = await _enroll(db, "a@x.com", "卖家")
    kb, b = await _enroll(db, "b@x.com", "买家")
    async with db.connect() as conn:
        await item_traits.grant_satchel(conn, a, ITEM, 5)
        await conn.commit()
    await market.market_ops(ka, f"sell {ITEM} 5 10")
    _travel(monkeypatch, db, 40)
    await _duty(db, a, b)
    a0, b0 = await _tickets(db, a), await _tickets(db, b)
    with pytest.raises(ValueError) as exc:
        await market.market_ops(kb, "buy 1")
    assert "已经变质" in str(exc.value) and "没有扣你的票" in str(exc.value)
    assert await _tickets(db, b) == b0, "买家不扣票（含手续费）"
    assert await _tickets(db, a) == a0, "卖家也没收到钱"
    assert await _qty(db, b, ITEM) == 0
    async with db.connect() as conn:
        left = (await (await conn.execute("SELECT COUNT(*) FROM market_listings WHERE buyer_id IS NULL")).fetchone())[0]
        stray = (await (await conn.execute(
            "SELECT COUNT(*) FROM item_trait_batches WHERE steward_id=0 AND loc LIKE 'market:%'")).fetchone())[0]
    assert left == 0 and stray == 0, "过期挂单被清掉，不留残批"
    log = await _spoil_log(db, a)
    assert any("集市挂单#1" in t and "x5" in t and "已变质" in t for t in log), log


def test_partly_expired_listing_sells_only_fresh_goods(monkeypatch) -> None:
    asyncio.run(_market_partial(monkeypatch))


async def _market_partial(monkeypatch) -> None:
    from server import item_traits, market

    db = await _boot(Path(tempfile.mkdtemp(prefix="exp-part-")))
    ka, a = await _enroll(db, "a@x.com", "卖家")
    kb, b = await _enroll(db, "b@x.com", "买家")
    async with db.connect() as conn:
        await item_traits.grant_satchel(conn, a, ITEM, 3)          # 老的 3 条
        await conn.commit()
    _travel(monkeypatch, db, 30)
    await _duty(db, a, b)
    async with db.connect() as conn:
        await item_traits.grant_satchel(conn, a, ITEM, 2)          # 新的 2 条（+30h 才到）
        await conn.commit()
    await market.market_ops(ka, f"sell {ITEM} 5 10")                 # 先进先出：3 老 + 2 新一起挂
    _travel(monkeypatch, db, 10)                                     # 共 40h：老的 3 条过期，新的 2 条还新鲜
    await _duty(db, a, b)
    b0, a0 = await _tickets(db, b), await _tickets(db, a)
    with pytest.raises(ValueError) as exc:
        await market.market_ops(kb, "buy 1 5")                       # 想买 5 条，只剩 2 条新鲜
    assert "数量不对" in str(exc.value)
    assert await _tickets(db, b) == b0
    async with db.connect() as conn:
        qty = (await (await conn.execute("SELECT quantity FROM market_listings WHERE id=1")).fetchone())[0]
    assert qty == 2, "拒绝时过期的 3 条也已经清掉并落库"
    reply = await market.market_ops(kb, "buy 1 2")
    assert "x2" in reply
    assert await _qty(db, b, ITEM) == 2
    assert await _tickets(db, b) == b0 - (2 * 10 + 2)               # 2 条 × 10 + 手续费 2
    assert await _tickets(db, a) == a0 + 20
    log = await _spoil_log(db, a)
    assert sum("x3" in t for t in log) == 1, log


def test_market_list_view_cleans_expired_listings(monkeypatch) -> None:
    asyncio.run(_market_views(monkeypatch))


async def _market_views(monkeypatch) -> None:
    from server import item_traits, market

    db = await _boot(Path(tempfile.mkdtemp(prefix="exp-view-")))
    ka, a = await _enroll(db, "a@x.com", "卖家")
    kb, b = await _enroll(db, "b@x.com", "路人")
    async with db.connect() as conn:
        await item_traits.grant_satchel(conn, a, ITEM, 4)
        await conn.commit()
    await market.market_ops(ka, f"sell {ITEM} 4 10")
    _travel(monkeypatch, db, 40)
    await _duty(db, a, b)
    listing = await market.market_ops(kb, "list")
    assert "变质清理" in listing and "×4" in listing and "#1" in listing
    assert "x4" not in listing.split("变质清理")[1].split("\n", 1)[-1]
    assert "集市暂无挂单" in listing


def test_expired_swap_lot_cannot_be_claimed_and_no_fee(monkeypatch) -> None:
    asyncio.run(_swap(monkeypatch))


async def _swap(monkeypatch) -> None:
    from server import item_traits
    from server.game import shed

    db = await _boot(Path(tempfile.mkdtemp(prefix="exp-swap-")))
    ka, a = await _enroll(db, "a@x.com", "挂单人")
    kb, b = await _enroll(db, "b@x.com", "领取人")
    async with db.connect() as conn:
        await item_traits.grant_satchel(conn, a, ITEM, 5)
        await conn.commit()
    await shed.swap_ops(ka, f"offer {ITEM} 5")
    _travel(monkeypatch, db, 40)
    await _duty(db, a, b)
    b0 = await _tickets(db, b)
    with pytest.raises(ValueError) as exc:
        await shed.swap_ops(kb, "claim 1")
    assert "已经变质" in str(exc.value) and "没有收你的领取费" in str(exc.value)
    assert await _tickets(db, b) == b0
    assert await _qty(db, b, ITEM) == 0
    async with db.connect() as conn:
        left = (await (await conn.execute("SELECT COUNT(*) FROM swap_lots WHERE claimed_by IS NULL")).fetchone())[0]
    assert left == 0
    assert any("交换台挂单#1" in t and "x5" in t for t in await _spoil_log(db, a))


def test_expired_larder_goods_cannot_be_drawn_and_no_fee(monkeypatch) -> None:
    asyncio.run(_larder(monkeypatch))


async def _larder(monkeypatch) -> None:
    from server import item_traits, multi

    db = await _boot(Path(tempfile.mkdtemp(prefix="exp-larder-")))
    ka, a = await _enroll(db, "a@x.com", "捐赠人")
    kb, b = await _enroll(db, "b@x.com", "领取人")
    async with db.connect() as conn:
        await item_traits.grant_satchel(conn, a, ITEM, 5)
        await conn.commit()
    await multi.alliance_ops(ka, f"donate {ITEM} 5")
    _travel(monkeypatch, db, 40)
    await _duty(db, a, b)
    b0 = await _tickets(db, b)
    with pytest.raises(ValueError) as exc:
        await multi.alliance_ops(kb, f"draw {ITEM} 2")
    assert "库存不足" in str(exc.value) and "没有扣你的领取费" in str(exc.value)
    assert await _tickets(db, b) == b0 and await _qty(db, b, ITEM) == 0
    async with db.connect() as conn:
        row = await (await conn.execute("SELECT quantity FROM larder WHERE item=?", (ITEM,))).fetchone()
    assert (row[0] if row else 0) == 0
    assert any("联盟储藏室" in t and "x5" in t for t in await _spoil_log(db, None))


def test_contract_fill_rejects_rotten_goods_and_poster_escrow_is_untouched(monkeypatch) -> None:
    asyncio.run(_contract(monkeypatch))


async def _contract(monkeypatch) -> None:
    from server import item_traits, multi

    db = await _boot(Path(tempfile.mkdtemp(prefix="exp-contract-")))
    ka, a = await _enroll(db, "a@x.com", "交付人")
    kb, b = await _enroll(db, "b@x.com", "雇主")
    async with db.connect() as conn:
        await item_traits.grant_satchel(conn, a, ITEM, 5)
        await conn.commit()
    await multi.contract_ops(kb, f"post {ITEM} 5 20")
    b_after_post = await _tickets(db, b)
    _travel(monkeypatch, db, 40)                       # 鱼在交付人背包里放了 40 小时，已变质
    await _duty(db, a, b)
    a0 = await _tickets(db, a)
    with pytest.raises(ValueError) as exc:
        await multi.contract_ops(ka, "fill 1")
    assert "变质丢弃" in str(exc.value) and "×5" in str(exc.value)
    assert await _tickets(db, a) == a0, "没交出东西，不拿酬劳"
    assert await _tickets(db, b) == b_after_post and await _qty(db, b, ITEM) == 0
    async with db.connect() as conn:
        status = (await (await conn.execute("SELECT status FROM contracts WHERE id=1")).fetchone())[0]
    assert status == "open", "合约还开着，酬劳还在托管里"
    assert await _qty(db, a, ITEM) == 0
