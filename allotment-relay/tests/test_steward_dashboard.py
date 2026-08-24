#!/usr/bin/env python3
"""POST /api/steward/dashboard — 私有管家面板。"""
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


def test_steward_dashboard_api() -> None:
    asyncio.run(_test_steward_dashboard_api())


async def _test_steward_dashboard_api() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="steward-dash-"))
    db = await _boot(tmp)
    from server import steward_dashboard

    key = await db.create_api_key("owner@example.com")
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], "我家AI", "座右铭", "naturalist", "肖像")

    try:
        await steward_dashboard.fetch_dashboard("bad_key")
        raise AssertionError("bad key should fail")
    except ValueError as exc:
        assert "无效" in str(exc), exc

    data = await steward_dashboard.fetch_dashboard(key)
    assert data["name"] == "我家AI", data
    assert data["tickets"] == 120, data
    assert "parcels" in data and len(data["parcels"]) >= 3, data
    assert data["meter_lines"]["bar_duty"], data
    assert "status" in data, data
    assert data["status"]["label"] in ("在线", "离线"), data["status"]
    assert "shadow" in data, data
    assert isinstance(data["shadow"]["rep"], int), data["shadow"]
    assert data["meters"]["shadow_rep"] == data["shadow"]["rep"], data
    assert data["shadow"]["tier"], data["shadow"]
    assert data["memories"] == [], data["memories"]
    assert data["parcels"][0]["token"]
    assert "季节" in (data.get("climate") or "") or "一周一季" in (data.get("climate") or ""), data.get("climate")
    assert "quarry" in data and data["quarry"]["pick_tier"] == 0, data.get("quarry")
    assert "买镐" in data["quarry"]["line"], data["quarry"]
    assert "craft" in data and "砧" in data["craft"]["line"], data.get("craft")


if __name__ == "__main__":
    asyncio.run(_test_steward_dashboard_api())
    print("ok")
