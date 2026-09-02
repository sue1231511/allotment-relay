#!/usr/bin/env python3
"""Tt酱 gift：写「姜」送调味料作物，不误扣姜种。"""
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
        sid = (
            await (
                await conn.execute(
                    "SELECT id FROM stewards WHERE key_id=?", (row["id"],)
                )
            ).fetchone()
        )[0]
    return row["id"], sid


async def _qty(db, sid: int, item: str) -> int:
    async with db.connect() as conn:
        row = await (
            await conn.execute(
                "SELECT quantity FROM satchel WHERE steward_id=? AND item=?",
                (sid, item),
            )
        ).fetchone()
    return int(row[0]) if row else 0


def test_token_wants_seed() -> None:
    from server import tt

    assert tt._token_wants_seed("姜种")
    assert tt._token_wants_seed("大蒜种")
    assert tt._token_wants_seed("seed_ginger")
    assert tt._token_wants_seed("姜种子")
    assert not tt._token_wants_seed("姜")
    assert not tt._token_wants_seed("ginger")
    assert not tt._token_wants_seed("大蒜")
    assert not tt._token_wants_seed("chili")


def test_gift_prefers_crop_over_seed() -> None:
    asyncio.run(_test_gift_prefers_crop_over_seed())


async def _test_gift_prefers_crop_over_seed() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="tt-gift-seasoning-"))
    db = await _boot(tmp)
    from server import tt

    kid, sid = await _enroll(db, "ginger@example.com", "姜客")
    async with db.connect() as conn:
        await db.add_item(conn, sid, "seed_ginger", 3)
        await db.add_item(conn, sid, "crop_ginger", 2)
        await db.add_item(conn, sid, "seed_garlic", 2)
        await db.add_item(conn, sid, "crop_garlic", 2)
        await conn.commit()

    # 中文 / 英文都优先作物
    for cmd in ("gift 姜 1", "gift ginger 1"):
        msg = await tt.tt_ops(kid, cmd)
        assert "姜 x1" in msg, msg
        assert "姜种" not in msg, msg
        assert "眼睛亮了一下" in msg or "好感 +" in msg, msg

    assert await _qty(db, sid, "crop_ginger") == 0
    assert await _qty(db, sid, "seed_ginger") == 3

    garlic = await tt.tt_ops(kid, "gift 大蒜")
    assert "大蒜 x1" in garlic, garlic
    assert "大蒜种" not in garlic, garlic
    assert await _qty(db, sid, "crop_garlic") == 1
    assert await _qty(db, sid, "seed_garlic") == 2


def test_gift_explicit_seed_still_works() -> None:
    asyncio.run(_test_gift_explicit_seed_still_works())


async def _test_gift_explicit_seed_still_works() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="tt-gift-seed-"))
    db = await _boot(tmp)
    from server import tt

    kid, sid = await _enroll(db, "seed@example.com", "种客")
    async with db.connect() as conn:
        await db.add_item(conn, sid, "seed_ginger", 2)
        await db.add_item(conn, sid, "crop_ginger", 2)
        await conn.commit()

    msg = await tt.tt_ops(kid, "gift 姜种 1")
    assert "姜种 x1" in msg, msg
    assert await _qty(db, sid, "seed_ginger") == 1
    assert await _qty(db, sid, "crop_ginger") == 2

    msg2 = await tt.tt_ops(kid, "gift seed_ginger 1")
    assert "姜种 x1" in msg2, msg2
    assert await _qty(db, sid, "seed_ginger") == 0
    assert await _qty(db, sid, "crop_ginger") == 2


def test_gift_crop_only_when_no_seed_named() -> None:
    asyncio.run(_test_gift_crop_only_when_no_seed_named())


async def _test_gift_crop_only_when_no_seed_named() -> None:
    """只有种子时写「姜」仍可送种子（兜底）；有作物时绝不误送。"""
    tmp = Path(tempfile.mkdtemp(prefix="tt-gift-fallback-"))
    db = await _boot(tmp)
    from server import tt

    kid, sid = await _enroll(db, "onlyseed@example.com", "只种")
    async with db.connect() as conn:
        await db.add_item(conn, sid, "seed_ginger", 1)
        await conn.commit()

    msg = await tt.tt_ops(kid, "gift 姜")
    assert "姜种 x1" in msg, msg
    assert await _qty(db, sid, "seed_ginger") == 0


def test_help_mentions_seasoning_vs_seed() -> None:
    asyncio.run(_test_help_mentions_seasoning_vs_seed())


async def _test_help_mentions_seasoning_vs_seed() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="tt-gift-help-"))
    db = await _boot(tmp)
    from server import tt
    from server.mcp_dispatch import VISIT_HELP

    kid, _sid = await _enroll(db, "help@example.com", "手册客")
    help_text = await tt.tt_ops(kid, "help")
    assert "姜种" in help_text, help_text
    assert "调味料" in help_text, help_text
    assert "gift 姜" in VISIT_HELP or "姜=调味料" in VISIT_HELP, VISIT_HELP


if __name__ == "__main__":
    test_token_wants_seed()
    test_gift_prefers_crop_over_seed()
    test_gift_explicit_seed_still_works()
    test_gift_crop_only_when_no_seed_named()
    test_help_mentions_seasoning_vs_seed()
    print("ok")
