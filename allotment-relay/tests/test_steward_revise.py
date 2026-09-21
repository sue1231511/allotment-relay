#!/usr/bin/env python3
"""steward_ops revise：肖像写在同一句 command 里，不再整句塞进座右铭。"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
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


async def _enroll(db, email: str, name: str, motto: str = "", portrait: str = "") -> int:
    key = await db.create_api_key(email)
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], name, motto, "naturalist", portrait)
    return row["id"]


def test_split_profile_text() -> None:
    from server.mcp_dispatch import split_profile_text

    assert split_profile_text("") == ("", "")
    assert split_profile_text("潮声不断") == ("潮声不断", "")
    assert split_profile_text("座右铭 portrait ×××") == ("座右铭", "×××")
    assert split_profile_text("portrait ×××") == ("", "×××")
    assert split_profile_text("portrait=×××") == ("", "×××")
    assert split_profile_text("潮声不断 portrait 戴草帽") == ("潮声不断", "戴草帽")
    assert split_profile_text("潮声不断 肖像 短发草帽") == ("潮声不断", "短发草帽")
    assert split_profile_text("肖像=草帽短发") == ("", "草帽短发")
    assert split_profile_text("潮声不断 portrait=草帽") == ("潮声不断", "草帽")
    assert split_profile_text("foo portrait bar portrait 戴草帽") == ("foo portrait bar", "戴草帽")


def test_revise_parses_portrait_from_command() -> None:
    async def run() -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = await _boot(Path(tmp))
            from server import mcp_dispatch

            kid = await _enroll(db, "revise-a@example.com", "修档人")
            s = await db.get_steward_by_key_id(kid)
            assert s["motto"] == ""
            assert s["portrait"] == ""

            dumped = await mcp_dispatch.steward_ops(kid, "revise 座右铭 portrait ×××")
            assert "资料已修订" in dumped
            s = await db.get_steward_by_key_id(kid)
            assert s["motto"] == "座右铭", s["motto"]
            assert s["portrait"] == "×××", s["portrait"]
            assert "座右铭: 座右铭" in dumped
            assert "肖像: ×××" in dumped

            only_p = await mcp_dispatch.steward_ops(kid, "revise portrait 戴草帽")
            s = await db.get_steward_by_key_id(kid)
            assert s["motto"] == "座右铭", s["motto"]
            assert s["portrait"] == "戴草帽", s["portrait"]
            assert "戴草帽" in only_p

            eq = await mcp_dispatch.steward_ops(kid, "revise portrait=短发")
            s = await db.get_steward_by_key_id(kid)
            assert s["motto"] == "座右铭", s["motto"]
            assert s["portrait"] == "短发", s["portrait"]
            assert "短发" in eq

            both = await mcp_dispatch.steward_ops(kid, "revise 潮声不断 portrait 草帽短发")
            s = await db.get_steward_by_key_id(kid)
            assert s["motto"] == "潮声不断"
            assert s["portrait"] == "草帽短发"
            assert "潮声不断" in both

            zh = await mcp_dispatch.steward_ops(kid, "修订 潮声不断 肖像 外衣补丁")
            s = await db.get_steward_by_key_id(kid)
            assert s["portrait"] == "外衣补丁", s["portrait"]
            assert "外衣补丁" in zh

            motto_only = await mcp_dispatch.steward_ops(kid, "revise 只改这句话")
            s = await db.get_steward_by_key_id(kid)
            assert s["motto"] == "只改这句话"
            assert s["portrait"] == "外衣补丁"
            assert "外衣补丁" in motto_only

            try:
                await mcp_dispatch.steward_ops(kid, "revise")
                raise AssertionError("empty revise should explain usage")
            except ValueError as exc:
                assert "portrait" in str(exc)
                assert "没有单独" in str(exc)

    asyncio.run(run())


def test_enroll_can_set_portrait_in_command() -> None:
    async def run() -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = await _boot(Path(tmp))
            from server import mcp_dispatch

            key = await db.create_api_key("enroll-p@example.com")
            row = await db.get_key_row(key)
            text = await mcp_dispatch.steward_ops(
                row["id"], "enroll 岸安 潮声不断 portrait 戴草帽"
            )
            assert "欢迎 岸安" in text
            s = await db.get_steward_by_key_id(row["id"])
            assert s["name"] == "岸安"
            assert s["motto"] == "潮声不断", s["motto"]
            assert s["portrait"] == "戴草帽", s["portrait"]

    asyncio.run(run())


def test_revise_works_when_bar_duty_overdue() -> None:
    async def run() -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = await _boot(Path(tmp))
            from server import mcp_dispatch

            kid = await _enroll(db, "revise-duty@example.com", "逾期修档")
            async with db.connect() as conn:
                await conn.execute(
                    "UPDATE stewards SET last_bar_shift_at=1 WHERE key_id=?",
                    (kid,),
                )
                await conn.commit()
            text = await mcp_dispatch.steward_ops(kid, "revise portrait 还没上工")
            assert "还没上工" in text
            s = await db.get_steward_by_key_id(kid)
            assert s["portrait"] == "还没上工"

    asyncio.run(run())


def test_play_http_revise_portrait() -> None:
    async def run() -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = await _boot(Path(tmp))
            key = await db.create_api_key("play-revise@example.com")
            row = await db.get_key_row(key)
            await db.enroll_steward(row["id"], "网页人", "旧铭", "naturalist", "")
            from fastapi.testclient import TestClient
            from server.main import app

            client = TestClient(app)
            play = client.get("/play")
            assert play.status_code == 200
            assert "play.js?v=revise-portrait1" in play.text
            manual = client.get("/manual")
            assert manual.status_code == 200
            assert "想改座右铭 / 肖像" in manual.text
            res = client.post(
                "/api/play",
                json={
                    "api_key": key,
                    "tool": "steward_ops",
                    "command": "revise 座右铭 portrait ×××",
                },
            )
            assert res.status_code == 200, res.text
            data = res.json()
            assert "×××" in (data.get("text") or ""), data.get("text")
            dash = data.get("dashboard") or {}
            assert dash.get("motto") == "座右铭", dash
            assert dash.get("portrait") == "×××", dash

    asyncio.run(run())


def test_help_and_manual_name_the_real_syntax() -> None:
    from server import mcp_dispatch
    from server.mcp_app import mcp

    help_text = mcp_dispatch.STEWARD_HELP
    assert "revise 潮声不断 portrait 戴草帽" in help_text
    assert "没有单独的 portrait 参数" in help_text
    assert "肖像用 portrait 参数" not in help_text
    blob = (mcp._tool_manager.get_tool("steward_ops").description or "")
    assert "revise 潮声不断 portrait 戴草帽" in blob
    assert "没有单独 portrait 参数" in blob

    play_js = (ROOT / "server/static/play.js").read_text(encoding="utf-8")
    play_html = (ROOT / "server/templates/play.html").read_text(encoding="utf-8")
    assert "play-profile-form" in play_js
    assert "play-profile-portrait" in play_js
    assert "steward_ops" in play_js and "revise" in play_js
    assert "play.js?v=revise-portrait1" in play_html

    manual = (ROOT / "server/templates/partials/island-manual-content.html").read_text(
        encoding="utf-8"
    )
    assert "想改座右铭 / 肖像" in manual
    assert "点上手页头像打开「这一号」" in manual
    assert "不是上传图片" in manual
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert "revise 潮声不断 portrait 戴草帽" in readme


if __name__ == "__main__":
    test_split_profile_text()
    test_revise_parses_portrait_from_command()
    test_enroll_can_set_portrait_in_command()
    test_revise_works_when_bar_duty_overdue()
    test_play_http_revise_portrait()
    test_help_and_manual_name_the_real_syntax()
    print("ok")
