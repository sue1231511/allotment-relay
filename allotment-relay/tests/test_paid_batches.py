#!/usr/bin/env python3
"""实付批次账：Tt 货的退货价跟着批次走（实付 × 0.9），转手不会变成套利；批次数量始终 ≤ 背包数量。"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

import pytest

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


async def _enroll(db, email: str, name: str, *, tickets: int = 5000, score: int = 0) -> tuple[int, int]:
    key = await db.create_api_key(email)
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], name, "", "naturalist", "")
    day = db.day_id()
    async with db.connect() as conn:
        sid = (await (await conn.execute("SELECT id FROM stewards WHERE key_id=?", (row["id"],))).fetchone())[0]
        await conn.execute(
            "UPDATE stewards SET tickets=?, energy=100, health=100, last_active_at=? WHERE id=?",
            (tickets, db.now(), sid),
        )
        await conn.execute(
            "INSERT INTO bar_shifts (steward_id, day, job, period, created_at) VALUES (?,?,?,?,?)",
            (sid, day, "dish", "night", db.now()),
        )
        await conn.execute(
            "INSERT INTO tt_affinity (steward_id, score, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(steward_id) DO UPDATE SET score=excluded.score",
            (sid, score, db.now()),
        )
        await conn.commit()
    return row["id"], sid


async def _tickets(db, sid: int) -> int:
    async with db.connect() as conn:
        return int((await (await conn.execute("SELECT tickets FROM stewards WHERE id=?", (sid,))).fetchone())[0])


async def _qty(db, sid: int, item: str) -> int:
    async with db.connect() as conn:
        row = await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item=?", (sid, item))).fetchone()
    return int(row[0]) if row else 0


async def _paid_total(db, sid: int, item: str) -> int:
    from server import paid_ledger

    async with db.connect() as conn:
        return await paid_ledger.batch_total(conn, sid, item)


async def _assert_consistent(db) -> None:
    """批次账与背包/挂单一致：任何一格批次总量都不超过实际数量。"""
    from server import item_traits

    async with db.connect() as conn:
        await item_traits.ensure_trait_tables(conn)
        bad: list[str] = []
        for sid, item, tot in await (await conn.execute(
            "SELECT owner_id, item, SUM(qty) FROM paid_batches WHERE owner_kind='steward' GROUP BY owner_id, item"
        )).fetchall():
            have = await _qty_conn(conn, sid, item)
            if tot > have:
                bad.append(f"paid steward={sid} item={item} batches={tot} satchel={have}")
        for sid, item, tot in await (await conn.execute(
            "SELECT steward_id, item, SUM(qty) FROM item_trait_batches WHERE loc='satchel' GROUP BY steward_id, item"
        )).fetchall():
            have = await _qty_conn(conn, sid, item)
            if tot > have:
                bad.append(f"trait steward={sid} item={item} batches={tot} satchel={have}")
        for kind, table, qcol, where in (
            ("market", "market_listings", "quantity", "buyer_id IS NULL"),
            ("swap", "swap_lots", "quantity", "claimed_by IS NULL"),
        ):
            for ref, item, tot in await (await conn.execute(
                "SELECT owner_id, item, SUM(qty) FROM paid_batches WHERE owner_kind=? GROUP BY owner_id, item",
                (kind,),
            )).fetchall():
                row = await (await conn.execute(
                    f"SELECT {qcol} FROM {table} WHERE id=? AND {where}", (ref,))).fetchone()
                have = int(row[0]) if row else 0
                if tot > have:
                    bad.append(f"{kind} lot={ref} item={item} batches={tot} lot_qty={have}")
        for item, tot in await (await conn.execute(
            "SELECT item, SUM(qty) FROM paid_batches WHERE owner_kind='larder' GROUP BY item"
        )).fetchall():
            row = await (await conn.execute("SELECT quantity FROM larder WHERE item=?", (item,))).fetchone()
            have = int(row[0]) if row else 0
            if tot > have:
                bad.append(f"larder item={item} batches={tot} larder_qty={have}")
    assert not bad, bad


async def _qty_conn(conn, sid: int, item: str) -> int:
    row = await (await conn.execute(
        "SELECT quantity FROM satchel WHERE steward_id=? AND item=?", (sid, item))).fetchone()
    return int(row[0]) if row else 0


# ── 1. 用户要求的两条回归 ─────────────────────────────────────────────

def test_high_hearts_buy_gift_alt_refund_makes_no_profit() -> None:
    asyncio.run(_high_hearts_to_alt())


async def _high_hearts_to_alt() -> None:
    from server import pricing, tt
    from server.game import tote

    db = await _boot(Path(tempfile.mkdtemp(prefix="paid-hi-")))
    ka, a = await _enroll(db, "a@x.com", "高心号", score=100)
    kb, b = await _enroll(db, "b@x.com", "零心小号", score=0)
    for item, qty in (("tool_milker", 1), ("feed_animal", 40)):
        base = pricing.base_price(item)
        a_unit = pricing.tt_buy_price(base, 10)
        b_unit = pricing.tt_buy_price(base, 0)
        old_hole_refund = b_unit * 9 // 10           # 改版前的规则：小号按自己的 0 心价退
        assert old_hole_refund > a_unit, "这个物品得能复现旧漏洞"
        a0, b0 = await _tickets(db, a), await _tickets(db, b)
        await tt.tt_ops(ka, f"buy {item} {qty}")
        await tote.tote_ops(ka, f"gift 零心小号 {item} {qty}")
        await tote.tote_ops(kb, f"vend {item} {qty}")
        spent = a0 - await _tickets(db, a)
        got = await _tickets(db, b) - b0
        assert spent == a_unit * qty
        assert got == (a_unit * 9 // 10) * qty, (item, got, a_unit)
        assert got < spent, f"{item}: 两个号合起来必须亏钱，花 {spent} 退 {got}"
        await _assert_consistent(db)


def test_zero_hearts_self_buy_self_refund_loses_one_tenth() -> None:
    asyncio.run(_zero_hearts_self())


async def _zero_hearts_self() -> None:
    from server import pricing, tt
    from server.game import tote

    db = await _boot(Path(tempfile.mkdtemp(prefix="paid-zero-")))
    k, s = await _enroll(db, "z@x.com", "零心号", score=0)
    for item, qty in (("tool_milker", 1), ("feed_animal", 30), ("seed_fogpea", 30)):
        base = pricing.base_price(item)
        t0 = await _tickets(db, s)
        await tt.tt_ops(k, f"buy {item} {qty}")
        await tote.tote_ops(k, f"vend {item} {qty}")
        loss = t0 - await _tickets(db, s)
        paid = pricing.tt_buy_price(base, 0) * qty
        assert loss > 0
        assert loss == paid - (pricing.tt_buy_price(base, 0) * 9 // 10) * qty
        assert loss * 10 <= paid + 10 * qty, f"{item}: 亏 {loss}，应只亏约一成（花 {paid}）"
        assert await _paid_total(db, s, item) == 0
    await _assert_consistent(db)


# ── 2. 每条转手渠道：实付价跟着货走 ───────────────────────────────────

CHANNELS = ("market", "swap", "larder", "handoff_online", "handoff_offline", "contract")


@pytest.mark.parametrize("channel", CHANNELS)
def test_price_follows_the_goods_through_every_channel(channel: str, monkeypatch) -> None:
    from server import market_stall_gust

    async def _no_gust(conn, steward_id):
        return ""

    monkeypatch.setattr(market_stall_gust, "maybe_after_sell", _no_gust)
    asyncio.run(_channel(channel))


async def _channel(channel: str) -> None:
    from server import market, multi, pricing, tt
    from server.game import shed, tide, tote

    db = await _boot(Path(tempfile.mkdtemp(prefix=f"paid-{channel}-")))
    ka, a = await _enroll(db, "a@x.com", "甲高心", score=100)
    kb, b = await _enroll(db, "b@x.com", "乙零心", score=0)
    item, qty = "feed_animal", 10
    a_unit = pricing.tt_buy_price(pricing.base_price(item), 10)
    initial_total = await _tickets(db, a) + await _tickets(db, b)
    await tt.tt_ops(ka, f"buy {item} {qty}")

    if channel == "market":
        await market.market_ops(ka, f"sell {item} {qty} 1")
        await _assert_consistent(db)
        await market.market_ops(kb, "buy 1 4")
        await _assert_consistent(db)
        await market.market_ops(kb, "buy 1")
    elif channel == "swap":
        await shed.swap_ops(ka, f"offer {item} {qty}")
        await _assert_consistent(db)
        await shed.swap_ops(kb, "claim 1")
    elif channel == "larder":
        await multi.alliance_ops(ka, f"donate {item} {qty}")
        await _assert_consistent(db)
        await multi.alliance_ops(kb, f"draw {item} {qty}")
    elif channel in ("handoff_online", "handoff_offline"):
        async with db.connect() as conn:
            await conn.execute(
                "UPDATE stewards SET last_active_at=? WHERE id=?",
                (db.now() if channel == "handoff_online" else 0, b),
            )
            await conn.commit()
        await shed.shed_ops(ka, f"handoff 乙零心 {item} {qty}")
        await _assert_consistent(db)
        if channel == "handoff_offline":
            async with db.connect() as conn:
                await tide._collect_handoffs(conn, b)
                await conn.commit()
    elif channel == "contract":
        await multi.contract_ops(kb, f"post {item} {qty} 20")
        await multi.contract_ops(ka, "fill 1")
        # 乙是雇主，物品到了乙手里；甲拿了酬劳
    await _assert_consistent(db)

    receiver = b
    assert await _qty(db, receiver, item) == qty
    assert await _paid_total(db, receiver, item) == qty, "实付批次必须跟着货走"
    before = await _tickets(db, receiver)
    await tote.tote_ops(kb, f"vend {item} {qty}")
    refund = await _tickets(db, receiver) - before
    assert refund == (a_unit * 9 // 10) * qty, (channel, refund, a_unit)
    assert refund < a_unit * qty
    await _assert_consistent(db)
    # 两个号合起来：系统只在 Tt 收过一笔 (a_unit×件数)，退回的是 floor(0.9×实付)×件数；
    # 集市手续费、领取费是额外消耗，合约酬劳在两个号之间转移。合起来必须净亏。
    end_total = await _tickets(db, a) + await _tickets(db, b)
    assert end_total < initial_total, (channel, initial_total, end_total)
    assert initial_total - end_total >= a_unit * qty - refund, (channel, initial_total, end_total)


def test_market_cancel_and_partial_buy_keep_batches_consistent(monkeypatch) -> None:
    from server import market_stall_gust

    async def _no_gust(conn, steward_id):
        return ""

    monkeypatch.setattr(market_stall_gust, "maybe_after_sell", _no_gust)
    asyncio.run(_market_cancel())


async def _market_cancel() -> None:
    from server import market, pricing, tt
    from server.game import tote

    db = await _boot(Path(tempfile.mkdtemp(prefix="paid-cancel-")))
    ka, a = await _enroll(db, "a@x.com", "撤单甲", score=100)
    kb, b = await _enroll(db, "b@x.com", "买家乙", score=0)
    item = "feed_animal"
    a_unit = pricing.tt_buy_price(pricing.base_price(item), 10)
    await tt.tt_ops(ka, f"buy {item} 10")
    await market.market_ops(ka, f"sell {item} 10 1")
    assert await _paid_total(db, a, item) == 0
    await market.market_ops(kb, "buy 1 3")
    await _assert_consistent(db)
    await market.market_ops(ka, "cancel 1")
    await _assert_consistent(db)
    assert await _qty(db, a, item) == 7
    assert await _paid_total(db, a, item) == 7, "撤单要把实付批次退回卖家"
    assert await _paid_total(db, b, item) == 3
    before = await _tickets(db, a)
    await tote.tote_ops(ka, f"vend {item} 7")
    assert await _tickets(db, a) - before == (a_unit * 9 // 10) * 7


# ── 3. 来源规则 ───────────────────────────────────────────────────────

def test_unbatched_goods_refund_at_conservative_price() -> None:
    asyncio.run(_unbatched())


async def _unbatched() -> None:
    from server import pricing
    from server.game import tote

    db = await _boot(Path(tempfile.mkdtemp(prefix="paid-free-")))
    k, s = await _enroll(db, "f@x.com", "白得号", score=0)
    async with db.connect() as conn:
        await db.add_item(conn, s, "feed_animal", 20)        # 掉落/奖励：没有实付记录
        await conn.commit()
    before = await _tickets(db, s)
    await tote.tote_ops(k, "vend feed_animal 20")
    assert await _tickets(db, s) - before == pricing.ref_value("feed_animal") * 20
    assert pricing.ref_value("feed_animal") < pricing.tt_buy_price(pricing.base_price("feed_animal"), 10)


def test_plot_and_tool_shops_record_paid_price() -> None:
    asyncio.run(_other_shops())


async def _other_shops() -> None:
    from server import catalog
    from server.game import plot, tote

    db = await _boot(Path(tempfile.mkdtemp(prefix="paid-shop-")))
    k, s = await _enroll(db, "p@x.com", "杂货号", score=0)
    await plot.plot_ops(k, "buy 5 甘蓝")
    price = catalog.CROPS["kale"]["seed_price"]
    assert await _paid_total(db, s, "seed_kale") >= 5
    before = await _tickets(db, s)
    await tote.tote_ops(k, "vend seed_kale 5")
    assert await _tickets(db, s) - before == (price * 9 // 10) * 5


# ── 4. 老货补账 ───────────────────────────────────────────────────────

def test_legacy_stock_is_backfilled_once_and_changes_nothing_else() -> None:
    asyncio.run(_backfill())


async def _backfill() -> None:
    from server import paid_ledger, pricing
    from server.game import tote

    db = await _boot(Path(tempfile.mkdtemp(prefix="paid-legacy-")))
    k, s = await _enroll(db, "l@x.com", "老玩家", score=40)      # 4 心
    async with db.connect() as conn:
        await db.add_item(conn, s, "feed_animal", 12)           # 旧版买的：没有批次
        await conn.execute("DELETE FROM world_flags WHERE flag_key=?", (paid_ledger.FLAG_BACKFILL,))
        await conn.execute("DELETE FROM paid_batches")
        await conn.commit()
    tickets_before = await _tickets(db, s)
    qty_before = await _qty(db, s, "feed_animal")
    async with db.connect() as conn:
        added = await paid_ledger.backfill_legacy(conn)
        again = await paid_ledger.backfill_legacy(conn)
        await conn.commit()
    assert added >= 12 and again == 0
    assert await _tickets(db, s) == tickets_before and await _qty(db, s, "feed_animal") == qty_before
    assert await _paid_total(db, s, "feed_animal") == qty_before
    unit = pricing.tt_buy_price(pricing.base_price("feed_animal"), 4)
    t0 = await _tickets(db, s)
    await tote.tote_ops(k, f"vend feed_animal {qty_before}")
    assert await _tickets(db, s) - t0 == (unit * 9 // 10) * qty_before, "老玩家退货金额和改版前一致"
    await _assert_consistent(db)


# ── 5. 幽灵批次：取走物品时批次总是被对齐 ──────────────────────────────

def test_take_item_never_leaves_ghost_batches() -> None:
    asyncio.run(_ghosts())


async def _ghosts() -> None:
    from server import item_traits, paid_ledger

    db = await _boot(Path(tempfile.mkdtemp(prefix="paid-ghost-")))
    k, s = await _enroll(db, "g@x.com", "幽灵号", score=0)
    async with db.connect() as conn:
        await item_traits.grant_satchel(conn, s, "crop_kale", 3)
        await item_traits.grant_satchel(conn, s, "crop_kale", 2, quality="flavor")
        await db.add_item(conn, s, "feed_animal", 6)
        await paid_ledger.record_purchase(conn, s, "feed_animal", 6, 9)
        await conn.commit()
    async with db.connect() as conn:
        assert await db.take_item(conn, s, "crop_kale", 4)          # 默认：自动对齐品质批次
        assert await db.take_item(conn, s, "feed_animal", 4)
        await conn.commit()
    await _assert_consistent(db)
    assert await _paid_total(db, s, "feed_animal") == 2
    async with db.connect() as conn:
        tot = (await (await conn.execute(
            "SELECT COALESCE(SUM(qty),0) FROM item_trait_batches WHERE steward_id=? AND item='crop_kale'", (s,)
        )).fetchone())[0]
    assert tot == 1
    # 直接改表的路径用 sync_batches 对齐
    async with db.connect() as conn:
        await conn.execute("UPDATE satchel SET quantity=1 WHERE steward_id=? AND item='feed_animal'", (s,))
        await db.sync_batches(conn, s, "feed_animal")
        await conn.commit()
    await _assert_consistent(db)
    assert await _paid_total(db, s, "feed_animal") == 1


def test_gift_market_swap_do_not_leave_trait_ghosts(monkeypatch) -> None:
    from server import market_stall_gust

    async def _no_gust(conn, steward_id):
        return ""

    monkeypatch.setattr(market_stall_gust, "maybe_after_sell", _no_gust)
    asyncio.run(_trait_ghosts())


async def _trait_ghosts() -> None:
    from server import item_traits, market, multi
    from server.game import shed, tote

    db = await _boot(Path(tempfile.mkdtemp(prefix="paid-trait-")))
    ka, a = await _enroll(db, "a@x.com", "品质甲")
    kb, b = await _enroll(db, "b@x.com", "品质乙")
    async with db.connect() as conn:
        await item_traits.grant_satchel(conn, a, "crop_kale", 20)
        await conn.commit()
    await tote.tote_ops(ka, "gift 品质乙 crop_kale 3")
    await _assert_consistent(db)
    await market.market_ops(ka, "sell crop_kale 4 10")
    await _assert_consistent(db)
    await shed.swap_ops(ka, "offer crop_kale 2")
    await _assert_consistent(db)
    await multi.alliance_ops(ka, "donate crop_kale 5")
    await _assert_consistent(db)
    await market.market_ops(ka, "cancel 1")
    await _assert_consistent(db)
    await tote.tote_ops(ka, "vend crop_kale 3")
    await _assert_consistent(db)


if __name__ == "__main__":
    test_high_hearts_buy_gift_alt_refund_makes_no_profit()
    test_zero_hearts_self_buy_self_refund_loses_one_tenth()
    print("ok")
