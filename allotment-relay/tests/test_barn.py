#!/usr/bin/env python3
"""畜栏：每天一次收蛋奶，不是一周；空 collect 全收；可偷产物不可偷活畜。"""
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
        await conn.execute(
            "UPDATE stewards SET hut_built=1, hut_level=2, tickets=2000, barn_built=1 WHERE id=?",
            (sid,),
        )
        for slot in range(1, 7):
            await conn.execute(
                "INSERT OR IGNORE INTO barn_animals (steward_id, slot, species, fed) VALUES (?,?,NULL,0)",
                (sid, slot),
            )
        await conn.commit()
    return row["id"], sid


async def _stock(db, sid: int, slot: int, species: str, *, fed_today: bool = False) -> None:
    from server.barn import _day_id

    async with db.connect() as conn:
        await conn.execute(
            """
            UPDATE barn_animals SET species=?, stocked_at=?, fed=?, guard=?
            WHERE steward_id=? AND slot=?
            """,
            (
                species,
                db.now(),
                _day_id() if fed_today else 0,
                1 if species == "dog" else 0,
                sid,
                slot,
            ),
        )
        await db.add_item(conn, sid, "crop_rye", 12)
        await db.add_item(conn, sid, "crop_sweetpotato", 6)
        await db.add_item(conn, sid, "crop_kale", 6)
        await db.add_item(conn, sid, "crop_blueberry", 4)
        await db.add_item(conn, sid, "feed_animal", 8)
        await conn.commit()


async def _qty(db, sid: int, item: str) -> int:
    async with db.connect() as conn:
        row = await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item=?",
            (sid, item),
        )).fetchone()
    return int(row[0]) if row else 0


async def test_barn_daily_collect_not_weekly() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="barn-daily-"))
    db = await _boot(tmp)
    from server import barn

    kid, sid = await _enroll(db, "daily@example.com", "收蛋人")
    await _stock(db, sid, 1, "chicken")
    await _stock(db, sid, 2, "chicken")

    fed = await barn.barn_ops(kid, "feed")
    assert "已喂食" in fed, fed
    first = await barn.barn_ops(kid, "collect")
    assert "#1 收取" in first and "#2 收取" in first, first
    assert await _qty(db, sid, "egg") >= 4

    status = await barn.barn_ops(kid, "status")
    assert "今日已收" in status, status
    assert "不是一周一次" in status, status

    try:
        await barn.barn_ops(kid, "collect")
        raise AssertionError("second collect same day should fail")
    except ValueError as exc:
        msg = str(exc)
        assert "已收过" in msg, msg
        assert "换班" in msg, msg

    try:
        await barn.barn_ops(kid, "collect 1")
        raise AssertionError("slot 1 already collected")
    except ValueError as exc:
        assert "今日已收过" in str(exc), str(exc)


async def test_barn_collect_all_skips_done_slot() -> None:
    """旧 bug：空 collect 只收 1 号，再收就报今日已收过，2 号其实没收。"""
    tmp = Path(tempfile.mkdtemp(prefix="barn-slots-"))
    db = await _boot(tmp)
    from server import barn

    kid, sid = await _enroll(db, "slots@example.com", "两槽")
    await _stock(db, sid, 1, "chicken")
    await _stock(db, sid, 2, "chicken")
    await barn.barn_ops(kid, "feed")
    one = await barn.barn_ops(kid, "collect 1")
    assert "#1 收取" in one, one
    rest = await barn.barn_ops(kid, "collect")
    assert "#2 收取" in rest, rest
    assert "#1" not in rest, rest


async def test_barn_feed_resets_each_game_day() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="barn-feed-"))
    db = await _boot(tmp)
    from server import barn
    from server.barn import _day_id

    kid, sid = await _enroll(db, "feed@example.com", "喂鸡")
    await _stock(db, sid, 1, "chicken")
    await barn.barn_ops(kid, "feed 1")
    again = await barn.barn_ops(kid, "feed 1")
    assert "今日已喂" in again, again

    async with db.connect() as conn:
        await conn.execute(
            "UPDATE barn_animals SET fed=? WHERE steward_id=? AND slot=1",
            (_day_id() - 1, sid),
        )
        await conn.execute(
            "DELETE FROM barn_daily_collect WHERE steward_id=?",
            (sid,),
        )
        await conn.commit()

    status = await barn.barn_ops(kid, "status")
    assert "待喂" in status, status
    try:
        await barn.barn_ops(kid, "collect 1")
        raise AssertionError("collect without feeding today should fail")
    except ValueError as exc:
        assert "还没喂" in str(exc), str(exc)

    fed = await barn.barn_ops(kid, "feed 1")
    assert "已喂食" in fed, fed
    got = await barn.barn_ops(kid, "collect 1")
    assert "收取" in got, got


async def test_barn_old_fed_flag_is_not_today() -> None:
    """旧存档 fed=1 不再被当成「今日已喂」。"""
    tmp = Path(tempfile.mkdtemp(prefix="barn-oldfed-"))
    db = await _boot(tmp)
    from server import barn

    kid, sid = await _enroll(db, "oldfed@example.com", "旧喂")
    await _stock(db, sid, 1, "chicken")
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE barn_animals SET fed=1 WHERE steward_id=? AND slot=1",
            (sid,),
        )
        await conn.commit()
    status = await barn.barn_ops(kid, "status")
    assert "待喂" in status, status
    fed = await barn.barn_ops(kid, "feed 1")
    assert "已喂食" in fed, fed


async def test_barn_harvest_is_not_daily_collect() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="barn-hv-"))
    db = await _boot(tmp)
    from server import barn

    kid, sid = await _enroll(db, "hv@example.com", "出栏")
    await _stock(db, sid, 1, "chicken", fed_today=True)
    try:
        await barn.barn_ops(kid, "harvest 1")
        raise AssertionError("fresh chicken should not slaughter")
    except ValueError as exc:
        msg = str(exc)
        assert "collect" in msg and "出栏" in msg, msg


async def test_barn_steal_products_not_animals() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="barn-steal-"))
    db = await _boot(tmp)
    from server import barn, events

    thief_kid, thief_sid = await _enroll(db, "thief@example.com", "顺蛋")
    vic_kid, vic_sid = await _enroll(db, "vic@example.com", "失蛋")
    await _stock(db, vic_sid, 1, "chicken", fed_today=True)
    await _stock(db, vic_sid, 2, "pig")
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET last_active_at=? WHERE id=?",
            (db.now() - 4000, vic_sid),
        )
        await conn.commit()

    try:
        await barn.barn_ops(thief_kid, "偷 失蛋 2")
        raise AssertionError("pig should not be stealable")
    except ValueError as exc:
        assert "活畜" in str(exc) or "可顺" in str(exc), str(exc)

    events.random.random = lambda: 0.99  # type: ignore[method-assign]
    barn.random.random = lambda: 0.99  # type: ignore[method-assign]
    msg = await barn.barn_ops(thief_kid, "偷 失蛋")
    assert "顺走" in msg and "鸡蛋" in msg, msg
    assert "活畜没动" in msg, msg
    assert await _qty(db, thief_sid, "egg") == 1

    status = await barn.barn_ops(vic_kid, "status")
    assert "顺走" in status or "还可 collect" in status, status

    leftover = await barn.barn_ops(vic_kid, "collect 1")
    assert "收取" in leftover and "x1" in leftover, leftover
    assert "顺走" in leftover or "掐走" in leftover, leftover


async def test_barn_steal_caught() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="barn-bust-"))
    db = await _boot(tmp)
    from server import barn

    thief_kid, _thief_sid = await _enroll(db, "bust@example.com", "失手")
    _vic_kid, vic_sid = await _enroll(db, "dogvic@example.com", "有狗")
    await _stock(db, vic_sid, 1, "chicken", fed_today=True)
    await _stock(db, vic_sid, 3, "dog", fed_today=True)
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET last_active_at=? WHERE id=?",
            (db.now(), vic_sid),
        )
        await conn.commit()

    barn.random.random = lambda: 0.0  # type: ignore[method-assign]
    msg = await barn.barn_ops(thief_kid, "偷 有狗")
    assert "罚" in msg and "票" in msg, msg
    assert "被抓" not in msg or "罚" in msg


async def test_barn_help_and_buy_chinese() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="barn-help-"))
    db = await _boot(tmp)
    from server import barn

    kid, sid = await _enroll(db, "help@example.com", "图鉴")
    help_text = await barn.barn_ops(kid, "help")
    assert "每天一次" in help_text and "barn 偷" in help_text, help_text
    assert "不是一周一次" in help_text, help_text
    bought = await barn.barn_ops(kid, "buy 鸡 3")
    assert "#3" in bought and "鸡" in bought, bought


def main() -> None:
    asyncio.run(test_barn_daily_collect_not_weekly())
    asyncio.run(test_barn_collect_all_skips_done_slot())
    asyncio.run(test_barn_feed_resets_each_game_day())
    asyncio.run(test_barn_old_fed_flag_is_not_today())
    asyncio.run(test_barn_harvest_is_not_daily_collect())
    asyncio.run(test_barn_steal_products_not_animals())
    asyncio.run(test_barn_steal_caught())
    asyncio.run(test_barn_help_and_buy_chinese())
    print("barn tests ok")


if __name__ == "__main__":
    main()
