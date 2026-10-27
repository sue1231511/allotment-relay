#!/usr/bin/env python3
"""数量 / 单价 / 票数输入校验回归：负数与 0 一律拒绝，正常买卖照常。

对应审计报告 A（plot buy 负数）、B/B2（市场负数量/负单价）、C（合约、公仓、
联盟周目标、交换台）以及 db 层第二道防线。
"""
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


async def _enroll(db, email: str, name: str, tickets: int = 1000) -> tuple[int, int]:
    key = await db.create_api_key(email)
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], name, "", "naturalist", "")
    async with db.connect() as conn:
        sid = (await (await conn.execute(
            "SELECT id FROM stewards WHERE key_id=?", (row["id"],)
        )).fetchone())[0]
        await conn.execute(
            "UPDATE stewards SET tickets=?, energy=100, health=100 WHERE id=?",
            (tickets, sid),
        )
        await conn.commit()
    return row["id"], sid


async def _tickets(db, sid: int) -> int:
    async with db.connect() as conn:
        return int((await (await conn.execute(
            "SELECT tickets FROM stewards WHERE id=?", (sid,)
        )).fetchone())[0])


async def _give(db, sid: int, item: str, qty: int) -> None:
    async with db.connect() as conn:
        await db.add_item(conn, sid, item, qty)
        await conn.commit()


async def _qty(db, sid: int, item: str) -> int:
    return int((await db.get_satchel(sid)).get(item, 0))


async def _plot_refused(coro, *needles: str) -> str:
    """plot_ops 把 ValueError 包成「⚠ …」文本返回，不抛。"""
    text = await coro
    assert text.startswith("⚠"), text
    for n in needles:
        assert n in text, (n, text)
    return text


async def _rejects(coro, *needles: str) -> str:
    try:
        await coro
    except ValueError as exc:
        text = str(exc)
        for n in needles:
            assert n in text, (n, text)
        return text
    raise AssertionError("应当被拒绝，但成功了")


# ── 纯解析 ────────────────────────────────────────────────────────────────
def test_parse_positive_int() -> None:
    from server.inputs import INPUT_MAX, parse_positive_int

    assert parse_positive_int("3") == 3
    assert parse_positive_int("x5") == 5
    assert parse_positive_int("#7;") == 7
    assert parse_positive_int("１２") == 12
    for bad in ("0", "-1", "-100000", "1.5", "abc", "", "²"):
        with pytest.raises(ValueError):
            parse_positive_int(bad)
    with pytest.raises(ValueError):
        parse_positive_int(str(INPUT_MAX + 1))
    assert parse_positive_int(str(INPUT_MAX)) == INPUT_MAX


# ── db 第二道防线 ─────────────────────────────────────────────────────────
def test_db_layer_rejects_non_positive() -> None:
    asyncio.run(_test_db_layer())


async def _test_db_layer() -> None:
    db = await _boot(Path(tempfile.mkdtemp(prefix="inval-db-")))
    _, sid = await _enroll(db, "d@x.com", "底层号", 100)
    await _give(db, sid, "crop_kale", 2)
    async with db.connect() as conn:
        for bad in (0, -1, -50):
            await _rejects(db.add_item(conn, sid, "crop_kale", bad))
            await _rejects(db.take_item(conn, sid, "crop_kale", bad))
            await _rejects(db.spend_tickets(conn, sid, bad, reason="t"))
            await _rejects(db.grant_tickets(conn, sid, bad, reason="t"))
        await conn.commit()
    assert await _qty(db, sid, "crop_kale") == 2
    assert await _tickets(db, sid) == 100
    # 正常路径
    async with db.connect() as conn:
        assert await db.take_item(conn, sid, "crop_kale", 2) is True
        assert await db.take_item(conn, sid, "crop_kale", 1) is False
        await db.add_item(conn, sid, "crop_kale", 3)
        assert await db.spend_tickets(conn, sid, 40, reason="t") == 60
        await db.grant_tickets(conn, sid, 5, reason="t")
        await _rejects(db.spend_tickets(conn, sid, 10**6, reason="t"), "不足")
        await conn.commit()
    assert await _qty(db, sid, "crop_kale") == 3
    assert await _tickets(db, sid) == 65


# ── A：plot_ops buy ───────────────────────────────────────────────────────
def test_plot_buy_negative() -> None:
    asyncio.run(_test_plot_buy())


async def _test_plot_buy() -> None:
    from server import game

    db = await _boot(Path(tempfile.mkdtemp(prefix="inval-plot-")))
    kid, sid = await _enroll(db, "a@x.com", "甲甲", 1000)
    seed0 = await _qty(db, sid, "seed_kale")
    for bad in ("-100000", "-1", "0", "1.5"):
        await _plot_refused(game.plot_ops(kid, f"buy {bad} 甘蓝"))
    assert await _tickets(db, sid) == 1000
    assert await _qty(db, sid, "seed_kale") == seed0
    msg = await game.plot_ops(kid, "buy 3 甘蓝")
    assert "x3" in msg
    assert await _tickets(db, sid) == 1000 - 7 * 3
    assert await _qty(db, sid, "seed_kale") == seed0 + 3
    await _plot_refused(game.plot_ops(kid, "buy 999999 甘蓝"), "不足")


# ── vend ─────────────────────────────────────────────────────────────────
def test_vend_negative() -> None:
    asyncio.run(_test_vend())


async def _test_vend() -> None:
    from server.game import tote

    db = await _boot(Path(tempfile.mkdtemp(prefix="inval-vend-")))
    kid, sid = await _enroll(db, "v@x.com", "卖货号", 1000)
    await _give(db, sid, "crop_kale", 3)
    for bad in ("-50", "0"):
        await _rejects(tote.tote_ops(kid, f"vend 甘蓝 {bad}"))
    assert await _qty(db, sid, "crop_kale") == 3
    assert await _tickets(db, sid) == 1000
    await tote.tote_ops(kid, "vend 甘蓝 2")
    assert await _qty(db, sid, "crop_kale") == 1
    assert await _tickets(db, sid) == 1000 + 16 * 2
    # 送礼
    _, peer = await _enroll(db, "p@x.com", "收礼号", 0)
    for bad in ("-5", "0"):
        await _rejects(tote.tote_ops(kid, f"gift 收礼号 票 {bad}"))
    await tote.tote_ops(kid, "gift 收礼号 票 10")
    assert await _tickets(db, peer) == 10


# ── B / B2：集市 ─────────────────────────────────────────────────────────
def test_market_negative_and_legacy() -> None:
    asyncio.run(_test_market())


async def _test_market() -> None:
    from server import market

    db = await _boot(Path(tempfile.mkdtemp(prefix="inval-mkt-")))
    ka, a = await _enroll(db, "a@x.com", "挂单号", 100)
    kb, b = await _enroll(db, "b@x.com", "买家号", 100)
    await _give(db, a, "crop_kale", 5)
    for q, p in (("-1000", "5"), ("0", "5"), ("1", "-1000000000"), ("1", "0")):
        await _rejects(market.market_ops(ka, f"sell crop_kale {q} {p}"))
    assert await _qty(db, a, "crop_kale") == 5
    await market.market_ops(ka, "sell crop_kale 2 10")
    assert await _qty(db, a, "crop_kale") == 3
    for bad in ("-1", "0"):
        await _rejects(market.market_ops(kb, f"buy 1 {bad}"))
    await market.market_ops(kb, "buy 1 1")
    assert await _tickets(db, b) == 100 - 10 - 2
    assert await _tickets(db, a) == 100 + 10
    assert await _qty(db, b, "crop_kale") == 1

    # 旧数据：线上可能已有负价/负量挂单。不能被买，卖家能撤（只删记录，不退负数货）
    async with db.connect() as conn:
        await conn.execute(
            "INSERT INTO market_listings (seller_id, item, quantity, price, suggested, note, created_at)"
            " VALUES (?,?,?,?,?,?,?)", (a, "crop_kale", 1, -999, 16, "", db.now()))
        await conn.execute(
            "INSERT INTO market_listings (seller_id, item, quantity, price, suggested, note, created_at)"
            " VALUES (?,?,?,?,?,?,?)", (a, "crop_kale", -500, 5, 16, "", db.now()))
        await conn.commit()
        rows = await (await conn.execute(
            "SELECT id, quantity, price FROM market_listings WHERE buyer_id IS NULL")).fetchall()
    bad_ids = [r[0] for r in rows if r[1] < 1 or r[2] < 1]
    assert len(bad_ids) == 2
    t_b = await _tickets(db, b)
    for lid in bad_ids:
        await _rejects(market.market_ops(kb, f"buy {lid}"), "异常")
    assert await _tickets(db, b) == t_b
    kale_a = await _qty(db, a, "crop_kale")
    for lid in bad_ids:
        await market.market_ops(ka, f"cancel {lid}")
    # 正数量那单（负价）退 1 件；负数量那单只删记录、不凭空发货
    assert await _qty(db, a, "crop_kale") == kale_a + 1


# ── C：合约 / 公仓 / 联盟周目标 / 交换台 ─────────────────────────────────
def test_contract_larder_league_swap() -> None:
    asyncio.run(_test_family_c())


async def _test_family_c() -> None:
    from server import multi
    from server.game import shed

    db = await _boot(Path(tempfile.mkdtemp(prefix="inval-c-")))
    ka, a = await _enroll(db, "a@x.com", "发布号", 500)
    kb, b = await _enroll(db, "b@x.com", "交付号", 500)
    await _give(db, b, "crop_kale", 2)
    await _give(db, b, "crop_beet", 2)

    # 合约：发布时拒绝
    for q, r in (("-500", "1"), ("0", "1"), ("1", "-5"), ("1", "0")):
        await _rejects(multi.contract_ops(ka, f"post crop_kale {q} {r}"))
    await _rejects(multi.contract_ops(ka, "post 看护 -3 30"))
    await _rejects(multi.contract_ops(ka, "post 看护 3 -30"))
    assert await _tickets(db, a) == 500
    # 合约：正常发布 + 交付
    await multi.contract_ops(ka, "post crop_kale 2 40")
    assert await _tickets(db, a) == 460
    await multi.contract_ops(kb, "fill 1")
    assert await _tickets(db, b) == 540
    assert await _qty(db, b, "crop_kale") == 0
    assert await _qty(db, a, "crop_kale") == 2

    # 合约：旧数据里的负数量/零酬劳合约不能交付，发布人能撤
    async with db.connect() as conn:
        await conn.execute(
            "INSERT INTO contracts (poster_id, want_item, want_qty, reward_tickets, created_at)"
            " VALUES (?,?,?,?,?)", (a, "crop_beet", -500, 1, db.now()))
        await conn.commit()
    beet_b = await _qty(db, b, "crop_beet")
    await _rejects(multi.contract_ops(kb, "fill 2"), "异常")
    assert await _qty(db, b, "crop_beet") == beet_b

    # 公仓 donate / draw、联盟周目标 contribute
    for bad in ("-300", "0"):
        await _rejects(multi.alliance_ops(kb, f"donate crop_beet {bad}"))
        await _rejects(multi.alliance_ops(kb, f"draw crop_beet {bad}"))
        await _rejects(multi.league_ops(kb, f"contribute crop_beet {bad}"))
    assert await _qty(db, b, "crop_beet") == beet_b
    await multi.alliance_ops(kb, "donate crop_beet 1")
    assert await _qty(db, b, "crop_beet") == beet_b - 1
    async with db.connect() as conn:
        row = await (await conn.execute("SELECT quantity FROM larder WHERE item='crop_beet'")).fetchone()
    assert row[0] == 1

    # 交换台
    for bad in ("-300", "0"):
        await _rejects(shed.swap_ops(kb, f"offer crop_beet {bad}"))
    assert await _qty(db, b, "crop_beet") == beet_b - 1
    await shed.swap_ops(kb, "offer crop_beet 1")
    assert await _qty(db, b, "crop_beet") == beet_b - 2
    # 旧数据：负数量挂单不能领，挂单人撤掉只删记录
    async with db.connect() as conn:
        await conn.execute(
            "INSERT INTO swap_lots (depositor_id, item, quantity, note, created_at) VALUES (?,?,?,?,?)",
            (b, "crop_beet", -300, "", db.now()))
        lot = (await (await conn.execute("SELECT MAX(id) FROM swap_lots")).fetchone())[0]
        await conn.commit()
    await _rejects(shed.swap_ops(ka, f"claim {lot}"), "异常")
    before = await _qty(db, b, "crop_beet")
    await shed.swap_ops(kb, f"cancel {lot}")
    assert await _qty(db, b, "crop_beet") == before


# ── 其余数量入口：0 不再被悄悄当成 1 ─────────────────────────────────────
def test_zero_is_not_silently_one() -> None:
    asyncio.run(_test_zero())


async def _test_zero() -> None:
    from server import tt, kitchen

    db = await _boot(Path(tempfile.mkdtemp(prefix="inval-zero-")))
    kid, sid = await _enroll(db, "z@x.com", "零号号", 1000)
    await _rejects(tt.tt_ops(kid, "buy 动物饲料 0"))
    await _rejects(tt.tt_ops(kid, "gift 票 0"))
    await _rejects(kitchen.kitchen_ops(kid, "store 甘蓝 0"))
    assert await _tickets(db, sid) == 1000
    await tt.tt_ops(kid, "buy 动物饲料 2")
    assert await _qty(db, sid, "feed_animal") == 2


# ── HTTP /v1 层：≤0 返回 400，不再被悄悄当成 1 ───────────────────────────
def test_v1_qty_rejects_non_positive() -> None:
    asyncio.run(_test_v1())


async def _test_v1() -> None:
    from server.v1 import farm_service, place_service, shop_service
    from server.v1.errors import ApiError, clean_qty

    db = await _boot(Path(tempfile.mkdtemp(prefix="inval-v1-")))
    kid, sid = await _enroll(db, "h@x.com", "网页号", 1000)
    for bad in (-5, 0):
        for call in (
            lambda b=bad: shop_service.buy("k", kid, "动物饲料", b),
            lambda b=bad: farm_service.buy("k", kid, "甘蓝", b),
            lambda b=bad: place_service.vend("k", kid, "甘蓝", b),
        ):
            with pytest.raises(ApiError):
                await call()
    assert await _tickets(db, sid) == 1000
    assert clean_qty(None, 24) == 1
    assert clean_qty(500, 24) == 24


if __name__ == "__main__":
    test_parse_positive_int()
    for fn in (_test_db_layer, _test_plot_buy, _test_vend, _test_market, _test_family_c, _test_zero, _test_v1):
        asyncio.run(fn())
    print("ok")
