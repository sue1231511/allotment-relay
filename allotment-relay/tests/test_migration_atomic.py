#!/usr/bin/env python3
"""一次性迁移：补数据和「已补」标记同一个保存点，失败整体回滚、记日志、下次启动重试；失败不拦岛启动。"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FLAG = "spoil_clock_backfill_v1"


async def _boot(tmp: Path):
    os.environ["DATA_DIR"] = str(tmp)
    from server import config, db

    config.DATA_DIR = tmp
    config.DB_PATH = tmp / "relay.db"
    db.DATA_DIR = tmp
    db.DB_PATH = tmp / "relay.db"
    await db.init_db()
    return db


async def _legacy(db) -> int:
    """旧世界：背包、潮柜里各有没有变质记录的货；标记已清掉（模拟升级前的库）。"""
    key = await db.create_api_key("m@x.com")
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], "老玩家", "", "naturalist", "")
    async with db.connect() as conn:
        sid = (await (await conn.execute("SELECT id FROM stewards WHERE key_id=?", (row["id"],))).fetchone())[0]
        await db.add_item(conn, sid, "fish_herring", 4)
        await db.add_item(conn, sid, "crop_kale", 3)
        await conn.execute(
            "INSERT INTO hut_cabinet (steward_id, item, quantity, stored_at) VALUES (?,?,?,?)",
            (sid, "crop_kale", 5, db.now()))
        await conn.execute("DELETE FROM world_flags WHERE flag_key IN (?, 'trait_ghost_heal_v1', 'paid_batch_backfill_v1')", (FLAG,))
        await conn.execute("DELETE FROM hui_notices")
        await conn.execute("DELETE FROM chronicle WHERE action='spoil_notice'")
        await conn.commit()
    return sid


async def _snapshot(db) -> dict[str, int]:
    async with db.connect() as conn:
        out = {}
        for name, sql in (
            ("batches", "SELECT COUNT(*) FROM item_trait_batches"),
            ("flag", f"SELECT COUNT(*) FROM world_flags WHERE flag_key='{FLAG}'"),
            ("notice", "SELECT COUNT(*) FROM hui_notices"),
            ("news", "SELECT COUNT(*) FROM chronicle WHERE action='spoil_notice'"),
        ):
            try:
                out[name] = int((await (await conn.execute(sql)).fetchone())[0])
            except Exception:
                out[name] = 0
        return out


def test_helper_rolls_back_data_and_flag_together_and_logs(caplog) -> None:
    asyncio.run(_helper(caplog))


async def _helper(caplog) -> None:
    db = await _boot(Path(tempfile.mkdtemp(prefix="mig-helper-")))

    async def failing(conn, stats):
        for i in range(3):
            await conn.execute(
                "INSERT INTO world_flags (flag_key, applied_at, detail) VALUES (?,?,?)",
                (f"probe_{i}", 1, ""))
            stats["processed"] += 1
        raise RuntimeError("中途炸了")

    async with db.connect() as conn:
        with caplog.at_level(logging.ERROR):
            with pytest.raises(RuntimeError):
                await db.run_flagged_migration(conn, "probe_flag", "探针迁移", failing)
        await conn.commit()
    async with db.connect() as conn:
        rows = await (await conn.execute(
            "SELECT flag_key FROM world_flags WHERE flag_key LIKE 'probe_%'")).fetchall()
    assert rows == [], "数据和标记都不留"
    rec = [r for r in caplog.records if "一次性迁移失败" in r.getMessage()]
    assert rec and "探针迁移" in rec[0].getMessage() and "已处理=3" in rec[0].getMessage()
    assert rec[0].exc_info and rec[0].exc_info[0] is RuntimeError, "必须带异常栈，不吞异常"

    async def ok(conn, stats):
        await conn.execute("INSERT INTO world_flags (flag_key, applied_at, detail) VALUES ('probe_ok',1,'')")
        return 1

    async with db.connect() as conn:
        assert await db.run_flagged_migration(conn, "probe_flag", "探针迁移", ok) == 1
        assert await db.run_flagged_migration(conn, "probe_flag", "探针迁移", failing) == 0, "有标记就不再跑"
        await conn.commit()


def test_spoil_backfill_failure_midway_leaves_nothing_and_retry_succeeds(caplog, monkeypatch) -> None:
    asyncio.run(_midway(caplog, monkeypatch))


async def _midway(caplog, monkeypatch) -> None:
    from server import item_traits

    db = await _boot(Path(tempfile.mkdtemp(prefix="mig-mid-")))
    sid = await _legacy(db)
    before = await _snapshot(db)
    real_chronicle = db.add_chronicle

    async def boom(action, *a, **k):
        if action == "spoil_notice":          # 批次已经插完，写告示时才炸：最坏的时机
            raise RuntimeError("写纪事失败")
        return await real_chronicle(action, *a, **k)

    monkeypatch.setattr(db, "add_chronicle", boom)
    async with db.connect() as conn:
        with caplog.at_level(logging.ERROR):
            with pytest.raises(RuntimeError):
                await item_traits.backfill_spoil_clock(conn)
        await conn.commit()
    assert await _snapshot(db) == before, "批次、标记、告示、纪事一个都不能留下"
    rec = [r for r in caplog.records if "一次性迁移失败" in r.getMessage()]
    assert rec and "老存货补变质起点" in rec[0].getMessage() and spoil_flag_in(rec[0].getMessage())
    processed = int(rec[0].getMessage().split("已处理=")[1].split(" ")[0])
    assert processed > 0, "日志要记下失败前已经处理了多少条"
    assert rec[0].exc_info, "必须带异常栈"

    monkeypatch.setattr(db, "add_chronicle", real_chronicle)
    async with db.connect() as conn:
        added = await item_traits.backfill_spoil_clock(conn)
        await conn.commit()
    after = await _snapshot(db)
    assert added == 4 + 3 + 5 and after["flag"] == 1 and after["notice"] == 1 and after["news"] == 1
    assert after["batches"] == before["batches"] + 3, "下次启动重试成功：背包鱼、背包甘蓝、潮柜甘蓝三批"


def spoil_flag_in(msg: str) -> bool:
    return FLAG in msg


def test_init_db_does_not_stop_the_island_when_a_migration_fails_and_retries_next_start(caplog, monkeypatch) -> None:
    asyncio.run(_init_db_fail_open(caplog, monkeypatch))


async def _init_db_fail_open(caplog, monkeypatch) -> None:
    from server import item_traits

    db = await _boot(Path(tempfile.mkdtemp(prefix="mig-init-")))
    await _legacy(db)
    before = await _snapshot(db)
    real = item_traits._spoil_seconds

    def broken(*a, **k):
        raise RuntimeError("保质期表坏了")

    monkeypatch.setattr(item_traits, "_spoil_seconds", broken)
    with caplog.at_level(logging.ERROR):
        await db.init_db()                       # 不能抛：岛照常启动
    text = caplog.text
    assert "一次性迁移失败" in text and "岛继续启动" in text and "下次启动重试" in text
    assert await _snapshot(db) == before, "失败的迁移不留半截"

    monkeypatch.setattr(item_traits, "_spoil_seconds", real)
    await db.init_db()                           # 下次启动：自动重试成功
    after = await _snapshot(db)
    assert after["flag"] == 1 and after["notice"] == 1 and after["batches"] > before["batches"]
    await db.init_db()                           # 再启动：不重复
    assert await _snapshot(db) == after


# ── 线上已有 #340 写法的标记：新外壳必须认得，不重跑、不重复插入 ──────────────────

def test_flag_names_are_pinned_to_what_340_wrote_in_production() -> None:
    from server import item_traits, paid_ledger

    assert paid_ledger.FLAG_BACKFILL == "paid_batch_backfill_v1"
    assert item_traits.GHOST_HEAL_FLAG == "trait_ghost_heal_v1"


def test_340_style_flags_in_the_db_are_honored_no_rerun_no_duplicates() -> None:
    asyncio.run(_legacy_flags())


async def _legacy_flags() -> None:
    from server import paid_ledger

    db = await _boot(Path(tempfile.mkdtemp(prefix="mig-340-")))
    sid = await _legacy(db)
    ts = 1_790_000_000

    async def counts() -> dict[str, int]:
        async with db.connect() as conn:
            paid = (await (await conn.execute("SELECT COUNT(*), COALESCE(SUM(qty),0) FROM paid_batches")).fetchone())
            kale = (await (await conn.execute(
                "SELECT COALESCE(SUM(qty),0) FROM item_trait_batches WHERE steward_id=? AND loc='satchel' "
                "AND item='crop_kale'", (sid,))).fetchone())[0]
        return {"paid_rows": int(paid[0]), "paid_qty": int(paid[1]), "kale_batch_qty": int(kale)}

    # 线上状态：#340 部署时跑过这两个迁移，留下了（旧写法的）标记；之后又出现了「重跑就会改库」的数据
    async with db.connect() as conn:
        await db.add_item(conn, sid, "feed_animal", 12)                       # Tt 货，没有实付批次
        await db.add_item(conn, sid, "crop_kale", 5)
        await conn.execute(
            "INSERT INTO item_trait_batches (steward_id, loc, item, qty, quality, weight_milli, spoil_at) "
            "VALUES (?, 'satchel', 'crop_kale', 20, 'plain', 0, ?)", (sid, db.now() + 100000))   # 幽灵 20 件
        await conn.execute("DELETE FROM world_flags WHERE flag_key IN ('paid_batch_backfill_v1','trait_ghost_heal_v1')")
        await conn.execute(      # #340 的写法：detail 是 added=N / dropped=N
            "INSERT INTO world_flags (flag_key, applied_at, detail) VALUES ('paid_batch_backfill_v1', ?, 'added=7')", (ts,))
        await conn.execute(
            "INSERT INTO world_flags (flag_key, applied_at, detail) VALUES ('trait_ghost_heal_v1', ?, 'dropped=0')", (ts,))
        await conn.commit()
    before = await counts()
    assert before["paid_qty"] == 0 and before["kale_batch_qty"] == 20

    await db.init_db()                                   # 部署新版本：启动
    after = await counts()
    assert after == before, f"旧标记在，两个迁移不能重跑、批次数量不能变：{before} → {after}"
    async with db.connect() as conn:
        rows = dict(await (await conn.execute(
            "SELECT flag_key, detail FROM world_flags WHERE flag_key IN ('paid_batch_backfill_v1','trait_ghost_heal_v1')"
        )).fetchall())
        direct_paid = await paid_ledger.backfill_legacy(conn)
        from server import item_traits
        direct_heal = await item_traits.heal_ghost_batches(conn)
        await conn.commit()
    assert rows == {"paid_batch_backfill_v1": "added=7", "trait_ghost_heal_v1": "dropped=0"}, "旧标记原样保留"
    assert direct_paid == 0 and direct_heal == 0
    assert await counts() == before

    # 对照：没有旧标记（比如标记丢了）时迁移会跑——证明上面「没变」确实是因为认出了标记
    async with db.connect() as conn:
        await conn.execute("DELETE FROM world_flags WHERE flag_key IN ('paid_batch_backfill_v1','trait_ghost_heal_v1')")
        await conn.commit()
    await db.init_db()
    ran = await counts()
    async with db.connect() as conn:
        tracked_in_satchel = sum(
            int(q) for it, q in await (await conn.execute(
                "SELECT item, quantity FROM satchel WHERE steward_id=? AND quantity>0", (sid,))).fetchall()
            if paid_ledger.is_tracked(it)
        )
    assert tracked_in_satchel >= 12 and ran["paid_qty"] == tracked_in_satchel, "背包里每件记账货都补了实付批次"
    async with db.connect() as conn:
        kale_in_satchel = (await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item='crop_kale'", (sid,))).fetchone())[0]
    assert ran["kale_batch_qty"] == kale_in_satchel, "幽灵批次被对齐到背包数量"

    # 就算标记丢了又重跑一次：迁移本身只补「缺的」，不会重复插入实付批次
    async with db.connect() as conn:
        await conn.execute("DELETE FROM world_flags WHERE flag_key IN ('paid_batch_backfill_v1','trait_ghost_heal_v1')")
        await conn.commit()
    await db.init_db()
    assert await counts() == ran


# ── 启动日志：跳过、成功、失败三种结果都能从日志里认出来 ──────────────────────────

def test_startup_logs_show_skip_success_and_failure_for_each_migration(caplog, monkeypatch) -> None:
    asyncio.run(_startup_logs(caplog, monkeypatch))


async def _startup_logs(caplog, monkeypatch) -> None:
    from server import item_traits

    db = await _boot(Path(tempfile.mkdtemp(prefix="mig-logs-")))
    sid_legacy = await _legacy(db)          # 清掉三个标记、造好老存货
    names = {
        "实付批次补账": "paid_batch_backfill_v1",
        "幽灵批次对齐": "trait_ghost_heal_v1",
        "老存货补变质起点": FLAG,
    }
    # 线上状态：前两个在 #340 时已跑过（旧标记在），第三个是新的
    async with db.connect() as conn:
        for flag in ("paid_batch_backfill_v1", "trait_ghost_heal_v1"):
            await conn.execute(
                "INSERT INTO world_flags (flag_key, applied_at, detail) VALUES (?, 1, 'old')", (flag,))
        await conn.commit()

    def lines() -> list[str]:
        return [r.getMessage() for r in caplog.records if "一次性迁移" in r.getMessage()]

    with caplog.at_level(logging.INFO):
        await db.init_db()
    first = lines()
    for name in ("实付批次补账", "幽灵批次对齐"):
        assert any(f"迁移={name}" in m and f"标记={names[name]}" in m and "已完成，跳过" in m for m in first), (name, first)
    assert any("一次性迁移完成" in m and "迁移=老存货补变质起点" in m and f"标记={FLAG}" in m and "处理=" in m for m in first), first

    caplog.clear()
    with caplog.at_level(logging.INFO):
        await db.init_db()
    second = lines()
    for name, flag in names.items():
        assert any(f"迁移={name}" in m and f"标记={flag}" in m and "已完成，跳过" in m for m in second), (name, second)

    # 失败：下一个新标记的迁移在 ERROR 级别带名字、标记名、已处理条数
    async with db.connect() as conn:
        await conn.execute("DELETE FROM world_flags WHERE flag_key=?", (FLAG,))
        await db.add_item(conn, sid_legacy, "fish_herring", 2)      # 再来一点没有变质记录的货，迁移才有东西可补
        await conn.commit()
    monkeypatch.setattr(item_traits, "_spoil_seconds", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("坏了")))
    caplog.clear()
    with caplog.at_level(logging.INFO):
        await db.init_db()
    fail = [r for r in caplog.records if "一次性迁移失败" in r.getMessage()]
    assert fail and fail[0].levelno == logging.ERROR and "迁移=老存货补变质起点" in fail[0].getMessage()
    assert f"标记={FLAG}" in fail[0].getMessage() and "已处理=" in fail[0].getMessage()
