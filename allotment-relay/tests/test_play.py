#!/usr/bin/env python3
"""人类上手页 /api/play — 同一张凭证、同一套 command。"""
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


def test_play_api() -> None:
    asyncio.run(_test_play_api())


async def _test_play_api() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="play-"))
    db = await _boot(tmp)
    from server import play as play_mod

    key = await db.create_api_key("play@example.com")
    try:
        await play_mod.run_play("bad_key", "", "")
        raise AssertionError("bad key should fail")
    except ValueError as exc:
        assert "无效" in str(exc), exc

    snap = await play_mod.run_play(key, "", "")
    assert snap["ok"] is True, snap
    assert snap["enrolled"] is False, snap
    assert snap["places"] and snap["places"][0]["name"] == "海边", snap["places"]

    enrolled = await play_mod.run_play(key, "steward_ops", "enroll 岸边的人")
    assert enrolled["enrolled"] is True, enrolled
    assert enrolled["dashboard"]["name"] == "岸边的人", enrolled
    assert "欢迎" in (enrolled.get("text") or ""), enrolled

    sown = await play_mod.run_play(key, "plot_ops", "sow 1 甘蓝")
    assert sown["ok"] is True, sown
    plots = sown["dashboard"]["parcels"]
    one = next(p for p in plots if p.get("token") == "1" and not p.get("orchard") and not p.get("greenhouse"))
    assert one["state"] != "fallow", one

    try:
        await play_mod.run_play(key, "not_a_tool", "status")
        raise AssertionError("unknown tool should fail")
    except ValueError as exc:
        assert "未知工具" in str(exc), exc


if __name__ == "__main__":
    asyncio.run(_test_play_api())
    print("ok")
