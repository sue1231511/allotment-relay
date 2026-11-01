#!/usr/bin/env python3
"""精力梯子与渔网新规告示：只写一次，重复启动不重复；全新的岛不写；失败整体回滚、下次重试。"""
from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path


async def _boot(tmp: Path):
    os.environ["DATA_DIR"] = str(tmp)
    from server import config, db

    config.DATA_DIR = tmp
    config.DB_PATH = tmp / "relay.db"
    db.DATA_DIR = tmp
    db.DB_PATH = tmp / "relay.db"
    db._DB_MUTEX = asyncio.Lock()
    await db.init_db()
    return db


async def _counts(db) -> dict[str, int]:
    from server import energy_notice as en

    async with db.connect() as conn:
        one = lambda sql, *a: conn.execute(sql, a)
        notice = (await (await one("SELECT COUNT(*) FROM hui_notices WHERE body=?", en.ENERGY_LADDER_NOTICE)).fetchone())[0]
        news = (await (await one("SELECT COUNT(*) FROM chronicle WHERE action=?", en.ENERGY_LADDER_ACTION)).fetchone())[0]
        flag = (await (await one("SELECT COUNT(*) FROM world_flags WHERE flag_key=?", en.ENERGY_LADDER_FLAG)).fetchone())[0]
    return {"notice": int(notice), "news": int(news), "flag": int(flag)}


async def _enroll(db, email: str, name: str) -> None:
    key = await db.create_api_key(email)
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], name, "", "naturalist", "")


def test_flag_name_and_text() -> None:
    from server import energy_notice as en

    assert en.ENERGY_LADDER_FLAG == "energy_ladder_notice_v1"
    assert en.ENERGY_LADDER_NOTICE.startswith("【潮生会告示 · 灶台与渔网新规】\n即日起岛上几处规矩调整：\n1. ")
    assert en.ENERGY_LADDER_NOTICE.endswith("有疑问来潮生会留言。")
    for n in "123456":
        assert f"\n{n}. " in en.ENERGY_LADDER_NOTICE


def test_written_once_on_upgrade_and_not_repeated() -> None:
    asyncio.run(_once())


async def _once() -> None:
    from server import energy_notice as en

    db = await _boot(Path(tempfile.mkdtemp(prefix="energy-notice-")))
    # 全新的岛启动时还没有人：不写告示，但标记写下，以后不补
    assert await _counts(db) == {"notice": 0, "news": 0, "flag": 1}
    # 模拟「老岛升级上线」：岛上有人，标记还没有
    await _enroll(db, "n1@example.com", "老岛民")
    async with db.connect() as conn:
        await conn.execute("DELETE FROM world_flags WHERE flag_key=?", (en.ENERGY_LADDER_FLAG,))
        await conn.commit()
    await db.init_db()
    assert await _counts(db) == {"notice": 1, "news": 1, "flag": 1}
    async with db.connect() as conn:
        tag, body = await (await conn.execute("SELECT tag, body FROM hui_notices WHERE body=?", (en.ENERGY_LADDER_NOTICE,))).fetchone()
        text = (await (await conn.execute("SELECT text FROM chronicle WHERE action=?", (en.ENERGY_LADDER_ACTION,))).fetchone())[0]
    assert tag == "厅示" and body == text == en.ENERGY_LADDER_NOTICE
    # 重复启动、直接再调：都不重复
    await db.init_db()
    await db.init_db()
    async with db.connect() as conn:
        assert await en.announce_energy_ladder(conn) == 0
        await conn.commit()
    assert await _counts(db) == {"notice": 1, "news": 1, "flag": 1}


def test_fresh_island_gets_no_notice_even_after_people_join() -> None:
    asyncio.run(_fresh())


async def _fresh() -> None:
    db = await _boot(Path(tempfile.mkdtemp(prefix="energy-notice-fresh-")))
    await _enroll(db, "n2@example.com", "新岛民")
    await db.init_db()
    assert await _counts(db) == {"notice": 0, "news": 0, "flag": 1}


def test_failure_rolls_back_together_and_retries_next_start(monkeypatch) -> None:
    asyncio.run(_failure(monkeypatch))


async def _failure(monkeypatch) -> None:
    from server import energy_notice as en

    db = await _boot(Path(tempfile.mkdtemp(prefix="energy-notice-fail-")))
    await _enroll(db, "n3@example.com", "老岛民")
    async with db.connect() as conn:
        await conn.execute("DELETE FROM world_flags WHERE flag_key=?", (en.ENERGY_LADDER_FLAG,))
        await conn.commit()

    real = db.add_chronicle

    async def boom(action, *a, **kw):
        if action == en.ENERGY_LADDER_ACTION:
            raise RuntimeError("写纪事时炸了")
        return await real(action, *a, **kw)

    monkeypatch.setattr(db, "add_chronicle", boom)
    await db.init_db()  # 启动迁移失败不拦岛启动
    assert await _counts(db) == {"notice": 0, "news": 0, "flag": 0}  # 数据和标记都没留
    monkeypatch.setattr(db, "add_chronicle", real)
    await db.init_db()  # 下次启动自动重试
    assert await _counts(db) == {"notice": 1, "news": 1, "flag": 1}
