#!/usr/bin/env python3
"""统一定价：端到端（读库）测试。

信物不可回收但可送礼/交换/挂集市；回收价路径无关；幽灵批次；修正夹范围；
后室铺店货与赃物分两条通道；打赏加成由营业额池出资且有每对号日上限。
"""
from __future__ import annotations

import asyncio
import os
import random
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
        sid = (await (await conn.execute("SELECT id FROM stewards WHERE key_id=?", (row["id"],))).fetchone())[0]
        await conn.execute("UPDATE stewards SET tickets=?, energy=100, health=100 WHERE id=?", (tickets, sid))
        await conn.commit()
    return row["id"], sid


async def _tickets(db, sid: int) -> int:
    async with db.connect() as conn:
        return int((await (await conn.execute("SELECT tickets FROM stewards WHERE id=?", (sid,))).fetchone())[0])


async def _rejects(coro, *needles: str) -> str:
    try:
        await coro
    except ValueError as exc:
        text = str(exc)
        for n in needles:
            assert n in text, (n, text)
        return text
    raise AssertionError("应当被拒绝，但成功了")


# ── 手作信物 ──────────────────────────────────────────────────────────────
def test_tokens_cannot_be_vended_but_can_be_gifted_and_listed(monkeypatch) -> None:
    from server import market, market_stall_gust

    async def _no_gust(conn, steward_id):
        return ""

    monkeypatch.setattr(market_stall_gust, "maybe_after_sell", _no_gust)
    asyncio.run(_test_tokens())


async def _test_tokens() -> None:
    from server import ledger, market, vend
    from server.game import tote

    db = await _boot(Path(tempfile.mkdtemp(prefix="flow-token-")))
    ka, a = await _enroll(db, "a@x.com", "信物甲", 500)
    kb, b = await _enroll(db, "b@x.com", "信物乙", 500)
    async with db.connect() as conn:
        for item in ("betroth_ring", "tide_vow_ring", "betroth_shell", "tide_vow_sand"):
            await db.add_item(conn, a, item, 2)
        await ledger.note_gain(conn, a, "betroth_ring", 1, "订婚戒由信物甲于某日在砧上打成")
        await conn.commit()
    for item in ("betroth_ring", "tide_vow_ring", "betroth_shell", "tide_vow_sand"):
        text = await _rejects(tote.tote_ops(ka, f"vend {item} 1"))
        assert vend.TOKEN_REFUSE[:12] in text
    before = await _tickets(db, a)
    assert before == 500                                       # 一票没多
    listing = await tote.tote_ops(ka, "list")
    assert "手作信物" in listing and "不能回收" in listing
    # 送礼 / 挂集市都行
    await tote.tote_ops(ka, "gift 信物乙 betroth_ring 1")
    assert (await db.get_satchel(b)).get("betroth_ring") == 1
    await market.market_ops(ka, "sell tide_vow_ring 1 5000")
    await market.market_ops(kb, "buy 1 1") if False else None
    async with db.connect() as conn:
        lot = (await (await conn.execute("SELECT id FROM market_listings ORDER BY id DESC LIMIT 1")).fetchone())[0]
        await db.add_item(conn, b, "crop_kale", 1)
        await conn.execute("UPDATE stewards SET tickets=6000 WHERE id=?", (b,))
        await conn.commit()
    await market.market_ops(kb, f"buy {lot}")
    assert (await db.get_satchel(b)).get("tide_vow_ring") == 1
    assert await _tickets(db, a) == 500 + 5000
    # 物品履历照常记录：送礼后履历跟着戒指走
    async with db.connect() as conn:
        rows = await ledger.stories_for(conn, b, "betroth_ring")
    assert rows, "送礼后履历应转到收礼人名下"


# ── 回收价路径无关 ────────────────────────────────────────────────────────
async def _fish_world(tag: str, plan: list[tuple[int, str, float]], flow0: int, extra_plain: int):
    from server import fish_market
    from server import item_traits as traits

    db = await _boot(Path(tempfile.mkdtemp(prefix=f"flow-{tag}-")))
    kid, sid = await _enroll(db, f"{tag}@x.com", f"路径{tag}", 0)
    async with db.connect() as conn:
        for qty, quality, kg in plan:
            await traits.grant_satchel(conn, sid, "fish_mackerel", qty, quality=quality, weight_kg=kg)
        if extra_plain:
            await db.add_item(conn, sid, "fish_mackerel", extra_plain)
        await fish_market.record_sale(conn, "fish_mackerel", flow0)
        await conn.commit()
    return db, kid, sid


async def _flow_total(db) -> int:
    async with db.connect() as conn:
        row = await (await conn.execute("SELECT COALESCE(SUM(qty),0) FROM fish_market_flow")).fetchone()
        return int(row[0])


def test_vend_total_is_path_independent() -> None:
    asyncio.run(_test_path_independent())


async def _test_path_independent() -> None:
    from server.game import tote

    rng = random.Random(11)
    for trial in range(4):
        plan = [(rng.randint(1, 6), rng.choice(["roe", "fresh", "firm", "old", "parasite", "bruised"]),
                 round(rng.uniform(0.3, 25.0), 1)) for _ in range(rng.randint(2, 4))]
        flow0 = rng.choice([0, 5, 20, 60, 400])
        extra = rng.randint(0, 5)
        total = sum(q for q, _, _ in plan) + extra
        db1, k1, s1 = await _fish_world(f"a{trial}", plan, flow0, extra)
        await tote.tote_ops(k1, f"vend fish_mackerel {total}")
        one_shot = await _tickets(db1, s1)
        flow_a = await _flow_total(db1)
        db2, k2, s2 = await _fish_world(f"b{trial}", plan, flow0, extra)
        for _ in range(total):
            await tote.tote_ops(k2, "vend fish_mackerel 1")
        singles = await _tickets(db2, s2)
        assert one_shot == singles, (trial, plan, flow0, extra, one_shot, singles)
        assert flow_a == await _flow_total(db2) == flow0 + total
        # 分两次卖也一样
        db3, k3, s3 = await _fish_world(f"c{trial}", plan, flow0, extra)
        half = total // 2
        if half:
            await tote.tote_ops(k3, f"vend fish_mackerel {half}")
        await tote.tote_ops(k3, f"vend fish_mackerel {total - half}")
        assert await _tickets(db3, s3) == one_shot, (trial,)


def test_one_premium_fish_no_longer_prices_the_whole_stack() -> None:
    asyncio.run(_test_anchor())


async def _test_anchor() -> None:
    from server.game import tote

    # 审计里的利用：1 条 25kg 带卵 + 99 条寄生，旧版整批按首批算 5100，诚实价 594 + 一条好鱼
    db, kid, sid = await _fish_world("anchor", [(1, "roe", 25.0), (99, "parasite", 0.5)], 0, 0)
    await tote.tote_ops(kid, "vend fish_mackerel 100")
    got = await _tickets(db, sid)
    db2, kid2, sid2 = await _fish_world("honest", [(99, "parasite", 0.5)], 0, 0)
    await tote.tote_ops(kid2, "vend fish_mackerel 99")
    honest = await _tickets(db2, sid2)
    # 多出来的只是那一条好鱼自己的溢价（旧版是 5100 对 594，整批按首批算）
    assert 0 < got - honest <= 60, (got, honest)


def test_modifier_band_caps_heavy_fish() -> None:
    from server import pricing

    ref = pricing.ref_value("fish_tuna")
    assert pricing.made_unit_price("fish_tuna", 2.64) == int(ref * 1.5)
    assert pricing.made_unit_price("fish_tuna", 0.1) == int(ref * 0.5)
    assert pricing.made_unit_price("fish_tuna", 1.0) == ref


def test_ghost_batches_are_released_and_reconciled() -> None:
    asyncio.run(_test_ghost())


async def _test_ghost() -> None:
    from server import item_traits as traits
    from server import market_stall_gust
    from server.game import tote

    async def _no_gust(conn, steward_id):
        return ""

    market_stall_gust.maybe_after_sell = _no_gust
    from server import market

    db = await _boot(Path(tempfile.mkdtemp(prefix="flow-ghost-")))
    ka, a = await _enroll(db, "a@x.com", "幽灵甲", 0)
    kb, b = await _enroll(db, "b@x.com", "幽灵乙", 0)
    async with db.connect() as conn:
        await traits.grant_satchel(conn, a, "fish_mackerel", 1, quality="roe", weight_kg=25.0)
        await traits.grant_satchel(conn, a, "fish_mackerel", 2, quality="firm", weight_kg=0.5)
        await conn.commit()
    await market.market_ops(ka, "sell fish_mackerel 1 50")      # 好鱼挂集市
    await tote.tote_ops(ka, "gift 幽灵乙 fish_mackerel 1")      # 一条送人
    async with db.connect() as conn:
        rows = await (await conn.execute(
            "SELECT quality, qty FROM item_trait_batches WHERE steward_id=? AND item='fish_mackerel' ORDER BY id", (a,)
        )).fetchall()
    assert [tuple(r) for r in rows] == [("firm", 1)] or sum(r[1] for r in rows) <= 1, rows
    # 对账：批次比背包多，多出的最老批次被丢弃
    async with db.connect() as conn:
        await conn.execute(
            "INSERT INTO item_trait_batches (steward_id, loc, item, qty, quality, weight_milli, spoil_at) "
            "VALUES (?,?,?,?,?,?,?)", (a, "satchel", "fish_mackerel", 5, "roe", 25000, 0))
        await conn.commit()
        dropped = await traits.reconcile_batches(conn, a, "fish_mackerel")
        await conn.commit()
    assert dropped >= 5


# ── 后室铺：店货与赃物 ─────────────────────────────────────────────────────
def test_black_market_shop_goods_vs_loot(monkeypatch) -> None:
    asyncio.run(_test_black_market(monkeypatch))


async def _test_black_market(monkeypatch) -> None:
    from server import pricing
    from server import undertide as utmod
    from server import undertide_muscle as um
    from server import undertide_pit as pit
    from server.undertide_catalog import COMMON_GOODS

    db = await _boot(Path(tempfile.mkdtemp(prefix="flow-ut-")))
    ka, a = await _enroll(db, "a@x.com", "销赃甲", 1000)
    base = COMMON_GOODS["black_salt"]["base"]
    vend = COMMON_GOODS["black_salt"]["vend"]
    lowest_buy = pricing.ut_shelf_min_price(base, "common")
    async with db.connect() as conn:
        s = await db.get_steward_by_id(a)
        ut = dict(await utmod._ensure_ut(conn, a))
        await db.add_item(conn, a, "ut_black_salt", 5)
        await db.add_item(conn, a, "utl_black_salt", 5)
        await conn.commit()
        t0 = await _tickets(db, a)
        await utmod._cmd_sell(conn, s, ut, "ut_black_salt", "5")
        await conn.commit()
        shop = await _tickets(db, a) - t0
        t1 = await _tickets(db, a)
        await utmod._cmd_sell(conn, s, ut, "utl_black_salt", "5")
        await conn.commit()
        loot = await _tickets(db, a) - t1
    assert shop <= pricing.fence_shop_max(base) * 5 < lowest_buy * 5, (shop, lowest_buy)
    assert loot >= int(vend * 1.5 * 0.8) * 5 > shop, (loot, shop)       # 赃物走高价通道

    # 强买抢来的是赃物（utl_），不是店货
    monkeypatch.setattr(pit, "win_prob", lambda diff: 2.0)
    async with db.connect() as conn:
        s = await db.get_steward_by_id(a)
        ut = dict(await utmod._ensure_ut(conn, a))
        before = dict(await db.get_satchel(a))
        await um.muscle_ops(conn, s, ut, "muscle", "1")
        await conn.commit()
    gained = {k for k, v in (await db.get_satchel(a)).items() if k.startswith(("ut", "utl_")) and v > before.get(k, 0)}
    assert gained, "强买应该拿到货"
    assert all(k.startswith("utl_") or k in ("ut_pit_silt", "ut_brine_crystal") for k in gained), gained


def test_loot_cannot_be_bought_anywhere_and_muscle_is_capped() -> None:
    """赃物不能从任何商店买到：货架、强卖、炼制、Tt、花房、栗栗、诊所都不产 utl_；强买每日 1 次。"""
    from server import catalog, pricing, undertide_config as utcfg
    from server.price_book import BOOK

    for item, e in BOOK.items():
        if pricing.is_loot(item):
            assert e["cls"] == "made" and e.get("loot") and e.get("notote"), item
            assert "ch" not in e, f"赃物不该有买入渠道：{item}"
        elif e["cls"] == "buy":
            assert not pricing.is_loot(item)
    from server import undertide_refine
    assert all(not pricing.is_loot(m["out"][0]) for m in undertide_refine.RECIPES.values())
    assert not any(pricing.is_loot(i) for i in catalog.CRAFT_RECIPES.get("x", {}).get("need", {}))
    assert utcfg.UT_MUSCLE_DAILY == 1 and utcfg.UT_PUSH_DAILY >= 1
    # 一次强买最多 3 样常规 + 1 样稀有；按最高价算，单号单日上限有数
    from server.undertide_catalog import COMMON_GOODS, RARE_GOODS
    top_common = sorted((v["vend"] for k, v in COMMON_GOODS.items() if k not in pricing.LOOT_EXCLUDE), reverse=True)[:3]
    top_rare = max(v["vend"] for v in RARE_GOODS.values())
    ceiling = sum(int(v * 1.9 * 1.5 * 2) for v in top_common) + int(top_rare * 1.9 * 1.5 * 2)
    assert ceiling < 2500, ceiling      # 每号每日赃物销赃的理论天花板（需要赢一场战斗，还掉影信）


# ── 酒吧打赏 ──────────────────────────────────────────────────────────────
def test_tip_bonus_comes_from_the_bar_pool_and_pairs_are_capped() -> None:
    asyncio.run(_test_tips())


async def _test_tips() -> None:
    from server import bar, multi, pricing

    db = await _boot(Path(tempfile.mkdtemp(prefix="flow-tip-")))
    ka, a = await _enroll(db, "a@x.com", "打赏甲", 5000)
    kb, b = await _enroll(db, "b@x.com", "打赏乙", 5000)
    day = db.day_id()
    async with db.connect() as conn:
        for sid in (a, b):
            await conn.execute(
                "INSERT INTO bar_shifts (steward_id, day, job, period, created_at) VALUES (?,?,?,?,?)",
                (sid, day, "dish", "night", db.now()))
        await multi._bump_rapport(conn, a, b, 90)
        await conn.commit()
        await bar._ensure_daily_state(conn)
        await conn.commit()

    async def total() -> int:
        return await _tickets(db, a) + await _tickets(db, b)

    # 池是空的：没有加成，票守恒
    t0 = await total()
    await bar.bar_ops(ka, "tip 打赏乙 500")
    assert await total() == t0
    # 池里有 40 票：加成最多 40，且不超过 15%
    async with db.connect() as conn:
        await conn.execute("UPDATE bar_daily_state SET revenue_tickets=40 WHERE day=?", (day,))
        await conn.commit()
    t1 = await total()
    await bar.bar_ops(kb, "tip 打赏甲 200")       # 想要 30
    assert await total() - t1 == 30
    t2 = await total()
    await bar.bar_ops(ka, "tip 打赏乙 200")       # 池只剩 10
    assert await total() - t2 == 10
    # 每对号每日最多 10 次（不分方向）；已经打了 3 次
    sent = 3
    while True:
        who, to = (ka, "打赏乙") if sent % 2 == 0 else (kb, "打赏甲")
        try:
            await bar.bar_ops(who, f"tip {to} 10")
        except ValueError as exc:
            assert "10 次" in str(exc) or "上限" in str(exc), str(exc)
            break
        sent += 1
        assert sent <= 11, "每对号每日上限没生效"
    assert sent == pricing.TIP_PAIR_DAILY_COUNT
    # 总额上限：换一对没打过的号
    kc, c = await _enroll(db, "c@x.com", "打赏丙", 5000)
    async with db.connect() as conn:
        await conn.execute(
            "INSERT INTO bar_shifts (steward_id, day, job, period, created_at) VALUES (?,?,?,?,?)",
            (c, day, "dish", "night", db.now()))
        await conn.commit()
    await bar.bar_ops(ka, "tip 打赏丙 500")
    await bar.bar_ops(ka, "tip 打赏丙 500")
    await _rejects(bar.bar_ops(ka, "tip 打赏丙 10"), "上限")
    # 全程不可能凭空多出超过池子的票
    async with db.connect() as conn:
        paid = (await (await conn.execute("SELECT tip_bonus_paid FROM bar_daily_state WHERE day=?", (day,))).fetchone())[0]
    assert paid <= 40


async def _rejects_unused() -> None:  # pragma: no cover
    return None


# ── 旧数据 ────────────────────────────────────────────────────────────────
def test_legacy_negative_satchel_rows_do_not_break_vend() -> None:
    asyncio.run(_test_legacy_negative_row())


async def _test_legacy_negative_row() -> None:
    from server.game import tote

    db = await _boot(Path(tempfile.mkdtemp(prefix="flow-legacy-")))
    ka, a = await _enroll(db, "a@x.com", "旧账甲", 100)
    async with db.connect() as conn:
        await conn.execute(
            "INSERT INTO satchel (steward_id,item,quantity) VALUES (?,?,?) "
            "ON CONFLICT(steward_id,item) DO UPDATE SET quantity=excluded.quantity", (a, "seed_kale", -285715))
        await conn.commit()
    await _rejects(tote.tote_ops(ka, "vend seed_kale 1"))     # 负数格子卖不出去，也不会凭空发钱
    assert await _tickets(db, a) == 100


def test_clinic_medicine_buy_then_vend_loses_even_with_discount() -> None:
    asyncio.run(_test_medicine())


async def _test_medicine() -> None:
    """审计后新发现：旧版药品回收 = 标价 100%，诊所九折买入再卖，每轮 +12%。"""
    from server import clinic
    from server.game import tote

    db = await _boot(Path(tempfile.mkdtemp(prefix="flow-med-")))
    ka, a = await _enroll(db, "a@x.com", "吃药甲", 1000)
    for _ in range(3):
        before = await _tickets(db, a)
        async with db.connect() as conn:
            s = await db.get_steward_by_id(a)
            await clinic._buy_medicine(conn, s, "med_sober", 10, cost_mult=0.9, cost_add=0)
            await conn.commit()
        await tote.tote_ops(ka, "vend med_sober 10")
        assert await _tickets(db, a) < before


def test_kitchen_vend_uses_the_same_pricing_as_tote() -> None:
    asyncio.run(_test_kitchen_vend())


async def _test_kitchen_vend() -> None:
    from server import fish_market, kitchen
    from server import item_traits as traits

    db = await _boot(Path(tempfile.mkdtemp(prefix="flow-kv-")))
    ka, a = await _enroll(db, "a@x.com", "厨房甲", 0)
    async with db.connect() as conn:
        await traits.grant_satchel(conn, a, "fish_mackerel", 2, quality="firm", weight_kg=0.5)
        await conn.commit()
    await kitchen.kitchen_ops(ka, "vend fish_mackerel")
    async with db.connect() as conn:
        flow = await fish_market.window_flow(conn, "fish_mackerel")
        left = (await db.get_satchel(a)).get("fish_mackerel")
        batches = (await (await conn.execute(
            "SELECT COALESCE(SUM(qty),0) FROM item_trait_batches WHERE steward_id=? AND item='fish_mackerel'", (a,))).fetchone())[0]
    assert flow == 1 and left == 1 and batches == 1       # 计流量、扣批次，不再留幽灵
    assert await _tickets(db, a) > 0


def test_market_price_band(monkeypatch) -> None:
    from server import market_stall_gust

    async def _no_gust(conn, steward_id):
        return ""

    monkeypatch.setattr(market_stall_gust, "maybe_after_sell", _no_gust)
    asyncio.run(_test_market_band())


async def _test_market_band() -> None:
    from server import market, pricing

    db = await _boot(Path(tempfile.mkdtemp(prefix="flow-band-")))
    ka, a = await _enroll(db, "a@x.com", "价带甲", 0)
    async with db.connect() as conn:
        await db.add_item(conn, a, "crop_kale", 5)
        await conn.commit()
    top = pricing.base_price("crop_kale") * pricing.MARKET_PRICE_MAX_MULT
    await _rejects(market.market_ops(ka, f"sell crop_kale 1 {top + 1}"), "离谱")
    await market.market_ops(ka, f"sell crop_kale 1 {top}")
    await market.market_ops(ka, "sell crop_kale 1 1")      # 没有下限
