#!/usr/bin/env python3
"""目送人·阿槐：拜访、每日送别与回看。"""
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
    key = await db.create_api_key("musong@example.com")
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], "送行者", "", "naturalist", "")
    return db, row["id"]


async def test_musong_flow() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="musong-"))
    db, kid = await _boot(tmp)
    from server import mcp_dispatch, musong, npc

    listing = await npc.npc_ops(kid, "list")
    assert "目送人·阿槐" in listing and "musong send" in listing
    visit = await musong.musong_ops(kid, "visit")
    assert "目送人·阿槐" in visit and "渡口" in visit, visit
    sent = await mcp_dispatch.visit_bundle(kid, "musong send 安")
    assert "阿槐把“安”写在渡口的小册上" in sent
    assert "雾智 +2" in sent and "档信 +1" in sent
    remembered = await mcp_dispatch.visit_bundle(kid, "musong remember")
    assert "安" in remembered and "目送过" in remembered
    try:
        await musong.musong_ops(kid, "send 另一个人")
        raise AssertionError("second daily sendoff should fail")
    except ValueError as exc:
        assert "今天已经" in str(exc)

    async with db.connect() as conn:
        count = (await (await conn.execute("SELECT COUNT(*) FROM musong_sendoffs")).fetchone())[0]
    assert count == 1


def main() -> None:
    asyncio.run(test_musong_flow())
    print("musong tests ok")


if __name__ == "__main__":
    main()
