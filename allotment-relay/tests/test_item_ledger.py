#!/usr/bin/env python3
"""物品履历：行囊仍叠放，有来历的东西另记一本。"""
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


async def _enroll(db, email: str, name: str) -> tuple[str, int, int]:
    key = await db.create_api_key(email)
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], name, "", "naturalist", "")
    async with db.connect() as conn:
        sid = (await (await conn.execute(
            "SELECT id FROM stewards WHERE key_id=?", (row["id"],)
        )).fetchone())[0]
    return key, row["id"], sid


def test_help_copy() -> None:
    from server import mcp_dispatch
    from server.mcp_app import mcp

    assert "履历" in mcp_dispatch.TOTE_HELP
    assert "潮誓戒" in mcp_dispatch.TOTE_HELP
    assert "甘蓝没有" in mcp_dispatch.TOTE_HELP
    tote = mcp._tool_manager.get_tool("tote_ops")
    assert "履历" in (tote.description or "")
    bag = (ROOT / "server/static/island/ui/bag.js").read_text(encoding="utf-8")
    assert "island-bag-story" in bag
    play_js = (ROOT / "server/static/play.js").read_text(encoding="utf-8")
    assert "play-item-story" in play_js
    assert "stockStoryBits" in play_js
    html = (ROOT / "server/templates/partials/island-manual-content.html").read_text(encoding="utf-8")
    assert "点开会写出从哪来" in html


def test_kale_has_no_story() -> None:
    asyncio.run(_test_kale_has_no_story())


async def _test_kale_has_no_story() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="ledger-kale-"))
    db = await _boot(tmp)
    _key, _kid, sid = await _enroll(db, "kale@example.com", "菜农")
    from server import ledger

    assert not ledger.is_notable("crop_kale")
    assert ledger.is_notable("tide_vow_ring")
    assert ledger.is_notable("quarry_gold_sand")
    assert ledger.is_notable("fish_swordfish")
    assert not ledger.is_notable("fish_herring")
    async with db.connect() as conn:
        n = await ledger.note_gain(conn, sid, "crop_kale", 1, "不该留下")
        await conn.commit()
    assert n == 0
    async with db.connect() as conn:
        stories = await ledger.stories_for(conn, sid)
    assert stories == []


def test_ring_inherits_vein_and_gift() -> None:
    asyncio.run(_test_ring_inherits_vein_and_gift())


async def _test_ring_inherits_vein_and_gift() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="ledger-ring-"))
    db = await _boot(tmp)
    _giver_key, giver_kid, giver = await _enroll(db, "yan@example.com", "晏安")
    _recv_key, recv_kid, recv = await _enroll(db, "mao@example.com", "猫猫")
    from server import game, ledger

    async with db.connect() as conn:
        await db.add_item(conn, giver, "quarry_gold_sand", 1)
        place = ledger.claim_place(1, "gold")
        await ledger.note_gain(
            conn, giver, "quarry_gold_sand", 1,
            f"金砂由晏安于{ledger.calendar_phrase()}在{place}掘出",
        )
        gone = await ledger.consume(conn, giver, "quarry_gold_sand", 1)
        inherited = [ledger.origin_snippet(lines, "quarry_gold_sand") for lines in gone]
        story = [f"潮誓戒由晏安于{ledger.calendar_phrase()}在岸工坊打造"] + [s for s in inherited if s]
        await db.add_item(conn, giver, "tide_vow_ring", 1)
        await ledger.birth(conn, giver, "tide_vow_ring", story, qty=1)
        await conn.commit()

    listed = await game.tote_ops(giver_kid, "list")
    assert "潮誓戒" in listed, listed
    assert "岸工坊打造" in listed, listed
    assert "盐风崖东脉" in listed, listed

    full = await game.tote_ops(giver_kid, "履历 潮誓戒")
    assert "岸工坊打造" in full, full
    assert "金砂" in full, full

    gifted = await game.tote_ops(giver_kid, "gift 猫猫 潮誓戒 1")
    assert "猫猫" in gifted, gifted

    recv_list = await game.tote_ops(recv_kid, "履历")
    assert "赠予猫猫" in recv_list, recv_list
    assert "岸工坊打造" in recv_list, recv_list
    async with db.connect() as conn:
        left = await ledger.stories_for(conn, giver, "tide_vow_ring")
        got = await ledger.stories_for(conn, recv, "tide_vow_ring")
    assert left == []
    assert len(got) == 1
    assert any("赠予猫猫" in ln for ln in got[0]["lines"])


def test_dashboard_stock_story() -> None:
    asyncio.run(_test_dashboard_stock_story())


async def _test_dashboard_stock_story() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="ledger-dash-"))
    db = await _boot(tmp)
    key, _kid, sid = await _enroll(db, "dash@example.com", "档客")
    from server import ledger, steward_dashboard

    async with db.connect() as conn:
        await db.add_item(conn, sid, "tide_vow_ring", 1)
        await ledger.note_gain(
            conn, sid, "tide_vow_ring", 1,
            f"潮誓戒由档客于{ledger.calendar_phrase()}从 Tt酱柜上买下",
        )
        await conn.commit()
    dash = await steward_dashboard.fetch_dashboard(key)
    ring = next(it for it in dash["stock"] if it["item"] == "tide_vow_ring")
    assert ring.get("story"), ring
    assert any("Tt酱" in ln or "买下" in ln for ln in ring["story"]), ring


def main() -> None:
    test_help_copy()
    test_kale_has_no_story()
    test_ring_inherits_vein_and_gift()
    test_dashboard_stock_story()
    print("item ledger tests ok")


if __name__ == "__main__":
    main()
