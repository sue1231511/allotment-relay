#!/usr/bin/env python3
"""桥桥诊所：氛围进门、买药用药、治病、窗台斑鸠；井下伤归晏安。"""
from __future__ import annotations

import asyncio
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
    key = await db.create_api_key("clinic@example.com")
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], "病号", "", "naturalist", "")
    async with db.connect() as conn:
        sid = (await (await conn.execute(
            "SELECT id FROM stewards WHERE key_id=?", (row["id"],)
        )).fetchone())[0]
        await conn.execute("UPDATE stewards SET tickets=500 WHERE id=?", (sid,))
        await conn.commit()
    return db, row["id"], sid


async def test_clinic_status_scene() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="clinic-story-"))
    db, kid, sid = await _boot(tmp)
    from server import health, mcp_dispatch

    async with db.connect() as conn:
        await health.inflict(conn, sid, "sprain", source="event")
        await conn.commit()

    status = await mcp_dispatch.visit_bundle(kid, "clinic status")
    assert "桥桥大夫诊所" in status, status
    assert "sprain" in status or "扭伤" in status, status
    assert any(x in status for x in ("斑鸠", "药柜", "铃铛", "阳光")), status


async def test_clinic_treat_and_buy_use() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="clinic-treat-"))
    db, kid, sid = await _boot(tmp)
    from server import health, mcp_dispatch

    async with db.connect() as conn:
        await health.inflict(conn, sid, "hangover", source="event")
        await conn.commit()

    with patch("server.clinic.random.random", return_value=0.99):
        treated = await mcp_dispatch.visit_bundle(kid, "clinic treat hangover")
    assert "桥桥大夫" in treated, treated
    assert "宿醉" in treated or "hangover" in treated.lower(), treated

    async with db.connect() as conn:
        cur = await conn.execute(
            "SELECT 1 FROM steward_ailments WHERE steward_id=? AND ailment_key='hangover'",
            (sid,),
        )
        assert await cur.fetchone() is None

    bought = await mcp_dispatch.visit_bundle(kid, "clinic buy 醒酒药")
    assert "醒酒药" in bought, bought

    async with db.connect() as conn:
        await health.inflict(conn, sid, "hangover", source="event")
        await conn.commit()

    used = await mcp_dispatch.visit_bundle(kid, "clinic use 醒酒药")
    assert "醒酒药" in used or "宿醉" in used, used


async def test_clinic_refuses_pit_injuries() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="clinic-pit-refuse-"))
    db, kid, sid = await _boot(tmp)
    from server import health, mcp_dispatch

    async with db.connect() as conn:
        await health.inflict(conn, sid, "ring_shock", source="pit")
        await conn.commit()

    try:
        await mcp_dispatch.visit_bundle(kid, "clinic treat 斗场震伤")
        raise AssertionError("expected pit injury refusal")
    except ValueError as e:
        assert "找晏安去" in str(e), e

    status = await mcp_dispatch.visit_bundle(kid, "clinic status")
    assert "井下伤" in status or "晏安" in status, status
    assert "干农活" not in status, status


async def test_clinic_refuses_pit_sourced_sprain() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="clinic-pit-sprain-"))
    db, kid, sid = await _boot(tmp)
    from server import health, mcp_dispatch

    async with db.connect() as conn:
        await health.inflict(conn, sid, "sprain", source="pit")
        await conn.commit()

    status = await mcp_dispatch.visit_bundle(kid, "clinic status")
    assert "深坑打架" in status, status
    assert "干农活" not in status, status

    try:
        await mcp_dispatch.visit_bundle(kid, "clinic treat sprain")
        raise AssertionError("expected pit-sourced sprain refusal")
    except ValueError as e:
        assert "找晏安去" in str(e), e


async def test_clinic_dove_feed() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="clinic-dove-"))
    db, kid, sid = await _boot(tmp)
    from server import mcp_dispatch

    async with db.connect() as conn:
        await db.add_item(conn, sid, "crop_fogpea", 2)
        await conn.commit()

    fed = await mcp_dispatch.visit_bundle(kid, "clinic dove 喂")
    assert "斑鸠" in fed, fed
    assert "好感" in fed, fed

    s = await db.get_steward_by_id(sid)
    assert int(s.get("clinic_dove_affinity") or 0) >= 2


async def test_clinic_catalog() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="clinic-catalog-"))
    _db, kid, _sid = await _boot(tmp)
    from server import mcp_dispatch

    cat = await mcp_dispatch.visit_bundle(kid, "clinic catalog")
    for name in ("醒酒药", "净血针剂", "祛咒香", "回春汤", "大补丸", "调理"):
        assert name in cat, cat
    assert "急救包" not in cat, cat


async def test_clinic_tonic_restores_health() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="clinic-tonic-"))
    db, kid, sid = await _boot(tmp)
    from server import mcp_dispatch

    async with db.connect() as conn:
        await conn.execute("UPDATE stewards SET health=60, tickets=800 WHERE id=?", (sid,))
        await conn.commit()

    with patch("server.clinic.random.random", return_value=0.99):
        msg = await mcp_dispatch.visit_bundle(kid, "clinic 调理 中")
    assert "身体 +" in msg, msg
    assert "中调理" in msg or "调理" in msg, msg

    s = await db.get_steward_by_id(sid)
    assert int(s["health"]) == 90, s["health"]
    assert int(s["tickets"]) < 800, s["tickets"]
    assert int(s.get("clinic_tonic_count") or 0) == 1


async def test_clinic_buy_use_tonic() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="clinic-buy-tonic-"))
    db, kid, sid = await _boot(tmp)
    from server import mcp_dispatch

    async with db.connect() as conn:
        await conn.execute("UPDATE stewards SET health=70, tickets=500 WHERE id=?", (sid,))
        await conn.commit()

    with patch("server.clinic.random.random", return_value=0.99):
        bought = await mcp_dispatch.visit_bundle(kid, "clinic buy 回春汤")
    assert "回春汤" in bought, bought

    used = await mcp_dispatch.visit_bundle(kid, "clinic use 回春汤")
    assert "身体 +" in used, used
    s = await db.get_steward_by_id(sid)
    assert int(s["health"]) == 88, s["health"]


async def test_clinic_tonic_full_health_refuses() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="clinic-tonic-full-"))
    db, kid, sid = await _boot(tmp)
    from server import mcp_dispatch

    async with db.connect() as conn:
        await conn.execute("UPDATE stewards SET health=100, tickets=500 WHERE id=?", (sid,))
        await conn.commit()

    try:
        with patch("server.clinic.random.random", return_value=0.99):
            await mcp_dispatch.visit_bundle(kid, "clinic 调理 小")
        raise AssertionError("expected full-health refusal")
    except ValueError as e:
        assert "满分" in str(e), e


if __name__ == "__main__":
    asyncio.run(test_clinic_status_scene())
    asyncio.run(test_clinic_treat_and_buy_use())
    asyncio.run(test_clinic_refuses_pit_injuries())
    asyncio.run(test_clinic_refuses_pit_sourced_sprain())
    asyncio.run(test_clinic_dove_feed())
    asyncio.run(test_clinic_catalog())
    asyncio.run(test_clinic_tonic_restores_health())
    asyncio.run(test_clinic_buy_use_tonic())
    asyncio.run(test_clinic_tonic_full_health_refuses())
    print("ok")
