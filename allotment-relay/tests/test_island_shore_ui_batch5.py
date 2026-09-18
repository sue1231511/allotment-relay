#!/usr/bin/env python3
"""batch5：/island 港口水层/搏鱼/解挂/部件与小屋配种 API 映射。"""
from __future__ import annotations

import pytest

from server.v1 import hut_service, shore_service


def test_shore_command_layer_unsnag_fight_parts():
    assert shore_service._command("layer", "deep") == ("tide", "水层 deep")
    assert shore_service._command("unsnag", "硬拉") == ("tide", "解挂 硬拉")
    assert shore_service._command("fishfight", "放走") == ("tide", "搏鱼 放走")
    assert shore_service._command("voyage", "parts repair") == ("tide", "voyage 部件 修")


def test_shore_command_layer_bad():
    from server.v1.errors import ApiError

    with pytest.raises(ApiError):
        shore_service._command("layer", "abyss")


def test_hut_command_barn_breed():
    assert hut_service._command("barn_breed", "2") == ("barn", "breed 2")
