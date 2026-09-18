#!/usr/bin/env python3
"""第三批扩展：禁捕、生态、履历、屋顶、井蚀。"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_fish_ban_stable():
    from server import fish_ban

    a = fish_ban.banned_species(100)
    b = fish_ban.banned_species(100)
    assert a == b
    assert fish_ban.notice_text(100)


def test_ecology_pick():
    from server import fish_ecology

    assert "shore" in fish_ecology.ZONE_FOR_MODE["net"]


async def _test_roof():
    from server import config, db, hut_roof

    with tempfile.TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        os.environ["DATA_DIR"] = str(tmp_p)
        config.DATA_DIR = tmp_p
        config.DB_PATH = tmp_p / "relay.db"
        db.DATA_DIR = tmp_p
        db.DB_PATH = tmp_p / "relay.db"
        await db.init_db()
        key = await db.create_api_key("roof@test.local")
        row = await db.get_key_row(key)
        await db.enroll_steward(row["id"], "Roof", "", "naturalist", "")
        async with db.connect() as conn:
            sid = (await (await conn.execute(
                "SELECT id FROM stewards WHERE key_id=?", (row["id"],)
            )).fetchone())[0]
            r, mx = await hut_roof.get_roof(conn, sid)
            assert r == mx == 100


def test_hut_roof():
    asyncio.run(_test_roof())
