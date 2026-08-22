#!/usr/bin/env python3
"""小屋新家具：吊床/浴桶/腌菜坛/晾鱼架/梳妆台/航海书架。"""
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


async def _install(db, sid: int, slot: str, key: str) -> None:
    async with db.connect() as conn:
        await conn.execute(
            "INSERT INTO hut_fittings (steward_id, slot, item_key, installed_at)"
            " VALUES (?, ?, ?, ?)",
            (sid, slot, key, db.now()),
        )
        await conn.commit()


def test_hammock_and_vanity() -> None:
    asyncio.run(_test_hammock_and_vanity())


async def _test_hammock_and_vanity() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="hammock-"))
    db = await _boot(tmp)
    from server import hut

    kid, sid = await _enroll(db, "hammock@example.com", "吊床客")
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET hut_built=1, energy=10, standing=50 WHERE id=?",
            (sid,),
        )
        await conn.commit()

    try:
        await hut.hut_ops(kid, "睡")
        raise AssertionError("no bed/hammock should refuse")
    except ValueError as exc:
        assert "床" in str(exc) or "睡" in str(exc), exc

    await _install(db, sid, "soft_1", "hammock")
    msg = await hut.hut_ops(kid, "睡")
    assert "吊床" in msg and "精力 +35" in msg, msg

    await _install(db, sid, "soft_2", "vanity")
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET bed_rest_at=0, energy=10 WHERE id=?", (sid,)
        )
        await conn.commit()
    msg2 = await hut.hut_ops(kid, "睡")
    assert "档信 +1" in msg2, msg2
    s = await db.get_steward_by_id(sid)
    assert s["standing"] == 51, s["standing"]

    # 装了真床：按床算（50），同一份冷却
    await _install(db, sid, "hard_1", "bed")
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET bed_rest_at=0, energy=10 WHERE id=?", (sid,)
        )
        await conn.commit()
    msg3 = await hut.hut_ops(kid, "睡")
    assert "精力 +50" in msg3, msg3


def test_bath_tub() -> None:
    asyncio.run(_test_bath_tub())


async def _test_bath_tub() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="bath-"))
    db = await _boot(tmp)
    from server import hut

    kid, sid = await _enroll(db, "bath@example.com", "泡澡客")
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET hut_built=1, mist_wit=40 WHERE id=?", (sid,)
        )
        await conn.commit()

    try:
        await hut.hut_ops(kid, "泡澡")
        raise AssertionError("no tub should refuse")
    except ValueError as exc:
        assert "浴桶" in str(exc), exc

    await _install(db, sid, "hard_1", "bath_tub")
    msg = await hut.hut_ops(kid, "泡澡")
    assert "雾智 +15" in msg, msg
    s = await db.get_steward_by_id(sid)
    assert s["mist_wit"] == 55, s["mist_wit"]

    try:
        await hut.hut_ops(kid, "泡澡")
        raise AssertionError("cooldown should refuse")
    except ValueError as exc:
        assert "小时" in str(exc), exc


def test_pickle_crock() -> None:
    asyncio.run(_test_pickle_crock())


async def _test_pickle_crock() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="pickle-"))
    db = await _boot(tmp)
    from server import hut, kitchen

    kid, sid = await _enroll(db, "pickle@example.com", "腌菜客")
    async with db.connect() as conn:
        await conn.execute("UPDATE stewards SET hut_built=1 WHERE id=?", (sid,))
        await db.add_item(conn, sid, "crop_kale", 5)
        await db.add_item(conn, sid, "crop_mango", 2)
        await conn.commit()

    try:
        await hut.hut_ops(kid, "腌 甘蓝 4")
        raise AssertionError("no crock should refuse")
    except ValueError as exc:
        assert "腌菜坛" in str(exc), exc

    await _install(db, sid, "hard_1", "pickle_crock")
    msg = await hut.hut_ops(kid, "腌 甘蓝 4")
    assert "腌菜 x2" in msg, msg
    async with db.connect() as conn:
        kale = (await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item='crop_kale'",
            (sid,),
        )).fetchone())[0]
        jars = (await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item='pickles'",
            (sid,),
        )).fetchone())[0]
    assert kale == 1 and jars == 2, (kale, jars)

    # 水果不收
    try:
        await hut.hut_ops(kid, "腌 芒果 2")
        raise AssertionError("fruit should refuse")
    except ValueError as exc:
        assert "水果" in str(exc), exc

    # 腌菜可以直接吃：+6、安全、清水果连击
    eat_msg = await kitchen.kitchen_ops(kid, "eat 腌菜")
    assert "精力 +6" in eat_msg and "安全" in eat_msg, eat_msg


def test_fish_rack() -> None:
    asyncio.run(_test_fish_rack())


async def _test_fish_rack() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="rack-"))
    db = await _boot(tmp)
    from server import hut, kitchen

    kid, sid = await _enroll(db, "rack@example.com", "晾鱼客")
    async with db.connect() as conn:
        await conn.execute("UPDATE stewards SET hut_built=1, energy=20 WHERE id=?", (sid,))
        await db.add_item(conn, sid, "fish_mackerel", 5)
        await conn.commit()

    try:
        await hut.hut_ops(kid, "晾 鲭鱼 4")
        raise AssertionError("no rack should refuse")
    except ValueError as exc:
        assert "晾鱼架" in str(exc), exc

    await _install(db, sid, "soft_1", "fish_rack")
    msg = await hut.hut_ops(kid, "晾 鲭鱼 4")
    assert "鱼干·鲭鱼 x2" in msg, msg
    async with db.connect() as conn:
        fish = (await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item='fish_mackerel'",
            (sid,),
        )).fetchone())[0]
        dried = (await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item='dried_mackerel'",
            (sid,),
        )).fetchone())[0]
    assert fish == 1 and dried == 2, (fish, dried)

    eat_msg = await kitchen.kitchen_ops(kid, "eat 鱼干·鲭鱼")
    assert "精力 +10" in eat_msg and "安全" in eat_msg, eat_msg


def test_bookshelf() -> None:
    asyncio.run(_test_bookshelf())


async def _test_bookshelf() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="shelf-"))
    db = await _boot(tmp)
    from server import hut

    kid, sid = await _enroll(db, "shelf@example.com", "读书客")
    async with db.connect() as conn:
        await conn.execute("UPDATE stewards SET hut_built=1, mist_wit=40 WHERE id=?", (sid,))
        await conn.commit()

    try:
        await hut.hut_ops(kid, "读")
        raise AssertionError("no shelf should refuse")
    except ValueError as exc:
        assert "书架" in str(exc), exc

    await _install(db, sid, "soft_1", "bookshelf")
    msg = await hut.hut_ops(kid, "读")
    assert "雾智 +2" in msg and "【" in msg, msg
    s = await db.get_steward_by_id(sid)
    assert s["mist_wit"] == 42, s["mist_wit"]

    try:
        await hut.hut_ops(kid, "读")
        raise AssertionError("daily limit should refuse")
    except ValueError as exc:
        assert "明日" in str(exc) or "翻过" in str(exc), exc


def main() -> None:
    test_hammock_and_vanity()
    test_bath_tub()
    test_pickle_crock()
    test_fish_rack()
    test_bookshelf()
    print("hut furniture tests ok")


if __name__ == "__main__":
    main()
