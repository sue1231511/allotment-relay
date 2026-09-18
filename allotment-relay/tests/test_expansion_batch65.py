#!/usr/bin/env python3
"""batch65：§五 挂水草理网、雨风暴贝壳、逃畜足迹。"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def test_net_weed_clear_luck():
    async def run():
        import os
        import sys

        sys.path.insert(0, str(ROOT))
        os.environ["DATA_DIR"] = str(Path(tempfile.mkdtemp()))
        tmp = Path(os.environ["DATA_DIR"])
        from server import config, db, light_bad_events as lb

        config.DATA_DIR = tmp
        config.DB_PATH = tmp / "relay.db"
        db.DATA_DIR = tmp
        db.DB_PATH = tmp / "relay.db"
        await db.init_db()
        key = await db.create_api_key("n@example.com")
        row = await db.get_key_row(key)
        await db.enroll_steward(row["id"], "Net", "", "naturalist", "")
        s = await db.get_steward_by_key_id(row["id"])
        async with db.connect() as conn:
            await lb.set_flag(conn, s["id"], "net_weed")
            with patch("server.event_opportunity.random.random", lambda: 0.01):
                adj, note = await lb.net_empty_bonus(conn, s["id"])
            await conn.commit()
        assert adj == 0.10
        assert note and ("饵" in note or "漂绳" in note)
        stock = await db.get_satchel(s["id"])
        assert stock.get("bait_worm", 0) >= 2 or stock.get("drift_twine", 0) >= 1

    asyncio.run(run())


def test_storm_dig_shell():
    async def run():
        import os
        import sys

        sys.path.insert(0, str(ROOT))
        os.environ["DATA_DIR"] = str(Path(tempfile.mkdtemp()))
        tmp = Path(os.environ["DATA_DIR"])
        from server import config, db, event_opportunity as opp

        config.DATA_DIR = tmp
        config.DB_PATH = tmp / "relay.db"
        db.DATA_DIR = tmp
        db.DB_PATH = tmp / "relay.db"
        await db.init_db()
        key = await db.create_api_key("s@example.com")
        row = await db.get_key_row(key)
        await db.enroll_steward(row["id"], "Storm", "", "naturalist", "")
        s = await db.get_steward_by_key_id(row["id"])
        with patch("server.event_opportunity.random.random", lambda: 0.01):
            async with db.connect() as conn:
                msg = await opp.maybe_storm_beach_luck(
                    conn, s["id"], context="dig", weather="storm",
                )
                await conn.commit()
        assert msg and "贝壳" in msg or "螺" in msg or "化石" in msg
        stock = await db.get_satchel(s["id"])
        assert any(
            stock.get(k, 0) >= 1
            for k in ("fossil_shell", "shell_conch", "shell_catseye", "shell_scallop")
        )

    asyncio.run(run())


def test_runaway_trail_luck():
    async def run():
        import os
        import sys

        sys.path.insert(0, str(ROOT))
        os.environ["DATA_DIR"] = str(Path(tempfile.mkdtemp()))
        tmp = Path(os.environ["DATA_DIR"])
        from server import config, db, barn_runaway_rescue as rescue

        config.DATA_DIR = tmp
        config.DB_PATH = tmp / "relay.db"
        db.DATA_DIR = tmp
        db.DB_PATH = tmp / "relay.db"
        await db.init_db()
        key = await db.create_api_key("b@example.com")
        row = await db.get_key_row(key)
        await db.enroll_steward(row["id"], "Barn", "", "naturalist", "")
        s = await db.get_steward_by_key_id(row["id"])
        async with db.connect() as conn:
            await conn.execute(
                "INSERT INTO barn_animals (steward_id, slot, species, fed, temper, escaped_at) "
                "VALUES (?,1,'chicken',1,'calm',999)",
                (s["id"],),
            )
            await conn.commit()
        with patch("server.event_opportunity.random.random", lambda: 0.01):
            async with db.connect() as conn:
                msg = await rescue.resolve(conn, dict(s), 1, "诱回")
                await conn.commit()
        assert "回栏" in msg
        assert "潮" in msg or "饵" in msg or "贝" in msg or "玻璃" in msg

    asyncio.run(run())
