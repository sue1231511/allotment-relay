#!/usr/bin/env python3
"""考勤逾期：手册放行的诊所与只读入口仍开；份地仍锁。"""
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
        await conn.execute("UPDATE stewards SET last_bar_shift_at=1, tickets=400 WHERE id=?", (sid,))
        await conn.commit()
    return row["id"], sid


def _locked(exc: BaseException) -> bool:
    text = str(exc)
    return "上工" in text or "打卡" in text or "考勤" in text


async def _run() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="duty-read-"))
    db = await _boot(tmp)
    from server import clinic, hut, mcp_dispatch as mux, npc, story, tale
    from server import game

    kid, _sid = await _enroll(db, "duty-read@example.com", "逾期客")

    listed = await mux.visit_bundle(kid, "list")
    assert "桥桥" in listed or "qiaoqiao" in listed or "诊所" in listed, listed

    clinic_txt = await mux.visit_bundle(kid, "clinic")
    assert "诊所" in clinic_txt or "桥桥" in clinic_txt, clinic_txt
    assert not _locked(ValueError(clinic_txt))

    visit_qiao = await npc.npc_ops(kid, "visit 桥桥")
    assert "诊所" in visit_qiao or "桥桥" in visit_qiao, visit_qiao
    visit_clinic = await mux.visit_bundle(kid, "桥桥")
    assert "诊所" in visit_clinic or "桥桥" in visit_clinic, visit_clinic

    hut_txt = await hut.hut_ops(kid, "status")
    assert hut_txt and not _locked(ValueError(hut_txt)), hut_txt

    tale_txt = await tale.tale_ops(kid, "list")
    assert tale_txt and ("tale_ops" in tale_txt or "潮闻" in tale_txt or "accept" in tale_txt), tale_txt

    story_txt = await story.story_ops(kid, "list")
    assert "灰姑娘" in story_txt or "cinderella" in story_txt, story_txt

    league = await mux.alliance_bundle(kid, "league status")
    assert "周" in league or "目标" in league or "联盟" in league, league

    try:
        await game.plot_ops(kid, "status")
        raise AssertionError("overdue should still lock plot status")
    except ValueError as exc:
        assert _locked(exc), exc

    try:
        await game.tote_ops(kid, "list")
        raise AssertionError("overdue should still lock tote")
    except ValueError as exc:
        assert _locked(exc), exc

    direct = await clinic.clinic_ops(kid, "status")
    assert "诊所" in direct or "桥桥" in direct, direct


def test_duty_read_exempt() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    test_duty_read_exempt()
    print("ok")
