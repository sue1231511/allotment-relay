#!/usr/bin/env python3
"""牲口病、接触感染、霍衡兽医兜底。"""
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
    for key in ("VET_NPC_URL", "VET_NPC_API_KEY", "VET_NPC_MODEL"):
        os.environ.pop(key, None)
    from server import config, db

    config.DATA_DIR = tmp
    config.DB_PATH = tmp / "relay.db"
    db.DATA_DIR = tmp
    db.DB_PATH = tmp / "relay.db"
    await db.init_db()
    return db


async def _enroll(db, email: str, name: str) -> tuple[int, int]:
    key = await db.create_api_key(email)
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], name, "", "naturalist", "")
    async with db.connect() as conn:
        sid = (
            await (
                await conn.execute(
                    "SELECT id FROM stewards WHERE key_id=?", (row["id"],)
                )
            ).fetchone()
        )[0]
        await conn.execute(
            "UPDATE stewards SET barn_built=1, tickets=500 WHERE id=?",
            (sid,),
        )
        await conn.execute(
            "INSERT OR IGNORE INTO barn_animals (steward_id, slot, species, fed) VALUES (?,?,NULL,0)",
            (sid, 1),
        )
        await conn.commit()
    return row["id"], sid


async def _test_treat_clears_ailment_and_charges() -> None:
    from server import barn_disease, vet

    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        db = await _boot(tmp)
        kid, sid = await _enroll(db, "vet@t.test", "栏主")
        async with db.connect() as conn:
            await conn.execute(
                """
                UPDATE barn_animals SET species='sheep', stocked_at=?, fed=1, born_at=?,
                    ailment='hoof_rot', ailment_at=?
                WHERE steward_id=? AND slot=1
                """,
                (db.now() - 100, db.now() - 100, db.now() - 100, sid),
            )
            await conn.commit()
        msg = await vet.vet_ops(kid, "treat 1")
        assert "蹄瘟" in msg and "票" in msg, msg
        async with db.connect() as conn:
            row = await (
                await conn.execute(
                    "SELECT ailment FROM barn_animals WHERE steward_id=? AND slot=1",
                    (sid,),
                )
            ).fetchone()
            tickets = (
                await (
                    await conn.execute("SELECT tickets FROM stewards WHERE id=?", (sid,))
                ).fetchone()
            )[0]
        assert row and row[0] in ("", None)
        assert tickets == 500 - barn_disease.BARN_AILMENTS["hoof_rot"]["cost"]


async def _test_harvest_sick_can_infect() -> None:
    from server import barn, barn_disease, health

    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        db = await _boot(tmp)
        kid, sid = await _enroll(db, "sick@t.test", "病栏")
        async with db.connect() as conn:
            await conn.execute(
                """
                UPDATE barn_animals SET species='pig', stocked_at=?, fed=1, born_at=?,
                    ailment='murrain', ailment_at=?
                WHERE steward_id=? AND slot=1
                """,
                (db.now() - 2000, db.now() - 2000, db.now() - 100, sid),
            )
            await conn.commit()
            ill = await barn_disease.contact_human(
                conn, sid, "murrain", source="harvest", force=True
            )
            await conn.commit()
            ailments = await health.list_ailments(conn, sid)
        assert ill, ill
        assert any(a["key"] == "murrain_touch" for a in ailments), ailments
        ready = barn._ready(
            {
                "species": "pig",
                "stocked_at": db.now() - 2000,
                "fed": 1,
            },
            "pig",
        )
        assert ready


async def _test_vet_chat_fallback_without_env() -> None:
    from server import vet

    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        db = await _boot(tmp)
        kid, _sid = await _enroll(db, "chat@t.test", "闲聊客")
        msg = await vet.vet_ops(kid, "")
        assert "霍衡" in msg, msg
        assert "真 AI" in msg or "外线" in msg or "老规矩" in msg, msg
        help_text = await vet.vet_ops(kid, "help")
        assert "兽医 treat 1" in help_text
        assert "桥桥" in help_text


async def _test_climate_pools_have_non_drought() -> None:
    from server import config, disaster

    spring = {k for k, _ in config.SEASON_CLIMATE_WEIGHTS["春"]}
    summer = {k for k, _ in config.SEASON_CLIMATE_WEIGHTS["夏"]}
    autumn = {k for k, _ in config.SEASON_CLIMATE_WEIGHTS["秋"]}
    winter = {k for k, _ in config.SEASON_CLIMATE_WEIGHTS["冬"]}
    assert "drought" in spring and "blossom_tide" in spring and "spring_flood" in spring
    assert "drought" in summer and "red_tide" in summer and "thunderstorm" in summer
    assert "drought" in autumn and "murrain_week" in autumn and "leaf_fall" in autumn
    assert "drought" in winter and "snowbound" in winter and "north_wind" in winter
    seen = {disaster.pick_season_climate("春") for _ in range(80)}
    assert "blossom_tide" in seen or "pest_wave" in seen or "warm_rain" in seen


def test_treat_clears_ailment_and_charges() -> None:
    asyncio.run(_test_treat_clears_ailment_and_charges())


def test_harvest_sick_can_infect() -> None:
    asyncio.run(_test_harvest_sick_can_infect())


def test_vet_chat_fallback_without_env() -> None:
    asyncio.run(_test_vet_chat_fallback_without_env())


def test_climate_pools_have_non_drought() -> None:
    asyncio.run(_test_climate_pools_have_non_drought())


def test_vet_npc_openai_compat_settings() -> None:
    from server import vet_npc

    os.environ.pop("VET_NPC_URL", None)
    os.environ.pop("VET_NPC_API_KEY", None)
    os.environ.pop("VET_NPC_MODEL", None)
    assert vet_npc.settings() is None

    os.environ["VET_NPC_API_KEY"] = "sk-test"
    os.environ["VET_NPC_MODEL"] = "MiniMax-M2.5"
    os.environ["VET_NPC_URL"] = "https://user:pass@api.example.com/v1"
    assert vet_npc.settings() is None
    os.environ["VET_NPC_URL"] = "https://api.example.com/v1?foo=1"
    assert vet_npc.settings() is None
    os.environ["VET_NPC_URL"] = "https://api.example.com/v1"
    url, key, model = vet_npc.settings()
    assert url.endswith("/v1/chat/completions")
    assert key == "sk-test" and model == "MiniMax-M2.5"
    assert vet_npc.uses_reasoning_split("MiniMax-M2.5")
    assert vet_npc.uses_reasoning_split("abab6.5-chat")
    assert not vet_npc.uses_reasoning_split("qwen-plus")
    assert not vet_npc.uses_reasoning_split("glm-4")
    os.environ["VET_NPC_URL"] = "https://api.moonshot.cn/v1/chat/completions"
    url, _, _ = vet_npc.settings()
    assert url == "https://api.moonshot.cn/v1/chat/completions"
    for env_key in ("VET_NPC_URL", "VET_NPC_API_KEY", "VET_NPC_MODEL"):
        os.environ.pop(env_key, None)


async def _test_visit_ops_routes_treat() -> None:
    from server import mcp_dispatch

    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        db = await _boot(tmp)
        kid, sid = await _enroll(db, "route@t.test", "路由客")
        async with db.connect() as conn:
            await conn.execute(
                """
                UPDATE barn_animals SET species='sheep', stocked_at=?, fed=1, born_at=?,
                    ailment='hoof_rot', ailment_at=?
                WHERE steward_id=? AND slot=1
                """,
                (db.now() - 100, db.now() - 100, db.now() - 100, sid),
            )
            await conn.commit()
        msg = await mcp_dispatch.visit_bundle(kid, "兽医 treat 1")
        assert "蹄瘟" in msg, msg
        async with db.connect() as conn:
            row = await (
                await conn.execute(
                    "SELECT ailment FROM barn_animals WHERE steward_id=? AND slot=1",
                    (sid,),
                )
            ).fetchone()
        assert row and row[0] in ("", None)
        help_text = await mcp_dispatch.visit_bundle(kid, "help")
        assert "兽医 treat 1" in help_text and "霍衡" in help_text


def test_visit_ops_routes_treat() -> None:
    asyncio.run(_test_visit_ops_routes_treat())


def test_fishing_ailments_include_tide_rash() -> None:
    from server import health

    assert "tide_rash" in health.TRIGGER_AILMENTS["net"]
    assert "tide_rash" in health.TRIGGER_AILMENTS["beach"]
    assert "barn_fever" in health.TRIGGER_AILMENTS["barn_feed"]


if __name__ == "__main__":
    test_treat_clears_ailment_and_charges()
    test_harvest_sick_can_infect()
    test_vet_chat_fallback_without_env()
    test_climate_pools_have_non_drought()
    test_vet_npc_openai_compat_settings()
    test_visit_ops_routes_treat()
    test_fishing_ailments_include_tide_rash()
    print("ok")
