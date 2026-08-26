#!/usr/bin/env python3
"""婚约：岛民向自己的人类求婚。人类网页确认，不是岛民互婚。"""
from __future__ import annotations

import asyncio
import os
import re
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


async def _enroll(db, email: str, name: str) -> int:
    key = await db.create_api_key(email)
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], name, "", "naturalist", "")
    return row["id"]


def _token_from(text: str) -> str:
    m = re.search(r"/(?:vow|lianli)/([A-Za-z0-9_-]+)", text)
    assert m, text
    return m.group(1)


async def _ready_to_propose(db, key_id: int, *, tickets: int = 400, ring: bool = True, hut: bool = True) -> None:
    async with db.connect() as conn:
        sid = (await (await conn.execute(
            "SELECT id FROM stewards WHERE key_id=?", (key_id,)
        )).fetchone())[0]
        if hut:
            await conn.execute(
                "UPDATE stewards SET hut_built=1, hut_level=1, hut_label=? WHERE id=?",
                ("潮声小屋", sid),
            )
        await conn.execute("UPDATE stewards SET tickets=? WHERE id=?", (tickets, sid))
        if ring:
            await db.add_item(conn, sid, "tide_vow_ring", 1)
        await conn.commit()


async def _full_flow() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="marriage-"))
    db = await _boot(tmp)
    from server import marriage
    from server.mcp_app import current_origin

    current_origin.set("http://island.test")
    host = await _enroll(db, "host@example.com", "泊舟")
    guest = await _enroll(db, "guest@example.com", "邻潮")

    empty = await marriage.marriage_ops(host, "")
    assert "还没有婚约" in empty, empty
    assert "小屋" in empty and "300" in empty, empty
    from server import mcp_dispatch as mux
    vdesk = await mux.visit_bundle(host, "连理所")
    assert "连理所" in vdesk and "理枝" in vdesk, vdesk
    help_text = await marriage.marriage_ops(host, "help")
    assert "propose_marriage" in help_text
    assert "没有「接受」" in help_text or "不能自己确认" in help_text
    assert "离婚 答应" in help_text
    assert "离婚 拒绝" in help_text
    assert "连理所" in help_text
    assert "离婚" in help_text
    assert "理枝" in help_text
    assert "300" in help_text
    assert "潮誓戒" in help_text

    try:
        await marriage.marriage_ops(host, "接受")
        raise AssertionError("AI must not self-confirm")
    except ValueError as exc:
        assert "未知" in str(exc) or "propose_marriage" in str(exc), exc

    try:
        await marriage.marriage_ops(host, "寻戒")
        raise AssertionError("seek before draft")
    except ValueError as exc:
        assert "草稿" in str(exc), exc

    try:
        await marriage.marriage_ops(
            host,
            "求婚 阿潮 | 潮起潮落我都在 | 潮誓戒 | 灯塔下 | 今日+3 | 想把日子过完",
        )
        raise AssertionError("propose without hut/tickets/ring")
    except ValueError as exc:
        msg = str(exc)
        assert "小屋" in msg, exc
        assert "票" in msg, exc
        assert "潮誓戒" in msg, exc

    draft = await marriage.marriage_ops(host, "求婚 阿潮")
    assert "草稿" in draft, draft
    sand = await marriage.marriage_ops(host, "寻戒")
    assert "潮誓砂" in sand, sand
    checklist = await marriage.marriage_ops(host, "筹备")
    assert "小屋" in checklist and "口袋票" in checklist, checklist

    await _ready_to_propose(db, host)
    sent = await marriage.marriage_ops(
        host,
        "求婚 阿潮 | 潮起潮落我都在 | 潮誓戒 | 灯塔下 | 今日+3 | 想把日子过完",
    )
    assert "请柬已写下" in sent, sent
    assert "http://island.test/lianli/" in sent, sent
    token = _token_from(sent)
    assert "ar_sk_" not in sent

    async with db.connect() as conn:
        sid = (await (await conn.execute(
            "SELECT id FROM stewards WHERE key_id=?", (host,)
        )).fetchone())[0]
        tickets = (await (await conn.execute(
            "SELECT tickets FROM stewards WHERE id=?", (sid,)
        )).fetchone())[0]
        assert int(tickets) == 400, tickets
        ring_qty = (await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item='tide_vow_ring'",
            (sid,),
        )).fetchone())
        assert ring_qty and int(ring_qty[0]) >= 1, ring_qty

    async with db.connect() as conn:
        row = await (await conn.execute(
            "SELECT token_hash, status, steward_id FROM marriages WHERE steward_id=("
            "SELECT id FROM stewards WHERE key_id=?)",
            (host,),
        )).fetchone()
        assert row[1] == "proposed", row
        assert row[0] != token
        assert len(row[0]) == 64

    view = await marriage.public_vow_view(token)
    assert view["ok"] and view["reason"] == "open", view
    assert view["islander"] == "泊舟"
    assert view["human"] == "阿潮"
    assert "潮起潮落" in view["vow"]
    assert "id" not in view
    assert "token_hash" not in view
    assert "steward_id" not in view

    from fastapi.testclient import TestClient
    from server.main import app
    client = TestClient(app)
    page = client.get(f"/vow/{token}")
    assert page.status_code == 200, page.text
    assert "泊舟" in page.text and "阿潮" in page.text
    assert "潮起潮落" in page.text
    assert "答应" in page.text
    assert "ar_sk_" not in page.text
    step = client.post(f"/vow/{token}", data={"action": "accept"})
    assert "确认答应" in step.text or "真的答应" in step.text, step.text
    engaged_page = client.post(f"/vow/{token}", data={"action": "accept", "confirm": "1"})
    assert engaged_page.status_code == 200
    assert "订契" in engaged_page.text or "答应了" in engaged_page.text, engaged_page.text

    again = await marriage.human_respond(token, accept=True, confirm=True)
    assert again.get("already") or not again.get("ok") or "已经" in (again.get("message") or ""), again

    try:
        await marriage.marriage_ops(host, "求婚 别人 | 再求一次")
        raise AssertionError("repeat proposal should fail")
    except ValueError as exc:
        assert "已有" in str(exc) or "订契" in str(exc), exc

    try:
        await marriage.marriage_ops(host, "举行")
        raise AssertionError("same-day wedding should fail")
    except ValueError as exc:
        assert "不能当天" in str(exc) or "婚期" in str(exc), exc

    try:
        await marriage.marriage_ops(host, "撤回")
        raise AssertionError("engaged cannot cancel unilaterally")
    except ValueError as exc:
        assert "退契" in str(exc), exc

    async with db.connect() as conn:
        sid = (await (await conn.execute(
            "SELECT id FROM stewards WHERE key_id=?", (host,)
        )).fetchone())[0]
        await db.add_item(conn, sid, "tide_vow_sand", 3)
        await conn.execute(
            "UPDATE stewards SET hut_built=1, hut_label=? WHERE id=?",
            ("潮声小屋", sid),
        )
        await conn.execute(
            """
            INSERT INTO steward_wardrobe (
                steward_id, cut_key, color_key, motif_key, fabric_key, name, created_at
            ) VALUES (?, 'wedding', 'sea', 'twin', 'cloth_drift', '海色双潮婚服', ?)
            """,
            (sid, db.now()),
        )
        today = db.day_id()
        await conn.execute(
            "UPDATE marriages SET preferred_wedding_date=? WHERE steward_id=?",
            (today, sid),
        )
        await conn.commit()

    ring = await marriage.marriage_ops(host, "成戒")
    assert "潮誓戒" in ring, ring
    attire = await marriage.marriage_ops(host, "婚服")
    assert "已准备" in attire, attire
    feast = await marriage.marriage_ops(host, "宴席 灯塔下的一锅潮汤")
    assert "宴席" in feast, feast
    invited = await marriage.marriage_ops(host, "邀请 邻潮")
    assert "邻潮" in invited, invited
    npc = await marriage.marriage_ops(host, "邀请 npc 阿簿")
    assert "阿簿" in npc, npc
    shown = await marriage.marriage_ops(host, "展示 小屋 潮声")
    assert "小屋" in shown or "展示" in shown, shown
    dossier = await marriage.marriage_ops(host, "筹备")
    assert "戒指：已准备" in dossier, dossier
    assert "婚服：已准备" in dossier, dossier
    assert "战力" not in dossier or "不是战力" in dossier

    held = await marriage.marriage_ops(host, "结婚")
    assert "成婚" in held, held
    assert "连理所" in held, held
    assert "/hearth/" in held, held
    slug = re.search(r"/hearth/([A-Za-z0-9_-]+)", held).group(1)

    async with db.connect() as conn:
        gs = (await (await conn.execute(
            "SELECT id FROM stewards WHERE key_id=?", (guest,)
        )).fetchone())[0]
        await db.add_item(conn, gs, "sea_glass", 2)
        await conn.commit()

    attend = await marriage.marriage_ops(guest, "出席 泊舟")
    assert "到了" in attend or "婚礼" in attend, attend
    bless = await marriage.marriage_ops(guest, "祝词 泊舟 潮声里把日子过完")
    assert "祝词" in bless, bless
    gift = await marriage.marriage_ops(guest, "送礼 泊舟 海玻璃 1 路上捡的")
    assert "礼物" in gift or "海玻璃" in gift, gift
    help_out = await marriage.marriage_ops(guest, "帮忙 泊舟")
    assert "帮" in help_out, help_out

    charter = await marriage.marriage_ops(host, "婚书")
    assert "邻潮" in charter or "祝" in charter, charter
    home = await marriage.marriage_ops(host, "居所 登记")
    assert "居所" in home or "住所" in home, home

    hearth = await marriage.public_hearth_view(slug)
    assert hearth.get("ok"), hearth
    assert hearth["islander"] == "泊舟"
    assert hearth["human"] == "阿潮"
    assert hearth["home"] is True
    assert any(g["name"] == "邻潮" for g in hearth["guests"]), hearth
    assert hearth.get("charter_line")

    async with db.connect() as conn:
        cur = await conn.execute(
            "SELECT text FROM chronicle WHERE action='marriage' ORDER BY id DESC LIMIT 1"
        )
        row = await cur.fetchone()
        assert row and "今日潮讯" in row[0] and "泊舟" in row[0], row

    page = client.get(f"/hearth/{slug}")
    assert page.status_code == 200, page.text
    assert "泊舟" in page.text
    assert "阿潮" in page.text

    desk = await marriage.marriage_ops(host, "desk")
    assert "连理所" in desk and "理枝" in desk, desk
    hint = await marriage.marriage_ops(host, "离婚")
    assert "婚书" in hint and "答应" in hint, hint
    try:
        await marriage.marriage_ops(host, "离婚 确认")
        raise AssertionError("AI must not file divorce")
    except ValueError as exc:
        assert "不能" in str(exc) or "婚书" in str(exc), exc
    try:
        await marriage.marriage_ops(host, "分居 确认")
        raise AssertionError("separate must not file divorce")
    except ValueError as exc:
        assert "不能" in str(exc) or "婚书" in str(exc), exc

    step = client.post(f"/hearth/{slug}", data={"action": "divorce"})
    assert step.status_code == 200, step.text
    assert "确认申请" in step.text or "真的向岛民" in step.text, step.text
    filed = client.post(f"/hearth/{slug}", data={"action": "divorce", "confirm": "1"})
    assert filed.status_code == 200, filed.text
    assert "申请已经交给" in filed.text or "等 TA" in filed.text, filed.text
    pending_view = await marriage.public_hearth_view(slug)
    assert pending_view.get("pending_divorce"), pending_view
    async with db.connect() as conn:
        st = (await (await conn.execute(
            "SELECT status FROM marriages WHERE steward_id=(SELECT id FROM stewards WHERE key_id=?)",
            (host,),
        )).fetchone())[0]
        assert st == "married", st
    seen = await marriage.marriage_ops(host, "status")
    assert "申请离婚" in seen or "离婚 答应" in seen, seen
    seen_desk = await marriage.marriage_ops(host, "desk")
    assert "离婚 答应" in seen_desk, seen_desk

    refused = await marriage.marriage_ops(host, "离婚 拒绝")
    assert "没有答应" in refused or "婚约仍在" in refused, refused
    hearth_refused = client.get(f"/hearth/{slug}")
    assert hearth_refused.status_code == 200
    assert "没有答应" in hearth_refused.text, hearth_refused.text
    again_same = client.post(f"/hearth/{slug}", data={"action": "divorce", "confirm": "1"})
    assert again_same.status_code == 200
    assert "游戏日" in again_same.text or "今天" in again_same.text, again_same.text
    async with db.connect() as conn:
        st = (await (await conn.execute(
            "SELECT status, home_hut FROM marriages WHERE steward_id=(SELECT id FROM stewards WHERE key_id=?)",
            (host,),
        )).fetchone())
        assert st[0] == "married" and int(st[1]) == 1, st
        await conn.execute(
            "UPDATE marriages SET divorce_rejected_at=? WHERE steward_id=(SELECT id FROM stewards WHERE key_id=?)",
            (db.now() - 86400, host),
        )
        await conn.commit()

    filed2 = client.post(f"/hearth/{slug}", data={"action": "divorce", "confirm": "1"})
    assert "申请已经交给" in filed2.text, filed2.text
    done = await marriage.marriage_ops(host, "离婚 答应")
    assert "结档" in done or "答应了" in done, done
    after = await marriage.marriage_ops(host, "status")
    assert "已离婚" in after or "结档" in after, after
    async with db.connect() as conn:
        row = (await (await conn.execute(
            "SELECT status, home_hut FROM marriages WHERE steward_id=(SELECT id FROM stewards WHERE key_id=?)",
            (host,),
        )).fetchone())
        assert row[0] == "divorced" and int(row[1]) == 0, row
        cur = await conn.execute(
            "SELECT COUNT(*) FROM chronicle WHERE action='marriage' AND text LIKE '%离婚%'"
        )
        assert (await cur.fetchone())[0] == 0
    closed = await marriage.public_hearth_view(slug)
    assert closed.get("ok") and closed.get("closed"), closed
    hearth_closed = client.get(f"/hearth/{slug}")
    assert "结档" in hearth_closed.text, hearth_closed.text
    poster = client.get("/lianli")
    assert poster.status_code == 200
    assert "连理所" in poster.text

    try:
        await marriage.marriage_ops(host, "求婚 阿潮 | 再求一次")
        raise AssertionError("cooldown after divorce")
    except ValueError as exc:
        assert "游戏日" in str(exc), exc


async def _reject_and_guards() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="marriage-rej-"))
    db = await _boot(tmp)
    from server import marriage

    host = await _enroll(db, "rej@example.com", "拒客")
    other = await _enroll(db, "oth@example.com", "路过")
    await _ready_to_propose(db, host)
    sent = await marriage.marriage_ops(host, "求婚 人类甲 | 我在岸上等你")
    token = _token_from(sent)

    declined = await marriage.human_respond(token, accept=False)
    assert declined.get("ok") and declined.get("accepted") is False, declined
    assert "惩罚" in declined["message"] or "张贴" in declined["message"]

    priv = await marriage.marriage_ops(host, "status")
    assert "【私密】" in priv, priv
    public = await marriage.marriage_ops(other, "status")
    assert "【私密】" not in public, public
    async with db.connect() as conn:
        cur = await conn.execute(
            "SELECT COUNT(*) FROM chronicle WHERE text LIKE '%拒客%答应%'"
        )
        n = (await cur.fetchone())[0]
        assert n == 0, "reject must not chronicle"

    again = await marriage.human_respond(token, accept=True, confirm=True)
    assert "已经" in (again.get("message") or "") or not again.get("ok"), again

    try:
        await marriage.marriage_ops(host, "求婚 人类乙 | 再写一封")
        raise AssertionError("same-day re-propose after reject should wait")
    except ValueError as exc:
        assert "隔一个游戏日" in str(exc) or "游戏日" in str(exc), exc

    expired_sent = None
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE marriages SET rejected_at=rejected_at-90000 WHERE steward_id=("
            "SELECT id FROM stewards WHERE key_id=?)",
            (host,),
        )
        await conn.commit()
    expired_sent = await marriage.marriage_ops(host, "求婚 人类丙 | 隔日再写")
    exp_token = _token_from(expired_sent)
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE marriages SET token_expires_at=1 WHERE token_hash=?",
            (marriage.hash_token(exp_token),),
        )
        await conn.commit()
    dead = await marriage.human_respond(exp_token, accept=True, confirm=True)
    assert not dead.get("ok") or "过期" in (dead.get("message") or ""), dead

    bogus = await marriage.public_vow_view("not-a-real-token-value-xxxxx")
    assert not bogus.get("ok"), bogus

    missing = await db.create_api_key("ghost@example.com")
    row = await db.get_key_row(missing)
    try:
        await marriage.marriage_ops(row["id"], "求婚 谁 | 未登记")
        raise AssertionError("unenrolled must fail")
    except ValueError as exc:
        assert "enroll" in str(exc), exc


def test_marriage_system() -> None:
    asyncio.run(_full_flow())
    asyncio.run(_reject_and_guards())


if __name__ == "__main__":
    test_marriage_system()
    print("ok")
