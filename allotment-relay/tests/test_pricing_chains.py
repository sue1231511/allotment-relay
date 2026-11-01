#!/usr/bin/env python3
"""加工链：成品回收价 ≤ 2.0 × 材料回收价合计；全部材料都能买到的配方不能形成循环。"""
from __future__ import annotations

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _ref(item: str) -> int:
    from server import pricing

    return pricing.ref_value(item)


def test_craft_recipes_obey_premium_cap() -> None:
    from server import catalog, pricing
    from server.price_book import BOOK

    checked = 0
    for key, r in catalog.CRAFT_RECIPES.items():
        out = r["out"]
        if out not in BOOK:      # 信物、小屋家具（家具走小屋折旧）
            continue
        cost = sum(_ref(i) * q for i, q in r["need"].items())
        got = _ref(out) * int(r.get("qty", 1))
        assert got <= pricing.P_MAX * cost + 1e-9, (key, got, cost)
        checked += 1
    assert checked > 30


def test_named_dishes_obey_premium_cap_at_every_star() -> None:
    from server import catalog, pricing

    for key, meta in catalog.KITCHEN_DISHES.items():
        cost = sum(_ref(i) for i in meta["ings"])
        for stars in range(1, 6):
            price = catalog.dish_sell_price(key, stars)
            assert price <= pricing.P_MAX * cost + 1e-9, (key, stars, price, cost)
        assert catalog.dish_base_sell(key) <= pricing.P_MAX * cost + 1e-9


def test_brine_kelp_pot_is_no_longer_capped_and_black_salt_fish_still_is() -> None:
    from server import catalog

    # 卤浸海藻锅原来的定价 70（材料 44 的 1.59 倍），5★ 119 被 2.0× 封顶压到 88。
    # 系统回收只小赚（3★ ≈ 材料 ×1.1），定价改回 48 以后 5★ 是 81，不再碰顶。
    assert catalog.dish_sell_price("brine_kelp_pot", 3) == 48
    assert catalog.dish_sell_price("brine_kelp_pot", 5) == 81 <= catalog.dish_cap("brine_kelp_pot")
    # 现在还会被封顶的例子：黑盐炖鱼 5★ 原价 149，封到 148
    assert catalog.dish_sell_price("black_salt_fish", 5) == catalog.dish_cap("black_salt_fish") == 148


def _worst_case_random(monkeypatch):
    """让 score_mix 里所有「随机加星」都命中，得到每个搭配的最高星级。"""
    from server import cook_mix

    class _Always:
        @staticmethod
        def random():
            return 0.0

        @staticmethod
        def choice(seq):
            return seq[0]

    monkeypatch.setattr(cook_mix, "random", _Always)


def test_free_mix_obeys_premium_cap(monkeypatch) -> None:
    """自由组合：两样全排列穷举 + 三到五样 6 万次随机，最高星级下也不超 2.0×。"""
    from server import catalog, cook_mix, pricing

    _worst_case_random(monkeypatch)
    pool = [
        i for i, p in catalog.ITEM_PRICES.items()
        if p > 0 and cook_mix.classify(i) not in ("refuse",)
        and not i.startswith(("fit_", "deco_", "live_", "tool_", "dish_", "meal_", "mix_"))
    ]
    steward = {"hut_built": 1, "hut_level": 2}

    def check(ings):
        res = cook_mix.score_mix(ings, steward, quality_bonus=3)
        cost = sum(catalog.suggested_price(i) for i in ings)
        sell = catalog.suggested_price(res.item)
        assert sell <= pricing.mix_cap_from_tier(res.tier), (ings, res.item, sell, res.tier)
        if cost > 0:
            assert sell <= pricing.P_MAX * cost + 1e-9, (ings, res.item, sell, cost)
        return sell, cost

    rng = random.Random(20260427)
    worst = 0.0
    for _ in range(60000):
        n = rng.randint(2, 5)
        ings = [rng.choice(pool) for _ in range(n)]
        sell, cost = check(ings)
        if cost > 0:
            worst = max(worst, sell / cost)
    # 改版前最高 3.6 倍；现在最高恰好 2.0 倍
    assert worst <= pricing.P_MAX + 1e-9, worst
    sample = rng.sample(pool, 120)
    for a in sample:
        for b in sample:
            check([a, b])


def test_mix_cap_is_below_two_times_real_food_value(monkeypatch) -> None:
    """档位 = 材料身价 // 20，封顶取下界，所以对非垃圾搭配 sell ≤ 2×实际身价。"""
    from server import catalog, cook_mix, pricing

    _worst_case_random(monkeypatch)
    rng = random.Random(7)
    pool = [i for i, p in catalog.ITEM_PRICES.items()
            if p >= 6 and cook_mix.classify(i) in ("produce", "protein", "season", "rich")]
    for _ in range(20000):
        ings = [rng.choice(pool) for _ in range(rng.randint(2, 4))]
        res = cook_mix.score_mix(ings, {"hut_built": 1, "hut_level": 2}, quality_bonus=3)
        food = sum(catalog.ITEM_PRICES.get(i, 1) for i in ings)
        assert catalog.suggested_price(res.item) <= pricing.P_MAX * max(food, 12) + 1e-9, (ings, res.item)


# ── 闭合循环：只靠系统买入、层层加工，造不出比买入成本更贵的回收价 ───────────
def system_cost_closure(recipes: dict) -> dict[str, float]:
    """C(x) = min(最低买入价, 任一配方 Σ C(材料)/产出量)，材料有一样没 C 就不算。不动点迭代。"""
    from server import pricing
    from server.price_book import BOOK

    cost: dict[str, float] = {}
    for item in BOOK:
        low = pricing.min_buy_price(item)
        if low > 0:
            cost[item] = float(low)
    changed = True
    while changed:
        changed = False
        for r in recipes.values():
            if not all(i in cost for i in r["need"]):
                continue
            total = sum(cost[i] * q for i, q in r["need"].items()) / int(r.get("qty", 1))
            out = r["out"]
            if out not in cost or total < cost[out] - 1e-9:
                cost[out] = total
                changed = True
    return cost


def violations(recipes: dict) -> list[tuple[str, int, float]]:
    from server import pricing

    bad = []
    for item, c in system_cost_closure(recipes).items():
        sell = pricing.ref_value(item)
        if sell >= c:
            bad.append((item, sell, c))
    return bad


def test_no_closed_buy_craft_sell_loop() -> None:
    from server import catalog

    assert violations(catalog.CRAFT_RECIPES) == []


def test_closure_test_catches_a_bad_recipe(monkeypatch) -> None:
    """反例：假造一条「漂绳×2 → 回收 30 的成品」配方，闭合测试必须报出来。"""
    from server import catalog, pricing
    from server.price_book import BOOK

    fake = dict(catalog.CRAFT_RECIPES)
    fake["fake_loop"] = {"out": "fake_out", "qty": 1, "need": {"drift_twine": 2}}
    monkeypatch.setitem(BOOK, "fake_out", {"B": 100, "cls": "made"})
    assert pricing.ref_value("fake_out") == 70
    assert [v[0] for v in violations(fake)] == ["fake_out"]


def test_refine_recipes_never_make_loot_from_shop_goods() -> None:
    """潮下炼制：产出里没有赃物（utl_），所以买货→炼制→赃物销赃的路走不通。"""
    from server import pricing, undertide_refine

    for key, meta in undertide_refine.RECIPES.items():
        assert not pricing.is_loot(meta["out"][0]), key
        for item, _q in meta["ings"]:
            assert not pricing.is_loot(item), key


if __name__ == "__main__":
    print("run with pytest (uses monkeypatch)")
