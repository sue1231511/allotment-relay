#!/usr/bin/env python3
"""老存货补变质起点：上线时刻起算、按所在位置给一整段保质期；上线后不会立刻变质，过了整段才清。"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

H = 3600


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
        sid = (await (await conn.execute("SELECT id FROM stewards WHERE key_id=?", (row["id"],))).fetchone())[0]
        await conn.execute(
            "UPDATE stewards SET tickets=5000, energy=100, health=100, hut_built=1, hut_level=2, "
            "last_active_at=?, last_bar_shift_at=? WHERE id=?",
            (db.now(), db.now(), sid),
        )
        for slot, key_ in (("soft_1", "cabinet"), ("soft_2", "fridge")):
            await conn.execute(
                "INSERT INTO hut_fittings (steward_id, slot, item_key, installed_at) VALUES (?,?,?,?)",
                (sid, slot, key_, db.now()),
            )
        await conn.commit()
    return row["id"], sid


def _travel(monkeypatch, db, hours: float) -> None:
    real = db.now
    monkeypatch.setattr(db, "now", lambda: real() + int(hours * H))


async def _duty(db, sid: int) -> None:
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET last_active_at=?, last_bar_shift_at=? WHERE id=?", (db.now(), db.now(), sid))
        await conn.commit()


async def _legacy_world(db):
    """造一个「旧版本留下的」世界：背包/潮柜/冰箱/集市里都有没有变质记录的货。"""
    from server import item_traits
    from server.catalog import KITCHEN_DISHES, dish_item

    ka, a = await _enroll(db, "a@x.com", "老玩家")
    dish = dish_item(next(iter(KITCHEN_DISHES)), 3)
    async with db.connect() as conn:
        await item_traits.ensure_trait_tables(conn)
        await db.add_item(conn, a, "fish_herring", 6)                       # 没有批次的鱼
        await item_traits.grant_satchel(conn, a, "fish_herring", 2)         # 另有 2 条有批次（新鲜）
        await db.add_item(conn, a, "crop_kale", 4)
        await conn.execute(
            "INSERT INTO hut_cabinet (steward_id, item, quantity, stored_at) VALUES (?,?,?,?)",
            (a, "crop_kale", 5, db.now() - 10 * 86400))
        await conn.execute(
            "INSERT INTO hut_cabinet (steward_id, item, quantity, stored_at) VALUES (?,?,?,?)",
            (a, "fish_herring", 3, db.now() - 20 * 86400))
        dish_key = next(iter(KITCHEN_DISHES))
        await conn.execute(
            "INSERT INTO meal_storage (steward_id, dish_key, stars, quantity, stored_at) VALUES (?,?,?,?,?)",
            (a, dish_key, 3, 2, db.now() - 30 * 86400))
        await conn.execute(
            "INSERT INTO market_listings (seller_id, item, quantity, price, suggested, note, created_at) "
            "VALUES (?,?,?,?,?,?,?)", (a, "fish_herring", 2, 5, 5, "", db.now()))
        await conn.execute("DELETE FROM world_flags WHERE flag_key IN ('spoil_clock_backfill_v1')")
        await conn.execute("DELETE FROM hui_notices")
        await conn.execute("DELETE FROM chronicle WHERE action='spoil_notice'")
        await conn.commit()
    return ka, a, dish


async def _batch_rows(db, owner: int, loc: str, item: str) -> list[tuple[int, int, str]]:
    async with db.connect() as conn:
        rows = await (await conn.execute(
            "SELECT qty, spoil_at, quality FROM item_trait_batches WHERE steward_id=? AND loc=? AND item=? ORDER BY id",
            (owner, loc, item))).fetchall()
    return [(int(q), int(s), qu) for q, s, qu in rows]


def test_backfill_gives_each_location_a_full_shelf_life_from_now() -> None:
    asyncio.run(_backfill_values())


async def _backfill_values() -> None:
    from server import item_traits

    db = await _boot(Path(tempfile.mkdtemp(prefix="bf-vals-")))
    ka, a, dish = await _legacy_world(db)
    async with db.connect() as conn:
        tickets = (await (await conn.execute("SELECT tickets FROM stewards WHERE id=?", (a,))).fetchone())[0]
        satchel_before = dict(await (await conn.execute(
            "SELECT item, quantity FROM satchel WHERE steward_id=?", (a,))).fetchall())
    t0 = db.now()
    async with db.connect() as conn:
        added = await item_traits.backfill_spoil_clock(conn)
        again = await item_traits.backfill_spoil_clock(conn)
        await conn.commit()
    assert again == 0
    # 背包：鱼 8 条里 2 条已有批次，补 6 条，整段 36 小时（行囊 ×1）；甘蓝 4 棵 72 小时
    fish = await _batch_rows(db, a, "satchel", "fish_herring")
    assert sum(q for q, _, _ in fish) == 8
    legacy_fish = [r for r in fish if r[2] == ""]
    assert legacy_fish == [(6, legacy_fish[0][1], "")] and abs(legacy_fish[0][1] - (t0 + 36 * H)) <= 5
    kale = await _batch_rows(db, a, "satchel", "crop_kale")
    assert [q for q, _, _ in kale] == [4] and abs(kale[0][1] - (t0 + 72 * H)) <= 5
    # 潮柜 ×1.8
    (cq, cs, _), = await _batch_rows(db, a, "cabinet", "crop_kale")
    assert cq == 5 and abs(cs - (t0 + int(72 * H * 1.8))) <= 5
    (fq, fs, _), = await _batch_rows(db, a, "cabinet", "fish_herring")
    assert fq == 3 and abs(fs - (t0 + int(36 * H * 1.8))) <= 5
    # 冰箱 ×3.5（熟菜 18 小时）
    (mq, ms, _), = await _batch_rows(db, a, "fridge", dish)
    assert mq == 2 and abs(ms - (t0 + int(18 * H * 3.5))) <= 5
    # 集市上的货按行囊算
    (lq, ls, _), = await _batch_rows(db, 0, item_traits.escrow_loc("market", 1), "fish_herring")
    assert lq == 2 and abs(ls - (t0 + 36 * H)) <= 5
    assert added == 6 + 4 + 5 + 3 + 2 + 2
    # 只加批次行：票、背包、柜子里的数量一点没动
    async with db.connect() as conn:
        assert (await (await conn.execute("SELECT tickets FROM stewards WHERE id=?", (a,))).fetchone())[0] == tickets
        assert dict(await (await conn.execute(
            "SELECT item, quantity FROM satchel WHERE steward_id=?", (a,))).fetchall()) == satchel_before
        assert (await (await conn.execute(
            "SELECT SUM(quantity) FROM hut_cabinet WHERE steward_id=?", (a,))).fetchone())[0] == 8


def test_backfill_posts_one_island_notice() -> None:
    asyncio.run(_notice())


async def _notice() -> None:
    from server import item_traits

    db = await _boot(Path(tempfile.mkdtemp(prefix="bf-notice-")))
    await _legacy_world(db)
    async with db.connect() as conn:
        await item_traits.backfill_spoil_clock(conn)
        await item_traits.backfill_spoil_clock(conn)
        await conn.commit()
        notices = await (await conn.execute("SELECT tag, body FROM hui_notices WHERE retracted=0")).fetchall()
        news = await (await conn.execute("SELECT text FROM chronicle WHERE action='spoil_notice'")).fetchall()
    assert len(notices) == 1 and len(news) == 1, "全岛告示和纪事各只写一条"
    body = notices[0][1]
    assert "潮柜" in body and "冰箱" in body and "会变质" in body and "不重新计时" in body
    assert "一整段保质期" in body or "整段保质期" in body


def test_legacy_stock_not_spoiled_right_after_launch_but_cleared_after_full_span(monkeypatch) -> None:
    asyncio.run(_after_launch(monkeypatch))


async def _after_launch(monkeypatch) -> None:
    from server import hut, item_traits, kitchen
    from server.game import tote

    db = await _boot(Path(tempfile.mkdtemp(prefix="bf-clock-")))
    ka, a, dish = await _legacy_world(db)
    async with db.connect() as conn:
        await item_traits.backfill_spoil_clock(conn)
        await conn.commit()

    async def satchel_fish() -> int:
        async with db.connect() as conn:
            row = await (await conn.execute(
                "SELECT quantity FROM satchel WHERE steward_id=? AND item='fish_herring'", (a,))).fetchone()
        return int(row[0]) if row else 0

    # 上线后立刻：什么都不会坏（以前没有记录、过了几十天的货也不会）
    assert "变质丢弃" not in await tote.tote_ops(ka, "list")
    assert "放坏" not in await hut.cabinet_command(await db.get_steward_by_id(a), [])
    assert "放坏" not in await kitchen.fridge_status_text(await db.get_steward_by_id(a))
    assert await satchel_fish() == 8

    # 过了 35 小时：行囊里的鱼还没到整段 36 小时，不清
    _travel(monkeypatch, db, 35)
    await _duty(db, a)
    assert "变质丢弃" not in await tote.tote_ops(ka, "list")
    assert await satchel_fish() == 8

    # 过了 37 小时：行囊里没有记录的 6 条鱼到期被清，写明；有批次的 2 条（不是老存货）本来就是 37 小时前才来的，也到期
    _travel(monkeypatch, db, 2)
    await _duty(db, a)
    listing = await tote.tote_ops(ka, "list")
    assert "变质丢弃" in listing and "×6" in listing
    assert await satchel_fish() == 0

    # 已过 37 小时。再过 25 小时（共 62）：冰箱熟菜整段 63 小时、潮柜鱼 64.8 小时，都还没到
    _travel(monkeypatch, db, 25)
    await _duty(db, a)
    assert "放坏" not in await hut.cabinet_command(await db.get_steward_by_id(a), [])

    # 共 64 小时：冰箱熟菜过了 63 小时，清掉并写明；潮柜里的鱼（64.8 小时）还在
    _travel(monkeypatch, db, 2)
    await _duty(db, a)
    status = await hut.cabinet_command(await db.get_steward_by_id(a), [])
    assert "冰箱里的" in status and "×2" in status and "放坏了" in status, status
    async with db.connect() as conn:
        rows = dict(await (await conn.execute(
            "SELECT item, quantity FROM hut_cabinet WHERE steward_id=?", (a,))).fetchall())
    assert rows == {"crop_kale": 5, "fish_herring": 3}

    # 共 66 小时：潮柜里的鱼过了整段 64.8 小时，清掉并写明；甘蓝整段 129.6 小时，还在
    _travel(monkeypatch, db, 2)
    await _duty(db, a)
    status = await hut.cabinet_command(await db.get_steward_by_id(a), [])
    assert "潮柜里的" in status and "×3" in status and "放坏了" in status, status
    async with db.connect() as conn:
        rows = dict(await (await conn.execute(
            "SELECT item, quantity FROM hut_cabinet WHERE steward_id=?", (a,))).fetchall())
    assert rows == {"crop_kale": 5}

    # 共 130 小时：甘蓝过了整段，清掉并写明
    _travel(monkeypatch, db, 64)
    await _duty(db, a)
    status = await hut.cabinet_command(await db.get_steward_by_id(a), [])
    assert "潮柜里的" in status and "×5" in status and "放坏了" in status, status
