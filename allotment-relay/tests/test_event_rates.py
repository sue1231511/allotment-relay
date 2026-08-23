#!/usr/bin/env python3
"""随机事件倍率与新野生动物池。"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_event_rate_mult() -> None:
    from server import config

    assert config.EVENT_RATE_MULT == 1.3
    assert config.EVENT_ROLL_CHANCE == round(0.08 * 1.3, 4)
    assert config.SCRUMP_EVENT_CHANCE == round(0.18 * 1.3, 4)
    assert config.FARM_TRIGGER_CHANCE["gather"] == round(0.06 * 1.3, 4)


def test_new_wildlife_keys() -> None:
    from server.farming import WILDLIFE

    keys = {w["key"] for w in WILDLIFE}
    assert {"crab", "moth", "turtle"}.issubset(keys)


async def _test_world_pulse_pool() -> None:
    from server import event_gen

    seen = set()
    for _ in range(80):
        pulse = event_gen.generate_world_pulse()
        seen.add(pulse["effect"])
    assert "warm_breeze" in seen
    assert "gnat_swarm" in seen


def test_world_pulse_pool() -> None:
    asyncio.run(_test_world_pulse_pool())


if __name__ == "__main__":
    test_event_rate_mult()
    test_new_wildlife_keys()
    test_world_pulse_pool()
    print("ok")
