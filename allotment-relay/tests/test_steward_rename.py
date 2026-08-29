#!/usr/bin/env python3
"""人类改岛民名：仅 HTTP，不进 MCP。"""
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


def test_rename_steward_human_only() -> None:
    async def run() -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = await _boot(Path(tmp))
            key_a = await db.create_api_key("a@example.com")
            row_a = await db.get_key_row(key_a)
            await db.enroll_steward(row_a["id"], "旧名", "", "naturalist", "")
            s = await db.get_steward_by_key_id(row_a["id"])
            assert s and s["name"] == "旧名"

            key_b = await db.create_api_key("b@example.com")
            row_b = await db.get_key_row(key_b)
            await db.enroll_steward(row_b["id"], "别人", "", "naturalist", "")

            updated = await db.rename_steward(int(s["id"]), "新名")
            assert updated["name"] == "新名"
            again = await db.get_steward_by_id(int(s["id"]))
            assert again and again["name"] == "新名"

            try:
                await db.rename_steward(int(s["id"]), "别人")
                raise AssertionError("should reject taken name")
            except ValueError as exc:
                assert "已被登记" in str(exc)

            try:
                await db.rename_steward(int(s["id"]), "新名")
                raise AssertionError("should reject same name")
            except ValueError as exc:
                assert "已经是" in str(exc)

            # MCP steward_ops must not grow a rename verb
            from server import mcp_dispatch
            help_text = await mcp_dispatch.steward_ops(int(row_a["id"]), "help")
            assert "改名" not in help_text
            assert "rename" not in help_text.lower()
            try:
                await mcp_dispatch.steward_ops(int(row_a["id"]), "rename 偷偷")
                raise AssertionError("MCP must not rename")
            except ValueError as exc:
                assert "未知" in str(exc)
            assert (await db.get_steward_by_id(int(s["id"])))["name"] == "新名"

    asyncio.run(run())


if __name__ == "__main__":
    test_rename_steward_human_only()
    print("ok")
