#!/usr/bin/env python3
"""堆肥桶：粪便不进潮柜；行囊/购买与柜子同一 24 上限。"""
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
        await conn.execute(
            "UPDATE stewards SET hut_built=1, hut_level=2, tickets=800, barn_built=1 WHERE id=?",
            (sid,),
        )
        await conn.commit()
    return row["id"], sid


async def _install(db, sid: int, slot: str, key: str) -> None:
    async with db.connect() as conn:
        await conn.execute(
            """
            INSERT INTO hut_fittings (steward_id, slot, item_key, installed_at)
            VALUES (?, ?, ?, ?)
            """,
            (sid, slot, key, db.now()),
        )
        await conn.commit()


async def test_cabinet_rejects_manure() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="manure-cab-"))
    db = await _boot(tmp)
    from server import hut

    _kid, sid = await _enroll(db, "poo@example.com", "柜粪")
    await _install(db, sid, "soft_1", "cabinet")
    async with db.connect() as conn:
        await db.add_item(conn, sid, "manure_sheep", 3)
        await conn.commit()
    s = await db.get_steward_by_id(sid)
    try:
        await hut.cabinet_command(s, ["存", "羊粪", "2"])
        raise AssertionError("manure should not go into cabinet")
    except ValueError as exc:
        msg = str(exc)
        assert "粪便" in msg and "堆肥桶" in msg, msg


async def test_compost_bin_layers_and_take() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="compost-bin-"))
    db = await _boot(tmp)
    from server import barn, hut

    kid, sid = await _enroll(db, "bin@example.com", "沤肥")
    await _install(db, sid, "soft_1", "compost_bin")
    async with db.connect() as conn:
        await db.add_item(conn, sid, "manure_sheep", 8)
        await conn.commit()
    s = await db.get_steward_by_id(sid)

    put = await hut.compost_bin_command(s, ["存", "羊粪", "3"])
    assert "堆肥桶" in put and "+6 层" in put, put
    assert "结出堆肥" not in put, put

    s = await db.get_steward_by_id(sid)
    put2 = await hut.compost_bin_command(s, ["存", "羊粪", "1"])
    assert "结出堆肥 x1" in put2, put2
    assert "1/7 层" in put2, put2

    took = await hut.compost_bin_command(s, ["取", "堆肥", "1"])
    assert "取出堆肥 x1" in took, took
    async with db.connect() as conn:
        row = await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item='compost'",
            (sid,),
        )).fetchone()
    assert row and row[0] >= 1, row

    s = await db.get_steward_by_id(sid)
    via_barn = await barn.barn_ops(kid, "compost 羊粪 1")
    assert "堆肥桶" in via_barn or "层" in via_barn, via_barn


async def test_buy_respects_satchel_stack() -> None:
    """可叠放货满一组可开下一组；工具仍只能 1。"""
    tmp = Path(tempfile.mkdtemp(prefix="buy-cap-"))
    db = await _boot(tmp)
    from server import game, tt
    from server.catalog import format_stack_qty, item_stack_cap, satchel_full_message

    assert item_stack_cap("seed_kale") == 24
    assert item_stack_cap("tool_hoe") == 1
    assert "每组" in satchel_full_message("tool_hoe", 1, 1, 1)
    assert format_stack_qty(25, 24) == "x25（2组 24+1）"

    kid, sid = await _enroll(db, "cap@example.com", "囤种")
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE satchel SET quantity=24 WHERE steward_id=? AND item='seed_kale'",
            (sid,),
        )
        await conn.execute(
            """
            INSERT INTO satchel (steward_id, item, quantity) VALUES (?,?,1)
            ON CONFLICT(steward_id, item) DO UPDATE SET quantity=1
            """,
            (sid, "tool_hoe"),
        )
        await conn.commit()

    bought = await tt.tt_ops(kid, "buy 甘蓝种 1")
    assert "甘蓝" in bought or "种" in bought, bought
    bag = await db.get_satchel(sid)
    assert bag.get("seed_kale") == 25, bag

    plot = await game.plot_ops(kid, "buy 1 甘蓝")
    assert "购入" in plot or "甘蓝" in plot, plot
    bag2 = await db.get_satchel(sid)
    assert bag2.get("seed_kale") == 26, bag2

    try:
        await tt.tt_ops(kid, "buy 锄头 1")
        raise AssertionError("tool buy should refuse when already holding one")
    except ValueError as exc:
        assert "行囊" in str(exc) or "锄" in str(exc), exc

    listed = await game.tote_ops(kid, "list")
    assert "2组" in listed or "x26" in listed, listed


def test_help_copy() -> None:
    from server import game
    from server.mcp_dispatch import HUT_HELP, TOTE_HELP, VISIT_HELP

    assert "堆肥桶 存 羊粪 3" in HUT_HELP
    assert "buy compost_bin" in HUT_HELP
    assert "粪便不能进潮柜" in HUT_HELP
    assert "空槽也能装" in HUT_HELP
    assert "桶不是柜子" in HUT_HELP
    assert "24" in TOTE_HELP
    assert "24" in VISIT_HELP
    manual = asyncio.run(game.relay_manual())
    assert "堆肥桶 存 羊粪 3" in manual
    assert "buy compost_bin" in manual
    assert "空槽也能装" in manual
    assert "桶不是柜子" in manual
    assert "行囊/潮柜/冰箱同种货可占多组" in manual or "MC 式" in manual
    assert "每组基础 24" in manual or "基础 24" in manual


async def test_buy_install_empty_slot_then_put() -> None:
    """空槽 install 必须真正写入 hut_fittings，否则会报还没装。"""
    tmp = Path(tempfile.mkdtemp(prefix="compost-empty-"))
    db = await _boot(tmp)
    from server import hut

    kid, sid = await _enroll(db, "empty-slot@example.com", "空槽沤肥")
    bought = await hut.hut_ops(kid, "buy compost_bin")
    assert "堆肥桶" in bought, bought

    installed = await hut.hut_ops(kid, "install soft_1 compost_bin")
    assert "堆肥桶" in installed, installed

    async with db.connect() as conn:
        row = await (await conn.execute(
            "SELECT item_key FROM hut_fittings WHERE steward_id=? AND slot='soft_1'",
            (sid,),
        )).fetchone()
        sat = await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item='fit_compost_bin'",
            (sid,),
        )).fetchone()
    assert row and row[0] == "compost_bin", row
    assert not sat or int(sat[0] or 0) == 0, sat

    status = await hut.hut_ops(kid, "status")
    assert "堆肥桶" in status, status

    async with db.connect() as conn:
        await db.add_item(conn, sid, "manure_sheep", 4)
        await conn.commit()

    put = await hut.hut_ops(kid, "堆肥桶 转化 羊粪 3")
    assert "堆肥桶" in put and "+6 层" in put, put
    put2 = await hut.hut_ops(kid, "堆肥桶 存 羊粪 1")
    assert "结出堆肥 x1" in put2, put2
    took = await hut.hut_ops(kid, "堆肥桶 取 堆肥 1")
    assert "取出堆肥 x1" in took, took


async def test_install_replaces_occupied_slot() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="compost-swap-"))
    db = await _boot(tmp)
    from server import hut

    kid, sid = await _enroll(db, "swap-slot@example.com", "换槽沤肥")
    await hut.hut_ops(kid, "buy cabinet")
    cab = await hut.hut_ops(kid, "install soft_1 cabinet")
    assert "潮柜" in cab or "柜" in cab, cab
    await hut.hut_ops(kid, "buy compost_bin")
    swapped = await hut.hut_ops(kid, "install soft_1 compost_bin")
    assert "堆肥桶" in swapped, swapped

    async with db.connect() as conn:
        fit = await (await conn.execute(
            "SELECT item_key FROM hut_fittings WHERE steward_id=? AND slot='soft_1'",
            (sid,),
        )).fetchone()
        cab_row = await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item='fit_cabinet'",
            (sid,),
        )).fetchone()
        await db.add_item(conn, sid, "manure_sheep", 1)
        await conn.commit()
    assert fit and fit[0] == "compost_bin", fit
    assert cab_row and int(cab_row[0]) >= 1, cab_row

    put = await hut.hut_ops(kid, "堆肥桶 存 羊粪 1")
    assert "+2 层" in put, put


def main() -> None:
    test_help_copy()
    asyncio.run(test_cabinet_rejects_manure())
    asyncio.run(test_compost_bin_layers_and_take())
    asyncio.run(test_buy_install_empty_slot_then_put())
    asyncio.run(test_install_replaces_occupied_slot())
    asyncio.run(test_buy_respects_satchel_stack())
    print("compost bin / stack cap tests ok")


if __name__ == "__main__":
    main()
