#!/usr/bin/env python3
"""变质清理：不许误扣新货，丢了什么必须在回复里写明（榴莲事故回归）。"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

HOURS = 3600


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
            "UPDATE stewards SET tickets=5000, energy=100, health=100, last_active_at=?, last_bar_shift_at=? WHERE id=?",
            (db.now(), db.now(), sid),
        )
        await conn.commit()
    return row["id"], sid


async def _qty(db, sid: int, item: str) -> int:
    async with db.connect() as conn:
        row = await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item=?", (sid, item))).fetchone()
    return int(row[0]) if row else 0


async def _batches(db, sid: int, item: str) -> list[tuple[int, bool]]:
    from server import item_traits

    async with db.connect() as conn:
        await item_traits.ensure_trait_tables(conn)
        rows = await (await conn.execute(
            "SELECT qty, spoil_at>0 AND spoil_at<=? FROM item_trait_batches WHERE steward_id=? AND item=? ORDER BY id",
            (db.now(), sid, item))).fetchall()
    return [(int(q), bool(e)) for q, e in rows]


def _travel(monkeypatch, db, hours: int) -> None:
    real = db.now
    monkeypatch.setattr(db, "now", lambda: real() + hours * HOURS)


async def _refresh_duty(db, *sids: int) -> None:
    async with db.connect() as conn:
        for sid in sids:
            await conn.execute(
                "UPDATE stewards SET last_active_at=?, last_bar_shift_at=? WHERE id=?",
                (db.now(), db.now(), sid),
            )
        await conn.commit()


# ── 1. 事故复现：送走一批 → 72 小时后 → 收获新一批 → 卖一个 ─────────────

def test_gift_then_72h_then_harvest_then_vend_keeps_new_batch(monkeypatch) -> None:
    asyncio.run(_accident(monkeypatch))


async def _accident(monkeypatch) -> None:
    from server import item_traits
    from server.game import tote

    db = await _boot(Path(tempfile.mkdtemp(prefix="spoil-acc-")))
    ka, a = await _enroll(db, "a@x.com", "kk薛洄贵")
    kb, b = await _enroll(db, "b@x.com", "邻居")
    async with db.connect() as conn:
        await item_traits.grant_satchel(conn, a, "crop_durian", 30)
        await conn.commit()
    await tote.tote_ops(ka, "gift 邻居 crop_durian 30")      # 全送走：批次账里不许留 30 件幽灵
    assert await _qty(db, a, "crop_durian") == 0
    assert await _batches(db, a, "crop_durian") == []
    _travel(monkeypatch, db, 73)
    await _refresh_duty(db, a, b)
    async with db.connect() as conn:                            # 新一批收获
        await item_traits.grant_satchel(conn, a, "crop_durian", 40)
        await conn.commit()
    reply = await tote.tote_ops(ka, "vend crop_durian 1")
    assert await _qty(db, a, "crop_durian") == 39, reply
    assert "变质" not in reply
    assert await _batches(db, a, "crop_durian") == [(39, False)]


def test_preexisting_ghost_batch_cannot_eat_new_goods(monkeypatch) -> None:
    asyncio.run(_legacy_ghost(monkeypatch))


async def _legacy_ghost(monkeypatch) -> None:
    """线上已经存在的幽灵批次（旧版本送礼没扣）：过期后既不能扣掉新收获的货，也不许刷出假的丢弃提示。"""
    from server import item_traits
    from server.game import tote

    db = await _boot(Path(tempfile.mkdtemp(prefix="spoil-ghost-")))
    ka, a = await _enroll(db, "a@x.com", "老号")
    async with db.connect() as conn:
        await item_traits.ensure_trait_tables(conn)
        await conn.execute(      # 幽灵：背包里早就没有这批货了
            "INSERT INTO item_trait_batches (steward_id, loc, item, qty, quality, weight_milli, spoil_at) "
            "VALUES (?, 'satchel', 'crop_durian', 30, 'plain', 0, ?)", (a, db.now() + 72 * HOURS))
        await conn.commit()
    _travel(monkeypatch, db, 73)
    await _refresh_duty(db, a)
    async with db.connect() as conn:
        await item_traits.grant_satchel(conn, a, "crop_durian", 40)
        await conn.commit()
    assert await _batches(db, a, "crop_durian") == [(30, True), (40, False)]
    reply = await tote.tote_ops(ka, "vend crop_durian 1")
    assert await _qty(db, a, "crop_durian") == 39, reply
    assert "变质" not in reply, "幽灵批次不是真变质，不能报丢弃"
    assert await _batches(db, a, "crop_durian") == [(39, False)]


def test_purge_never_takes_more_than_satchel_really_holds(monkeypatch) -> None:
    asyncio.run(_purge_clamp(monkeypatch))


async def _purge_clamp(monkeypatch) -> None:
    from server import item_traits

    db = await _boot(Path(tempfile.mkdtemp(prefix="spoil-clamp-")))
    ka, a = await _enroll(db, "a@x.com", "钳制号")
    async with db.connect() as conn:
        await item_traits.grant_satchel(conn, a, "crop_durian", 40)       # 新货，72 小时后才坏
        await item_traits.ensure_trait_tables(conn)
        await conn.execute(      # 一条比背包还大的过期幽灵批次
            "INSERT INTO item_trait_batches (steward_id, loc, item, qty, quality, weight_milli, spoil_at) "
            "VALUES (?, 'satchel', 'crop_durian', 500, 'plain', 0, 1)", (a,))
        await conn.commit()
    async with db.connect() as conn:
        notes = await item_traits.purge_spoiled(conn, a)
        await conn.commit()
    assert await _qty(db, a, "crop_durian") == 40, "新货一件都不能少"
    assert notes == []
    assert await _batches(db, a, "crop_durian") == [(40, False)]


# ── 2. 真变质：丢了什么、多少，一定写在回复里 ──────────────────────────

def test_real_spoilage_is_reported_by_vend(monkeypatch) -> None:
    asyncio.run(_vend_reports(monkeypatch))


async def _vend_reports(monkeypatch) -> None:
    from server import item_traits
    from server.game import tote

    db = await _boot(Path(tempfile.mkdtemp(prefix="spoil-vend-")))
    ka, a = await _enroll(db, "a@x.com", "卖货号")
    async with db.connect() as conn:
        await item_traits.grant_satchel(conn, a, "crop_kale", 4)
        await item_traits.grant_satchel(conn, a, "fish_herring", 3)       # 另一种货：卖甘蓝时不能顺带清它
        await conn.commit()
    _travel(monkeypatch, db, 73)
    await _refresh_duty(db, a)
    async with db.connect() as conn:
        await item_traits.grant_satchel(conn, a, "crop_kale", 10)
        await conn.commit()
    reply = await tote.tote_ops(ka, "vend crop_kale 1")
    assert "变质丢弃" in reply and "×3" in reply and "甘蓝" in reply, reply
    assert await _qty(db, a, "crop_kale") == 10
    assert await _qty(db, a, "fish_herring") == 3, "卖甘蓝不能顺带清走别的物品"
    # 鱼已经过期（36 小时）但没人动它：list 才会清，并且写明
    listing = await tote.tote_ops(ka, "list")
    assert "变质丢弃" in listing and "×3" in listing, listing
    assert await _qty(db, a, "fish_herring") == 0
    assert "fish_herring" not in listing.split("变质丢弃")[1].split("\n", 1)[-1], "列表里不该再出现已经丢掉的货"


def test_list_purge_is_committed_and_list_shows_post_purge_stock(monkeypatch) -> None:
    asyncio.run(_list_commit(monkeypatch))


async def _list_commit(monkeypatch) -> None:
    from server import item_traits
    from server.game import tote

    db = await _boot(Path(tempfile.mkdtemp(prefix="spoil-list-")))
    ka, a = await _enroll(db, "a@x.com", "列表号")
    async with db.connect() as conn:
        await item_traits.grant_satchel(conn, a, "fish_herring", 5)
        await conn.commit()
    _travel(monkeypatch, db, 40)
    await _refresh_duty(db, a)
    first = await tote.tote_ops(ka, "list")
    assert "变质丢弃" in first and "×5" in first
    assert await _qty(db, a, "fish_herring") == 0, "list 说丢了，库里就要真丢（以前没 commit）"
    second = await tote.tote_ops(ka, "list")
    assert "变质丢弃" not in second


def test_cooked_dish_vend_reports_spoilage(monkeypatch) -> None:
    asyncio.run(_dish_vend(monkeypatch))


async def _dish_vend(monkeypatch) -> None:
    from server import item_traits, kitchen
    from server.catalog import KITCHEN_DISHES, dish_item

    db = await _boot(Path(tempfile.mkdtemp(prefix="spoil-dish-")))
    ka, a = await _enroll(db, "a@x.com", "厨子")
    dish = dish_item(next(iter(KITCHEN_DISHES)), 3)
    async with db.connect() as conn:
        await item_traits.grant_satchel(conn, a, dish, 3)
        await conn.commit()
    _travel(monkeypatch, db, 21)
    await _refresh_duty(db, a)
    reply = await kitchen.kitchen_ops(ka, f"vend {dish}")
    assert "变质丢弃" in reply and "×2" in reply, reply
    assert await _qty(db, a, dish) == 0


def test_departures_never_silently_discard(monkeypatch) -> None:
    asyncio.run(_departures(monkeypatch))


async def _departures(monkeypatch) -> None:
    """送礼、挂集市等转手不许顺带清走任何东西（以前会静默清掉该玩家所有过期批次）。"""
    from server import item_traits, market
    from server.game import tote

    db = await _boot(Path(tempfile.mkdtemp(prefix="spoil-dep-")))
    ka, a = await _enroll(db, "a@x.com", "转手甲")
    kb, b = await _enroll(db, "b@x.com", "转手乙")
    async with db.connect() as conn:
        await item_traits.grant_satchel(conn, a, "fish_herring", 5)
        await item_traits.grant_satchel(conn, a, "crop_kale", 6)
        await conn.commit()
    _travel(monkeypatch, db, 40)       # 鱼已过期（36 小时），甘蓝没过期（72 小时）
    await _refresh_duty(db, a, b)
    await tote.tote_ops(ka, "gift 转手乙 crop_kale 2")
    await market.market_ops(ka, "sell crop_kale 2 10")
    assert await _qty(db, a, "fish_herring") == 5, "转手不能顺带丢鱼"
    assert await _qty(db, a, "crop_kale") == 2


# ── 3. 启动时一次性对齐旧幽灵 ─────────────────────────────────────────

def test_heal_ghost_batches_on_init_is_one_shot() -> None:
    asyncio.run(_heal())


async def _heal() -> None:
    from server import item_traits

    db = await _boot(Path(tempfile.mkdtemp(prefix="spoil-heal-")))
    ka, a = await _enroll(db, "a@x.com", "清账号")
    async with db.connect() as conn:
        await item_traits.grant_satchel(conn, a, "crop_durian", 5)
        await conn.execute(
            "INSERT INTO item_trait_batches (steward_id, loc, item, qty, quality, weight_milli, spoil_at) "
            "VALUES (?, 'satchel', 'crop_durian', 20, 'plain', 0, ?)", (a, db.now() + 100))
        await conn.execute("DELETE FROM world_flags WHERE flag_key='trait_ghost_heal_v1'")
        await conn.commit()
    async with db.connect() as conn:
        dropped = await item_traits.heal_ghost_batches(conn)
        again = await item_traits.heal_ghost_batches(conn)
        await conn.commit()
    assert dropped == 20 and again == 0
    assert await _qty(db, a, "crop_durian") == 5, "补账只动批次账，不动物品"
    assert sum(q for q, _ in await _batches(db, a, "crop_durian")) == 5


# ── 4. 只读调查脚本 ───────────────────────────────────────────────────

def test_investigation_script_is_read_only_and_never_prints_keys(caplog) -> None:
    import hashlib
    import importlib.util
    import logging

    tmp = Path(tempfile.mkdtemp(prefix="spoil-script-"))
    secret: dict[str, str] = {}

    async def build() -> None:
        from server import item_traits

        db = await _boot(tmp)
        key = await db.create_api_key("s@x.com")
        secret["key"] = key
        row = await db.get_key_row(key)
        await db.enroll_steward(row["id"], "查账号", "", "naturalist", "")
        async with db.connect() as conn:
            sid = (await (await conn.execute("SELECT id FROM stewards WHERE key_id=?", (row["id"],))).fetchone())[0]
            await item_traits.grant_satchel(conn, sid, "crop_durian", 5)
            await conn.execute(      # 幽灵：已过期、背包里没有
                "INSERT INTO item_trait_batches (steward_id, loc, item, qty, quality, weight_milli, spoil_at) "
                "VALUES (?, 'satchel', 'crop_durian', 30, 'plain', 0, 1)", (sid,))
            await db.add_chronicle("gift", "查账号 送礼给 邻居：榴莲（crop_durian）x28", sid, conn=conn)
            await conn.commit()

    asyncio.run(build())
    db_file = tmp / "relay.db"

    def fingerprint() -> str:
        h = hashlib.sha256()
        for name in ("relay.db", "relay.db-wal"):
            f = tmp / name
            if f.exists():
                h.update(f.read_bytes())
        return h.hexdigest()

    spec = importlib.util.spec_from_file_location(
        "investigate_vanished_items", ROOT / "scripts" / "investigate_vanished_items.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    before = fingerprint()
    with caplog.at_level(logging.INFO):
        code = mod.main(["查账号", "榴莲", "--db", str(db_file)])
    assert code == 0
    assert fingerprint() == before, "调查脚本不许改库"
    text = caplog.text
    assert secret["key"] not in text and "ar_sk_" not in text, "不许打印任何 key"
    assert "背包里 crop_durian 现有 5 件" in text
    assert "幽灵批次" in text and "已过期" in text
    assert "送礼给 邻居" in text
    assert mod.main(["不存在的人", "榴莲", "--db", str(db_file)]) == 1
