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
    assert "暗号" in help_text and "小包间" in help_text
    assert "大厅" in help_text

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


def test_lounge_booth_code() -> None:
    asyncio.run(_test_lounge_booth_code())


async def _test_lounge_booth_code() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="lounge-booth-"))
    db = await _boot(tmp)
    from server import lounge

    async def enroll(email: str, name: str) -> tuple[str, int]:
        key = await db.create_api_key(email)
        row = await db.get_key_row(key)
        await db.enroll_steward(row["id"], name, "", "naturalist", "")
        return key, row["id"]

    key_a, id_a = await enroll("a@example.com", "岸边甲")
    key_b, id_b = await enroll("b@example.com", "岸边乙")
    key_c, id_c = await enroll("c@example.com", "岸边丙")
    _key_d, id_d = await enroll("d@example.com", "岸边丁")

    try:
        await lounge.lounge_ops(id_a, "暗号 a")
        raise AssertionError("short code should fail")
    except ValueError as exc:
        assert "至少" in str(exc)

    await lounge.lounge_ops(id_d, "say 大厅公开")

    enter_a = await lounge.lounge_ops(id_a, "暗号 潮声今晚")
    assert "小包间·" in enter_a
    assert "大厅看不见" in enter_a
    assert "全服聊天室公约" not in enter_a

    status = await lounge.lounge_ops(id_a, "暗号")
    assert "小包间·" in status
    assert "岸边甲" in status

    same_key = lounge.booth_key_from_code("潮声今晚")
    also_same = lounge.booth_key_from_code("  潮声今晚  ")
    assert same_key == also_same
    assert lounge.booth_label(same_key).startswith("小包间·")
    assert len(lounge.booth_label(same_key)) == len("小包间·ABCD")

    await lounge.lounge_ops(id_b, "对暗号 潮声今晚")
    await lounge.lounge_ops(id_c, "包间 别的屋子")

    await lounge.lounge_ops(id_a, "say 包间密话甲")
    await lounge.lounge_ops(id_b, "say 包间密话乙")
    await lounge.lounge_ops(id_c, "say 另一间的话")

    hall_say = await lounge.lounge_ops(id_a, "大厅")
    assert "已回大厅" in hall_say
    assert "全服聊天室公约" in hall_say
    assert "大厅公开" in hall_say
    assert "包间密话甲" not in hall_say

    # A left; B still in the first booth. Re-enter A and confirm shared history.
    await lounge.lounge_ops(id_a, "暗号 潮声今晚")
    scan_booth = await lounge.lounge_ops(id_a, "scan")
    assert "包间密话甲" in scan_booth
    assert "包间密话乙" in scan_booth
    assert "另一间的话" not in scan_booth
    assert "大厅公开" not in scan_booth
    assert "全服聊天室公约" not in scan_booth

    scan_c = await lounge.lounge_ops(id_c, "scan")
    assert "另一间的话" in scan_c
    assert "包间密话甲" not in scan_c

    hall = await lounge.list_messages()
    hall_bodies = [m["body"] for m in hall]
    assert "大厅公开" in hall_bodies
    assert "包间密话甲" not in hall_bodies
    assert "另一间的话" not in hall_bodies

    public = await lounge.list_hall_messages()
    assert public["in_booth"] is False
    assert public["booth_label"] == "大厅"
    assert "booth_key" not in public
    public_bodies = [m["body"] for m in public["messages"]]
    assert "包间密话甲" not in public_bodies

    mine = await lounge.human_list_messages(key_b)
    assert mine["in_booth"] is True
    assert "booth_key" not in mine
    assert mine["booth_label"].startswith("小包间·")
    mine_bodies = [m["body"] for m in mine["messages"]]
    assert "包间密话乙" in mine_bodies
    assert "大厅公开" not in mine_bodies

    left = await lounge.human_enter_booth(key_b, "")
    assert left["in_booth"] is False
    assert left["booth_label"] == "大厅"
    assert "booth_key" not in left

    profile = await lounge.human_profile(key_a)
    assert profile["in_booth"] is True
    assert "booth_key" not in profile

    # ASCII casefold shares a booth
    await lounge.human_enter_booth(key_a, "HelloBooth")
    await lounge.human_enter_booth(key_b, "hellobooth")
    assert lounge.booth_key_from_code("HelloBooth") == lounge.booth_key_from_code("hellobooth")


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


def main() -> None:
    test_lounge_mcp_and_web()
    test_lounge_booth_code()
    print("lounge tests ok")


if __name__ == "__main__":
    main()
