#!/usr/bin/env python3
"""§53 井蚀高 → 地面盐斑。"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


async def _boot(tmp: Path):
    import os
    import sys

    sys.path.insert(0, str(ROOT))
    os.environ["DATA_DIR"] = str(tmp)
    from server import config, db

    config.DATA_DIR = tmp
    config.DB_PATH = tmp / "relay.db"
    db.DATA_DIR = tmp
    db.DB_PATH = tmp / "relay.db"
    await db.init_db()
    return db


def test_salt_blot_lowers_fertility():
    async def run():
        db = await _boot(Path(tempfile.mkdtemp(prefix="salt-")))
        from server import layer_link, well_corrosion

        key = await db.create_api_key("s@example.com")
        row = await db.get_key_row(key)
        await db.enroll_steward(row["id"], "盐测", "", "naturalist", "")
        s = await db.get_steward_by_key_id(row["id"])
        async with db.connect() as conn:
            await conn.execute(
                "UPDATE parcels SET crop='kale', harvest_left=3, grow_target=100, soil_fertility=80 "
                "WHERE steward_id=? AND slot=1 AND NOT orchard AND NOT greenhouse",
                (s["id"],),
            )
            await conn.execute(
                "INSERT INTO steward_undertide (steward_id, access) VALUES (?,1)",
                (s["id"],),
            )
            await conn.execute(
                "UPDATE steward_undertide SET well_corrosion=85 WHERE steward_id=?",
                (s["id"],),
            )
            await conn.commit()

        with patch("server.layer_link.random.random", return_value=0.0):
            async with db.connect() as conn:
                msg = await layer_link.maybe_salt_blot_after_well(conn, s["id"])
                await conn.commit()
                assert msg and "盐斑" in msg, msg
                fert = await conn.execute(
                    "SELECT soil_fertility FROM parcels WHERE steward_id=? AND slot=1",
                    (s["id"],),
                )
                assert int((await fert.fetchone())[0]) == 68

    asyncio.run(run())
