"""batch63：consistency 绿、relay_manual 关键针、MCP 描述对齐。"""
from __future__ import annotations

import asyncio


def test_relay_manual_expansion_needles():
    from server import game

    text = asyncio.run(game.relay_manual())
    for needle in (
        "份地地况写成熟、待打理、待浇水各几块",
        "价格自定",
        "投稿 岸上旧收音机",
        "套餐客",
        "shop 套餐",
    ):
        assert needle in text, needle


def test_mcp_steward_and_kitchen_blobs():
    from tests import test_consistency as tc

    tc.test_mcp_descriptions()
