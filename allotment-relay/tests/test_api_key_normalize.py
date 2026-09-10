#!/usr/bin/env python3
"""网页误贴 MCP 地址时仍能认出同一张凭证；人和家机不是互斥会话。"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_normalize_api_key_shapes() -> None:
    from server import db

    key = "ar_sk_abcdefghijklmnopqrstuvwx-yz012"
    assert db.normalize_api_key(key) == key
    assert db.normalize_api_key(f"  {key}  ") == key
    assert db.normalize_api_key(f"https://isle.example/mcp/?api_key={key}") == key
    assert db.normalize_api_key(f"http://127.0.0.1:8787/mcp/?api_key={key}") == key
    assert db.normalize_api_key(f"api_key={key}") == key
    assert db.normalize_api_key(f"?api_key={key}") == key
    assert db.normalize_api_key(f"Authorization: Bearer {key}") == key
    assert db.normalize_api_key("https://isle.example/mcp/") == ""
    assert db.normalize_api_key("") == ""
    assert "不要贴整段 MCP" in db.invalid_key_message("https://isle.example/mcp/")
    assert "同一个号" in db.invalid_key_message("ar_sk_not_in_db_xxxxx")


async def _boot(tmp: Path):
    os.environ["DATA_DIR"] = str(tmp)
    from server import config, db

    config.DATA_DIR = tmp
    config.DB_PATH = tmp / "relay.db"
    db.DATA_DIR = tmp
    db.DB_PATH = tmp / "relay.db"
    await db.init_db()
    return db


def test_get_key_row_accepts_mcp_url() -> None:
    asyncio.run(_test_get_key_row_accepts_mcp_url())


async def _test_get_key_row_accepts_mcp_url() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="key-norm-"))
    db = await _boot(tmp)
    key = await db.create_api_key("norm@example.com")
    wrapped = f"https://isle.example/mcp/?api_key={key}"
    row = await db.get_key_row(wrapped)
    assert row, wrapped
    assert row["api_key"] == key
    same = await db.get_key_row(f"api_key={key}")
    assert same and same["id"] == row["id"]


def test_human_and_mcp_can_use_same_key() -> None:
    asyncio.run(_test_human_and_mcp_can_use_same_key())


async def _test_human_and_mcp_can_use_same_key() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="key-share-"))
    db = await _boot(tmp)
    key = await db.create_api_key("share@example.com")
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], "同号人", "", "naturalist", "")

    from server import play

    mcp_url = f"https://isle.example/mcp/?api_key={key}"

    async def human() -> dict:
        return await play.snapshot(key)

    async def house() -> dict:
        return await play.snapshot(mcp_url)

    human_snap, house_snap = await asyncio.gather(human(), house())
    assert human_snap["enrolled"] is True
    assert house_snap["enrolled"] is True
    assert human_snap["dashboard"]["name"] == house_snap["dashboard"]["name"] == "同号人"


def test_session_accepts_mcp_url() -> None:
    asyncio.run(_test_session_accepts_mcp_url())


async def _test_session_accepts_mcp_url() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="key-sess-"))
    db = await _boot(tmp)
    key = await db.create_api_key("sess@example.com")
    await db.enroll_steward((await db.get_key_row(key))["id"], "网址客", "", "naturalist", "")
    from fastapi.testclient import TestClient
    from server.main import app

    client = TestClient(app)
    wrapped = f"https://isle.example/mcp/?api_key={key}"
    res = client.post("/api/v1/session", json={"api_key": wrapped})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    assert body["enrolled"] is True
    assert body["me"]["name"] == "网址客"

    play_res = client.post("/api/play", json={"api_key": wrapped, "tool": "", "command": ""})
    assert play_res.status_code == 200, play_res.text
    assert play_res.json()["enrolled"] is True


def main() -> None:
    test_normalize_api_key_shapes()
    test_get_key_row_accepts_mcp_url()
    test_human_and_mcp_can_use_same_key()
    test_session_accepts_mcp_url()
    print("api key normalize ok")


if __name__ == "__main__":
    main()
