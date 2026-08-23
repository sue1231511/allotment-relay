#!/usr/bin/env python3
"""Tt酱货架回收进价九成：退货少亏，不再腰斩。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_shop_recycle_is_nine_tenths() -> None:
    from server import config, tt
    from server.catalog import suggested_price

    assert config.TT_SHOP_VEND_RATE == 0.90
    for item, base, _kind in tt.shop_skus():
        recycle = tt.recycle_price(item)
        assert recycle is not None, item
        assert recycle == max(1, int(base * 0.90)), (item, recycle, base)
        assert suggested_price(item) == recycle
        # 标价 20 的货回收 18，不再腰斩到 8
        assert recycle >= int(base * 0.85)


def test_durian_seed_not_halved() -> None:
    from server.catalog import suggested_price

    vend = suggested_price("seed_durian")
    assert vend == int(48 * 0.90)
    assert 48 - vend <= 5


def test_grown_crop_still_sells_full() -> None:
    from server.catalog import CROPS, suggested_price

    assert suggested_price("crop_kale") == CROPS["kale"]["sell"]
    assert suggested_price("seed_kale") == max(1, int(CROPS["kale"]["seed_price"] * 0.90))


if __name__ == "__main__":
    test_shop_recycle_is_nine_tenths()
    test_durian_seed_not_halved()
    test_grown_crop_still_sells_full()
    print("ok")
