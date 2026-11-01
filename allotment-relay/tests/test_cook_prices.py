#!/usr/bin/env python3
"""定点菜 3★ 不亏材料回收；自由组合正经搭配也不倒贴；乱炖按材料身价兜底；熟菜精力抬高。"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.catalog import (  # noqa: E402
    KITCHEN_DISHES,
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
        assert sell3 >= cost, f"{key} 3★ {sell3} < 材料 {cost} ({meta['name']})"
        # 系统回收压得低：3★ 锚定在材料价 +0~20%，想赚钱走小馆/集市
        assert sell3 <= int(cost * 1.2), f"{key} 3★ {sell3} > 材料×1.2 {cost} ({meta['name']})"
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


def test_eatery_ref_beats_vend() -> None:
    from server.catalog import dish_energy, dish_item, eatery_reference_price

    for key in KITCHEN_DISHES:
        for stars in (1, 3, 5):
            item = dish_item(key, stars)
            ref = eatery_reference_price(item)
            vend = dish_sell_price(key, stars)
            energy = dish_energy(item)
            # 卖给食客的参考价明显高于系统回收；精力是定价锚点之一
            assert ref >= vend * 1.2, (key, stars, ref, vend)
            assert ref >= energy * 3 - 1, (key, stars, ref, energy)


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
    # 好搭配的乱炖比生吃（水果 4 / 生鱼 10 / 生肉 12）划算；垃圾档（j）本来就是废料，不比
    assert mix_energy("o", 1) >= 15
    assert mix_energy("g", 3) >= 25
    assert mix_energy("x", 3) >= 29


def test_energy_ladder_mix_below_named_dishes() -> None:
    """梯子：生吃 < 零食饮品 < 乱炖 < 定点菜。乱炖同星任何档、任何材料档都低于同星最便宜的定点菜，不然菜谱白学。"""
    from server.catalog import NAMED_DISH_ENERGY_MAX, NAMED_DISH_ENERGY_MIN

    assert min(m["energy"] for m in KITCHEN_DISHES.values()) == NAMED_DISH_ENERGY_MIN
    assert max(m["energy"] for m in KITCHEN_DISHES.values()) == NAMED_DISH_ENERGY_MAX
    for stars in range(1, 6):
        dish_floor = NAMED_DISH_ENERGY_MIN + 3 * stars
        for grade in "joxg":
            for tier in range(0, 10):
                assert mix_energy(grade, stars, tier) < dish_floor, (grade, stars, tier)
    # 档越高、材料越贵、星越高，精力不降
    for stars in range(1, 6):
        for tier in range(0, 10):
            seq = [mix_energy(g, stars, tier) for g in "joxg"[:1] + "o" + "g" + "x"]
            assert seq == sorted(seq), (stars, tier, seq)
        for grade in "jogx":
            assert [mix_energy(grade, stars, t) for t in range(10)] == sorted(mix_energy(grade, stars, t) for t in range(10))


def test_named_dish_energy_follows_material_price() -> None:
    """定点菜精力按材料价从低到高排：材料更贵的不会比便宜的回得更少。"""
    from server.catalog import dish_ingredient_cost

    ranked = sorted(KITCHEN_DISHES, key=lambda k: (dish_ingredient_cost(k), len(KITCHEN_DISHES[k]["ings"]), k))
    energies = [KITCHEN_DISHES[k]["energy"] for k in ranked]
    assert energies == sorted(energies)


def test_special_dish_bonus_not_above_best_named_dish() -> None:
    """特殊加成叠上去，3★ 吃到的总精力不超过定点菜 5★ 的最高值（36+15=51）。"""
    best = NAMED_MAX_5 = 36 + 3 * 5
    from server import kitchen_special as ks

    bonus = {"lantern_sashimi": 9, "tide_bone_soup": 6, "moon_bean_stew": 8, "lamp_sprout_stir": 6, "moon_bean_cake": 5}
    for key, extra in bonus.items():
        assert key in ks.SPECIAL_DISH_KEYS
        assert KITCHEN_DISHES[key]["energy"] + 3 * 3 + extra <= best, key


def test_cook_daily_limits() -> None:
    asyncio.run(_test_cook_daily_limits())


async def _test_cook_daily_limits() -> None:
    import os
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp(prefix="cook-limit-"))
    os.environ["DATA_DIR"] = str(tmp)
    from server import config, db, kitchen

    config.DATA_DIR = tmp
    config.DB_PATH = tmp / "relay.db"
    db.DATA_DIR = tmp
    db.DB_PATH = tmp / "relay.db"
    await db.init_db()
    key = await db.create_api_key("limit@example.com")
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], "厨限", "", "naturalist", "")
    kid = row["id"]
    async with db.connect() as conn:
        sid = (await (await conn.execute(
            "SELECT id FROM stewards WHERE key_id=?", (kid,)
        )).fetchone())[0]
    dish = "garlic_oyster"
    for ing in KITCHEN_DISHES[dish]["ings"]:
        async with db.connect() as conn:
            await db.add_item(conn, sid, ing, 20)
            await conn.commit()
    async with db.connect() as conn:
        await db.add_item(conn, sid, "crop_kale", 24)
        await db.add_item(conn, sid, "fish_herring", 24)
        await conn.commit()
    for _ in range(config.KITCHEN_RECIPE_COOK_DAILY):
        await kitchen.kitchen_ops(kid, f"cook {dish}")
    try:
        await kitchen.kitchen_ops(kid, f"cook {dish}")
        raise AssertionError("recipe limit should refuse")
    except ValueError as exc:
        assert "定点菜" in str(exc), exc
    for _ in range(config.KITCHEN_MIX_COOK_DAILY):
        await kitchen.kitchen_ops(kid, "cook crop_kale fish_herring")
    try:
        await kitchen.kitchen_ops(kid, "cook crop_kale fish_herring")
        raise AssertionError("mix limit should refuse")
    except ValueError as exc:
        assert "自由组合" in str(exc), exc


def main() -> None:
    test_named_dishes_star3_covers_vend()
    test_eatery_ref_beats_vend()
    test_named_dish_energy_beats_raw()
    test_mix_star3_covers_bucket()
    test_mix_energy_beats_raw()
    test_energy_ladder_mix_below_named_dishes()
    test_cook_daily_limits()
    print("cook price tests ok")
    print(f"{'菜':<16} {'材料':>4} {'3★回收':>6} {'5★回收':>6} {'精力':>4} {'小馆参考':>6}  3★回收盈")
    from server.catalog import dish_item, eatery_reference_price
    for key, meta in KITCHEN_DISHES.items():
        cost = dish_ingredient_cost(key)
        s3 = dish_sell_price(key, 3)
        ref = eatery_reference_price(dish_item(key, 3))
        print(
            f"{meta['name']:<16} {cost:4d} {s3:6d} "
            f"{dish_sell_price(key, 5):6d} {meta['energy']:4d} {ref:6d}  {s3 - cost:+d}"
        )
    print("乱炖兜底示例：j tier5 1★ =", mix_sell_price("j", 5, 1), "票")


if __name__ == "__main__":
    main()
