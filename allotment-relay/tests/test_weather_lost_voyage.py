#!/usr/bin/env python3
"""天气互咬、失物、出航途中节点、岛上怪谈。"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

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


async def _enroll(db, email: str, name: str, *, tickets: int = 800) -> tuple[int, int]:
    key = await db.create_api_key(email)
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], name, "", "naturalist", "")
    async with db.connect() as conn:
        sid = (await (await conn.execute(
            "SELECT id FROM stewards WHERE key_id=?", (row["id"],)
        )).fetchone())[0]
        await conn.execute(
            "UPDATE stewards SET last_bar_shift_at=?, energy=80, tickets=? WHERE id=?",
            (db.now(), tickets, sid),
        )
        await conn.commit()
    return row["id"], sid


def test_help_copy() -> None:
    from server import chaoshen, mcp_dispatch

    assert "失物" in mcp_dispatch.VISIT_HELP
    assert "潮生会 失物 交 银色打火机" in mcp_dispatch.VISIT_HELP
    assert "潮生会 失物" in chaoshen.CHAOSHEN_HELP
    assert "绕行" in mcp_dispatch.TIDE_HELP
    assert "失物" in mcp_dispatch.TIDE_HELP
    assert "阵风当天露天地不用浇" in mcp_dispatch.PLOT_HELP
    assert "岛上传言" in mcp_dispatch.PLOT_HELP
    assert "看不见的脉" in mcp_dispatch.QUARRY_HELP
    assert "银色打火机" in mcp_dispatch.TOTE_HELP
    climate = (ROOT / "server/static/island/ui/climate.js").read_text(encoding="utf-8")
    assert "island-rumors" in climate
    assert "没人保证哪句是真的" in climate
    manual = (ROOT / "server/templates/partials/island-manual-content.html").read_text(
        encoding="utf-8"
    )
    assert "和岛上传言和岛上传言" not in manual
    assert "木牌下是本周纪事和岛上传言" in manual


def test_folklore_public_hides_truth() -> None:
    from server import folklore

    lines = folklore.public_lines()
    assert len(lines) == 3, lines
    for ln in lines:
        assert isinstance(ln, str) and ln
        assert "true" not in ln.lower()
        assert "假" not in ln
        assert "真的" not in ln or "没人保证" in folklore.weather_appendix()
    appendix = folklore.weather_appendix()
    assert "岛上最近在传" in appendix
    assert "没人保证哪句是真的" in appendix
    for row in folklore.week_rumors():
        assert "text" in row and "true" in row
        assert row["text"] in lines
    dumped = json.dumps(folklore.public_lines(), ensure_ascii=False)
    assert '"true"' not in dumped


def test_weather_helpers() -> None:
    from server import world

    outdoor = {"greenhouse": 0, "watered": 0}
    gh = {"greenhouse": 1, "watered": 0}
    with patch("server.world.current_weather", return_value="gale"):
        assert world.plot_rains(outdoor) is True
        assert world.plot_rains(gh) is False
        assert world.plot_watered(outdoor) is True
        assert world.plot_watered(gh) is False
        assert world.fridge_spoil_mult() == 1.0
        assert world.misty_fish_empty() == 0.0
        assert world.misty_hidden_vein_bonus("fog") == 0
    with patch("server.world.current_weather", return_value="clear"):
        assert world.plot_rains(outdoor) is False
        assert world.plot_watered({"greenhouse": 0, "watered": 1}) is True
        assert world.fridge_spoil_mult() == 0.72
        assert world.orchard_clear_mult({"orchard": 1, "greenhouse": 0}) == 0.90
        assert world.orchard_clear_mult({"orchard": 1, "greenhouse": 1}) == 1.0
    with patch("server.world.current_weather", return_value="misty"):
        assert world.misty_fish_empty() == 0.08
        assert world.misty_hidden_vein_bonus("fog") == 10
        assert world.misty_hidden_vein_bonus("shale") == 0
    with patch("server.world.current_tide", return_value="flood"):
        assert world.flood_closes_casino() is True
    with patch("server.world.current_tide", return_value="ebb"):
        assert world.flood_closes_casino() is False


def test_lost_spawn_turn_in_and_gift() -> None:
    asyncio.run(_test_lost_spawn_turn_in_and_gift())


async def _test_lost_spawn_turn_in_and_gift() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="lost-"))
    db = await _boot(tmp)
    kid_a, sid_a = await _enroll(db, "lost-a@example.com", "捡客")
    kid_b, sid_b = await _enroll(db, "lost-b@example.com", "失主")
    from server import lost_found as lost_mod
    from server import mcp_dispatch as mux

    async with db.connect() as conn:
        a = await db.get_steward_by_id(sid_a)
        b = await db.get_steward_by_id(sid_b)
        line = await lost_mod.spawn(conn, a, "lost_lighter", source="bar")
        await conn.execute(
            "UPDATE lost_items SET owner_hint=? WHERE item='lost_lighter' AND holder_id=?",
            ("失主", sid_a),
        )
        await conn.commit()
    assert "银色打火机" in line, line
    status = await mux.visit_bundle(kid_a, "潮生会 失物")
    assert "银色打火机" in status, status
    asked = await mux.visit_bundle(kid_a, "潮生会 失物 问")
    assert "阿簿" in asked or "潮生会" in asked, asked

    empty_wallet = await lost_mod.maybe_from_bar(
        None, a, {"id": "found_wallet", "tags": ["lost_item"]}
    )
    assert empty_wallet is None

    gifted = await mux.tote_bundle(kid_a, "gift 失主 银色打火机 1")
    assert "这是我的" in gifted, gifted
    async with db.connect() as conn:
        row = await (await conn.execute(
            "SELECT resolved, resolution, holder_id FROM lost_items WHERE item='lost_lighter'"
        )).fetchone()
        bag_b = await db.get_satchel(sid_b)
    assert int(row[0]) == 1 and row[1] == "right" and int(row[2]) == sid_b
    assert int(bag_b.get("lost_lighter") or 0) == 1

    async with db.connect() as conn:
        a = await db.get_steward_by_id(sid_a)
        await lost_mod.spawn(conn, a, "lost_coat", source="beach")
        await conn.commit()
    turned = await mux.visit_bundle(kid_a, "潮生会 失物 交 旧外套")
    assert "阿簿" in turned or "档信" in turned, turned
    async with db.connect() as conn:
        bag_a = await db.get_satchel(sid_a)
        row = await (await conn.execute(
            "SELECT resolved, resolution FROM lost_items WHERE item='lost_coat'"
        )).fetchone()
    assert int(bag_a.get("lost_coat") or 0) == 0
    assert int(row[0]) == 1 and row[1] == "hui"


def test_sea_node_resolve_and_watch() -> None:
    asyncio.run(_test_sea_node_resolve_and_watch())


async def _test_sea_node_resolve_and_watch() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="sea-node-"))
    db = await _boot(tmp)
    kid, sid = await _enroll(db, "sea@example.com", "船客")
    from server import marine, voyage_sea_node as sea_mod

    now = db.now()
    async with db.connect() as conn:
        await conn.execute(
            """
            INSERT INTO voyages (steward_id, route, departed_at, returns_at, status, encounter)
            VALUES (?, 'near', ?, ?, 'sailing', '{}')
            """,
            (sid, now - 400, now + 800),
        )
        await conn.commit()
        voyage = await marine._get_voyage(conn, sid)
        with patch("server.voyage_sea_node.random.random", return_value=0.01), patch(
            "server.voyage_sea_node._weather_kind", return_value="fog"
        ):
            note = await sea_mod.maybe_on_watch(conn, voyage)
            await conn.commit()
        assert note and "绕行" in note, note
        voyage = await marine._get_voyage(conn, sid)
        assert voyage["status"] == "sea_node"
        s = await db.get_steward_by_id(sid)
        msg = await sea_mod.resolve(conn, s, voyage, "绕行")
        await conn.commit()
        assert "绕开" in msg or "慢" in msg, msg
        voyage = await marine._get_voyage(conn, sid)
        assert voyage["status"] == "sailing"
        payload = json.loads(voyage["encounter"] or "{}")
        assert payload.get("sea_node_done") is True
        assert "sea_node" not in payload

        await conn.execute(
            "UPDATE voyages SET status='sailing', departed_at=?, returns_at=?, encounter='{}' WHERE steward_id=?",
            (now - 10, now + 1200, sid),
        )
        await conn.commit()
        early = await marine._get_voyage(conn, sid)
        skipped = await sea_mod.maybe_on_watch(conn, early)
        assert skipped is None
        still = await marine._get_voyage(conn, sid)
        assert still["status"] == "sailing"


def test_hui_http_lost() -> None:
    asyncio.run(_test_hui_http_lost())


async def _test_hui_http_lost() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="hui-lost-"))
    db = await _boot(tmp)
    key = await db.create_api_key("hui-lost@example.com")
    from fastapi.testclient import TestClient
    from server.main import app
    from server import lost_found as lost_mod

    client = TestClient(app)
    opened = client.post("/api/v1/session", json={"api_key": key, "name": "交还客"})
    assert opened.status_code == 200, opened.text
    world = opened.json().get("world") or {}
    assert isinstance(world.get("rumors"), list), world
    assert world["rumors"], world.get("rumors")

    row = await db.get_key_row(key)
    async with db.connect() as conn:
        s = await db.get_steward_by_key_id(int(row["id"]))
        await lost_mod.spawn(conn, s, "lost_photo", source="beach")
        await conn.commit()

    hall = client.get("/api/v1/hui", headers={"Authorization": f"Bearer {key}"})
    assert hall.status_code == 200, hall.text
    hui = hall.json()["hui"]
    assert any(t["key"] == "lost" for t in hui["tabs"]), hui
    rows = (hui.get("items") or {}).get("lost") or []
    assert any(r.get("kind") == "lost_turn" for r in rows), rows
    target = next(r["target"] for r in rows if r.get("kind") == "lost_turn")
    turned = client.post(
        "/api/v1/hui/act",
        headers={"Authorization": f"Bearer {key}", "Idempotency-Key": "lost-turn"},
        json={"kind": "lost_turn", "target": target},
    )
    assert turned.status_code == 200, turned.text
    assert "阿簿" in (turned.json().get("event") or {}).get("narrative", "") or "档信" in (
        (turned.json().get("event") or {}).get("narrative", "")
    ), turned.text


def test_gale_skips_water() -> None:
    asyncio.run(_test_gale_skips_water())


async def _test_gale_skips_water() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="gale-water-"))
    db = await _boot(tmp)
    kid, sid = await _enroll(db, "gale@example.com", "雨客")
    planted = db.now() - 400
    async with db.connect() as conn:
        await conn.execute(
            """
            UPDATE parcels SET crop='kale', planted_at=?, tended=1, watered=0,
                greenhouse=0, orchard=0
            WHERE steward_id=? AND slot=1 AND COALESCE(orchard,0)=0
              AND COALESCE(greenhouse,0)=0
            """,
            (planted, sid),
        )
        await conn.commit()
    from server import mcp_dispatch as mux

    with patch("server.world.current_weather", return_value="gale"):
        msg = await mux.plot_bundle(kid, "浇水 1")
    assert "阵风已经替这块地浇过一轮" in msg, msg
    async with db.connect() as conn:
        watered = (await (await conn.execute(
            "SELECT watered FROM parcels WHERE steward_id=? AND slot=1 AND COALESCE(orchard,0)=0",
            (sid,),
        )).fetchone())[0]
    assert int(watered or 0) == 0


def test_tide_hoist_keeps_bottles() -> None:
    asyncio.run(_test_tide_hoist_keeps_bottles())


async def _test_tide_hoist_keeps_bottles() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="hoist-"))
    db = await _boot(tmp)
    kid, _ = await _enroll(db, "hoist@example.com", "瓶客")
    from server import mcp_dispatch as mux

    fished = await mux.tide_bundle(kid, "捞瓶")
    assert "没有在处理的航程" not in fished, fished
    try:
        look = await mux.tide_bundle(kid, "看瓶")
    except ValueError as exc:
        look = str(exc)
    assert "没有在处理的航程" not in look, look
    try:
        await mux.tide_bundle(kid, "看")
    except ValueError as exc:
        assert "没有在处理的航程" in str(exc), str(exc)
    else:
        raise AssertionError("tide_ops 看 should hoist to voyage")


def main() -> None:
    test_help_copy()
    test_folklore_public_hides_truth()
    test_weather_helpers()
    test_lost_spawn_turn_in_and_gift()
    test_sea_node_resolve_and_watch()
    test_hui_http_lost()
    test_gale_skips_water()
    test_tide_hoist_keeps_bottles()
    print("weather lost voyage tests ok")


if __name__ == "__main__":
    main()
