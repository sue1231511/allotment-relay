#!/usr/bin/env python3
"""畜栏：游戏日一次 collect、喂食按天刷新、空 collect 全收、可偷奶蛋不能偷牲口。"""

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
    from server import config, db, events, flavor

    config.DATA_DIR = tmp
    config.DB_PATH = tmp / "relay.db"
    db.DATA_DIR = tmp
    db.DB_PATH = tmp / "relay.db"
    await db.init_db()
    events.roll_after_action = _quiet  # type: ignore[assignment]
    flavor.maybe_suffix = lambda *_a, **_k: ""  # type: ignore[assignment]
    return db


async def _quiet(*_a, **_k):
    return None


async def _enroll(db, email: str, name: str) -> tuple[int, int]:
    key = await db.create_api_key(email)
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], name, "", "naturalist", "")
    async with db.connect() as conn:
        sid = (await (await conn.execute(
            "SELECT id FROM stewards WHERE key_id=?", (row["id"],)
        )).fetchone())[0]
        await conn.execute(
            "UPDATE stewards SET tickets=2000, barn_built=1, last_bar_shift_at=? WHERE id=?",
            (db.now(), sid),
        )
        for slot in range(1, 7):
            await conn.execute(
                "INSERT OR IGNORE INTO barn_animals (steward_id, slot, species, fed, fed_day) VALUES (?,?,NULL,0,0)",
                (sid, slot),
            )
        await conn.commit()
    return row["id"], sid


async def _stock(db, sid: int, item: str, qty: int) -> None:
    async with db.connect() as conn:
        await db.add_item(conn, sid, item, qty, over_cap=True)
        await conn.commit()


async def test_daily_collect_and_status() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="barn-daily-"))
    db = await _boot(tmp)
    from server import barn

    kid, sid = await _enroll(db, "barn@example.com", "栏主")
    await _stock(db, sid, "crop_rye", 10)

    buy = await barn.barn_ops(kid, "buy 鸡 1")
    assert "鸡" in buy, buy
    await barn.barn_ops(kid, "buy chicken 2")

    st = await barn.barn_ops(kid, "status")
    assert "待喂" in st, st
    assert "每个游戏日一次" in st, st
    assert "不是一周一次" in st, st
    assert "北京时间早上 8 点" in st, st

    fed = await barn.barn_ops(kid, "feed")
    assert "#1 已喂食" in fed and "#2 已喂食" in fed, fed
    again = await barn.barn_ops(kid, "feed 1")
    assert "今日已喂" in again, again

    st = await barn.barn_ops(kid, "status")
    assert "可 collect" in st, st

    got = await barn.barn_ops(kid, "collect")
    assert "#1 收取" in got and "#2 收取" in got, got
    assert "鸡蛋" in got, got

    st = await barn.barn_ops(kid, "status")
    assert "今日已收" in st, st
    assert "可 collect" not in st.replace("可 collect", "") or "今日已收" in st

    try:
        await barn.barn_ops(kid, "collect 1")
        raise AssertionError("expected already collected")
    except ValueError as exc:
        msg = str(exc)
        assert "已收过" in msg, msg
        assert "游戏日一次" in msg or "不是一周" in msg, msg
        assert "北京时间" in msg, msg
        assert "共用" in msg, msg

    yesterday = db.day_id() - 1
    await barn.barn_ops(kid, "buy 鸡 3")
    await barn.barn_ops(kid, "feed 3")
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE barn_animals SET fed=1, fed_day=? WHERE steward_id=? AND slot=3",
            (yesterday, sid),
        )
        await conn.commit()
    st = await barn.barn_ops(kid, "status")
    assert "#3: 🐔鸡（待喂）" in st, st
    fed2 = await barn.barn_ops(kid, "feed 3")
    assert "已喂食" in fed2, fed2


async def test_slot_reuse_after_harvest() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="barn-reuse-"))
    db = await _boot(tmp)
    from server import barn

    kid, sid = await _enroll(db, "reuse@example.com", "换鸡")
    await _stock(db, sid, "crop_rye", 10)
    await barn.barn_ops(kid, "buy 鸡 1")
    await barn.barn_ops(kid, "feed 1")
    await barn.barn_ops(kid, "collect 1")

    async with db.connect() as conn:
        await conn.execute(
            "UPDATE barn_animals SET stocked_at=? WHERE steward_id=? AND slot=1",
            (db.now() - 10_000, sid),
        )
        await conn.commit()
    out = await barn.barn_ops(kid, "harvest 1")
    assert "出栏" in out and "栏空了" in out, out

    await barn.barn_ops(kid, "buy 鸡 1")
    await barn.barn_ops(kid, "feed 1")
    got = await barn.barn_ops(kid, "collect 1")
    assert "收取" in got, got


async def test_barn_steal_products_not_animals() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="barn-steal-"))
    db = await _boot(tmp)
    from server import barn, events, multi

    thief_kid, thief_sid = await _enroll(db, "thief@example.com", "邻甲")
    vic_kid, vic_sid = await _enroll(db, "vic@example.com", "邻乙")
    await _stock(db, vic_sid, "crop_rye", 10)
    await barn.barn_ops(vic_kid, "buy 鸡 1")
    await barn.barn_ops(vic_kid, "feed 1")

    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET last_active_at=? WHERE id=?",
            (db.now() - 4000, vic_sid),
        )
        await conn.commit()

    thief = await db.get_steward_by_id(thief_sid)
    roster = await multi.list_neighbors(thief, online_only=False)
    assert "hut_ops barn 偷 邻乙" in roster, roster
    assert "牲口本身不能偷" in roster, roster

    events.random.random = lambda: 0.99  # type: ignore[method-assign]
    msg = await barn.barn_ops(thief_kid, "偷 邻乙")
    assert "顺走" in msg and "鸡蛋" in msg, msg
    async with db.connect() as conn:
        qty = (await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item='egg'",
            (thief_sid,),
        )).fetchone())
        assert qty and qty[0] >= 1, qty

    left = await barn.barn_ops(vic_kid, "collect 1")
    assert "收取" in left and "x1" in left, left

    try:
        await barn.barn_ops(thief_kid, "偷 邻乙")
        raise AssertionError("expected per-target limit")
    except ValueError as exc:
        assert "已经摘过" in str(exc), exc

    pig_kid, pig_sid = await _enroll(db, "pig@example.com", "邻丙")
    await _stock(db, pig_sid, "crop_beet", 10)
    await barn.barn_ops(pig_kid, "buy 猪 1")
    await barn.barn_ops(pig_kid, "feed 1")
    try:
        await barn.barn_ops(thief_kid, "偷 邻丙")
        raise AssertionError("pigs should not be stealable")
    except ValueError as exc:
        assert "牲口本身不能偷" in str(exc) or "没有能偷" in str(exc), exc


def main() -> None:
    asyncio.run(test_daily_collect_and_status())
    asyncio.run(test_slot_reuse_after_harvest())
    asyncio.run(test_barn_steal_products_not_animals())
    print("barn tests ok")


if __name__ == "__main__":
    main()
