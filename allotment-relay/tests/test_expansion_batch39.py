"""batch39：坏事件档位标签 + 收集簿样板。"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_bad_event_tier_tag():
    from server import bad_event_tiers as tiers

    msg = tiers.tag(tiers.TIER_HEAVY, "测试")
    assert "重" in msg and "测试" in msg


def test_collections_sheet_empty():
    async def run():
        from server import db, island_collections as coll

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("c@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "藏家", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    text = await coll.sheet(conn, s["id"])
                assert "收集簿" in text
                assert "进度" in text and "/12" in text

    asyncio.run(run())
