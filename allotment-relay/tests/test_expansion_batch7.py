#!/usr/bin/env python3
"""第七批：虫害/温室多选项、帆撕三选一。"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_pest_ignore_action():
    from server import plot_pests

    assert "不管" in plot_pests.PEST_META or "gh_leak" in plot_pests.PEST_META


async def _test_sail_resolve():
    from server import config, db, marine, voyage_sail_event

    with tempfile.TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        os.environ["DATA_DIR"] = str(tmp_p)
        config.DATA_DIR = tmp_p
        config.DB_PATH = tmp_p / "relay.db"
        db.DATA_DIR = tmp_p
        db.DB_PATH = tmp_p / "relay.db"
        await db.init_db()
        key = await db.create_api_key("b7@test.local")
        row = await db.get_key_row(key)
        await db.enroll_steward(row["id"], "B7", "", "naturalist", "")
        async with db.connect() as conn:
            sid = (await (await conn.execute(
                "SELECT id FROM stewards WHERE key_id=?", (row["id"],)
            )).fetchone())[0]
            await conn.execute(
                "UPDATE stewards SET tickets=100, boat_key='skiff' WHERE id=?", (sid,),
            )
            now = db.now()
            await conn.execute(
                """
                INSERT INTO voyages (steward_id, route, departed_at, returns_at, status, encounter)
                VALUES (?, 'near', ?, ?, 'sail_tear', '{}')
                """,
                (sid, now, now + 3600),
            )
            vid = (await (await conn.execute(
                "SELECT id FROM voyages WHERE steward_id=?", (sid,),
            )).fetchone())[0]
            voyage = await marine._get_voyage(conn, sid)
            s = await db.get_steward_by_id(sid)
            msg = await voyage_sail_event.resolve(conn, s, voyage, "硬撑")
            await conn.commit()
            assert "硬撑" in msg
            st = (await (await conn.execute(
                "SELECT status FROM voyages WHERE id=?", (vid,),
            )).fetchone())[0]
            assert st == "sailing"


def test_sail_resolve():
    asyncio.run(_test_sail_resolve())
