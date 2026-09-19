"""batch66：合伙船、拔除灰肥、风暴残骸、岸上地陷、方案缺树、鱼拓/船模。"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_catalog_trees_craft_collections():
    from server.catalog import CROPS, CRAFT_ITEMS, CRAFT_RECIPES, ITEM_NAMES
    from server.island_collections import ENTRIES
    from server.home_drinks import RECIPES

    for key in ("pomelo", "lemon", "olive", "mulberry", "coffee", "cacao"):
        assert key in CROPS, key
        assert CROPS[key].get("tree")
    assert "柚子" in CROPS["pomelo"]["name"]
    assert "craft_gyotaku" in CRAFT_ITEMS
    assert "craft_boat_model" in CRAFT_ITEMS
    assert "ash_fert" in CRAFT_ITEMS
    assert "wreck_scrap" in CRAFT_ITEMS
    assert "gyotaku" in CRAFT_RECIPES
    assert "boat_model" in CRAFT_RECIPES
    keys = {e[0] for e in ENTRIES}
    assert "craft_gyotaku" in keys
    assert "craft_boat_model" in keys
    assert "pomelo_tea" in RECIPES
    assert "lemon_water" in RECIPES
    assert "病株灰肥" in ITEM_NAMES.get("ash_fert", "")


def test_docs_name_partner_boat():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    help_txt = (root / "server/mcp_dispatch.py").read_text(encoding="utf-8")
    assert "合伙 开 漂航船" in help_txt
    readme = (root.parent / "README.md").read_text(encoding="utf-8")
    assert "合伙 开 漂航船" in readme
    game = (root / "server/game.py").read_text(encoding="utf-8")
    assert "合伙 开 漂航船" in game
    manual = (root / "server/templates/partials/island-manual-content.html").read_text(
        encoding="utf-8"
    )
    assert "合伙" in manual
    track = (root.parent / "docs/TIDE_FULL_EXPANSION.md").read_text(encoding="utf-8")
    assert "合伙船" in track and "⬜ | 合伙船" not in track
