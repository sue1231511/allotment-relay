#!/usr/bin/env python3
"""小橘 — 女明星：应援收件盒、打赏分账、围观开嗓门禁、粉丝团、懒结算、面板裁决。"""
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


async def test_star_flow() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="star-flow-"))
    db = await _boot(tmp)
    from server import bar, star

    kid, sid = await _enroll(db, "fan@example.com", "粉丝甲")

    # 空命令=她的档；首建行不该被懒结算伪回补
    status = await star.star_ops(kid, "")
    assert "小橘" in status and "热度" in status, status
    assert "不开嗓" in status, status
    state = await star.get_state()
    assert state["heat"] == 20, state["heat"]

    # 围观门禁：今晚没定场子 → 报错
    try:
        await star.star_ops(kid, "围观")
        raise AssertionError("watch should block when venue not set today")
    except ValueError as exc:
        assert "不开嗓" in str(exc), exc

    # 面板定今晚：酒馆开嗓
    await star.owner_set_tonight("bar", "normal", "", "三首短的", "牛仔外套", "唱给晚归的人")
    status = await star.star_ops(kid, "小橘")
    assert "开嗓" in status and "三首短的" in status, status

    # 应援进收件盒，24h 内第二条被挡
    cheer = await star.star_ops(kid, "应援 今晚的高音很稳")
    assert "卡片" in cheer or "收件盒" in cheer, cheer
    try:
        await star.star_ops(kid, "应援 再说一句")
        raise AssertionError("cheer daily should block")
    except ValueError as exc:
        assert "用过了" in str(exc), exc

    # 打赏 20：酒馆场子荔栀抽三成（int 截断），小橘实收 14，营收 +6
    async with db.connect() as conn:
        before_rev = (await (await conn.execute(
            "SELECT revenue_tickets FROM bar_daily_state WHERE day=?", (db.now() // 86400,)
        )).fetchone() or [0])[0]
    tip = await star.star_ops(kid, "打赏 20票 唱得值")
    assert "-20 票" in tip and "荔栀抽走 6" in tip, tip
    async with db.connect() as conn:
        after_rev = (await (await conn.execute(
            "SELECT revenue_tickets FROM bar_daily_state WHERE day=?", (db.now() // 86400,)
        )).fetchone() or [0])[0]
        fans_tip = (await (await conn.execute(
            "SELECT tip_total FROM star_fans WHERE steward_id=?", (sid,)
        )).fetchone() or [None])[0]
    assert after_rev - before_rev == 6, (before_rev, after_rev)
    assert fans_tip is None, "打赏不该自动入粉丝团"

    # 粉丝团入团一次，重复被挡
    join = await star.star_ops(kid, "粉丝团")
    assert "团" in join, join
    try:
        await star.star_ops(kid, "粉丝团")
        raise AssertionError("fan rejoin should block")
    except ValueError as exc:
        assert "退团" in str(exc), exc

    # 围观成功：耗精力5、听歌回神（normal=8，净+3），每日2次
    async with db.connect() as conn:
        energy_before = (await (await conn.execute(
            "SELECT energy FROM stewards WHERE id=?", (sid,)
        )).fetchone())[0]
    watch = await star.star_ops(kid, "围观")
    assert "的场" in watch and "回神" in watch, watch
    async with db.connect() as conn:
        energy_after = (await (await conn.execute(
            "SELECT energy FROM stewards WHERE id=?", (sid,)
        )).fetchone())[0]
    assert energy_after >= energy_before - 5 + 8, (energy_before, energy_after)
    await star.star_ops(kid, "围观")
    try:
        await star.star_ops(kid, "围观")
        raise AssertionError("watch daily cap should block")
    except ValueError as exc:
        assert "赖着不走" in str(exc), exc

    # 今晚嘉宾行进 bar tonight
    tonight = await bar.bar_ops(kid, "tonight")
    assert "小橘" in tonight, tonight

    # 面板裁决：应援被看到 → 热度+1、档信+1
    async with db.connect() as conn:
        prop = (await (await conn.execute(
            "SELECT id FROM star_proposals WHERE steward_id=? AND status='pending'", (sid,)
        )).fetchone())[0]
        standing_before = (await (await conn.execute(
            "SELECT standing FROM stewards WHERE id=?", (sid,)
        )).fetchone())[0]
        heat_before = (await (await conn.execute(
            "SELECT heat FROM star_state WHERE id=1"
        )).fetchone())[0]
    decide = await star.owner_decide(prop, accept=True)
    assert "读了" in decide["msg"], decide
    async with db.connect() as conn:
        heat_after = (await (await conn.execute(
            "SELECT heat FROM star_state WHERE id=1"
        )).fetchone())[0]
        standing_after = (await (await conn.execute(
            "SELECT standing FROM stewards WHERE id=?", (sid,)
        )).fetchone())[0]
    assert heat_after == heat_before + 1, (heat_before, heat_after)
    assert standing_after == standing_before + 1, (standing_before, standing_after)

    # 点歌：15 票进箱，钱归她的账
    async with db.connect() as conn:
        tips_before = (await (await conn.execute(
            "SELECT total_tips FROM star_state WHERE id=1"
        )).fetchone())[0]
    song = await star.star_ops(kid, "点歌 晚风")
    assert "15" in song and "纸条" in song, song
    async with db.connect() as conn:
        tips_after = (await (await conn.execute(
            "SELECT total_tips FROM star_state WHERE id=1"
        )).fetchone())[0]
    assert tips_after == tips_before + 15, (tips_before, tips_after)


async def test_star_stage_and_lazy_settle() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="star-stage-"))
    db = await _boot(tmp)
    from server import star

    kid, sid = await _enroll(db, "fan2@example.com", "粉丝乙")

    # 热度不够 → 专场开不了
    try:
        await star.owner_set_tonight("stage", "great", "", "", "", "")
        raise AssertionError("stage should need heat 35")
    except ValueError as exc:
        assert "压不住" in str(exc), exc

    # 手动抬到 40：专场开张，打赏全额归她（不进酒馆营收）
    async with db.connect() as conn:
        await conn.execute("UPDATE star_state SET heat=40 WHERE id=1")
        await conn.commit()
    await star.owner_set_tonight("stage", "great", "", "", "", "")
    tip = await star.star_ops(kid, "打赏 30")
    assert "荔栀抽走" not in tip and "-30 票" in tip, tip

    # 懒结算：把 last_settle_day 拨回 1 天（昨晚 stage 开嗓）→ heat +2-1 = +1
    async with db.connect() as conn:
        await conn.execute("UPDATE star_state SET last_settle_day=? WHERE id=1",
                           (db.now() // 86400 - 1,))
        await conn.commit()
        heat_before = (await (await conn.execute(
            "SELECT heat FROM star_state WHERE id=1"
        )).fetchone())[0]
    state = await star.get_state()
    assert state["heat"] == heat_before + 1, (heat_before, state["heat"])

    # 网页快照
    snap = await star.public_star_snapshot()
    assert snap["name"] == "小橘" and snap["active"] and snap["venue"] == "stage", snap
    assert snap["stage_unlocked"] and snap["stage_need"] == 0, snap

    # 发动态日上限
    await star.owner_post("今晚风大，第三首改慢一点唱。")
    for _ in range(4):
        await star.owner_post("水一水")
    try:
        await star.owner_post("第六条")
        raise AssertionError("post daily cap should block")
    except ValueError as exc:
        assert "神秘感" in str(exc), exc


def test_star_mcp_description() -> None:
    from server.mcp_app import mcp

    tool = mcp._tool_manager.get_tool("star_ops")
    blob = f"{tool.description}\n{(tool.parameters.get('properties') or {}).get('command', {}).get('description', '')}"
    assert "小橘" in blob
    assert "应援" in blob
    assert "打赏" in blob


def main() -> None:
    asyncio.run(test_star_flow())
    test_star_mcp_description()
    asyncio.run(test_star_stage_and_lazy_settle())
    print("star tests ok")


if __name__ == "__main__":
    main()
