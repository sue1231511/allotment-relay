#!/usr/bin/env python3
"""岸工坊：打/取、盐田、打捞、陈列柜。"""
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


async def _expect_error(coro) -> str:
    try:
        out = await coro
    except ValueError as exc:
        return str(exc)
    raise AssertionError(f"expected error, got: {out}")


async def _qty(db, sid: int, item: str) -> int:
    async with db.connect() as conn:
        row = await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item=?",
            (sid, item),
        )).fetchone()
    return int(row[0] if row else 0)


async def test_help_and_empty_clean() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="craft-help2-"))
    db = await _boot(tmp)
    kid, _sid = await _enroll(db, "ch2@example.com", "看砧人")
    from server import craft

    empty = await craft.craft_ops(kid, "")
    help_txt = await craft.craft_ops(kid, "help")
    assert "打 铜钉" in empty and "取" in empty and "打捞" in empty, empty
    assert "forge_ops" in empty and "tide_ops dig" in empty, empty
    assert empty == help_txt
    status = await craft.craft_ops(kid, "status")
    assert "砧" in status and "盐田" in status, status
    catalog = await craft.craft_ops(kid, "图鉴")
    assert "铜钉" in catalog and "亮壳一套" in catalog, catalog
    assert "潮纹秤锤" in catalog and "雾铅网坠" in catalog, catalog
    assert "砧上全套" in catalog, catalog


async def test_craft_loop() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="craft-loop-"))
    db = await _boot(tmp)
    kid, sid = await _enroll(db, "cl@example.com", "砧边")
    from server import craft

    missing = await _expect_error(craft.craft_ops(kid, "打 铜钉"))
    assert "缺材料" in missing, missing

    async with db.connect() as conn:
        await db.add_item(conn, sid, "quarry_copper_bar", 1)
        await db.add_item(conn, sid, "drift_twine", 1)
        await conn.commit()

    started = await craft.craft_ops(kid, "打 铜钉")
    assert "开打" in started and "铜钉" in started, started
    assert await _qty(db, sid, "quarry_copper_bar") == 0
    assert await _qty(db, sid, "craft_copper_nails") == 0

    early = await _expect_error(craft.craft_ops(kid, "取"))
    assert "还没好" in early, early

    busy = await _expect_error(craft.craft_ops(kid, "打 网补丁"))
    assert "正在打" in busy or "先 craft_ops 取" in busy, busy

    async with db.connect() as conn:
        await conn.execute(
            "UPDATE steward_craft SET job_ready_at=0 WHERE steward_id=?", (sid,)
        )
        await conn.commit()

    taken = await craft.craft_ops(kid, "取")
    assert "铜钉" in taken, taken
    assert await _qty(db, sid, "craft_copper_nails") == 3


async def test_salt_pan() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="craft-salt-"))
    db = await _boot(tmp)
    kid, sid = await _enroll(db, "cs@example.com", "晒盐人")
    from server import craft, world

    old_tide = world.current_tide
    old_clear = world.clear_seconds_between
    world.current_tide = lambda: "ebb"  # type: ignore[assignment]
    try:
        blocked = await _expect_error(craft.craft_ops(kid, "灌"))
        assert "涨潮" in blocked, blocked
    finally:
        world.current_tide = old_tide

    world.current_tide = lambda: "flood"  # type: ignore[assignment]
    try:
        filled = await craft.craft_ops(kid, "灌")
        assert "灌进" in filled, filled
        not_ready = await _expect_error(craft.craft_ops(kid, "收盐"))
        assert "晒" in not_ready or "结壳" in not_ready, not_ready
        world.clear_seconds_between = lambda a, b: 2000  # type: ignore[assignment]
        harvested = await craft.craft_ops(kid, "收盐")
        assert "海盐晶" in harvested or "盐" in harvested, harvested
        assert await _qty(db, sid, "quarry_salt") >= 1
    finally:
        world.current_tide = old_tide
        world.clear_seconds_between = old_clear


async def test_salvage_window() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="craft-salv-"))
    db = await _boot(tmp)
    kid, sid = await _enroll(db, "sv@example.com", "余滩")
    from server import craft, health, world

    closed = {
        "open": False, "kind": "", "label": "滩上没风暴货",
        "energy": 0, "empty": 1.0, "hazard": 0.0,
    }
    gale = {
        "open": True, "kind": "gale", "label": "风暴中",
        "energy": 10, "empty": 0.0, "hazard": 0.0,
    }
    old_win = world.salvage_window
    old_choices = craft.random.choices
    old_crand = craft.random.random
    old_hrand = health.random.random
    world.salvage_window = lambda **kw: closed  # type: ignore[assignment]
    try:
        shut = await _expect_error(craft.craft_ops(kid, "打捞"))
        assert "dig" in shut or "风暴" in shut, shut
        world.salvage_window = lambda **kw: gale  # type: ignore[assignment]
        craft.random.choices = lambda keys, weights=None, k=1: [keys[0]]  # type: ignore[method-assign]
        health.random.random = lambda: 0.99  # type: ignore[method-assign]
        craft.random.random = lambda: 0.99  # type: ignore[method-assign]
        got = await craft.craft_ops(kid, "打捞")
        assert "打捞" in got and "不是赶海" in got, got
        assert await _qty(db, sid, "drift_twine") >= 1
    finally:
        world.salvage_window = old_win
        craft.random.choices = old_choices
        craft.random.random = old_crand
        health.random.random = old_hrand


async def test_exhibit_donate() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="craft-ex-"))
    db = await _boot(tmp)
    kid, sid = await _enroll(db, "ex@example.com", "柜客")
    from server import craft
    from server.catalog import resolve_exhibit_key

    assert resolve_exhibit_key("亮壳") == "shine_shells"
    assert resolve_exhibit_key("亮壳一套") == "shine_shells"
    assert resolve_exhibit_key("未命名小鱼") == "walkblue"
    assert resolve_exhibit_key("矿石") == "ores"

    missing = await _expect_error(craft.craft_ops(kid, "捐 亮壳"))
    assert "缺" in missing, missing

    shells = (
        "shell_shine_catseye", "shell_shine_conch", "shell_shine_scallop",
        "shell_shine_starfish", "shell_shine_mussel",
    )
    async with db.connect() as conn:
        for item in shells:
            await db.add_item(conn, sid, item, 1)
        await conn.commit()

    donated = await craft.craft_ops(kid, "捐 亮壳一套")
    assert "陈列" in donated or "亮壳" in donated, donated
    for item in shells:
        assert await _qty(db, sid, item) == 0, item
    assert await _qty(db, sid, "fit_shine_rail") == 1
    again = await craft.craft_ops(kid, "捐 亮壳")
    assert "已经捐过" in again, again


async def test_workshop_exhibit_and_fog_sinker() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="craft-mid-"))
    db = await _boot(tmp)
    kid, sid = await _enroll(db, "mid@example.com", "满砧测")
    from server import craft, config
    from server.catalog import resolve_exhibit_key, resolve_recipe_key

    assert resolve_recipe_key("潮纹秤锤") == "tide_weight"
    assert resolve_recipe_key("雾铅网坠") == "fog_sinker"
    assert resolve_exhibit_key("砧上全套") == "workshop"
    assert resolve_exhibit_key("工坊") == "workshop"

    async with db.connect() as conn:
        await db.add_item(conn, sid, "craft_copper_nails", 3)
        await db.add_item(conn, sid, "craft_net_patch", 1)
        await db.add_item(conn, sid, "quarry_salt", 1)
        await db.add_item(conn, sid, "craft_timber", 2)
        await conn.commit()
    donated = await craft.craft_ops(kid, "捐 砧上全套")
    assert "砧上" in donated or "陈列" in donated, donated
    assert await _qty(db, sid, "fit_anvil_plaque") == 1

    missing = await _expect_error(craft.craft_ops(kid, "补网"))
    assert "网补丁" in missing or "网坠" in missing, missing

    async with db.connect() as conn:
        await db.add_item(conn, sid, "craft_fog_sinker", 1)
        await db.add_item(conn, sid, "craft_net_patch", 1)
        await conn.commit()
    patched = await craft.craft_ops(kid, "补网")
    assert "雾铅" in patched or "网坠" in patched, patched
    assert "14" in patched, patched
    async with db.connect() as conn:
        reduce = await craft.active_net_patch(conn, sid)
    assert abs(reduce - config.CRAFT_FOG_SINKER_EMPTY) < 1e-6, reduce
    assert await _qty(db, sid, "craft_fog_sinker") == 0
    assert await _qty(db, sid, "craft_net_patch") == 1


async def test_public_pages() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="spec-pub-"))
    await _boot(tmp)
    from server import craft, hut, marine, market

    tide = await marine.public_snapshot()
    assert "nets_today" in tide and "voyages_out" in tide and "feed" in tide
    huts = await hut.public_snapshot()
    assert "huts" in huts and "barns" in huts and "mascots" in huts
    mk = await market.public_snapshot()
    assert "open" in mk and "listings" in mk
    ws = await craft.public_snapshot()
    assert "jobs" in ws


async def test_chop_drops_timber() -> None:
    from server import farming

    plot = {
        "crop": "mango",
        "planted_at": 10**12,
        "grow_target": 10**12,
        "tended": 0,
        "watered": 0,
        "fertilized": 0,
    }
    result = farming.chop_tree(plot)
    assert result["ok"], result
    keys = [k for k, _n in result["loot"]]
    assert "craft_timber" in keys, result["loot"]
    assert "drift_twine" in keys, result["loot"]


async def test_public_snapshot() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="craft-pub-"))
    await _boot(tmp)
    from server import craft

    snap = await craft.public_snapshot()
    assert "climate" in snap and "feed" in snap
    assert "jobs" in snap and "salvages_today" in snap
    assert "exhibits" in snap and "pans_brined" in snap
    assert snap.get("hints")


def test_craft_help_and_empty() -> None:
    asyncio.run(test_help_and_empty_clean())


def test_craft_job() -> None:
    asyncio.run(test_craft_loop())


def test_craft_salt() -> None:
    asyncio.run(test_salt_pan())


def test_craft_salvage() -> None:
    asyncio.run(test_salvage_window())


def test_craft_exhibit() -> None:
    asyncio.run(test_exhibit_donate())


def test_craft_midgame() -> None:
    asyncio.run(test_workshop_exhibit_and_fog_sinker())


def test_craft_chop() -> None:
    asyncio.run(test_chop_drops_timber())


def test_craft_public() -> None:
    asyncio.run(test_public_snapshot())


def test_spectator_public() -> None:
    asyncio.run(test_public_pages())


if __name__ == "__main__":
    test_craft_help_and_empty()
    test_craft_job()
    test_craft_salt()
    test_craft_salvage()
    test_craft_exhibit()
    test_craft_midgame()
    test_craft_chop()
    test_craft_public()
    test_spectator_public()
    print("craft tests ok")
