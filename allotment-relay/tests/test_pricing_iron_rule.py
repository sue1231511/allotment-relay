#!/usr/bin/env python3
"""铁律：同一个玩家、同一时刻，任何物品最低买入价 > 任意渠道最高卖出价。

买入渠道、卖出渠道都用游戏里真实的价格函数现算（不是抄公式），遍历：
  全部有买入渠道的物品 × 好感 0..10 心 × 各渠道的折扣极端（花房四域满级、诊所九折、
  后室铺影信各档、景气极端、幸运）。整数结算后严格比较。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _buy_channels():
    """{物品: [(渠道名, 是否吃好感, 价格函数(hearts)->最低买入价)]}，全部来自真实数据。"""
    from server import catalog as c
    from server import health, pricing, tt, undertide
    from server.clinic_copy import CLINIC_MEDICINES
    from server.florist_catalog import FLOWERS, TEAS
    from server.lili_catalog import ticket_cost_for_steward
    from server.undertide_catalog import COMMON_GOODS, LINKED_GOODS, RARE_GOODS
    from server.undertide_config import UT_REP_TIERS

    out: dict[str, list] = {}

    def add(item, name, fn):
        out.setdefault(item, []).append((name, fn))

    for item, base, kind in tt.shop_skus():
        if pricing.is_token(item):
            continue
        if kind == "dowry":
            add(item, "tt_flat", lambda h, b=base: b)
        else:
            add(item, "tt", lambda h, b=base: tt.sale_price(b, h * 10))
    for k, v in c.CROPS.items():
        add(f"seed_{k}", "plot", lambda h, p=v["seed_price"]: p)
    for k, v in c.TOOLS.items():
        add(f"tool_{k}", "tool_ops", lambda h, p=v["cost"]: p)
    for cat in (c.HUT_HARD, c.HUT_SOFT):
        for k, v in cat.items():
            if v.get("craft_only") or int(v.get("cost") or 0) <= 0:
                continue
            add(f"fit_{k}", "hut", lambda h, p=int(v["cost"]): p)
    for k, v in c.LIVESTOCK.items():
        add(f"live_{k}", "barn", lambda h, p=v["buy"]: p)
    maxed = {"farm": 5, "beach": 5, "fish": 5, "sea": 5}
    for k, v in FLOWERS.items():
        add(f"flower_{k}", "florist",
            lambda h, p=v["price"]: ticket_cost_for_steward(p, ["farm", "beach"], maxed))
    for k, v in TEAS.items():
        add(f"flower_tea_{k}", "florist",
            lambda h, p=v["price"] - 8: ticket_cost_for_steward(p, ["farm", "beach"], maxed))
    for key, v in CLINIC_MEDICINES.items():
        add(key, "clinic", lambda h, p=int(v["price"]): health._bill_cost(p, cost_mult=0.9, cost_add=0))
    for layer, goods in (("common", COMMON_GOODS), ("linked", LINKED_GOODS), ("rare", RARE_GOODS)):
        for k, v in goods.items():
            add(f"ut_{k}", "ut_shelf",
                lambda h, v=v, layer=layer: min(
                    undertide._shelf_price(v, layer, rep) for rep, *_ in UT_REP_TIERS
                ))
    return out


def _sell_channels(item: str, hearts: int) -> list[tuple[str, int]]:
    """这件货此刻所有卖出渠道能给的最高价（各渠道取最有利的修正）。"""
    from server import catalog as c
    from server import hut, pricing
    from server.price_book import BOOK
    from server.undertide_catalog import COMMON_GOODS, LINKED_GOODS, RARE_GOODS

    out: list[tuple[str, int]] = []
    entry = BOOK[item]
    if not entry.get("notote") and c.ITEM_PRICES.get(item, 0) > 0:
        out.append(("vend", pricing.refund_for_player(item, hearts)))
    if item.startswith("fit_"):
        cost = int(entry["B"])
        out.append(("hut_sell", hut.furniture_sell_quote(cost, int(time.time()), int(time.time()))["refund"]))
    if item.startswith("ut_"):
        goods = {**COMMON_GOODS, **LINKED_GOODS, **RARE_GOODS}[item[3:]]
        out.append(("fence", pricing.fence_shop_max(int(goods["base"]))))
        out.append(("push", pricing.fence_shop_max(int(goods["base"]))))
    return out


def test_every_buyable_item_costs_more_than_it_sells_for() -> None:
    from server.price_book import BOOK

    channels = _buy_channels()
    assert len(channels) > 150
    checked = 0
    for item, chans in sorted(channels.items()):
        assert item in BOOK and BOOK[item]["cls"] == "buy", f"买得到却没标可买品：{item}"
        for hearts in range(0, 11):
            low = min(fn(hearts) for _name, fn in chans)
            sells = _sell_channels(item, hearts)
            for name, price in sells:
                assert low > price, (item, hearts, "最低买入", low, "渠道", name, "卖出", price)
                checked += 1
    assert checked > 1500


def test_no_made_item_has_a_buy_channel() -> None:
    """簿里标「产出品」的物品，任何商店都不能直接买到（否则就该改成可买品并过铁律）。"""
    from server.price_book import BOOK

    for item in _buy_channels():
        assert BOOK[item]["cls"] == "buy", item
    for item, e in BOOK.items():
        if e["cls"] == "buy" and not e.get("loot"):
            assert item in _buy_channels() or item.startswith("gold_set_"), f"簿里标可买品但没有渠道：{item}"


def test_lili_barter_with_buyable_goods_never_beats_hut_resale() -> None:
    """栗栗货单里，凡是「给的货全都能在商店买到」的单：买货的最低成本 + 票，必须高于换到的家具
    在小屋里最高能卖的钱，不然就是「买货→换家具→卖家具」的循环。
    给的货里只要有一样买不到（贝壳、鱼、作物……），那是劳动换家具，不是循环，不在这条里。
    """
    from server import hut, pricing
    from server.lili_catalog import generate_daily_offers

    now = int(time.time())
    checked = 0
    for day in range(1, 400):
        for off in generate_daily_offers(day):
            get = off["get"]
            if get.startswith("deco_junk_"):
                continue
            if not all(pricing.min_buy_price(i) > 0 for i in off["give"]):
                continue
            cost = sum(pricing.min_buy_price(i) * q for i, q in off["give"].items())
            cost += max(0, int(off["ticket_cost"]) - 8)      # 四域满级最多减 8 票
            val = hut._fitting_value(get)
            refund = hut.furniture_sell_quote(val["cost"], now, now)["refund"] * int(off.get("get_qty") or 1)
            assert cost > refund, (day, off, cost, refund)
            checked += 1
    assert checked >= 20


def test_fence_shop_payout_is_always_below_cheapest_buy() -> None:
    import random

    from server import pricing
    from server.undertide_catalog import COMMON_GOODS, LINKED_GOODS, RARE_GOODS

    rng = random.Random(1)
    for layer, goods in (("common", COMMON_GOODS), ("linked", LINKED_GOODS), ("rare", RARE_GOODS)):
        for k, v in goods.items():
            lowest_buy = pricing.ut_shelf_min_price(int(v["base"]), layer)
            worst = pricing.fence_shop_max(int(v["base"]))
            assert worst < lowest_buy, (k, worst, lowest_buy)
            for _ in range(200):
                got = pricing.fence_shop_payout(
                    int(v["base"]), u=rng.uniform(0, 2), tide=rng.uniform(0, 3),
                    lucky=rng.random() < 0.5,
                )
                assert got < lowest_buy, (k, got, lowest_buy)


def test_iron_rule_test_is_not_vacuous(monkeypatch) -> None:
    """反例：把回收系数调到 120%，铁律测试必须红（防止测试自己失效）。"""
    import pytest

    from server import pricing

    monkeypatch.setattr(pricing, "REFUND_PCT", 120)
    with pytest.raises(AssertionError):
        test_every_buyable_item_costs_more_than_it_sells_for()


def test_price_book_catches_literal_drift(monkeypatch) -> None:
    """反例：有人只改了目录里的字面价、没改价格簿，一致性测试必须红。"""
    import pytest

    from server import catalog

    monkeypatch.setitem(catalog.CROPS["kale"], "seed_price", 6)   # 种子字面价与簿里不一致
    from tests import test_price_book  # type: ignore

    with pytest.raises(AssertionError):
        test_price_book.test_book_matches_literal_prices()


if __name__ == "__main__":
    test_every_buyable_item_costs_more_than_it_sells_for()
    test_no_made_item_has_a_buy_channel()
    test_lili_barter_with_buyable_goods_never_beats_hut_resale()
    test_fence_shop_payout_is_always_below_cheapest_buy()
    print("ok")
