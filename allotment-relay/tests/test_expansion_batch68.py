"""batch68：方案点名作物/菜、鱼加工、收费服务、耐久册、事件册、排水、畜病。"""
from __future__ import annotations


def test_plan_crops_and_dishes():
    from server.catalog import CRAFT_ITEMS, CRAFT_RECIPES, CROPS, HEARTH_RECIPES, KITCHEN_DISHES
    from server.expansion_content import PLAN_CROP_NAMES, PLAN_DISH_NAMES

    names = {m.get("name") for m in CROPS.values()}
    missing = PLAN_CROP_NAMES - names
    assert not missing, missing

    dish_names = {m.get("name") for m in KITCHEN_DISHES.values()}
    dish_names |= {m.get("name") for m in HEARTH_RECIPES.values()}
    missing_d = PLAN_DISH_NAMES - dish_names
    assert not missing_d, missing_d

    for key in (
        "proc_pickled_fish", "proc_sashimi", "proc_kimchi",
        "proc_salted_egg", "boat_wax", "damp_guard", "bandage", "patch_cloth",
    ):
        assert key in CRAFT_ITEMS, key
    for key in ("pickled_fish", "sashimi", "kimchi", "boat_wax"):
        assert key in CRAFT_RECIPES, key


def test_event_catalog_and_durability():
    from server import durability, event_catalog, npc_services
    from server.works import PROJECT_BY_SLUG

    assert event_catalog.named_count() >= 50
    assert event_catalog.fatal_count() >= 5
    assert event_catalog.plan_pool_ok()
    assert durability.efficiency(100, 100) == 1.0
    assert durability.efficiency(0, 100) >= 0.45
    assert durability.fail_bonus(10, 100) > 0
    assert "drain_works" in PROJECT_BY_SLUG
    assert PROJECT_BY_SLUG["drain_works"]["bonus"] == "drain"
    for key in (
        "whet", "fish_process", "soil_test", "animal_wash",
        "furnish", "move_furn", "boat_repair", "vet", "gyotaku",
    ):
        assert key in npc_services.SERVICES
    assert npc_services.resolve("磨刀") == "whet"
    assert npc_services.resolve("鱼处理") == "fish_process"


def test_barn_ailments_and_cascade_imports():
    from server.barn_disease import BARN_AILMENTS, BARN_AILMENT_ALIASES
    from server import play_cascade

    for key in ("turkey_pox", "goose_gout", "quail_chill", "alpaca_rash", "dystocia"):
        assert key in BARN_AILMENTS
    assert BARN_AILMENT_ALIASES["火羽疹"] == "turkey_pox"
    assert BARN_AILMENT_ALIASES["驼疹"] == "alpaca_rash"
    assert callable(play_cascade.hint)


def test_docs_batch68():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    help_txt = (root / "server/mcp_dispatch.py").read_text(encoding="utf-8")
    assert "收费服务" in help_txt
    track = (root.parent / "docs/TIDE_FULL_EXPANSION.md").read_text(encoding="utf-8")
    assert "tide-full-expansion-source.md" in track
    assert "点名册每条≥2路" in track
    game = (root / "server/game.py").read_text(encoding="utf-8")
    assert "收费服务" in game
    assert "岸下排水" in game
