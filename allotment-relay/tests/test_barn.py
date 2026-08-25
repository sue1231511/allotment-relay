#!/usr/bin/env python3
"""畜栏：游戏日一次日收、空 collect 全栏、可偷蛋奶不能偷活畜。"""
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


async def _enroll(db, email: str, name: str, *, tickets: int = 800) -> tuple[int, int]:
    key = await db.create_api_key(email)
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], name, "", "naturalist", "")
    async with db.connect() as conn:
        sid = (await (await conn.execute(
            "SELECT id FROM stewards WHERE key_id=?", (row["id"],)
        )).fetchone())[0]
        await conn.execute(
            "UPDATE stewards SET tickets=?, barn_built=0, last_active_at=? WHERE id=?",
            (tickets, db.now() - 4000, sid),
        )
        await conn.commit()
    return row["id"], sid


async def _stock(db, sid: int, slot: int, species: str, *, fed_today: bool = True) -> None:
    day = db.day_id()
    async with db.connect() as conn:
        await conn.execute(
            "INSERT OR IGNORE INTO barn_animals (steward_id, slot, species, fed) VALUES (?,?,NULL,0)",
            (sid, slot),
        )
        await conn.execute(
            """
            UPDATE barn_animals
            SET species=?, stocked_at=?, fed=?, fed_day=?, guard=0
            WHERE steward_id=? AND slot=?
            """,
            (species, db.now() - 60, 1 if fed_today else 0, day if fed_today else 0, sid, slot),
        )
        await conn.commit()


async def _qty(db, sid: int, item: str) -> int:
    async with db.connect() as conn:
        row = await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item=?",
            (sid, item),
        )).fetchone()
    return int(row[0]) if row else 0


async def test_daily_collect_all_slots_not_just_one() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="barn-collect-"))
    db = await _boot(tmp)
    from server import barn, flavor

    flavor.maybe_suffix = lambda *_a, **_k: ""  # type: ignore[assignment]
    kid, sid = await _enroll(db, "c@example.com", "饲手甲")
    await barn.barn_ops(kid, "erect")
    await _stock(db, sid, 1, "chicken")
    await _stock(db, sid, 2, "cow")

    first = await barn.barn_ops(kid, "collect")
    assert "鸡蛋" in first and "牛奶" in first, first
    assert await _qty(db, sid, "egg") == 2
    assert await _qty(db, sid, "milk") == 2

    again = await barn.barn_ops(kid, "collect")
    assert "没有还能收" in again or "今日已收" in again, again
    assert "游戏日" in again or "北京" in again, again

    st = await barn.barn_ops(kid, "status")
    assert "今日已收" in st, st
    assert "不是一周一次" in st, st
    assert "北京 08:00" in st, st


async def test_empty_collect_does_not_stick_on_slot_one() -> None:
    """以前空 collect 只收 #1，#1 收过就报今日已收过，其它栏还挂着。"""
    tmp = Path(tempfile.mkdtemp(prefix="barn-slot1-"))
    db = await _boot(tmp)
    from server import barn, flavor

    flavor.maybe_suffix = lambda *_a, **_k: ""  # type: ignore[assignment]
    kid, sid = await _enroll(db, "s1@example.com", "只收一栏")
    await barn.barn_ops(kid, "erect")
    await _stock(db, sid, 1, "chicken")
    await _stock(db, sid, 2, "cow")
    only = await barn.barn_ops(kid, "collect 1")
    assert "鸡蛋" in only, only
    rest = await barn.barn_ops(kid, "collect")
    assert "牛奶" in rest, rest
    assert await _qty(db, sid, "milk") == 2


async def test_feed_is_per_game_day() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="barn-feed-"))
    db = await _boot(tmp)
    from server import barn, flavor

    flavor.maybe_suffix = lambda *_a, **_k: ""  # type: ignore[assignment]
    kid, sid = await _enroll(db, "f@example.com", "饲手乙")
    await barn.barn_ops(kid, "erect")
    await _stock(db, sid, 1, "chicken", fed_today=False)
    async with db.connect() as conn:
        await db.add_item(conn, sid, "crop_rye", 4)
        await conn.commit()

    fed = await barn.barn_ops(kid, "feed")
    assert "已喂" in fed, fed
    again = await barn.barn_ops(kid, "feed 1")
    assert "今日已喂" in again, again

    try:
        await barn.barn_ops(kid, "collect 1")
    except Exception as exc:  # noqa: BLE001
        raise AssertionError(f"fed today should collect: {exc}") from exc


async def test_barn_steal_products_not_animals() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="barn-steal-"))
    db = await _boot(tmp)
    from server import barn, flavor, game

    flavor.maybe_suffix = lambda *_a, **_k: ""  # type: ignore[assignment]
    barn.random.random = lambda: 0.99  # type: ignore[method-assign]

    thief_kid, thief_sid = await _enroll(db, "thief@example.com", "栏贼")
    vic_kid, vic_sid = await _enroll(db, "vic@example.com", "栏主")
    await barn.barn_ops(vic_kid, "erect")
    await _stock(db, vic_sid, 1, "chicken")
    await _stock(db, vic_sid, 2, "rabbit")

    thief = await db.get_steward_by_id(thief_sid)
    msg = await barn.barn_steal(thief, "栏主")
    assert "鸡蛋" in msg and "x1" in msg, msg
    assert await _qty(db, thief_sid, "egg") == 1
    assert await _qty(db, thief_sid, "meat_rabbit") == 0

    leftover = await barn.barn_ops(vic_kid, "collect 1")
    assert "剩下" in leftover or "偷过" in leftover, leftover
    assert await _qty(db, vic_sid, "egg") == 1

    st = await barn.barn_ops(vic_kid, "status")
    assert "今日已收" in st, st

    try:
        await barn.barn_ops(vic_kid, "collect 2")
        raise AssertionError("rabbit should not daily-collect")
    except ValueError as exc:
        assert "harvest" in str(exc) or "出栏" in str(exc), exc

    alias = await game.plot_ops(thief_kid, "偷畜 栏主")
    assert "已经摘过" in alias or "一次" in alias, alias


async def test_cannot_steal_after_owner_collect() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="barn-gone-"))
    db = await _boot(tmp)
    from server import barn, flavor

    flavor.maybe_suffix = lambda *_a, **_k: ""  # type: ignore[assignment]
    barn.random.random = lambda: 0.99  # type: ignore[method-assign]

    thief_kid, thief_sid = await _enroll(db, "t2@example.com", "晚来")
    vic_kid, vic_sid = await _enroll(db, "v2@example.com", "早收")
    await barn.barn_ops(vic_kid, "erect")
    await _stock(db, vic_sid, 1, "chicken")
    await barn.barn_ops(vic_kid, "collect")

    thief = await db.get_steward_by_id(thief_sid)
    try:
        await barn.barn_steal(thief, "早收")
        raise AssertionError("already collected eggs should not be stealable")
    except ValueError as exc:
        assert "活畜偷不走" in str(exc) or "没有未收" in str(exc), exc


async def test_buy_chinese_name() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="barn-buy-"))
    db = await _boot(tmp)
    from server import barn
    from server.catalog import resolve_livestock

    assert resolve_livestock("鸡") == "chicken"
    assert resolve_livestock("山羊") == "goat"
    assert resolve_livestock("羊") == "sheep"

    kid, _sid = await _enroll(db, "b@example.com", "买鸡人")
    await barn.barn_ops(kid, "erect")
    msg = await barn.barn_ops(kid, "buy 鸡 1")
    assert "鸡" in msg, msg


def main() -> None:
    asyncio.run(test_daily_collect_all_slots_not_just_one())
    asyncio.run(test_empty_collect_does_not_stick_on_slot_one())
    asyncio.run(test_feed_is_per_game_day())
    asyncio.run(test_barn_steal_products_not_animals())
    asyncio.run(test_cannot_steal_after_owner_collect())
    asyncio.run(test_buy_chinese_name())
    print("barn collect/steal tests ok")


if __name__ == "__main__":
    main()
