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


async def _ready_to_propose(
    db,
    key_id: int,
    *,
    tickets: int = 250000,
    ring: bool = True,
    hut: bool = True,
    hut_level: int | None = None,
) -> None:
    from server.catalog import HUT_MAX_LEVEL

    async with db.connect() as conn:
        sid = (await (await conn.execute(
            "SELECT id FROM stewards WHERE key_id=?", (key_id,)
        )).fetchone())[0]
        if hut:
            lvl = HUT_MAX_LEVEL if hut_level is None else hut_level
            await conn.execute(
                "UPDATE stewards SET hut_built=1, hut_level=?, hut_label=? WHERE id=?",
                (lvl, "潮声小屋", sid),
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
    assert "小屋" in empty and "彩礼" in empty, empty
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
    assert "彩礼" in help_text
    assert "潮誓戒" in help_text
    assert "最高档" in help_text or "临海邸" in help_text
    assert "6" in help_text
    assert "订婚" in help_text
    assert "跳过" in help_text
    assert "寻信" in help_text
    assert "小馆" in help_text
    assert "没有彩礼" in help_text
    assert "礼金 18800" not in help_text
    assert "18800 | 8888" not in help_text
    assert "举行前还能改" in help_text
    assert "订婚宴" in help_text and "还能改" in help_text

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
        assert "彩礼" in msg, exc
        assert "潮誓戒" in msg, exc

    draft = await marriage.marriage_ops(host, "求婚 阿潮")
    assert "草稿" in draft, draft
    sand = await marriage.marriage_ops(host, "寻戒")
    assert "潮誓砂" in sand, sand
    checklist = await marriage.marriage_ops(host, "筹备")
    assert "小屋" in checklist and "彩礼" in checklist, checklist

    await _ready_to_propose(db, host, hut_level=1)
    priced = await marriage.marriage_ops(host, "彩礼 100000")
    assert "100000" in priced or "10 万" in priced, priced
    try:
        await marriage.marriage_ops(
            host,
            "求婚 阿潮 | 潮起潮落我都在 | 潮誓戒 | 灯塔下 | 今日+3 | 想把日子过完",
        )
        raise AssertionError("Lv1 hut must not send")
    except ValueError as exc:
        msg = str(exc)
        assert "最高档" in msg or "临海邸" in msg, exc
        assert "upgrade" in msg, exc
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
        assert int(tickets) == 150000, tickets
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
    assert view.get("bride_price") == 100000
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
    assert "彩礼" in page.text
    assert "答应" in page.text
    assert "ar_sk_" not in page.text
    step = client.post(f"/vow/{token}", data={"action": "accept"})
    assert "确认答应" in step.text or "真的答应" in step.text, step.text
    engaged_page = client.post(f"/vow/{token}", data={"action": "accept", "confirm": "1"})
    assert engaged_page.status_code == 200
    assert "订契" in engaged_page.text or "答应了" in engaged_page.text, engaged_page.text
    async with db.connect() as conn:
        fund = await (await conn.execute("SELECT tickets FROM tide_fund WHERE id=1")).fetchone()
        assert not fund or int(fund[0] or 0) == 0, fund
        pocket = await (await conn.execute(
            "SELECT tickets FROM stewards WHERE key_id=?", (host,)
        )).fetchone()
        assert int(pocket[0]) == 150000, pocket

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
        for item in ("gold_necklace", "gold_bracelet", "gold_earrings"):
            await db.add_item(conn, sid, item, 1)
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
    gold = await marriage.marriage_ops(host, "金饰")
    assert "三金" in gold, gold
    feast = await marriage.marriage_ops(host, "吃席 滩席")
    assert "滩席" in feast, feast
    assert "还能改" in feast, feast
    same = await marriage.marriage_ops(host, "吃席 滩席")
    assert "已经是" in same, same
    peek = await marriage.marriage_ops(host, "吃席")
    assert "还能改" in peek and "滩席" in peek, peek
    up = await marriage.marriage_ops(host, "吃席 岸席")
    assert "岸席" in up and ("改成" in up or "改" in up), up
    assert await _pocket(db, host) == 150000 - 48800
    assert await _fund(db) == 0
    down = await marriage.marriage_ops(host, "吃席 滩席")
    assert "滩席" in down, down
    assert await _pocket(db, host) == 150000 - 18800
    invited = await marriage.marriage_ops(host, "邀请 邻潮")
    assert "邻潮" in invited, invited
    npc = await marriage.marriage_ops(host, "邀请 npc 阿簿")
    assert "阿簿" in npc, npc
    await marriage.marriage_ops(host, "吃席 岸席")
    extra_npc = await marriage.marriage_ops(host, "邀请 npc 韶年")
    assert "韶年" in extra_npc, extra_npc
    try:
        await marriage.marriage_ops(host, "吃席 滩席")
        raise AssertionError("too many guests to shrink feast")
    except ValueError as extra:
        msg = str(extra)
        assert "人" in msg or "最多" in msg, extra
    shown = await marriage.marriage_ops(host, "展示 小屋 潮声")
    assert "小屋" in shown or "展示" in shown, shown
    dossier = await marriage.marriage_ops(host, "筹备")
    assert "戒指：已准备" in dossier, dossier
    assert "婚服：已准备" in dossier, dossier
    assert "订婚" in dossier and "未办" in dossier, dossier
    assert "战力" not in dossier or "不是战力" in dossier

    held = await marriage.marriage_ops(host, "结婚")
    assert "成婚" in held, held
    assert "连理所" in held, held
    assert "/hearth/" in held, held
    try:
        await marriage.marriage_ops(host, "吃席 满潮席")
        raise AssertionError("married cannot change feast")
    except ValueError as extra:
        assert "成婚" in str(extra), extra
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
    assert not hearth.get("betrothal"), hearth
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
    await marriage.marriage_ops(host, "求婚 人类甲")
    await marriage.marriage_ops(host, "彩礼 100000")
    sent = await marriage.marriage_ops(host, "求婚 人类甲 | 我在岸上等你")
    token = _token_from(sent)
    async with db.connect() as conn:
        frozen = await (await conn.execute(
            "SELECT tickets FROM stewards WHERE key_id=?", (host,)
        )).fetchone()
        assert int(frozen[0]) == 150000, frozen

    declined = await marriage.human_respond(token, accept=False)
    assert declined.get("ok") and declined.get("accepted") is False, declined
    assert "惩罚" in declined["message"] or "张贴" in declined["message"]
    async with db.connect() as conn:
        refunded = await (await conn.execute(
            "SELECT tickets FROM stewards WHERE key_id=?", (host,)
        )).fetchone()
        assert int(refunded[0]) == 250000, refunded
        fund = await (await conn.execute("SELECT tickets FROM tide_fund WHERE id=1")).fetchone()
        assert not fund or int(fund[0] or 0) == 0

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
    await marriage.marriage_ops(host, "求婚 人类丙")
    await marriage.marriage_ops(host, "彩礼 100000")
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


async def _pocket(db, key_id: int) -> int:
    async with db.connect() as conn:
        row = await (await conn.execute(
            "SELECT tickets FROM stewards WHERE key_id=?", (key_id,)
        )).fetchone()
        return int(row[0])


async def _fund(db) -> int:
    async with db.connect() as conn:
        row = await (await conn.execute("SELECT tickets FROM tide_fund WHERE id=1")).fetchone()
        return int(row[0] or 0) if row else 0


async def _betrothal_flow() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="betrothal-"))
    db = await _boot(tmp)
    from server import cloth, marriage
    from server import mcp_dispatch as mux
    from server.mcp_app import current_origin

    current_origin.set("http://island.test")
    host = await _enroll(db, "host@example.com", "泊舟")
    other = await _enroll(db, "pipe@example.com", "岸灯")

    menu = await marriage.marriage_ops(host, "订婚")
    assert "跳过" in menu, menu
    assert "海边" in menu, menu
    assert "小馆" in menu, menu
    assert "没有彩礼" in menu, menu
    assert "礼金 18800" not in menu, menu
    assert "18800 | 8888 | 12800 | 3888" not in menu, menu

    try:
        await marriage.marriage_ops(host, "订婚 寻信")
        raise AssertionError("no draft cannot seek")
    except ValueError as exc:
        msg = str(exc)
        assert "草稿" in msg, exc
        assert "订契之后" not in msg, exc

    await marriage.marriage_ops(host, "求婚 阿潮")
    try:
        await marriage.marriage_ops(host, "订婚 礼金 18800")
        raise AssertionError("gift must fail")
    except ValueError as exc:
        msg = str(exc)
        assert "没有" in msg or "彩礼" in msg, exc

    try:
        await marriage.marriage_ops(host, "订婚 彩礼")
        raise AssertionError("caili alias must fail")
    except ValueError as exc:
        msg = str(exc)
        assert "没有" in msg or "彩礼" in msg, exc

    try:
        await marriage.marriage_ops(
            host, "订婚 礼金 18800 信物 8888 宴 12800 花束 3888"
        )
        raise AssertionError("fill-six must fail")
    except ValueError as exc:
        assert "地点" in str(exc) or "不要" in str(exc), exc

    await _ready_to_propose(db, host, tickets=50000, ring=False, hut=False)
    assert await _pocket(db, host) == 50000

    async with db.connect() as conn:
        sid = (await (await conn.execute(
            "SELECT id FROM stewards WHERE key_id=?", (host,)
        )).fetchone())[0]
        import random as random_mod
        old_rand = random_mod.random
        random_mod.random = lambda: 0.0
        try:
            forage_find = await marriage.maybe_place_find(conn, sid, "forage")
            beach_find = await marriage.maybe_place_find(conn, sid, "beach")
            pastry = await marriage.maybe_jingshan_pastry(conn, sid)
        finally:
            random_mod.random = old_rand
        await conn.commit()
    assert "潮花" in forage_find, forage_find
    assert "潮信贝" in beach_find, beach_find
    assert "糕点" in pastry, pastry

    token = await marriage.marriage_ops(host, "订婚 信物")
    assert "潮信贝" in token or "信物" in token, token
    feast = await marriage.marriage_ops(host, "订婚 宴 小馆 12800")
    assert "小馆" in feast or "宴" in feast, feast
    assert "还能改" in feast, feast
    same = await marriage.marriage_ops(host, "订婚 宴 小馆 12800")
    assert "已经是" in same, same
    peek = await marriage.marriage_ops(host, "订婚 宴")
    assert "还能改" in peek, peek
    chg = await marriage.marriage_ops(host, "订婚 宴 酒吧 8888")
    assert "酒吧" in chg or "改成" in chg, chg
    assert await _pocket(db, host) == 50000 - 8888
    assert await _fund(db) == 0
    bouquet = await marriage.marriage_ops(host, "订婚 花束")
    assert "确认页" in bouquet or "/lianli/" in bouquet, bouquet
    assert "订婚记下了" not in bouquet, bouquet
    assert "大厅已通报" not in bouquet, bouquet
    again = await marriage.marriage_ops(host, "订婚")
    assert "/lianli/" in again, again
    token = _token_from(again)
    from server import lounge
    notices = await lounge.list_messages()
    hit = [m for m in notices if m.get("source") == "notice"]
    assert not hit, hit

    view = await marriage.public_vow_view(token)
    assert view.get("ok") and view.get("kind") == "betrothal", view
    assert view.get("reason") == "open", view
    first = await marriage.human_respond(token, accept=True, confirm=False)
    assert first.get("need_confirm"), first
    notices = await lounge.list_messages()
    assert not [m for m in notices if m.get("source") == "notice"]

    declined = await marriage.human_respond(token, accept=False, confirm=False)
    assert declined.get("ok") and not declined.get("accepted"), declined
    notices = await lounge.list_messages()
    assert not [m for m in notices if m.get("source") == "notice"]
    still = await marriage.marriage_ops(host, "订婚")
    assert "已经办过" not in still, still
    assert "/lianli/" in still, still

    try:
        await marriage.marriage_ops(host, "订婚 答应")
        raise AssertionError("no betrothal accept command")
    except ValueError as exc:
        assert "看不懂" in str(exc) or "答应" in str(exc), exc

    renewed = await marriage.marriage_ops(host, "订婚 续请")
    assert "/lianli/" in renewed, renewed
    token = _token_from(renewed)
    from fastapi.testclient import TestClient
    from server.main import app
    page = TestClient(app).get(f"/lianli/{token}")
    assert page.status_code == 200, page.text
    assert "订婚" in page.text
    assert "向你求婚" not in page.text
    confirm = TestClient(app).post(
        f"/lianli/{token}",
        data={"action": "accept", "confirm": "1"},
    )
    assert confirm.status_code == 200, confirm.text
    assert "订婚已记下" in confirm.text or "记下" in confirm.text

    notices = await lounge.list_messages()
    hit = [m for m in notices if m.get("source") == "notice"]
    assert hit, notices
    assert "泊舟" in hit[-1]["body"] and "订婚记下" in hit[-1]["body"], hit[-1]
    assert hit[-1]["who"] == "理枝", hit[-1]
    assert hit[-1]["kind"] == "通报", hit[-1]
    scan = await lounge.lounge_ops(host, "scan")
    assert "理枝" in scan and "订婚记下" in scan, scan
    assert "成婚潮讯" in scan, scan
    back = await marriage.marriage_ops(host, "订婚 宴 小馆 12800")
    assert "小馆" in back or "改成" in back, back
    assert await _pocket(db, host) == 50000 - 12800
    assert await _fund(db) == 0

    via = await mux.visit_bundle(host, "连理所 订婚")
    assert "办过" in via or "已经" in via, via

    bought = await cloth.cloth_ops(host, "买 订婚服 海色")
    assert "订婚服" in bought, bought
    attire = await marriage.marriage_ops(host, "订婚 服装")
    assert "记进" in attire or "订婚服" in attire, attire

    await _ready_to_propose(db, host, tickets=400000)
    await marriage.marriage_ops(host, "彩礼 100000")
    sent = await marriage.marriage_ops(
        host,
        "求婚 阿潮 | 潮起潮落我都在 | 潮誓戒 | 灯塔下 | 今日+3",
    )
    await marriage.human_respond(_token_from(sent), accept=True, confirm=True)
    assert await _pocket(db, host) == 300000
    assert await _fund(db) == 0

    photo = await marriage.marriage_ops(host, "订婚 留影 小屋 2888")
    assert "留影" in photo or "记下" in photo, photo

    await marriage.marriage_ops(other, "求婚 灯花")
    try:
        await marriage.marriage_ops(
            other, "订婚 18800 | 8888 | 12800 | 3888 | 8888 | 2888"
        )
        raise AssertionError("pipe fill must fail")
    except ValueError as exc:
        assert "地点" in str(exc) or "不要" in str(exc), exc

    async with db.connect() as conn:
        sid = (await (await conn.execute(
            "SELECT id FROM stewards WHERE key_id=?", (host,)
        )).fetchone())[0]
        for item in ("gold_necklace", "gold_bracelet", "gold_earrings"):
            await db.add_item(conn, sid, item, 1)
        await conn.execute(
            """
            INSERT INTO steward_wardrobe (
                steward_id, cut_key, color_key, motif_key, fabric_key, name, created_at
            ) VALUES (?, 'wedding', 'sea', 'twin', 'cloth_drift', '海色双潮婚服', ?)
            """,
            (sid, db.now()),
        )
        await conn.execute(
            "UPDATE marriages SET preferred_wedding_date=? WHERE steward_id=?",
            (db.day_id(), sid),
        )
        await conn.commit()
    await marriage.marriage_ops(host, "婚服")
    await marriage.marriage_ops(host, "金饰")
    await marriage.marriage_ops(host, "吃席 滩席")
    held = await marriage.marriage_ops(host, "结婚")
    assert "成婚" in held, held
    slug = re.search(r"/hearth/([A-Za-z0-9_-]+)", held).group(1)
    hearth = await marriage.public_hearth_view(slug)
    assert hearth.get("betrothal"), hearth
    assert "信物" in hearth["betrothal"] or "宴" in hearth["betrothal"], hearth
    assert "旧礼金" not in hearth["betrothal"], hearth
    from fastapi.testclient import TestClient
    from server.main import app
    page = TestClient(app).get(f"/hearth/{slug}")
    assert page.status_code == 200, page.text
    assert "订婚" in page.text
    assert "旧礼金" not in page.text


async def _highest_photo_flow() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="photo-high-"))
    db = await _boot(tmp)
    from server import marriage

    host = await _enroll(db, "photo@example.com", "灯影")
    await _ready_to_propose(db, host, tickets=20000, ring=False, hut=True)
    await marriage.marriage_ops(host, "求婚 阿潮")

    async with db.connect() as conn:
        sid = (await (await conn.execute(
            "SELECT id FROM stewards WHERE key_id=?", (host,)
        )).fetchone())[0]
        n = await (await conn.execute(
            "SELECT COUNT(*) FROM npc_visits WHERE steward_id=? AND npc_key='buxing'",
            (sid,),
        )).fetchone()
        assert int(n[0] or 0) == 0

    try:
        await marriage.marriage_ops(host, "订婚 留影 灯塔席")
        raise AssertionError("feast mixup must fail")
    except ValueError as exc:
        assert "吃席" in str(exc), exc

    photo = await marriage.marriage_ops(host, "订婚 留影 灯塔")
    assert "灯塔" in photo, photo
    assert "8888" in photo or "8,888" in photo or "八" in photo or "记下" in photo, photo
    assert await _pocket(db, host) == 20000 - 8888
    assert await _fund(db) == 0

    async with db.connect() as conn:
        n = await (await conn.execute(
            "SELECT COUNT(*) FROM npc_visits WHERE steward_id=? AND npc_key='buxing'",
            (sid,),
        )).fetchone()
        assert int(n[0] or 0) >= 1, "lighthouse photo should count as a visit"

    same = await marriage.marriage_ops(host, "订婚 留影 灯塔 8888")
    assert "已经是" in same, same
    assert await _pocket(db, host) == 20000 - 8888

    try:
        await marriage.marriage_ops(host, "订婚 留影 海边")
        raise AssertionError("beach without activity must fail")
    except ValueError as exc:
        assert "寻信" in str(exc) or "采花" in str(exc) or "赶海" in str(exc), exc

    chg = await marriage.marriage_ops(host, "订婚 留影 小屋")
    assert "小屋" in chg, chg
    assert await _pocket(db, host) == 20000 - 1888
    assert await _fund(db) == 0

    back = await marriage.marriage_ops(host, "订婚 留影 最高")
    assert "灯塔" in back, back
    assert await _pocket(db, host) == 20000 - 8888

    async with db.connect() as conn:
        await conn.execute(
            "UPDATE marriages SET status=? WHERE steward_id=?",
            (marriage.STATUS_MARRIED, sid),
        )
        await conn.commit()
    try:
        await marriage.marriage_ops(host, "订婚 留影 灯塔 8888")
        raise AssertionError("married cannot change photo")
    except ValueError as exc:
        assert "成婚" in str(exc), exc


async def _old_db_migrates_betrothal_confirm() -> None:
    """线上旧库没有 betrothal_confirm_* 列；init_db 必须 ALTER，不能在 SCHEMA 里先建索引。"""
    import sqlite3

    tmp = Path(tempfile.mkdtemp(prefix="marriage-migrate-"))
    db_path = tmp / "relay.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE marriages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            steward_id INTEGER NOT NULL,
            partner_type TEXT NOT NULL DEFAULT 'human',
            partner_name TEXT NOT NULL,
            status TEXT NOT NULL,
            proposal_text TEXT NOT NULL DEFAULT '',
            proposal_item TEXT NOT NULL DEFAULT '',
            proposal_location TEXT NOT NULL DEFAULT '',
            preferred_wedding_date INTEGER,
            note TEXT NOT NULL DEFAULT '',
            token_hash TEXT,
            token_expires_at INTEGER,
            token_used_at INTEGER,
            confirmed_at INTEGER,
            rejected_at INTEGER,
            reject_seen INTEGER NOT NULL DEFAULT 0,
            wedding_at INTEGER,
            wedding_location TEXT NOT NULL DEFAULT '',
            vow_ai TEXT NOT NULL DEFAULT '',
            vow_human TEXT NOT NULL DEFAULT '',
            ring_ready INTEGER NOT NULL DEFAULT 0,
            attire_ready INTEGER NOT NULL DEFAULT 0,
            feast_note TEXT NOT NULL DEFAULT '',
            home_hut INTEGER NOT NULL DEFAULT 0,
            public_slug TEXT,
            charter_json TEXT NOT NULL DEFAULT '',
            filing_kind TEXT NOT NULL DEFAULT '',
            private_notice TEXT NOT NULL DEFAULT '',
            human_notice TEXT NOT NULL DEFAULT '',
            divorce_rejected_at INTEGER,
            bride_price INTEGER NOT NULL DEFAULT 0,
            bride_frozen INTEGER NOT NULL DEFAULT 0,
            gold_three INTEGER NOT NULL DEFAULT 0,
            gold_five INTEGER NOT NULL DEFAULT 0,
            feast_tier TEXT NOT NULL DEFAULT '',
            feast_ready INTEGER NOT NULL DEFAULT 0,
            attire_source TEXT NOT NULL DEFAULT '',
            betrothal_done INTEGER NOT NULL DEFAULT 0,
            betrothal_gift INTEGER NOT NULL DEFAULT 0,
            betrothal_token INTEGER NOT NULL DEFAULT 0,
            betrothal_feast INTEGER NOT NULL DEFAULT 0,
            betrothal_bouquet INTEGER NOT NULL DEFAULT 0,
            betrothal_attire INTEGER NOT NULL DEFAULT 0,
            betrothal_photo INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """
    )
    now = 1_700_000_000
    for sid, status, name in (
        (1, "draft", "阿草稿"),
        (2, "proposed", "阿请柬"),
        (3, "engaged", "阿订契"),
        (4, "married", "阿成婚"),
    ):
        conn.execute(
            """
            INSERT INTO marriages (
                steward_id, partner_type, partner_name, status, betrothal_done,
                created_at, updated_at
            ) VALUES (?, 'human', ?, ?, 1, ?, ?)
            """,
            (sid, name, status, now, now),
        )
    conn.commit()
    conn.close()

    os.environ["DATA_DIR"] = str(tmp)
    from server import config, db

    config.DATA_DIR = tmp
    config.DB_PATH = db_path
    db.DATA_DIR = tmp
    db.DB_PATH = db_path
    await db.init_db()
    async with db.connect() as c:
        cur = await c.execute("PRAGMA table_info(marriages)")
        cols = {row[1] for row in await cur.fetchall()}
        assert "betrothal_confirm_hash" in cols, cols
        assert "betrothal_confirm_expires_at" in cols, cols
        assert "betrothal_confirm_used_at" in cols, cols
        await c.execute("SELECT betrothal_confirm_hash FROM marriages")
        idx = await (
            await c.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
                ("idx_marriages_betrothal_confirm_hash",),
            )
        ).fetchone()
        assert idx, "unique index should exist after ALTER"
        cur = await c.execute(
            "SELECT partner_name, status, betrothal_done, betrothal_confirm_used_at "
            "FROM marriages ORDER BY id"
        )
        got = [(r[0], r[1], int(r[2] or 0), r[3]) for r in await cur.fetchall()]
        assert got == [
            ("阿草稿", "draft", 0, None),
            ("阿请柬", "proposed", 0, None),
            ("阿订契", "engaged", 0, None),
            ("阿成婚", "married", 1, None),
        ], got


async def _legacy_auto_seal_not_confirmed() -> None:
    """#113 旧档三件齐了就写下 betrothal_done；没点确认页不算订婚，空 订婚 必须再给链接。"""
    tmp = Path(tempfile.mkdtemp(prefix="betrothal-legacy-"))
    db = await _boot(tmp)
    from server import marriage
    from server.mcp_app import current_origin

    current_origin.set("http://island.test")
    host = await _enroll(db, "legacy@example.com", "旧档")
    await _ready_to_propose(db, host, tickets=50000, ring=False, hut=False)
    await marriage.marriage_ops(host, "求婚 阿潮")
    async with db.connect() as conn:
        sid = (await (await conn.execute(
            "SELECT id FROM stewards WHERE key_id=?", (host,)
        )).fetchone())[0]
        await conn.execute(
            """
            UPDATE marriages SET betrothal_token=8888, betrothal_feast=12800,
                betrothal_bouquet=3888, betrothal_done=1,
                betrothal_confirm_hash=NULL, betrothal_confirm_expires_at=NULL,
                betrothal_confirm_used_at=NULL
            WHERE steward_id=?
            """,
            (sid,),
        )
        await conn.commit()
    empty = await marriage.marriage_ops(host, "订婚")
    assert "已经办过" not in empty, empty
    assert "/lianli/" in empty, empty
    token = _token_from(empty)
    view = await marriage.public_vow_view(token)
    assert view.get("ok") and view.get("reason") == "open", view
    assert not int(view.get("betrothal_done") or 0), view
    from fastapi.testclient import TestClient
    from server.main import app
    page = TestClient(app).get(f"/lianli/{token}")
    assert page.status_code == 200, page.text
    assert "订婚已经记下了" not in page.text, page.text
    assert "想把订婚记进" in page.text, page.text
    first = await marriage.human_respond(token, accept=True, confirm=False)
    assert first.get("need_confirm"), first
    from server import lounge
    notices = await lounge.list_messages()
    assert not [m for m in notices if m.get("source") == "notice"], notices
    done = await marriage.human_respond(token, accept=True, confirm=True)
    assert done.get("accepted"), done
    notices = await lounge.list_messages()
    hit = [m for m in notices if m.get("source") == "notice"]
    assert hit, notices
    assert "旧档" in hit[-1]["body"] and "订婚记下" in hit[-1]["body"], hit[-1]
    sealed = await marriage.marriage_ops(host, "订婚")
    assert "已经办过" in sealed or "已办" in sealed, sealed
    assert "/lianli/" not in sealed, sealed


def test_marriage_system() -> None:
    asyncio.run(_full_flow())
    asyncio.run(_betrothal_flow())
    asyncio.run(_highest_photo_flow())
    asyncio.run(_reject_and_guards())
    asyncio.run(_old_db_migrates_betrothal_confirm())
    asyncio.run(_legacy_auto_seal_not_confirmed())


if __name__ == "__main__":
    test_marriage_system()
    print("ok")
