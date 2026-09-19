"""batch67：品质因子、薄荷窜地、特殊料理、木筏/钓位别名、难产、留种履历。"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_catalog_fish_boats_dishes_craft():
    from server.catalog import CRAFT_ITEMS, CRAFT_RECIPES, CROPS, HEARTH_RECIPES, KITCHEN_DISHES, SEA_CATCH
    from server.config import BOATS, VOYAGE_ROUTES, resolve_boat_key
    from server.kitchen_special import SPECIAL_DISH_KEYS
    from server.sea_layer_pref import resolve_layer

    for key in (
        "needlefish", "mudskipper", "horse_mackerel", "black_seabream",
        "hairtail", "skipjack", "angler", "fogfin",
    ):
        assert key in SEA_CATCH, key
    assert 50 <= len(SEA_CATCH) <= 60
    assert "raft" in BOATS
    assert BOATS["raft"]["rank"] == 0
    assert resolve_boat_key("木筏") == "raft"
    assert resolve_boat_key("舢板") == "skiff"
    assert resolve_boat_key("帆船") == "smack"
    assert resolve_boat_key("小渔船") == "watch_hoy"
    assert resolve_boat_key("双桅") == "drifter"
    assert resolve_boat_key("雾海") == "longliner"
    assert VOYAGE_ROUTES["near"]["min_boat"] == "raft"
    assert resolve_layer("栈桥") == "shore"
    assert resolve_layer("礁") == "near"
    assert resolve_layer("船尾") == "near"
    assert resolve_layer("浅湾") == "near"
    assert len(SPECIAL_DISH_KEYS) >= 15
    for key in (
        "tide_bone_soup", "moon_bean_cake", "red_algae_soup", "night_lantern_tea",
        "black_salt_fish", "fog_mushroom_soup",
    ):
        assert key in SPECIAL_DISH_KEYS
        assert key in KITCHEN_DISHES
    assert "proc_candied_fruit" in CRAFT_ITEMS
    assert "proc_fruit_vinegar" in CRAFT_ITEMS
    assert "candied_fruit" in CRAFT_RECIPES
    assert "fruit_vinegar" in CRAFT_RECIPES
    names = {r.get("name") for r in HEARTH_RECIPES.values()}
    assert "糖渍梨" in names
    assert "醋渍李" in names
    assert "柠檬醋" in names
    assert "蜜桃糖浆" in names
    assert CROPS["garden_mint"]["name"] == "薄荷"
