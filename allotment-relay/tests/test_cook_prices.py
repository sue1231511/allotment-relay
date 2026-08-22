#!/usr/bin/env python3
"""定点菜 3★ 不亏材料回收；自由组合正经搭配也不倒贴；乱炖按材料身价兜底；熟菜精力抬高。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.catalog import (  # noqa: E402
    KITCHEN_DISHES,
    COOK_STAR3_FLOOR,
    dish_base_sell,
    dish_ingredient_cost,
    dish_sell_price,
    mix_energy,
    mix_sell_price,
)


def test_named_dishes_star3_covers_vend() -> None:
    losers = []
    for key, meta in KITCHEN_DISHES.items():
        cost = dish_ingredient_cost(key)
        sell3 = dish_sell_price(key, 3)
        sell4 = dish_sell_price(key, 4)
        sell5 = dish_sell_price(key, 5)
        assert sell3 >= int(cost * COOK_STAR3_FLOOR), f"{key} 3★ {sell3} < 材料 {cost}×{COOK_STAR3_FLOOR}"
        assert sell3 >= cost, f"{key} 3★ {sell3} < 材料 {cost} ({meta['name']})"
        assert sell4 > sell3
        assert sell5 > sell4
        assert dish_base_sell(key) == sell3
        if sell3 < cost:
            losers.append(key)
    assert not losers
    # 沙拉不再堆四样贵料
    assert "crop_blueberry" not in KITCHEN_DISHES["goat_cheese_salad"]["ings"]
    assert "crop_lemongrass" not in KITCHEN_DISHES["papaya_salad"]["ings"]
    assert len(KITCHEN_DISHES["goat_cheese_salad"]["ings"]) == 3
    assert len(KITCHEN_DISHES["papaya_salad"]["ings"]) == 3


def test_named_dish_energy_beats_raw() -> None:
    # 做饭永远比生吃划算：定点菜精力 ≥22，灶台 meal ≥18
    for key, meta in KITCHEN_DISHES.items():
        assert meta["energy"] >= 22, f"{key} energy {meta['energy']} ({meta['name']})"
        assert meta["energy"] <= 36, f"{key} energy {meta['energy']} 过高"


def test_mix_star3_covers_bucket() -> None:
    # 纯 junk 料（粪/泥壳 tier 0）照旧不值钱
    assert mix_sell_price("j", 0, 3) <= 7
    # 好料乱炖（junk 档高 tier）按材料身价兜底 45%，不再两三票贱卖
    assert mix_sell_price("j", 5, 1) >= 45
    assert mix_sell_price("j", 3, 1) >= 30
    # 桶中值 90（tier 4 = 80~99）3★ 应盖过桶底
    assert mix_sell_price("g", 4, 3) >= 80
    assert mix_sell_price("x", 3, 3) >= 60
    assert mix_sell_price("o", 2, 3) >= 40


def test_mix_energy_beats_raw() -> None:
    assert mix_energy("j", 1) >= 6
    assert mix_energy("o", 2) >= 15
    assert mix_energy("g", 3) >= 30
    assert mix_energy("x", 3) >= 45


def main() -> None:
    test_named_dishes_star3_covers_vend()
    test_named_dish_energy_beats_raw()
    test_mix_star3_covers_bucket()
    test_mix_energy_beats_raw()
    print("cook price tests ok")
    print(f"{'菜':<16} {'材料':>4} {'3★':>4} {'4★':>4} {'5★':>4} {'精力':>4}  3★盈")
    for key, meta in KITCHEN_DISHES.items():
        cost = dish_ingredient_cost(key)
        s3 = dish_sell_price(key, 3)
        print(
            f"{meta['name']:<16} {cost:4d} {s3:4d} "
            f"{dish_sell_price(key, 4):4d} {dish_sell_price(key, 5):4d} "
            f"{meta['energy']:4d}  {s3 - cost:+d}"
        )
    print("乱炖兜底示例：j tier5 1★ =", mix_sell_price("j", 5, 1), "票")


if __name__ == "__main__":
    main()
