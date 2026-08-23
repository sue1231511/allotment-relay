#!/usr/bin/env python3
"""Tt酱货架不能买了再系统 vend 赚差价。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_shop_recycle_below_max_discount() -> None:
    from server import tt
    from server.catalog import suggested_price

    for item, base, _kind in tt.shop_skus():
        buy = tt.sale_price(base, 100)  # 满心 7.5 折
        recycle = tt.recycle_price(item)
        assert recycle is not None, item
        assert recycle < buy, (item, recycle, buy, base)
        assert suggested_price(item) == recycle


def test_durian_seed_no_longer_prints_tickets() -> None:
    from server import tt
    from server.catalog import suggested_price

    buy = tt.sale_price(48, 100)
    vend = suggested_price("seed_durian")
    assert buy > vend
    assert vend == int(48 * 0.40)


def test_grown_crop_still_sells_full() -> None:
    from server.catalog import CROPS, suggested_price

    assert suggested_price("crop_kale") == CROPS["kale"]["sell"]
    assert suggested_price("seed_kale") < CROPS["kale"]["seed_price"]


if __name__ == "__main__":
    test_shop_recycle_below_max_discount()
    test_durian_seed_no_longer_prints_tickets()
    test_grown_crop_still_sells_full()
    print("ok")
