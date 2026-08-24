#!/usr/bin/env python3
"""盐风崖潮脉矿：买镐、探脉、挖、洗、开坑。"""
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


async def _enroll(db, email: str, name: str) -> tuple[int, int]:
    key = await db.create_api_key(email)
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], name, "", "naturalist", "")
    async with db.connect() as conn:
        sid = (await (await conn.execute(
            "SELECT id FROM stewards WHERE key_id=?", (row["id"],)
        )).fetchone())[0]
    return row["id"], sid


def _quiet_random(mod) -> None:
    mod.random.choices = lambda keys, weights=None, k=1: [keys[0]]  # type: ignore[method-assign]
    mod.random.randint = lambda a, b: a  # type: ignore[method-assign]
    mod.random.random = lambda: 0.99  # type: ignore[method-assign]


async def test_help_and_empty() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="quarry-help-"))
    db = await _boot(tmp)
    kid, _sid = await _enroll(db, "qh@example.com", "看崖人")
    from server import quarry

    empty = await quarry.quarry_ops(kid, "")
    help_txt = await quarry.quarry_ops(kid, "help")
    assert "探脉" in empty and "挖" in empty and "买镐" in empty, empty
    assert "mine_ops" in empty and "tide_ops dig" in empty, empty
    assert empty == help_txt
    status = await quarry.quarry_ops(kid, "status")
    assert "盐风崖" in status and "坑1" in status and "无镐" in status, status


async def test_buy_prospect_hew_wash() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="quarry-loop-"))
    db = await _boot(tmp)
    kid, sid = await _enroll(db, "ql@example.com", "挥镐人")
    from server import health, quarry

    _quiet_random(quarry)
    _quiet_random(health)

    no_pick = await _expect_error(quarry.quarry_ops(kid, "挖"))
    assert "买镐" in no_pick, no_pick

    bought = await quarry.quarry_ops(kid, "买镐")
    assert "T1" in bought and "盐风镐" in bought, bought
    again = await quarry.quarry_ops(kid, "买镐")
    assert "已经有" in again, again

    found = await quarry.quarry_ops(kid, "探脉")
    assert "盐脉" in found or "页岩" in found or "铜绿" in found, found
    assert "挖" in found, found

    twice = await _expect_error(quarry.quarry_ops(kid, "探脉"))
    assert "刚探过" in twice or "还有" in twice, twice

    hewed = await quarry.quarry_ops(kid, "挖 1")
    assert "挖" in hewed and "精力" in hewed, hewed
    cooling = await _expect_error(quarry.quarry_ops(kid, "挖 1"))
    assert "刚挥过" in cooling, cooling

    async with db.connect() as conn:
        raw = await (await conn.execute(
            "SELECT item, quantity FROM satchel WHERE steward_id=? AND item LIKE 'quarry_%'",
            (sid,),
        )).fetchall()
        pick = (await (await conn.execute(
            "SELECT pick_tier, hews_total FROM steward_quarry WHERE steward_id=?",
            (sid,),
        )).fetchone())
    assert raw, "should have raw ore"
    assert pick[0] == 1 and pick[1] >= 1, pick

    item, qty = raw[0]
    from server.catalog import QUARRY_ORES, item_label
    washed = await quarry.quarry_ops(kid, f"洗 {item_label(item)} {qty}")
    assert "洗净" in washed, washed
    refined = QUARRY_ORES[item]["refined"]
    async with db.connect() as conn:
        have = (await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item=?",
            (sid, refined),
        )).fetchone())
    assert have and have[0] == qty, have


async def test_claim_and_upgrade_gate() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="quarry-claim-"))
    db = await _boot(tmp)
    kid, sid = await _enroll(db, "qc@example.com", "开坑人")
    from server import quarry

    preview = await quarry.quarry_ops(kid, "开坑")
    assert "50" in preview and "确认" in preview, preview
    bought = await quarry.quarry_ops(kid, "开坑 确认")
    assert "坑2" in bought, bought
    async with db.connect() as conn:
        count = (await (await conn.execute(
            "SELECT claim_count FROM steward_quarry WHERE steward_id=?", (sid,)
        )).fetchone())[0]
        ready = (await (await conn.execute(
            "SELECT ready_at FROM quarry_claims WHERE steward_id=? AND slot=2",
            (sid,),
        )).fetchone())[0]
    assert count == 2
    assert ready > 0

    await quarry.quarry_ops(kid, "买镐")
    async with db.connect() as conn:
        await conn.execute("UPDATE stewards SET tickets=tickets+200 WHERE id=?", (sid,))
        await conn.commit()
    up = await quarry.quarry_ops(kid, "升镐")
    assert "铜镐" in up and "确认" in up, up
    blocked = await _expect_error(quarry.quarry_ops(kid, "升镐 确认"))
    assert "缺少" in blocked, blocked


async def test_tt_buy_pick_and_names() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="quarry-tt-"))
    db = await _boot(tmp)
    kid, sid = await _enroll(db, "qt@example.com", "杂货镐")
    from server import tt
    from server.catalog import resolve_item_key, resolve_ore_key

    assert resolve_ore_key("海盐砂") == "quarry_salt_sand"
    assert resolve_item_key("海盐晶") == "quarry_salt"
    assert resolve_item_key("铜锭") == "quarry_copper_bar"

    msg = await tt.tt_ops(kid, "buy 盐风镐")
    assert "盐风镐" in msg, msg
    async with db.connect() as conn:
        from server import quarry
        prof = await quarry.ensure_profile(conn, sid)
        await conn.commit()
    assert prof["pick_tier"] >= 1, prof


async def test_flood_does_not_block_hew() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="quarry-flood-"))
    db = await _boot(tmp)
    kid, sid = await _enroll(db, "qf@example.com", "涨潮矿")
    from server import health, quarry, world

    _quiet_random(quarry)
    _quiet_random(health)
    old_tide = world.current_tide
    world.current_tide = lambda: "flood"  # type: ignore[assignment]
    try:
        await quarry.quarry_ops(kid, "买镐")
        await quarry.quarry_ops(kid, "探脉")
        msg = await quarry.quarry_ops(kid, "挖")
        assert "挖" in msg, msg
    finally:
        world.current_tide = old_tide
    async with db.connect() as conn:
        hews = (await (await conn.execute(
            "SELECT hews_total FROM steward_quarry WHERE steward_id=?", (sid,)
        )).fetchone())[0]
    assert hews >= 1


async def test_public_snapshot() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="quarry-pub-"))
    await _boot(tmp)
    from server import quarry
    snap = await quarry.public_snapshot()
    assert "climate" in snap and "hints" in snap
    assert "hews_today" in snap and "feed" in snap


async def _expect_error(coro) -> str:
    try:
        out = await coro
    except ValueError as exc:
        return str(exc)
    raise AssertionError(f"expected error, got: {out}")


def test_quarry_help_and_empty() -> None:
    asyncio.run(test_help_and_empty())


def test_quarry_loop() -> None:
    asyncio.run(test_buy_prospect_hew_wash())


def test_quarry_claim() -> None:
    asyncio.run(test_claim_and_upgrade_gate())


def test_quarry_tt_and_names() -> None:
    asyncio.run(test_tt_buy_pick_and_names())


def test_quarry_flood() -> None:
    asyncio.run(test_flood_does_not_block_hew())


def test_quarry_public() -> None:
    asyncio.run(test_public_snapshot())


if __name__ == "__main__":
    test_quarry_help_and_empty()
    test_quarry_loop()
    test_quarry_claim()
    test_quarry_tt_and_names()
    test_quarry_flood()
    test_quarry_public()
    print("ok")
