#!/usr/bin/env python3
"""引航：绑定、有效邀请、风控、分阶段奖励、幂等。"""
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


async def _enroll(db, email: str, name: str, **kwargs):
    key = await db.create_api_key(email, **kwargs)
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], name, "", "naturalist", "")
    s = await db.get_steward_by_key_id(row["id"])
    return row["id"], s, key


async def _qualify(conn, sid: int, bond: int = 500) -> None:
    from server import bond as bond_mod
    from server import db, invite

    old = db.now() - 4 * 86400
    await conn.execute("UPDATE stewards SET created_at=? WHERE id=?", (old, sid))
    if bond:
        await bond_mod.grant(conn, sid, bond, "labor", activity="plot")
    await invite.note_activity(conn, sid, "npc")
    await invite.note_activity(conn, sid, "tale")
    await invite.note_activity(conn, sid, "eatery")


async def test_old_account_gets_code() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="invite-old-"))
    db = await _boot(tmp)
    kid, s, _key = await _enroll(db, "old@t.test", "旧客")
    assert s["invite_code"]
    assert not s.get("invited_by")
    from server import invite, mcp_dispatch
    text = await mcp_dispatch.steward_ops(kid, "引航")
    assert s["invite_code"] in text
    assert "绑定" in text
    sheet = await mcp_dispatch.steward_ops(kid, "sheet")
    assert "引航码" in sheet
    view = await invite.player_view(s)
    assert "risk_score" not in view
    assert "weights" not in view
    assert view.get("official_reward_tickets") == 100
    assert view.get("official_reward_bond") == 20


async def test_self_invite_rejected() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="invite-self-"))
    db = await _boot(tmp)
    kid, s, _key = await _enroll(db, "self@t.test", "自引")
    from server import mcp_dispatch
    try:
        await mcp_dispatch.steward_ops(kid, f"绑定 {s['invite_code']}")
        raise AssertionError("should reject self")
    except ValueError as exc:
        assert "自己" in str(exc)


async def test_repeat_bind_rejected() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="invite-rebind-"))
    db = await _boot(tmp)
    _a, host, _ = await _enroll(db, "a@t.test", "东家")
    _b, other, _ = await _enroll(db, "b@t.test", "西家")
    kid, guest, _ = await _enroll(db, "c@t.test", "过客")
    from server import mcp_dispatch
    await mcp_dispatch.steward_ops(kid, f"绑定 {host['invite_code']}")
    try:
        await mcp_dispatch.steward_ops(kid, f"绑定 {other['invite_code']}")
        raise AssertionError("should reject rebind")
    except ValueError as exc:
        assert "不能改绑" in str(exc) or "已经结过" in str(exc)


async def test_invalid_code() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="invite-bad-"))
    db = await _boot(tmp)
    kid, _s, _ = await _enroll(db, "n@t.test", "路人")
    from server import mcp_dispatch
    try:
        await mcp_dispatch.steward_ops(kid, "绑定 NOSUCH1")
        raise AssertionError("should reject missing code")
    except ValueError as exc:
        assert "无效" in str(exc)


async def test_register_pending_then_enroll() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="invite-pending-"))
    db = await _boot(tmp)
    _hid, host, _ = await _enroll(db, "host@t.test", "引路")
    _gid, guest, _ = await _enroll(
        db, "g@t.test", "新来",
        invite_code=host["invite_code"],
        device_id="11111111-1111-4111-8111-111111111111",
        ip="10.0.0.8",
    )
    assert int(guest["invited_by"] or 0) == host["id"]
    assert guest["invite_status"] in ("pending", "risk_review", "invalid")


async def test_same_device_raises_risk_not_ban() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="invite-dev-"))
    db = await _boot(tmp)
    did = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    hid, host, _ = await _enroll(db, "h@t.test", "船主", device_id=did, ip="1.1.1.1")
    guests = []
    for i in range(3):
        _k, g, _ = await _enroll(
            db, f"g{i}@t.test", f"同机{i}",
            invite_code=host["invite_code"],
            device_id=did,
            ip="1.1.1.1",
        )
        guests.append(g)
        assert g["enrolled"]
    from server import db as dbmod, invite
    async with dbmod.connect() as conn:
        conn.row_factory = __import__("aiosqlite").Row
        last = await (await conn.execute(
            "SELECT * FROM stewards WHERE id=?", (guests[-1]["id"],)
        )).fetchone()
        host_row = await (await conn.execute(
            "SELECT * FROM stewards WHERE id=?", (host["id"],)
        )).fetchone()
        score, hits = await invite.risk_score(conn, dict(last), dict(host_row))
        assert "same_device" in hits
        assert score >= 40
        assert dict(last)["invite_status"] != "banned"
        s = await db.get_steward_by_id(guests[-1]["id"])
        assert s["enrolled"] == 1


async def test_shared_ip_two_players_stays_low() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="invite-ip-"))
    db = await _boot(tmp)
    _h, host, _ = await _enroll(db, "h@t.test", "家长", device_id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", ip="8.8.8.8")
    _k1, g1, _ = await _enroll(
        db, "p1@t.test", "同学甲",
        invite_code=host["invite_code"],
        device_id="cccccccc-cccc-4ccc-8ccc-cccccccccccc",
        ip="8.8.8.8",
    )
    _k2, g2, _ = await _enroll(
        db, "p2@t.test", "同学乙",
        invite_code=host["invite_code"],
        device_id="dddddddd-dddd-4ddd-8ddd-dddddddddddd",
        ip="8.8.8.8",
    )
    from server import db as dbmod, invite
    async with dbmod.connect() as conn:
        conn.row_factory = __import__("aiosqlite").Row
        inviter = dict(await (await conn.execute("SELECT * FROM stewards WHERE id=?", (host["id"],))).fetchone())
        invitee = dict(await (await conn.execute("SELECT * FROM stewards WHERE id=?", (g2["id"],))).fetchone())
        score, hits = await invite.risk_score(conn, invitee, inviter)
        assert "same_device" not in hits
        assert "ip_burst" not in hits
        assert invite.risk_band(score) == "low"


async def test_rewards_idempotent_tickets_and_bond() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="invite-pay-"))
    db = await _boot(tmp)
    _h, host, _ = await _enroll(db, "h@t.test", "谢人")
    _g, guest, _ = await _enroll(db, "g@t.test", "谢客", invite_code=host["invite_code"])
    from server import config, db as dbmod, invite
    host0 = await db.get_steward_by_id(host["id"])
    t0 = int(host0["tickets"])
    b0 = int(host0["island_bond"] or 0)
    async with dbmod.connect() as conn:
        conn.row_factory = __import__("aiosqlite").Row
        await _qualify(conn, guest["id"], 1600)
        r1 = await invite.evaluate_and_settle(conn, guest["id"], force=True)
        r2 = await invite.evaluate_and_settle(conn, guest["id"], force=True)
        await conn.commit()
    assert r1 and TIER_OK(r1)
    assert r2["granted"] == []
    host2 = await db.get_steward_by_id(host["id"])
    guest2 = await db.get_steward_by_id(guest["id"])
    assert int(host2["tickets"]) == t0 + int(config.INVITE_REWARD_QUALIFIED_TICKETS)
    assert int(host2["island_bond"]) == b0 + int(config.INVITE_REWARD_QUALIFIED_BOND)
    assert int(host2["invite_lantern"]) == 1
    assert guest2["invite_status"] == "rewarded"
    from server import progress
    async with dbmod.connect() as conn:
        have = await progress._unlocked_keys(conn, host["id"])
        have2 = await progress._unlocked_keys(conn, guest["id"])
    assert "navigator" in have
    assert "same_tide" in have2


def TIER_OK(result: dict) -> bool:
    return "qualified" in result.get("granted", []) or result.get("status") == "rewarded"


async def test_concurrent_settle() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="invite-race-"))
    db = await _boot(tmp)
    _h, host, _ = await _enroll(db, "h@t.test", "竞态主")
    _g, guest, _ = await _enroll(db, "g@t.test", "竞态客", invite_code=host["invite_code"])
    from server import db as dbmod, invite

    async def once():
        async with dbmod.connect() as conn:
            conn.row_factory = __import__("aiosqlite").Row
            await _qualify(conn, guest["id"], 600)
            result = await invite.evaluate_and_settle(conn, guest["id"], force=True)
            await conn.commit()
            return result

    a, b = await asyncio.gather(once(), once())
    granted = (a or {}).get("granted", []) + (b or {}).get("granted", [])
    assert granted.count("qualified") <= 1
    async with dbmod.connect() as conn:
        n = (await (await conn.execute(
            "SELECT COUNT(*) FROM invite_rewards WHERE invitee_id=? AND tier='qualified'",
            (guest["id"],),
        )).fetchone())[0]
    assert n == 1


async def test_new_device_after_clear_still_binds() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="invite-cookie-"))
    db = await _boot(tmp)
    _h, host, _ = await _enroll(db, "h@t.test", "码主", device_id="eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")
    _g, guest, _ = await _enroll(
        db, "g@t.test", "清过缓存",
        invite_code=host["invite_code"],
        device_id="ffffffff-ffff-4fff-8fff-ffffffffffff",
        ip="9.9.9.9",
    )
    assert int(guest["invited_by"]) == host["id"]


async def test_mid_risk_delays_official() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="invite-mid-"))
    db = await _boot(tmp)
    from server import config
    old_w, old_lo, old_hi = config.INVITE_RISK_WEIGHTS, config.INVITE_RISK_LOW_MAX, config.INVITE_RISK_MID_MAX
    config.INVITE_RISK_WEIGHTS = {**old_w, "same_device": 40, "device_burst": 0,
                                  "ip_burst": 0, "ip_overlap": 0, "behavior_anomaly": 0,
                                  "inviter_burst": 0, "proxy_hint": 0}
    config.INVITE_RISK_LOW_MAX = 24
    config.INVITE_RISK_MID_MAX = 54
    try:
        did = "12121212-1212-4121-8121-121212121212"
        _h, host, _ = await _enroll(db, "h@t.test", "中险主", device_id=did)
        _g, guest, _ = await _enroll(
            db, "g@t.test", "中险客", invite_code=host["invite_code"], device_id=did,
        )
        from server import db as dbmod, invite
        async with dbmod.connect() as conn:
            conn.row_factory = __import__("aiosqlite").Row
            await _qualify(conn, guest["id"], 600)
            result = await invite.evaluate_and_settle(conn, guest["id"])
            await conn.commit()
        assert result["band"] == "mid"
        assert result["status"] == "risk_review"
        assert "qualified" not in result["granted"]
        text = await invite.admin_clear(guest["id"])
        assert "解除" in text or "重算" in text
        guest2 = await db.get_steward_by_id(guest["id"])
        assert guest2["invite_status"] in ("qualified", "rewarded", "pending")
        async with dbmod.connect() as conn:
            conn.row_factory = __import__("aiosqlite").Row
            again = await invite.evaluate_and_settle(conn, guest["id"])
            await conn.commit()
        assert again["status"] not in ("risk_review", "invalid")
    finally:
        config.INVITE_RISK_WEIGHTS = old_w
        config.INVITE_RISK_LOW_MAX = old_lo
        config.INVITE_RISK_MID_MAX = old_hi


async def test_admin_clear_before_qualify_stays_cleared() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="invite-clear-"))
    db = await _boot(tmp)
    from server import config
    old_w, old_lo, old_hi = config.INVITE_RISK_WEIGHTS, config.INVITE_RISK_LOW_MAX, config.INVITE_RISK_MID_MAX
    config.INVITE_RISK_WEIGHTS = {**old_w, "same_device": 40, "device_burst": 0,
                                  "ip_burst": 0, "ip_overlap": 0, "behavior_anomaly": 0,
                                  "inviter_burst": 0, "proxy_hint": 0}
    config.INVITE_RISK_LOW_MAX = 24
    config.INVITE_RISK_MID_MAX = 54
    try:
        did = "14141414-1414-4141-8141-141414141414"
        _h, host, _ = await _enroll(db, "h@t.test", "清主", device_id=did)
        _g, guest, _ = await _enroll(
            db, "g@t.test", "清客", invite_code=host["invite_code"], device_id=did,
        )
        from server import db as dbmod, invite
        async with dbmod.connect() as conn:
            conn.row_factory = __import__("aiosqlite").Row
            before = await invite.evaluate_and_settle(conn, guest["id"])
            await conn.commit()
        assert before["band"] == "mid"
        assert before["status"] == "risk_review"
        await invite.admin_clear(guest["id"])
        async with dbmod.connect() as conn:
            conn.row_factory = __import__("aiosqlite").Row
            after = await invite.evaluate_and_settle(conn, guest["id"])
            await conn.commit()
        assert after["status"] == "pending"
        assert after["status"] not in ("risk_review", "invalid")
    finally:
        config.INVITE_RISK_WEIGHTS = old_w
        config.INVITE_RISK_LOW_MAX = old_lo
        config.INVITE_RISK_MID_MAX = old_hi


async def test_high_risk_not_counted_can_play() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="invite-high-"))
    db = await _boot(tmp)
    from server import config
    old_w = config.INVITE_RISK_WEIGHTS
    config.INVITE_RISK_WEIGHTS = {**old_w, "same_device": 40, "device_burst": 30}
    try:
        did = "13131313-1313-4131-8131-131313131313"
        _h, host, _ = await _enroll(db, "h@t.test", "高险主", device_id=did, ip="2.2.2.2")
        last = None
        last_kid = 0
        for i in range(3):
            kid, last, _ = await _enroll(
                db, f"x{i}@t.test", f"高险客{i}",
                invite_code=host["invite_code"], device_id=did, ip="2.2.2.2",
            )
            last_kid = kid
        from server import db as dbmod, invite, mcp_dispatch
        async with dbmod.connect() as conn:
            conn.row_factory = __import__("aiosqlite").Row
            await _qualify(conn, last["id"], 600)
            result = await invite.evaluate_and_settle(conn, last["id"])
            await conn.commit()
        assert result["band"] == "high"
        assert result["status"] == "invalid"
        sheet = await mcp_dispatch.steward_ops(last_kid, "sheet")
        assert "管理员" in sheet
        view = await invite.player_view(await db.get_steward_by_id(last["id"]))
        assert "risk_score" not in view
        assert view["my_status"] == "暂未计入"
    finally:
        config.INVITE_RISK_WEIGHTS = old_w


async def test_help_and_manual() -> None:
    from server.mcp_dispatch import STEWARD_HELP
    from server import game
    assert "引航" in STEWARD_HELP
    assert "绑定" in STEWARD_HELP
    assert "invite_ops" in STEWARD_HELP
    man = await game.relay_manual()
    assert "引航" in man
    assert "绑定" in man
    assert "100 工分票和 20 岛缘" in man


def test_invite() -> None:
    asyncio.run(test_old_account_gets_code())
    asyncio.run(test_self_invite_rejected())
    asyncio.run(test_repeat_bind_rejected())
    asyncio.run(test_invalid_code())
    asyncio.run(test_register_pending_then_enroll())
    asyncio.run(test_same_device_raises_risk_not_ban())
    asyncio.run(test_shared_ip_two_players_stays_low())
    asyncio.run(test_rewards_idempotent_tickets_and_bond())
    asyncio.run(test_concurrent_settle())
    asyncio.run(test_new_device_after_clear_still_binds())
    asyncio.run(test_mid_risk_delays_official())
    asyncio.run(test_admin_clear_before_qualify_stays_cleared())
    asyncio.run(test_high_risk_not_counted_can_play())
    asyncio.run(test_help_and_manual())


if __name__ == "__main__":
    test_invite()
    print("invite tests ok")
