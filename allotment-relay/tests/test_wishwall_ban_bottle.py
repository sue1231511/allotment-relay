#!/usr/bin/env python3
"""许愿墙两条反馈：赶海 BOTTLE_WASH_CHANCE；出海归港也走禁捞。"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

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


async def _enroll(db, email: str, name: str, *, tickets: int = 200) -> tuple[int, int]:
    key = await db.create_api_key(email)
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], name, "", "naturalist", "")
    async with db.connect() as conn:
        sid = (await (await conn.execute(
            "SELECT id FROM stewards WHERE key_id=?", (row["id"],)
        )).fetchone())[0]
        await conn.execute(
            "UPDATE stewards SET last_bar_shift_at=?, energy=80, tickets=?, "
            "hut_built=1, hut_level=2, boat_key='skiff' WHERE id=?",
            (db.now(), tickets, sid),
        )
        await conn.commit()
    return row["id"], sid


def test_bottle_wash_chance_exists() -> None:
    from server import config

    assert hasattr(config, "BOTTLE_WASH_CHANCE")
    assert hasattr(config, "BOTTLE_WISH_CHANCE")
    assert 0 < float(config.BOTTLE_WASH_CHANCE) < 1
    assert float(config.BOTTLE_WISH_CHANCE) == float(config.BOTTLE_WASH_CHANCE)


def test_island_collections_entries_is_list() -> None:
    from server.island_collections import ENTRIES

    assert isinstance(ENTRIES, list)
    assert ENTRIES
    assert ENTRIES[0][0] == "kale"
    assert ENTRIES[-1][0] == "craft_seed_box"


def test_try_wash_ashore_survives_missing_constant() -> None:
    asyncio.run(_test_try_wash_ashore_survives_missing_constant())


async def _test_try_wash_ashore_survives_missing_constant() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="bottle-wash-"))
    db = await _boot(tmp)
    from server import bottles, config

    kid, sid = await _enroll(db, "wash@example.com", "铲沙人")
    s = await db.get_steward_by_id(sid)
    saved_wash = getattr(config, "BOTTLE_WASH_CHANCE", None)
    saved_wish = getattr(config, "BOTTLE_WISH_CHANCE", None)
    try:
        if hasattr(config, "BOTTLE_WASH_CHANCE"):
            delattr(config, "BOTTLE_WASH_CHANCE")
        if hasattr(config, "BOTTLE_WISH_CHANCE"):
            delattr(config, "BOTTLE_WISH_CHANCE")
        with patch("server.bottles.random.random", return_value=0.99):
            msg = await bottles.try_wash_ashore(s)
        assert msg is None
    finally:
        if saved_wash is not None:
            config.BOTTLE_WASH_CHANCE = saved_wash
        if saved_wish is not None:
            config.BOTTLE_WISH_CHANCE = saved_wish


def test_ban_copy_covers_voyage() -> None:
    from server import fish_ban

    text = fish_ban.brief_ban(100) + fish_ban.notice_text(100)
    assert "出海归港" in text
    assert "渔排收" in text
    assert "不能卖" in text or "不能进袋" in text


def test_refuse_trade_blocks_banned_fish() -> None:
    from server import fish_ban

    with patch.object(fish_ban, "banned_species", return_value=["glassshrimp"]):
        assert fish_ban.refuse_trade("fish_glassshrimp")
        assert fish_ban.refuse_trade("glassshrimp")
        assert fish_ban.refuse_trade("fish_mackerel") is None
        assert fish_ban.refuse_trade("crop_kale") is None


def test_voyage_return_releases_banned_fish() -> None:
    asyncio.run(_test_voyage_return_releases_banned_fish())


async def _test_voyage_return_releases_banned_fish() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="ban-voyage-"))
    db = await _boot(tmp)
    from server import fish_ban, marine

    _, sid = await _enroll(db, "deep@example.com", "深漂人", tickets=200)
    async with db.connect() as conn:
        await conn.execute(
            """
            INSERT INTO voyages (steward_id, route, departed_at, returns_at, status, encounter)
            VALUES (?,?,?,?, 'sailing', ?)
            """,
            (
                sid,
                "deep",
                db.now() - 100,
                db.now() - 1,
                json.dumps({"voyage_fish": [], "boat_key": "skiff"}),
            ),
        )
        await conn.commit()
        voyage = await marine._get_voyage(conn, sid)
        assert voyage

    async def _no_extra(*_a, **_k):
        return ""

    with (
        patch.object(fish_ban, "banned_species", return_value=["glassshrimp"]),
        patch.object(marine, "voyage_loot_table", return_value=["fish_glassshrimp"] * 8),
        patch.object(marine.random, "random", return_value=0.99),
        patch("server.event_gen.generate_naval_encounter", return_value=None),
        patch("server.events.roll_after_action", new=_no_extra),
        patch("server.commons.roll_discovery", new=_no_extra),
    ):
        async with db.connect() as conn:
            s = await db.get_steward_by_id(sid)
            msg, fish_loot, hailed = await marine._resolve_voyage(conn, dict(s), voyage)
            await conn.commit()

    assert not hailed
    assert fish_loot == []
    assert "放生" in msg
    stock = await db.get_satchel(sid)
    assert stock.get("fish_glassshrimp", 0) == 0, stock
    async with db.connect() as conn:
        tickets = int((await (await conn.execute(
            "SELECT tickets FROM stewards WHERE id=?", (sid,)
        )).fetchone())[0])
    assert tickets < 200


def test_vend_refuses_banned_fish() -> None:
    asyncio.run(_test_vend_refuses_banned_fish())


async def _test_vend_refuses_banned_fish() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="ban-vend-"))
    db = await _boot(tmp)
    from server import fish_ban, game

    kid, sid = await _enroll(db, "vend@example.com", "卖虾人", tickets=80)
    async with db.connect() as conn:
        await db.add_item(conn, sid, "fish_glassshrimp", 1)
        await conn.commit()

    with patch.object(fish_ban, "banned_species", return_value=["glassshrimp"]):
        try:
            await game.tote_ops(kid, "vend 玻璃虾 1")
            raise AssertionError("banned fish should not vend")
        except ValueError as exc:
            assert "禁捞" in str(exc)
    stock = await db.get_satchel(sid)
    assert stock.get("fish_glassshrimp", 0) == 1
