#!/usr/bin/env python3
"""协作度总览 + peer 档上的协作行。"""
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


def test_rapport_sheet_and_peer_blurb() -> None:
    asyncio.run(_test_rapport_sheet_and_peer_blurb())


async def _test_rapport_sheet_and_peer_blurb() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="rapport-sheet-"))
    db = await _boot(tmp)
    from server import game, mcp_dispatch, social

    kid_a, sid_a = await _enroll(db, "a@example.com", "甲岛民")
    kid_b, sid_b = await _enroll(db, "b@example.com", "乙岛民")

    empty = await mcp_dispatch.steward_ops(kid_a, "协作")
    assert "还没有记录" in empty or "最高协作：0" in empty, empty
    assert "≥20" in empty, empty

    async with db.connect() as conn:
        await conn.execute(
            "INSERT INTO rapport (steward_a, steward_b, score) VALUES (?, ?, ?)",
            (min(sid_a, sid_b), max(sid_a, sid_b), 25),
        )
        await conn.commit()

    sheet = await social.rapport_sheet(sid_a)
    assert "乙岛民" in sheet and "25" in sheet, sheet
    assert "交换台" in sheet, sheet

    peer = await game.peer_sheet("乙岛民", viewer_id=sid_a)
    assert "协作度：25" in peer, peer
    assert "2 票" in peer or "手续费" in peer, peer

    self_peer = await game.peer_sheet("甲岛民", viewer_id=sid_a)
    assert "协作度" not in self_peer, self_peer

    via_mux = await mcp_dispatch.steward_ops(kid_a, "peer 乙岛民")
    assert "协作度：25" in via_mux, via_mux


def test_social_perk_helpers() -> None:
    from server import social

    assert social.perks_for_score(0) == []
    assert any("交换" in p for p in social.perks_for_score(20))
    assert "再 +" in social.next_perk_hint(5)
    assert "全开" in social.next_perk_hint(100) or "仍会涨" in social.next_perk_hint(100)
