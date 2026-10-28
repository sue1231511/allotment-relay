#!/usr/bin/env python3
"""价格簿与各处字面价一致；手作信物不进簿；产出品回收价与改版前一致。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

STAR_DISH = re.compile(r"^dish_.+_s[1-5]$")


def test_made_items_keep_old_sell_price() -> None:
    """产出品：floor(0.70B) 恰好等于改版前的回收价（正常玩家收入不变）。"""
    from server import catalog, pricing
    from server.price_book import BOOK

    checked = 0
    for item, old in catalog.LEGACY_ITEM_PRICES.items():
        if item in pricing.TOKEN_ITEMS or STAR_DISH.match(item) or item.startswith("mix_"):
            continue
        entry = BOOK[item]
        if entry["cls"] != "made":
            continue
        capped = pricing.cap_for(item)
        expect = old if capped is None else min(old, capped)
        assert pricing.ref_value(item) == expect, (item, old, capped, pricing.ref_value(item))
        checked += 1
    assert checked > 500


def test_book_matches_literal_prices() -> None:
    """价格簿是权威；目录里的字面价是镜像，任何一边改了没同步这里就红。"""
    from server import catalog as c
    from server import tt
    from server.clinic_copy import CLINIC_MEDICINES
    from server.florist_catalog import FLOWERS, TEAS
    from server.price_book import BOOK
    from server.undertide_catalog import COMMON_GOODS, LINKED_GOODS, RARE_GOODS
    from server import pricing

    for item, base, kind in tt.shop_skus():
        if pricing.is_token(item):
            assert item not in BOOK
            continue
        e = BOOK[item]
        assert e["cls"] == "buy" and e["B"] == base, (item, e, base)
        assert ("tt_flat" if kind == "dowry" else "tt") in e["ch"], item
    for k, meta in c.TOOLS.items():
        assert BOOK[f"tool_{k}"]["B"] >= meta["cost"]
        assert "tool_ops" in BOOK[f"tool_{k}"]["ch"]
    for cat in (c.HUT_HARD, c.HUT_SOFT):
        for k, meta in cat.items():
            if meta.get("craft_only") or int(meta.get("cost") or 0) <= 0:
                continue
            assert BOOK[f"fit_{k}"]["B"] == int(meta["cost"]), k
    for k, meta in c.LIVESTOCK.items():
        assert BOOK[f"live_{k}"]["B"] == int(meta["buy"]), k
    for k, meta in FLOWERS.items():
        assert BOOK[f"flower_{k}"]["B"] == meta["price"], k
    for k, meta in TEAS.items():
        assert BOOK[f"flower_tea_{k}"]["B"] == meta["price"] - 8, k
    for layer, goods in (("common", COMMON_GOODS), ("linked", LINKED_GOODS), ("rare", RARE_GOODS)):
        for k, meta in goods.items():
            e = BOOK[f"ut_{k}"]
            assert e["B"] == meta["base"] and e["layer"] == layer, k
    for key, meta in CLINIC_MEDICINES.items():
        assert BOOK[key]["B"] == int(meta["price"]), key
    for k, v in c.CROPS.items():
        assert BOOK[f"seed_{k}"]["B"] == v["seed_price"], k


def test_pricing_constants_mirror_game_constants() -> None:
    from server import clinic, pricing
    from server.catalog import SEA_CATCH  # noqa: F401
    from server.undertide_catalog import LAYER_MULT
    from server.undertide_config import UT_REP_TIERS

    assert pricing.CLINIC_MIN_MULT == clinic.CLINIC_DISCOUNT_MULT
    assert pricing.UT_LAYER_MULT == LAYER_MULT
    assert pricing.UT_REP_MULT_MIN == min(t[2] for t in UT_REP_TIERS)
    # 好感折扣表与 Tt 的 zhe() 一致
    from server import tt

    for h in range(0, 11):
        assert pricing.hearts_permille(h) == round(tt.zhe(h) * 100), h


def test_tokens_are_outside_the_book() -> None:
    from server import catalog, pricing
    from server.price_book import BOOK

    assert pricing.TOKEN_ITEMS >= {"betroth_ring", "tide_vow_ring"}
    for t in pricing.TOKEN_ITEMS:
        assert t not in BOOK
        assert t not in catalog.ITEM_PRICES
        assert not catalog.item_vendable(t)        # 不能卖给商店
        assert catalog.item_tradable(t)            # 玩家之间可以交易
        assert pricing.ref_value(t) == 0 and pricing.base_price(t) == 0


def test_book_sell_overrides_never_exceed_formula() -> None:
    from server import pricing
    from server.price_book import BOOK

    for item, e in BOOK.items():
        if e.get("sell") is None or e["cls"] != "buy":
            continue
        formula = pricing.min_buy_price(item) * pricing.REFUND_PCT // 100
        if "hut" in e.get("ch", ()):
            continue    # 家具展示价，真实回收走小屋折旧
        assert e["sell"] <= formula, (item, e["sell"], formula)


def test_no_unbooked_vendable_items() -> None:
    """tote 能回收的物品要么在簿里，要么是配方推出的动态物品（熟菜星级、混搭菜）。"""
    from server import catalog
    from server.price_book import BOOK

    for item, price in catalog.ITEM_PRICES.items():
        if item in BOOK or STAR_DISH.match(item) or item.startswith(("mix_", "dish_mix_")):
            continue
        raise AssertionError(f"没进价格簿的可回收物品：{item}={price}")


if __name__ == "__main__":
    test_made_items_keep_old_sell_price()
    test_book_matches_literal_prices()
    test_pricing_constants_mirror_game_constants()
    test_tokens_are_outside_the_book()
    test_book_sell_overrides_never_exceed_formula()
    test_no_unbooked_vendable_items()
    print("ok")
