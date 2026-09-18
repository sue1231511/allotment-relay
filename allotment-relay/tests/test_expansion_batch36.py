#!/usr/bin/env python3
"""§59 第三批余量：生态/血统/工程可见性。"""
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_seed_lineage_headline():
    async def run():
        from server import db, seed_lineage

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("seed@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "农人", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    assert await seed_lineage.headline(conn, s["id"]) is None
                    await seed_lineage.ensure_table(conn)
                    await conn.execute(
                        """
                        INSERT INTO steward_seed_lineage (steward_id, crop, generation, bias, label)
                        VALUES (?, 'kale', 2, 'plump', '自留2')
                        """,
                        (s["id"],),
                    )
                    line = await seed_lineage.headline(conn, s["id"])
                    assert line and "甘蓝" in line and "自留2" in line
                    await conn.commit()

    asyncio.run(run())


def test_probe_sand_flag():
    async def run():
        from server import db, light_bad_events as lb

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("p@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "赶海", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    await lb.set_flag(conn, s["id"], "probe_sand")
                    assert await lb.probe_energy_penalty(conn, s["id"]) == 2
                    await conn.commit()

    asyncio.run(run())
