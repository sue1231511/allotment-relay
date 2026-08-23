#!/usr/bin/env python3
"""全服聊天室 — MCP + 网页 API。"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def _boot(tmp: Path):
    os.environ["DATA_DIR"] = str(tmp)
    from server import config, db

    config.DATA_DIR = tmp
    config.DB_PATH = tmp / "relay.db"
    db.DATA_DIR = tmp
    db.DB_PATH = tmp / "relay.db"
    await db.init_db()
    return db


def test_lounge_mcp_and_web() -> None:
    asyncio.run(_test_lounge_mcp_and_web())


async def _test_lounge_mcp_and_web() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="lounge-"))
    db = await _boot(tmp)
    from server import config, lounge

    key = await db.create_api_key("chat@example.com")
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], "聊天测试", "", "naturalist", "")

    help_text = await lounge.lounge_ops(row["id"], "help")
    assert "scan" in help_text and "say" in help_text
    assert "name" in help_text and "mod mute" in help_text

    scan_empty = await lounge.lounge_ops(row["id"], "")
    assert "全服聊天室公约" in scan_empty
    assert "完全免费" in scan_empty
    assert "bug" in scan_empty.lower() or "异常" in scan_empty

    await lounge.lounge_ops(row["id"], "say 温室要 shed erect")
    await asyncio.sleep(lounge.LOUNGE_COOLDOWN_SEC + 1)

    name_result = await lounge.lounge_ops(row["id"], "name 小明")
    assert "小明·聊天测试" in name_result

    profile = await lounge.human_profile(key)
    assert profile["who"] == "小明·聊天测试"
    assert profile["human_name"] == "小明"

    web_msg = await lounge.human_post(key, "人类也来答疑")
    assert web_msg["kind"] == "人类"
    assert web_msg["who"] == "小明·聊天测试"

    msgs = await lounge.list_messages()
    assert len(msgs) == 2
    assert msgs[0]["source"] == "mcp"
    assert msgs[0]["who"] == "聊天测试"
    assert msgs[1]["source"] == "web"
    assert msgs[1]["who"] == "小明·聊天测试"

    pinned = lounge.pinned_notice("https://example.com/register")
    assert "虚构" in pinned
    assert "example.com/register" in pinned
    assert "bug" in pinned.lower() or "异常" in pinned

    try:
        await lounge.human_post(key, "http://spam.example")
        raise AssertionError("should block links")
    except ValueError as exc:
        assert "链接" in str(exc)

    # moderation
    victim_key = await db.create_api_key("victim@example.com")
    victim_row = await db.get_key_row(victim_key)
    await db.enroll_steward(victim_row["id"], "违规玩家", "", "naturalist", "")

    old_mods = config.LOUNGE_MOD_NAMES
    config.LOUNGE_MOD_NAMES = frozenset(["聊天测试"])
    try:
        await lounge.lounge_ops(row["id"], "mod mute 违规玩家 5")
        try:
            await lounge.human_post(victim_key, "还想说话")
            raise AssertionError("muted user should not post")
        except ValueError as exc:
            assert "禁言" in str(exc)

        await lounge.lounge_ops(row["id"], "mod unmute 违规玩家")
        await lounge.human_post(victim_key, "解封了")

        await lounge.lounge_ops(row["id"], "mod ban 违规玩家")
        try:
            await lounge.human_post(victim_key, "又被踢了")
            raise AssertionError("banned user should not post")
        except ValueError as exc:
            assert "移出" in str(exc)
    finally:
        config.LOUNGE_MOD_NAMES = old_mods


def test_eatery_dine_energy_scales_with_price() -> None:
    from server import config
    from server.eatery import _eat_gain

    assert _eat_gain("papaya_salad", 78) >= 22
    assert _eat_gain("meal_generic", 98) >= int(98 / config.EATERY_TICKETS_PER_ENERGY)


def test_fishing_gear_payout_bonus() -> None:
    from server.gear import fish_catch_payout

    low = {
        "bait": {"tier": 1, "catch": 0.05},
        "rod": {"tier": 1, "catch": 0.08},
        "net": {"tier": 1, "catch": 0.1},
    }
    high = {
        "bait": {"tier": 5, "catch": 0.35},
        "rod": {"tier": 5, "catch": 0.45},
        "net": {"tier": 5, "catch": 0.55},
    }
    low_mult, low_bonus = fish_catch_payout(low, mode="cast")
    high_mult, high_bonus = fish_catch_payout(high, mode="cast")
    assert high_mult > low_mult
    assert high_bonus > low_bonus

    net_low_mult, net_low_bonus = fish_catch_payout(low, mode="net")
    net_high_mult, net_high_bonus = fish_catch_payout(high, mode="net")
    assert net_low_mult == 1.0
    assert net_high_mult == 1.0
    assert net_high_bonus > net_low_bonus
