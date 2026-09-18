"""潮生会 /island 会厅：禁捕与鱼群入口。"""
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_hui_ask_shelf_has_fishban():
    async def run():
        from server import chaoshen, db

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("hui-fish@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "渔夫", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    shelf = await chaoshen.player_view(conn, s)
                ask = shelf["items"]["ask"]
                keys = {row["id"] for row in ask}
                assert "fishban-look" in keys
                fish_row = next(r for r in ask if r["id"] == "fishban-look")
                assert fish_row["target"] == "fishban"
                assert fish_row["kind"] == "look"

    asyncio.run(run())


def test_hui_fishban_act_command():
    from server.v1 import hui_service

    assert hui_service._command("look", "fishban") == "禁捕"

