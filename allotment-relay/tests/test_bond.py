#!/usr/bin/env python3
"""岛缘：岸上动手只加，井下只减，无上限，地板 0。"""
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


async def _row(db, sid: int) -> dict:
    s = await db.get_steward_by_id(sid)
    return dict(s)


async def test_story_complete_once() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="bond-story-"))
    db = await _boot(tmp)
    kid, sid = await _enroll(db, "story@example.com", "缘客")
    from server import bond, mcp_dispatch

    async with db.connect() as conn:
        g1 = await bond.story_complete(conn, sid, "tale:black_box_lover")
        g2 = await bond.story_complete(conn, sid, "tale:black_box_lover")
        await conn.commit()
    assert g1 == 100, g1
    assert g2 == 0, g2
    s = await _row(db, sid)
    assert int(s["island_bond"]) == 100
    assert int(s["island_bond_story"]) == 100

    text = await mcp_dispatch.steward_ops(kid, "岛缘")
    assert "岛缘" in text and "∞" in text, text
    assert "叙事" in text, text
    assert "100" in text.replace(",", ""), text


async def test_well_floor_zero() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="bond-well-"))
    db = await _boot(tmp)
    _, sid = await _enroll(db, "well@example.com", "井客")
    from server import bond

    async with db.connect() as conn:
        await bond.grant(conn, sid, 10, "labor")
        lost = await bond.well(conn, sid, bond.WELL_FIRST, once="well_first")
        again = await bond.well(conn, sid, bond.WELL_ENTER)
        await conn.commit()
    assert lost == -10, lost
    assert again == 0, again
    s = await _row(db, sid)
    assert int(s["island_bond"]) == 0
    assert int(s["island_bond_well"]) == 10


def test_donate_sqrt() -> None:
    from server import bond
    assert bond.donate_amount(50) == 42
    assert bond.donate_amount(0) == 0
    assert bond.donate_amount(1) == 6


async def test_sheet_and_inspect() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="bond-sheet-"))
    db = await _boot(tmp)
    kid, sid = await _enroll(db, "sheet@example.com", "档客")
    from server import bond, game

    async with db.connect() as conn:
        await bond.grant(conn, sid, 12, "labor")
        await conn.commit()
    s = await _row(db, sid)
    lines = "\n".join(bond.sheet_lines(s))
    assert "岛缘" in lines and "∞" in lines, lines
    assert "12" in lines.replace(",", ""), lines
    assert "你与潮汐岛结下的所有联系" in lines, lines

    sheet = await game.steward_sheet(kid)
    assert "岛缘" in sheet and "∞" in sheet, sheet


async def test_backfill_once() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="bond-bf-"))
    db = await _boot(tmp)
    _, sid = await _enroll(db, "bf@example.com", "补客")
    from server import bond

    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET island_bond_backfill=0 WHERE id=?", (sid,)
        )
        await conn.execute(
            """
            INSERT INTO steward_tales_done (steward_id, tale_key, outcome, completed_at)
            VALUES (?, 'black_box_lover', 'completed', 1)
            """,
            (sid,),
        )
        await conn.commit()
        await bond.ensure_backfill(conn, sid)
        await bond.ensure_backfill(conn, sid)
        await conn.commit()
    s = await _row(db, sid)
    assert int(s["island_bond_backfill"]) == 1
    assert int(s["island_bond"]) == 100
    assert int(s["island_bond_story"]) == 100


async def test_manual_and_visit_no_old_windows() -> None:
    from server import game, mcp_dispatch

    text = await game.relay_manual()
    assert "岛缘" in text
    assert "steward_ops 岛缘" in text
    assert "潮生会 周" not in text
    help_text = mcp_dispatch.STEWARD_HELP
    assert "岛缘" in help_text
    assert "潮生会 周" not in mcp_dispatch.VISIT_HELP


def test_bond() -> None:
    asyncio.run(test_story_complete_once())
    asyncio.run(test_well_floor_zero())
    test_donate_sqrt()
    asyncio.run(test_sheet_and_inspect())
    asyncio.run(test_backfill_once())
    asyncio.run(test_manual_and_visit_no_old_windows())


if __name__ == "__main__":
    test_bond()
    print("bond tests ok")
