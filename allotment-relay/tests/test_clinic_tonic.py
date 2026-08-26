#!/usr/bin/env python3
"""诊所调理：没病补身子，价贵；养命汤可囤。"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def _boot(tmp: Path, tickets: int = 2000):
    os.environ["DATA_DIR"] = str(tmp)
    from server import config, db

    config.DATA_DIR = tmp
    config.DB_PATH = tmp / "relay.db"
    db.DATA_DIR = tmp
    db.DB_PATH = tmp / "relay.db"
    await db.init_db()
    key = await db.create_api_key("tonic@example.com")
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], "虚人", "", "naturalist", "")
    async with db.connect() as conn:
        sid = (await (await conn.execute(
            "SELECT id FROM stewards WHERE key_id=?", (row["id"],)
        )).fetchone())[0]
        await conn.execute(
            "UPDATE stewards SET tickets=?, health=40 WHERE id=?",
            (tickets, sid),
        )
        await conn.commit()
    return db, row["id"], sid


async def test_tonic_menu_and_mid() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="tonic-menu-"))
    db, kid, sid = await _boot(tmp)
    from server import mcp_dispatch

    with patch("server.clinic._is_night", return_value=False), patch(
        "server.clinic.random.random", return_value=0.99
    ):
        menu = await mcp_dispatch.visit_bundle(kid, "clinic 调理")
        assert "养命调理" in menu or "调理 中" in menu, menu
        assert "88" in menu or "小补" in menu, menu
        assert "不治病" in menu or "treat" in menu, menu

        mid = await mcp_dispatch.visit_bundle(kid, "clinic 调理 中")
    assert "身体 +" in mid, mid
    assert "180" in mid or "养命调理" in mid, mid
    s = await db.get_steward_by_id(sid)
    assert int(s["health"]) == 54, s["health"]
    assert int(s["tickets"]) == 2000 - 180, s["tickets"]


async def test_tonic_full_and_refuse_when_full() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="tonic-full-"))
    db, kid, sid = await _boot(tmp)
    from server import mcp_dispatch

    with patch("server.clinic._is_night", return_value=False), patch(
        "server.clinic.random.random", return_value=0.99
    ):
        filled = await mcp_dispatch.visit_bundle(kid, "clinic 调理 满")
    assert "身体 +" in filled, filled
    s = await db.get_steward_by_id(sid)
    assert int(s["health"]) == 100, s["health"]
    assert int(s["tickets"]) == 2000 - 960, s["tickets"]

    try:
        await mcp_dispatch.visit_bundle(kid, "clinic 调理 中")
        raise AssertionError("expected refusal when health is full")
    except ValueError as e:
        assert "满了" in str(e), e


async def test_buy_use_tonic_soup() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="tonic-soup-"))
    db, kid, sid = await _boot(tmp)
    from server import mcp_dispatch

    with patch("server.clinic._is_night", return_value=False), patch(
        "server.clinic.random.random", return_value=0.99
    ):
        bought = await mcp_dispatch.visit_bundle(kid, "clinic buy 养命汤")
        assert "养命汤" in bought, bought
        used = await mcp_dispatch.visit_bundle(kid, "clinic use 养命汤")
    assert "身体 +" in used, used
    s = await db.get_steward_by_id(sid)
    assert int(s["health"]) == 48, s["health"]


async def test_tonic_too_poor() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="tonic-poor-"))
    _db, kid, _sid = await _boot(tmp, tickets=10)
    from server import mcp_dispatch

    with patch("server.clinic._is_night", return_value=False), patch(
        "server.clinic.random.random", return_value=0.99
    ):
        try:
            await mcp_dispatch.visit_bundle(kid, "clinic 调理 大")
            raise AssertionError("expected not enough tickets")
        except ValueError as e:
            assert "票" in str(e), e


async def test_sleep_restores_health() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="tonic-sleep-"))
    db, kid, sid = await _boot(tmp)
    from server import hut

    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET hut_built=1, hut_level=1, energy=20, health=40 WHERE id=?",
            (sid,),
        )
        await conn.execute(
            """
            INSERT INTO hut_fittings (steward_id, slot, item_key, installed_at)
            VALUES (?,?,?,?)
            """,
            (sid, "hard_1", "bed", 1),
        )
        await conn.commit()
    msg = await hut.hut_ops(kid, "睡")
    assert "身体 +" in msg, msg
    s = await db.get_steward_by_id(sid)
    assert int(s["health"]) == 46, s["health"]


async def test_event_health_effect() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="tonic-event-"))
    db, kid, sid = await _boot(tmp)
    from server import events

    s = await db.get_steward_by_id(sid)
    async with db.connect() as conn:
        holder: list[int | None] = [None]
        _msgs, ledger = await events._apply_effects(  # noqa: SLF001
            conn, s, ["health:6"], plot_id_holder=holder,
        )
        await conn.commit()
    assert ledger.get("health_delta") == 6
    s = await db.get_steward_by_id(sid)
    assert int(s["health"]) == 46, s["health"]


if __name__ == "__main__":
    asyncio.run(test_tonic_menu_and_mid())
    asyncio.run(test_tonic_full_and_refuse_when_full())
    asyncio.run(test_buy_use_tonic_soup())
    asyncio.run(test_tonic_too_poor())
    asyncio.run(test_sleep_restores_health())
    asyncio.run(test_event_health_effect())
    print("ok")
