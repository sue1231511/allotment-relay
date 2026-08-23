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
    tmp = Path(tempfile.mkdtemp(prefix="buy-cap-"))
    db = await _boot(tmp)
    from server import game, tt
    from server.catalog import item_stack_cap, satchel_full_message

    assert item_stack_cap("seed_kale") == 24
    assert item_stack_cap("tool_hoe") == 1
    assert "24" in satchel_full_message("seed_kale", 24, 1, 24)

    kid, sid = await _enroll(db, "cap@example.com", "囤种")
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE satchel SET quantity=24 WHERE steward_id=? AND item='seed_kale'",
            (sid,),
        )
        await conn.commit()
    try:
        await tt.tt_ops(kid, "buy 甘蓝种 1")
        raise AssertionError("tt buy should refuse over-stack")
    except ValueError as exc:
        assert "24" in str(exc) and "行囊" in str(exc), exc

    try:
        await game.plot_ops(kid, "buy 1 甘蓝")
        raise AssertionError("plot buy should refuse over-stack")
    except ValueError as exc:
        assert "24" in str(exc), exc

    listed = await game.tote_ops(kid, "list")
    assert "x24/24" in listed, listed


async def test_help_copy() -> None:
    from server import game
    from server.mcp_dispatch import HUT_HELP, TOTE_HELP, VISIT_HELP

    assert "堆肥桶 存 羊粪 3" in HUT_HELP
    assert "buy compost_bin" in HUT_HELP
    assert "粪便不能进潮柜" in HUT_HELP
    assert "24" in TOTE_HELP
    assert "24" in VISIT_HELP
    manual = asyncio.run(game.relay_manual())
    assert "堆肥桶 存 羊粪 3" in manual
    assert "buy compost_bin" in manual
    assert "行囊每种也最多 24" in manual


def main() -> None:
    test_help_copy()
    asyncio.run(test_cabinet_rejects_manure())
    asyncio.run(test_compost_bin_layers_and_take())
    asyncio.run(test_buy_respects_satchel_stack())
    print("compost bin / stack cap tests ok")


if __name__ == "__main__":
    main()
