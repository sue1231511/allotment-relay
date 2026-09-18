#!/usr/bin/env python3
"""塌方硬挖小概率多一块矿 — §5 坏事里的机会。"""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def test_hard_dig_bonus_ore():
    async def run():
        import os
        import sys

        sys.path.insert(0, str(ROOT))
        os.environ["DATA_DIR"] = str(Path(tempfile.mkdtemp()))
        tmp = Path(os.environ["DATA_DIR"])
        from server import config, db

        config.DATA_DIR = tmp
        config.DB_PATH = tmp / "relay.db"
        db.DATA_DIR = tmp
        db.DB_PATH = tmp / "relay.db"
        await db.init_db()
        from server import quarry_collapse as col_mod

        key = await db.create_api_key("q@example.com")
        row = await db.get_key_row(key)
        await db.enroll_steward(row["id"], "崖客", "", "naturalist", "")
        s = await db.get_steward_by_key_id(row["id"])
        async with db.connect() as conn:
            await conn.execute(
                "INSERT INTO steward_quarry (steward_id, pick_tier) VALUES (?,1)",
                (s["id"],),
            )
            await conn.execute(
                "INSERT INTO quarry_claims (steward_id, slot, vein, strikes_left, hazard, hazard_json) "
                "VALUES (?,1,'salt',3,?,?)",
                (s["id"], col_mod.HAZARD_COLLAPSE, json.dumps({"slot": 1})),
            )
            await conn.commit()

        rolls = iter([0.05, 0.99, 0.99])
        with patch("server.quarry_collapse.random.random", lambda: next(rolls)):
            async with db.connect() as conn:
                msg = await col_mod.resolve(conn, dict(s), 1, "硬挖")
                await conn.commit()
        assert "多捡到" in msg, msg
        sat = await db.get_satchel(s["id"])
        assert sat.get("quarry_salt_sand", 0) >= 1, sat

    asyncio.run(run())
