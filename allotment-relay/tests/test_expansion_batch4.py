#!/usr/bin/env python3
"""第二批余量：繁殖、部件、搏鱼、水层。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_sea_layers():
    from server import sea_layer_pref

    assert "near" in sea_layer_pref.zones_for_layer("near")
    assert "deep" in sea_layer_pref.zones_for_layer("deep")[0]


def test_boat_parts_fail():
    from server import boat_parts

    extra = boat_parts.fail_bonus({"sail": (20, 100), "rudder": (80, 100), "lantern": (90, 100)})
    assert extra > 0.05


def test_breedable():
    from server import barn_breeding

    assert "chicken" in barn_breeding.BREEDABLE
