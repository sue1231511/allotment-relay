#!/usr/bin/env python3
"""潮生会：岛上管事机构，不能加入。"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CST = timezone(timedelta(hours=8))


def _cst_ts(year: int, month: int, day: int, hour: int = 12) -> int:
    return int(datetime(year, month, day, hour, tzinfo=CST).timestamp())


TUE = _cst_ts(2026, 8, 25)
WED = _cst_ts(2026, 8, 26)


async def _boot(tmp: Path):
    os.environ["DATA_DIR"] = str(tmp)
    from server import config, db

    config.DATA_DIR = tmp
    config.DB_PATH = tmp / "relay.db"
    db.DATA_DIR = tmp
    db.DB_PATH = tmp / "relay.db"
    await db.init_db()
    return db


async def _enroll(db, email: str, name: str) -> int:
    key = await db.create_api_key(email)
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], name, "", "naturalist", "")
    return row["id"]


async def test_chaoshen_desk_and_refuse() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="chaoshen-"))
    db = await _boot(tmp)
    kid = await _enroll(db, "hui@example.com", "簿客")
    from server import mcp_dispatch, npc

    listing = await mcp_dispatch.visit_bundle(kid, "list")
    assert "阿簿" in listing and "潮生会" in listing and "不能加入" in listing, listing

    desk = await mcp_dispatch.visit_bundle(kid, "潮生会")
    assert "潮生会" in desk and "阿簿" in desk, desk
    assert "不能加入" in desk or "已经在册" in desk, desk
    assert "visit_ops 潮生会" in desk, desk

    asked = await mcp_dispatch.visit_bundle(kid, "潮生会 问")
    assert "考勤" in asked, asked
    assert "潮汐基金" in asked, asked
    assert "alliance_ops league" in asked, asked

    via_npc = await npc.npc_ops(kid, "visit 阿簿")
    assert "潮生会" in via_npc, via_npc

    via_alias = await npc.npc_ops(kid, "visit 潮生会")
    assert "值事" in via_alias or "阿簿" in via_alias, via_alias

    for bad in ("入会", "开会", "退会", "加入", "join"):
        try:
            await mcp_dispatch.visit_bundle(kid, f"潮生会 {bad}")
        except ValueError as exc:
            msg = str(exc)
            assert "不是给管理员加入" in msg, msg
        else:
            raise AssertionError(f"{bad} should refuse")

    help_text = await mcp_dispatch.visit_bundle(kid, "潮生会 help")
    assert "没有入会" in help_text and "基金 捐 50" in help_text, help_text
    assert "guild" in help_text, help_text
    assert "基金 捐 8" in help_text, help_text
    assert "税 交" in help_text, help_text
    assert "tax_ops" in help_text, help_text
    assert "不用领" in help_text and "周二" in help_text, help_text
    assert "alliance_ops league" in help_text, help_text
    assert "plot_ops commons" in help_text, help_text
    assert "不能贴" in help_text, help_text
    assert "潮汐基金" in desk, desk


async def test_chaoshen_old_windows_refuse() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="chaoshen-refuse-"))
    db = await _boot(tmp)
    kid = await _enroll(db, "oldwin@example.com", "旧客")
    from server import mcp_dispatch

    async with db.connect() as conn:
        sid = (await (await conn.execute(
            "SELECT id FROM stewards WHERE key_id=?", (kid,)
        )).fetchone())[0]
        await db.add_item(conn, sid, "crop_kale", 4)
        await conn.commit()

    try:
        await mcp_dispatch.visit_bundle(kid, "潮生会 捐 甘蓝 2")
    except ValueError as exc:
        msg = str(exc)
        assert "公仓不在潮生会" in msg, msg
        assert "alliance_ops donate" in msg, msg
    else:
        raise AssertionError("捐货 should refuse")

    try:
        await mcp_dispatch.visit_bundle(kid, "潮生会 仓")
    except ValueError as exc:
        assert "alliance_ops larder" in str(exc), str(exc)
    else:
        raise AssertionError("仓 should refuse")

    try:
        await mcp_dispatch.visit_bundle(kid, "潮生会 周")
    except ValueError as exc:
        msg = str(exc)
        assert "本周目标不在潮生会" in msg, msg
        assert "alliance_ops league" in msg, msg
    else:
        raise AssertionError("周 should refuse")

    try:
        await mcp_dispatch.visit_bundle(kid, "潮生会 公物")
    except ValueError as exc:
        assert "plot_ops commons" in str(exc), str(exc)
    else:
        raise AssertionError("公物 should refuse")

    try:
        await mcp_dispatch.visit_bundle(kid, "潮生会 领 12")
    except ValueError as exc:
        assert "plot_ops commons claim" in str(exc), str(exc)
    else:
        raise AssertionError("领 编号 should refuse")

    via_alliance = await mcp_dispatch.alliance_bundle(kid, "larder")
    assert "储藏室" in via_alliance or "空" in via_alliance or "仓" in via_alliance, via_alliance


async def test_chaoshen_public_snapshot() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="chaoshen-pub-"))
    await _boot(tmp)
    from server import chaoshen

    snap = await chaoshen.public_snapshot()
    assert snap["org"] == "潮生会"
    assert snap["clerk"] == "阿簿"
    assert "不收人" in snap["note"] or "不能" in snap["note"]
    assert "league" not in snap
    assert "larder" not in snap
    assert "commons_live" not in snap
    assert snap["fund"]["name"] == "潮汐基金"
    assert snap["fund"]["pool"] == 0


async def _set_tickets(db, key_id: int, tickets: int) -> None:
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET tickets=? WHERE key_id=?",
            (tickets, key_id),
        )
        await conn.commit()


async def _tickets(db, key_id: int) -> int:
    async with db.connect() as conn:
        row = await (await conn.execute(
            "SELECT tickets FROM stewards WHERE key_id=?", (key_id,)
        )).fetchone()
    return int(row[0])


async def test_tide_fund_average() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="chaoshen-fund-"))
    db = await _boot(tmp)
    rich = await _enroll(db, "rich@example.com", "余客")
    poor = await _enroll(db, "poor@example.com", "缺客")
    from server import chaoshen, mcp_dispatch

    real_now = db.now
    db.now = lambda: WED
    try:
        await _set_tickets(db, rich, 400)
        await _set_tickets(db, poor, 80)

        status_rich = await mcp_dispatch.visit_bundle(rich, "潮生会 基金")
        assert "岛均水准：240" in status_rich, status_rich
        assert "你的口袋：400" in status_rich, status_rich
        assert "不用领" in status_rich, status_rich

        try:
            await mcp_dispatch.visit_bundle(poor, "潮生会 基金 捐 20")
        except ValueError as exc:
            assert "没过岛均" in str(exc) or "不算有余" in str(exc), str(exc)
        else:
            raise AssertionError("poor should not donate")

        try:
            await mcp_dispatch.visit_bundle(rich, "潮生会 补贴")
        except ValueError as exc:
            assert "不用自己领" in str(exc) or "没有这条" in str(exc), str(exc)
        else:
            raise AssertionError("补贴 should refuse")

        donated = await mcp_dispatch.visit_bundle(rich, "潮生会 基金 捐 8")
        assert "8 票" in donated and "潮汐基金" in donated, donated
        assert await _tickets(db, rich) == 392

        more = await mcp_dispatch.visit_bundle(rich, "潮生会 基金 捐 50")
        assert "50 票" in more, more
        assert await _tickets(db, rich) == 342
        assert await _tickets(db, poor) == 80

        status = await mcp_dispatch.visit_bundle(poor, "潮生会 基金")
        assert "池里：58 票" in status, status

        try:
            await mcp_dispatch.visit_bundle(rich, "潮生会 捐 50")
        except ValueError as exc:
            assert "基金" in str(exc), str(exc)
        else:
            raise AssertionError("numeric 捐 should hint fund")

        snap = await chaoshen.public_snapshot()
        assert snap["fund"]["pool"] == 58
        assert snap["fund"]["avg"] == 211  # (342 + 80) / 2
        assert "周二" in (snap["fund"].get("weekdays") or "")
    finally:
        db.now = real_now


async def test_tide_fund_auto_payout() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="chaoshen-fund-pay-"))
    db = await _boot(tmp)
    rich = await _enroll(db, "pay-rich@example.com", "发余")
    poor = await _enroll(db, "pay-poor@example.com", "发缺")
    from server import chaoshen, mcp_dispatch

    real_now = db.now
    db.now = lambda: TUE
    try:
        await _set_tickets(db, rich, 400)
        await _set_tickets(db, poor, 80)
        donated = await mcp_dispatch.visit_bundle(rich, "潮生会 基金 捐 50")
        assert "50 票" in donated, donated
        assert await _tickets(db, rich) == 350
        assert await _tickets(db, poor) == 130  # 池里 50 全补出去，不到顶 2500
        assert "发放" in donated or "补" in donated, donated

        try:
            await mcp_dispatch.visit_bundle(poor, "潮生会 补贴")
        except ValueError as exc:
            assert "不用自己领" in str(exc), str(exc)
        else:
            raise AssertionError("补贴 should refuse even on payday")

        async with db.connect() as conn:
            again = await chaoshen.ensure_fund_payout(conn, ts=TUE)
            await conn.commit()
        assert again is None
        assert await _tickets(db, poor) == 130
        assert chaoshen.FUND_PAY_CAP == 2500
    finally:
        db.now = real_now


async def test_tide_fund_cap_raised() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="chaoshen-fund-cap-"))
    db = await _boot(tmp)
    rich = await _enroll(db, "cap-rich@example.com", "阔余")
    poor = await _enroll(db, "cap-poor@example.com", "阔缺")
    from server import mcp_dispatch

    real_now = db.now
    db.now = lambda: TUE
    try:
        await _set_tickets(db, rich, 10000)
        await _set_tickets(db, poor, 100)
        donated = await mcp_dispatch.visit_bundle(rich, "潮生会 基金 捐 3000")
        assert "3000" in donated or "3,000" in donated or "发放" in donated, donated
        # 旧顶 1000 会卡在 1100；新顶 2500 能补到 2600
        assert await _tickets(db, poor) == 2600, await _tickets(db, poor)
    finally:
        db.now = real_now


async def test_tide_fund_need_peers() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="chaoshen-fund-solo-"))
    db = await _boot(tmp)
    kid = await _enroll(db, "solo@example.com", "独客")
    from server import mcp_dispatch

    await _set_tickets(db, kid, 400)
    text = await mcp_dispatch.visit_bundle(kid, "潮生会 基金")
    assert "算不出" in text or "还不够" in text, text
    try:
        await mcp_dispatch.visit_bundle(kid, "潮生会 基金 捐 50")
    except ValueError as exc:
        assert "算不出" in str(exc) or "还不够" in str(exc), str(exc)
    else:
        raise AssertionError("solo donate should refuse")


async def test_hui_official_notices() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="hui-notice-"))
    db = await _boot(tmp)
    kid = await _enroll(db, "notice@example.com", "看客")
    from server import chaoshen, mcp_dispatch

    empty = await mcp_dispatch.visit_bundle(kid, "潮生会 告示")
    assert "暂无" in empty or "空" in empty, empty
    assert "不能贴" in empty, empty

    try:
        await mcp_dispatch.visit_bundle(kid, "潮生会 贴 互助 今晚出海")
    except ValueError as exc:
        assert "不能贴" in str(exc), str(exc)
    else:
        raise AssertionError("贴 should refuse")

    try:
        await mcp_dispatch.alliance_bundle(kid, "beacon post 互助 今晚出海")
    except ValueError as exc:
        assert "不能贴" in str(exc), str(exc)
    else:
        raise AssertionError("beacon post should refuse")

    try:
        await mcp_dispatch.visit_bundle(kid, "潮生会 回 1 收到")
    except ValueError as exc:
        assert "不能" in str(exc), str(exc)
    else:
        raise AssertionError("回 should refuse")

    posted = await chaoshen.owner_post("维修", "本周岸维照划，起步免。")
    assert posted["ok"] and posted["id"], posted

    shown = await mcp_dispatch.visit_bundle(kid, "潮生会 告示")
    assert "本周岸维照划" in shown, shown
    assert "潮生会" in shown, shown
    assert "维修" in shown, shown

    via_beacon = await mcp_dispatch.alliance_bundle(kid, "beacon scan")
    assert "本周岸维照划" in via_beacon, via_beacon

    tagged = await mcp_dispatch.visit_bundle(kid, "潮生会 告示 维修")
    assert "本周岸维照划" in tagged, tagged

    one = await mcp_dispatch.visit_bundle(kid, f"潮生会 告示 {posted['id']}")
    assert "本周岸维照划" in one, one

    snap = await chaoshen.public_snapshot()
    assert any("本周岸维照划" in (b.get("body") or "") for b in snap["beacons"]), snap
    assert all(b.get("author") == "潮生会" for b in snap["beacons"]), snap

    async with db.connect() as conn:
        sid = (await (await conn.execute(
            "SELECT id FROM stewards WHERE key_id=?", (kid,)
        )).fetchone())[0]
        await conn.execute(
            "INSERT INTO beacons (author_id, tag, body, created_at) VALUES (?,?,?,?)",
            (sid, "notice", "这是玩家留言不该上墙", db.now()),
        )
        await conn.commit()

    snap2 = await chaoshen.public_snapshot()
    assert all("玩家留言" not in (b.get("body") or "") for b in snap2["beacons"]), snap2
    listed = await mcp_dispatch.visit_bundle(kid, "潮生会 告示")
    assert "玩家留言" not in listed, listed

    retracted = await chaoshen.owner_retract(posted["id"])
    assert retracted["ok"], retracted
    gone = await mcp_dispatch.visit_bundle(kid, "潮生会 告示")
    assert "本周岸维照划" not in gone, gone
    try:
        await chaoshen.owner_retract(posted["id"])
    except ValueError as exc:
        assert "收下" in str(exc), str(exc)
    else:
        raise AssertionError("second retract should refuse")


async def test_hui_owner_http() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="hui-http-"))
    await _boot(tmp)
    from fastapi.testclient import TestClient
    from server import chaoshen, config
    from server.main import app

    config.HUI_KEY = "test-hui-key"
    client = TestClient(app)

    denied = client.get("/hui-owner?key=wrong")
    assert denied.status_code == 401, denied.text

    page = client.get("/hui-owner?key=test-hui-key")
    assert page.status_code == 200, page.text
    assert "上墙" in page.text
    assert "岛民" in page.text and "不能贴" in page.text

    posted = client.post(
        "/api/hui-owner/post",
        json={"key": "test-hui-key", "tag": "活动", "body": "周六补贴照发"},
    )
    assert posted.status_code == 200, posted.text
    data = posted.json()
    assert data.get("ok"), data

    snap = await chaoshen.public_snapshot()
    assert any("周六补贴照发" in (b.get("body") or "") for b in snap["beacons"]), snap

    public = client.get("/api/public/hui")
    assert public.status_code == 200, public.text
    bodies = [b.get("body") for b in public.json().get("beacons") or []]
    assert any("周六补贴照发" in (b or "") for b in bodies), bodies

    retracted = client.post(
        "/api/hui-owner/retract",
        json={"key": "test-hui-key", "id": data["id"]},
    )
    assert retracted.status_code == 200, retracted.text


def test_chaoshen() -> None:
    asyncio.run(test_chaoshen_desk_and_refuse())
    asyncio.run(test_chaoshen_old_windows_refuse())
    asyncio.run(test_chaoshen_public_snapshot())
    asyncio.run(test_tide_fund_average())
    asyncio.run(test_tide_fund_need_peers())
    asyncio.run(test_tide_fund_auto_payout())
    asyncio.run(test_tide_fund_cap_raised())
    asyncio.run(test_hui_official_notices())
    asyncio.run(test_hui_owner_http())


if __name__ == "__main__":
    test_chaoshen()
    print("ok")
