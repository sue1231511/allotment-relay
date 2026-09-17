#!/usr/bin/env python3
"""潮汐周报、岛安称呼、岛迹、岸上工程。"""
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


async def _enroll(db, email: str, name: str) -> tuple[int, int]:
    key = await db.create_api_key(email)
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], name, "", "naturalist", "")
    async with db.connect() as conn:
        sid = (await (await conn.execute(
            "SELECT id FROM stewards WHERE key_id=?", (row["id"],)
        )).fetchone())[0]
    return row["id"], sid


def test_help_copy() -> None:
    from server import chaoshen, mcp_dispatch

    assert "周报" in mcp_dispatch.STEWARD_HELP
    assert "纪事" in mcp_dispatch.STEWARD_HELP
    assert "工程" in chaoshen.CHAOSHEN_HELP
    assert "潮生会 工程 捐 岸木 10" in chaoshen.CHAOSHEN_HELP
    assert "潮生会 纪事" in chaoshen.CHAOSHEN_HELP
    assert "潮生会 周" not in chaoshen.CHAOSHEN_HELP
    assert "潮生会 周" not in mcp_dispatch.STEWARD_HELP
    assert "潮生会 周" not in mcp_dispatch.VISIT_HELP
    climate = (ROOT / "server/static/island/ui/climate.js").read_text(encoding="utf-8")
    assert "island-gazette" in climate
    assert "renderNotice" not in climate
    assert "island-climate-title" not in climate


def test_empty_gazette_and_titles() -> None:
    asyncio.run(_test_empty_gazette_and_titles())


async def _test_empty_gazette_and_titles() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="gazette-empty-"))
    db = await _boot(tmp)
    kid, sid = await _enroll(db, "gaz@example.com", "报客")
    from server import gazette, mcp_dispatch, progress, traces, works

    report = await gazette.report_text()
    assert "潮汐周报" in report, report
    assert "不是周目标" in report, report
    assert "岸上工程" in report or "工程" in report, report

    listed = await progress.progress_ops(kid, "成就")
    assert "夜灯守人" not in listed, listed
    assert "借雨的人" not in listed, listed
    try:
        await progress.progress_ops(kid, "称呼 夜灯守人")
    except ValueError as exc:
        assert "还没人这么叫你" in str(exc), str(exc)
    else:
        raise AssertionError("locked silent title should refuse")

    async with db.connect() as conn:
        for i in range(7):
            await db.add_chronicle("buxing", f"报客 在灯塔点了一盏守夜灯 #{i}", sid, conn=conn)
        await conn.commit()
    listed = await progress.progress_ops(kid, "成就")
    assert "夜灯守人" not in listed, listed

    async with db.connect() as conn:
        s = await db.get_steward_by_id(sid)
        for _ in range(7):
            await db.add_chronicle("buxing", "报客 在灯塔守夜", sid, conn=conn)
        await traces.maybe_watch_mark(conn, s)
        await progress.scan_achievements(conn, s)
        await conn.commit()
        marks = await traces.lines_for(conn, "lighthouse")
    listed = await progress.progress_ops(kid, "成就")
    assert "夜灯守人" in listed, listed
    assert "岛安的" in listed, listed
    assert any("报客" in ln and "刻了" in ln for ln in marks), marks
    worn = await progress.progress_ops(kid, "称呼 夜灯守人")
    assert "夜灯守人" in worn, worn

    async with db.connect() as conn:
        await db.add_chronicle("gift", "报客 把雾银戒递给了邻人", sid, conn=conn)
        await conn.commit()
    report = await gazette.report_text()
    assert "物的履历" in report or "雾银" in report, report

    async with db.connect() as conn:
        await conn.execute("DELETE FROM island_works")
        await conn.execute(
            """
            INSERT INTO island_works (slug, opened_at, status, have_json, completed_at, bonus_until)
            VALUES ('dock_repair', ?, 'open', '{}', 0, 0)
            """,
            (0,),
        )
        await db.add_item(conn, sid, "craft_timber", 24)
        await db.add_item(conn, sid, "craft_copper_nails", 12)
        await conn.execute("UPDATE stewards SET tickets=800 WHERE id=?", (sid,))
        await conn.commit()

    timber = await works.donate(kid, "岸木 24")
    assert "岸木" in timber, timber
    nails = await works.donate(kid, "铜钉 12")
    assert "铜钉" in nails, nails
    done = await works.donate(kid, "400")
    assert "收工" in done, done
    async with db.connect() as conn:
        assert await works.active_bonus(conn, "dock") is True
        harbor = await traces.lines_for(conn, "harbor")
    assert any("码头" in ln or "木" in ln for ln in harbor), harbor

    status = await mcp_dispatch.visit_bundle(kid, "潮生会 工程")
    assert "岸上工程" in status, status
    assert "不是潮汐基金" in status, status
    gazed = await mcp_dispatch.visit_bundle(kid, "潮生会 纪事")
    assert "潮汐周报" in gazed, gazed
    week = await mcp_dispatch.steward_ops(kid, "周报")
    assert "潮汐周报" in week, week


def test_hui_http_skus() -> None:
    asyncio.run(_test_hui_http_skus())


async def _test_hui_http_skus() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="gazette-http-"))
    db = await _boot(tmp)
    key = await db.create_api_key("hui-gaz@example.com")
    from fastapi.testclient import TestClient
    from server.main import app

    client = TestClient(app)
    opened = client.post("/api/v1/session", json={"api_key": key, "name": "工客"})
    assert opened.status_code == 200, opened.text
    gaz = ((opened.json().get("world") or {}).get("gazette") or {})
    assert gaz.get("title"), gaz

    hall = client.get("/api/v1/hui", headers={"Authorization": f"Bearer {key}"})
    assert hall.status_code == 200, hall.text
    hui = hall.json()["hui"]
    assert any(t["key"] == "works" for t in hui["tabs"]), hui
    rows = (hui.get("items") or {}).get("works") or []
    assert any(r.get("name") == "本周纪事" for r in rows), rows
    assert any(r.get("kind") == "donate_work" for r in rows), rows
    looked = client.post(
        "/api/v1/hui/act",
        headers={"Authorization": f"Bearer {key}", "Idempotency-Key": "gaz-look"},
        json={"kind": "look", "target": "gazette"},
    )
    assert looked.status_code == 200, looked.text
    assert "潮汐周报" in (looked.json().get("event") or {}).get("narrative", ""), looked.text
    work = client.post(
        "/api/v1/hui/act",
        headers={"Authorization": f"Bearer {key}", "Idempotency-Key": "work-look"},
        json={"kind": "look", "target": "work"},
    )
    assert work.status_code == 200, work.text
    assert "岸上工程" in (work.json().get("event") or {}).get("narrative", ""), work.text


def main() -> None:
    test_help_copy()
    test_empty_gazette_and_titles()
    test_hui_http_skus()
    print("gazette traces tests ok")


if __name__ == "__main__":
    main()
