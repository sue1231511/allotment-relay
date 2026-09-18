#!/usr/bin/env python3
"""第三批余量：套装、禁捕稳定、层联动。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_hut_combos():
    from server.hut import HutBonus
    from server import hut_combos

    b = HutBonus(keys={"brick_hearth", "fridge", "cabinet"})
    active = hut_combos.apply_combos(b)
    assert "灶链" in active
    assert b.brew_mist >= 3


def test_furniture_combo_keys():
    from server import hut_combos

    assert "kitchen_line" in hut_combos.COMBO_SETS
    assert "storm_line" in hut_combos.COMBO_SETS


def test_storm_line_combo():
    from server.hut import HutBonus
    from server import hut_combos

    b = HutBonus(keys={"storm_shutter", "net_dreamcatcher", "tide_clock"})
    active = hut_combos.apply_combos(b)
    assert "防风铃阵" in active
