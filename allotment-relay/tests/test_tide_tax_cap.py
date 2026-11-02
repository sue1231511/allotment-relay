#!/usr/bin/env python3
"""周潮与岸税不再叠加：冲走的票抵本周岸税；一周总拿走封顶（结算前口袋的 WEEKLY_TAKE_CAP_RATE）。"""
from __future__ import annotations

import asyncio
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

CST = timezone(timedelta(hours=8))


def _cst_ts(year: int, month: int, day: int, hour: int = 12) -> int:
    return int(datetime(year, month, day, hour, tzinfo=CST).timestamp())


# 2026-08-25 周二（W35）；2026-08-31 周一（W36）。
ENROLL_TUE = _cst_ts(2026, 8, 25)
NEXT_MON = _cst_ts(2026, 8, 31)
WEEK = "2026-W36"


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


async def _enroll(db, email: str, name: str) -> int:
    key = await db.create_api_key(email)
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], name, "", "naturalist", "")
    async with db.connect() as conn:
        return int((await (await conn.execute(
            "SELECT id FROM stewards WHERE key_id=?", (row["id"],)
        )).fetchone())[0])


async def _set(db, sid: int, tickets: int) -> None:
    async with db.connect() as conn:
        await conn.execute("UPDATE stewards SET tickets=? WHERE id=?", (tickets, sid))
        await conn.commit()


async def _pocket(db, sid: int) -> tuple[int, int]:
    async with db.connect() as conn:
        r = await (await conn.execute(
            "SELECT tickets, COALESCE(tax_arrears,0) FROM stewards WHERE id=?", (sid,)
        )).fetchone()
    return int(r[0]), int(r[1])


async def _ledger(db, sid: int):
    async with db.connect() as conn:
        return await (await conn.execute(
            "SELECT pocket_before, tide_taken, tide_cut, label FROM weekly_tide_ledger "
            "WHERE steward_id=? AND week_id=?", (sid, WEEK)
        )).fetchone()


async def _bill(db, sid: int):
    async with db.connect() as conn:
        return await (await conn.execute(
            "SELECT assessed, paid, tickets_at, tide_offset, cap_cut, pocket_before "
            "FROM shore_tax_bills WHERE steward_id=? AND week_id=?", (sid, WEEK)
        )).fetchone()


async def _chron(db, sid: int, action: str) -> list[str]:
    async with db.connect() as conn:
        rows = await (await conn.execute(
            "SELECT text FROM chronicle WHERE actor_id=? AND action=? ORDER BY id", (sid, action)
        )).fetchall()
    return [r[0] for r in rows]


async def _clear_week(db) -> None:
    async with db.connect() as conn:
        await conn.execute("DELETE FROM world_flags WHERE flag_key IN (?, ?)",
                           (f"weekly_tide:{WEEK}", f"shore_tax:{WEEK}"))
        await conn.execute("DELETE FROM weekly_tide_ledger WHERE week_id=?", (WEEK,))
        await conn.execute("DELETE FROM shore_tax_bills WHERE week_id=?", (WEEK,))
        await conn.commit()


async def _settle_week(db, intensity: str):
    """周一结算：先周潮，再岸税（和 game/base.py 的顺序一致）。返回 (周潮结果, 岸税结果, 税前岛均)。"""
    from server import disaster, tax

    async with db.connect() as conn:
        tide = await disaster.ensure_weekly_tide(conn, week_id=WEEK, intensity=intensity)
        avg = await tax.island_pocket_avg(conn)
        res = await tax.ensure_shore_tax(conn, ts=NEXT_MON)
        await conn.commit()
    return tide, res, avg


async def _island(db, tmp_name: str, rich: int, n_poor: int = 3):
    """一个富人 + 几个穷人，都在上周二登记，周一结算时不算新号。"""
    db_ = await _boot(Path(tempfile.mkdtemp(prefix=tmp_name)))
    db_.now = lambda: ENROLL_TUE
    rich_id = await _enroll(db_, "rich@example.com", "富客")
    poor = [await _enroll(db_, f"p{i}@example.com", f"穷{i}") for i in range(n_poor)]
    await _set(db_, rich_id, rich)
    for sid in poor:
        await _set(db_, sid, 2000)
    db_.now = lambda: NEXT_MON
    await _clear_week(db_)
    return db_, rich_id, poor


def test_settle_week_tax_pure() -> None:
    from server import config, tax

    assert config.WEEKLY_TAKE_CAP_RATE == 0.5
    # 抵税：冲走 14000，应交 20000 -> 6000；封顶线 100000-14000=86000，不触发
    r = tax.settle_week_tax(20000, 100000, 14000)
    assert (r["offset"], r["assessed"], r["cap_cut"]) == (14000, 6000, 0)
    # 抵到 0 为止，不会变负
    r = tax.settle_week_tax(5000, 100000, 14000)
    assert (r["offset"], r["assessed"], r["cap_cut"]) == (5000, 0, 0)
    # 没被冲：只剩封顶。应交 60000 > 结算前 100000 的一半，岸税压到 50000
    r = tax.settle_week_tax(60000, 100000, 0)
    assert (r["offset"], r["assessed"], r["cap_cut"]) == (0, 50000, 10000)
    # 被冲 30000，应交 70000：抵掉 30000 剩 40000；线上还剩 50000-30000=20000，岸税压到 20000
    r = tax.settle_week_tax(70000, 100000, 30000)
    assert (r["offset"], r["assessed"], r["cap_cut"]) == (30000, 20000, 20000)
    # 周潮已经冲到线上：岸税一分不收
    r = tax.settle_week_tax(70000, 100000, 50000)
    assert r["assessed"] == 0
    # 没有结算前口袋的记录（0）：封顶为 0
    assert tax.settle_week_tax(100, 0, 0)["assessed"] == 0
    # 总拿走永远不超线
    for pocket in (1000, 50000, 2102870):
        for raw in (0, 300, 90000, 999999):
            for tide in (0, 100, int(pocket * 0.5)):
                s = tax.settle_week_tax(raw, pocket, tide)
                assert tide + s["assessed"] <= max(int(pocket * 0.5), tide)


def test_levy_cap_unit() -> None:
    """_apply_levy 的 cap_taken：周潮票数压到线，少冲的记在第三个返回值。"""
    asyncio.run(_levy_cap_unit())


async def _levy_cap_unit() -> None:
    from server import disaster

    db, rich, _ = await _island(None, "ttc-unit-", 100000)
    await _set(db, rich, 100000)
    async with db.connect() as conn:
        import aiosqlite
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute("SELECT * FROM stewards WHERE id=?", (rich,))).fetchone()
        steward = dict(row)
        line, taken, cut = await disaster._apply_levy(
            conn, steward, 52500, intensity="high",
            wash_fish=False, wreck_boat=False, wipe_crop_chance=0.0, cap_taken=50000,
        )
        assert taken == 50000 and cut == 2500, (taken, cut)
        assert "封顶" in line and "抵本周岸税" in line, line
        await conn.commit()
    assert (await _pocket(db, rich))[0] == 50000


async def test_tide_offsets_tax() -> None:
    from server import tax

    db, rich, poor = await _island(None, "ttc-offset-", 100000)
    tide, res, avg = await _settle_week(db, "low")
    pocket_before, tide_taken, tide_cut, label = await _ledger(db, rich)
    assert pocket_before == 100000
    assert tide_taken == int(70000 * 0.20) == 14000
    assert tide_cut == 0 and label == "浅潮"
    # 穷人也有台账（结算前口袋），实冲 0
    p_before, p_taken, _, _ = await _ledger(db, poor[0])
    assert (p_before, p_taken) == (2000, 0)
    post = 100000 - tide_taken
    raw = tax.tax_due(post, avg, 0)
    assert raw > tide_taken, "用例要让应交额大于周潮冲走数，才能看出抵税"
    assessed, paid, _, offset, cap_cut, pb = await _bill(db, rich)
    assert offset == tide_taken
    assert assessed == raw - tide_taken
    assert cap_cut == 0 and pb == 100000
    left, arrears = await _pocket(db, rich)
    assert arrears == 0
    assert left == post - assessed
    # 纪事写清楚
    texts = await _chron(db, rich, "tax")
    joined = "\n".join(texts)
    assert f"浅潮已冲 {tide_taken}，抵税 {tide_taken}" in joined, joined
    assert str(raw) in joined  # 抵税前应交额也写出来
    # 周潮自己的纪事说明会抵税
    assert any("抵本周岸税" in t for t in await _chron(db, rich, "disaster"))
    # 总拿走没超线
    assert (100000 - left) <= int(100000 * 0.5)


async def test_offset_floors_at_zero_and_no_refund() -> None:
    from server import tax

    db, rich, _ = await _island(None, "ttc-floor-", 70000)
    tide, res, avg = await _settle_week(db, "mid")
    _, tide_taken, _, _ = await _ledger(db, rich)
    assert tide_taken == int(40000 * 0.45) == 18000
    raw = tax.tax_due(70000 - tide_taken, avg, 0)
    assert raw < tide_taken, "用例要让周潮冲走数大于应交额，抵到 0"
    assessed, _, _, offset, cap_cut, _ = await _bill(db, rich)
    assert (assessed, offset, cap_cut) == (0, raw, 0)
    left, arrears = await _pocket(db, rich)
    assert left == 70000 - tide_taken  # 抵不完的部分不退
    assert arrears == 0
    texts = "\n".join(await _chron(db, rich, "tax"))
    assert "本周岸税免交" in texts and f"抵税 {raw}" in texts, texts


async def test_cap_squeezes_tax(monkeypatch) -> None:
    """把封顶比例临时调到 0.25，让岸税被压：周潮 + 岸税合计 ≤ 结算前口袋 × 0.25。"""
    from server import config, tax

    monkeypatch.setattr(config, "WEEKLY_TAKE_CAP_RATE", 0.25)
    db, rich, _ = await _island(None, "ttc-cap-", 100000)
    tide, res, avg = await _settle_week(db, "low")
    _, tide_taken, tide_cut, _ = await _ledger(db, rich)
    assert tide_taken == 14000 and tide_cut == 0  # 14000 < 30000，周潮没触线
    raw = tax.tax_due(100000 - tide_taken, avg, 0)
    assessed, _, _, offset, cap_cut, _ = await _bill(db, rich)
    assert offset == 14000
    assert assessed == 25000 - 14000
    assert cap_cut == raw - 14000 - assessed > 0
    left, arrears = await _pocket(db, rich)
    assert 100000 - left == 25000 and arrears == 0
    assert "一周总拿走封顶" in "\n".join(await _chron(db, rich, "tax"))


async def test_tide_itself_capped_at_half() -> None:
    """光周潮就超过 50%：黑潮冲 52500，压到 50000；岸税一分不收；总拿走正好 50%。"""
    db, rich, _ = await _island(None, "ttc-tide-", 100000)
    tide, res, avg = await _settle_week(db, "high")
    pocket_before, tide_taken, tide_cut, label = await _ledger(db, rich)
    assert (pocket_before, tide_taken, tide_cut, label) == (100000, 50000, 2500, "黑潮")
    assessed, _, _, offset, _, _ = await _bill(db, rich)
    assert assessed == 0 and offset > 0
    left, arrears = await _pocket(db, rich)
    assert left == 50000 and arrears == 0
    line = "\n".join(await _chron(db, rich, "disaster"))
    assert "封顶" in line and "少冲了 2500" in line, line
    assert tide["drained"] == 50000


async def test_yanan_real_numbers() -> None:
    """晏安 11-02 的真实数：结算前 2,102,870，黑潮。新规下周潮压到 50%，岸税免交，口袋剩 1,051,435。"""
    db, rich, _ = await _island(None, "ttc-yanan-", 2102870)
    tide, res, avg = await _settle_week(db, "high")
    _, tide_taken, tide_cut, _ = await _ledger(db, rich)
    assert tide_taken == 1051435
    assert tide_cut == 1554652 - 1051435
    left, arrears = await _pocket(db, rich)
    assert left == 1051435 and arrears == 0
    assert (await _bill(db, rich))[0] == 0


async def test_new_account_exempt_still_tide_only() -> None:
    """本周新号免征：没有税单，不抵不封；周潮照冲（台账有）。"""
    db, rich, _ = await _island(None, "ttc-new-", 2000)
    db.now = lambda: _cst_ts(2026, 8, 31, 9)  # 周一早上才登记
    newbie = await _enroll(db, "newbie@example.com", "新号")
    await _set(db, newbie, 100000)
    db.now = lambda: NEXT_MON
    tide, res, avg = await _settle_week(db, "low")
    assert await _bill(db, newbie) is None
    ledger = await _ledger(db, newbie)
    assert ledger[0] == 100000 and ledger[1] == 14000
    left, arrears = await _pocket(db, newbie)
    assert left == 86000 and arrears == 0
    assert res["skipped_new"] >= 1


async def test_storm_shutter_and_side_effects_unchanged() -> None:
    """风暴窗板仍然只改票数（x0.85），抵税用的是实冲数。"""
    db, rich, _ = await _island(None, "ttc-shutter-", 100000)
    async with db.connect() as conn:
        await conn.execute(
            "INSERT INTO hut_fittings (steward_id, slot, item_key, installed_at) VALUES (?,?,?,?)",
            (rich, "window", "storm_shutter", ENROLL_TUE),
        )
        await conn.commit()
    tide, res, avg = await _settle_week(db, "low")
    _, tide_taken, _, _ = await _ledger(db, rich)
    assert tide_taken == max(1, int(14000 * 0.85)) == 11900
    assert (await _bill(db, rich))[3] == 11900  # 抵税 = 实冲数


async def test_idempotent_repeat_calls() -> None:
    """重复调用不重复冲、不重复抵、不重复封顶；税单被清标记重跑也不重复记欠。"""
    from server import disaster, tax

    db, rich, _ = await _island(None, "ttc-idem-", 100000)
    await _settle_week(db, "low")
    snap1 = (await _pocket(db, rich), await _ledger(db, rich), await _bill(db, rich))
    async with db.connect() as conn:
        assert await disaster.ensure_weekly_tide(conn, week_id=WEEK, intensity="high") is None
        assert await tax.ensure_shore_tax(conn, ts=NEXT_MON) is None
        await conn.commit()
    assert snap1 == (await _pocket(db, rich), await _ledger(db, rich), await _bill(db, rich))
    # 税标记被清、再跑一遍：已有税单不重复开、不重复记欠、不重复纪事
    n_before = len(await _chron(db, rich, "tax"))
    async with db.connect() as conn:
        await conn.execute("DELETE FROM world_flags WHERE flag_key=?", (f"shore_tax:{WEEK}",))
        await tax.ensure_shore_tax(conn, ts=NEXT_MON)
        await conn.commit()
    assert snap1 == (await _pocket(db, rich), await _ledger(db, rich), await _bill(db, rich))
    assert len(await _chron(db, rich, "tax")) == n_before
    async with db.connect() as conn:
        rows = (await (await conn.execute(
            "SELECT COUNT(*) FROM weekly_tide_ledger WHERE steward_id=? AND week_id=?", (rich, WEEK)
        )).fetchone())[0]
    assert rows == 1


async def test_status_and_sheet_show_offset() -> None:
    from server import tax

    db, rich, _ = await _island(None, "ttc-text-", 100000)
    await _settle_week(db, "low")
    async with db.connect() as conn:
        conn.row_factory = None
        snap = await tax.snapshot(conn, rich, ts=NEXT_MON)
    text = tax._status_text(snap)
    assert "浅潮已冲 14000，抵税 14000" in text, text
    assert "50%" in text
    assert snap["mine"]["tide_offset"] == 14000
    assert snap["take_cap_pct"] == 50
    assert "50%" in tax.TAX_HELP and "抵" in tax.TAX_HELP


def test_old_db_upgrades_smoothly() -> None:
    """老库（没有 weekly_tide_ledger、shore_tax_bills 没有新列）启动后自动补齐，老税单不丢。"""
    asyncio.run(_old_db())


async def _old_db() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="ttc-old-"))
    db = await _boot(tmp)
    sid = await _enroll(db, "old@example.com", "老岛民")
    async with db.connect() as conn:
        await conn.execute(
            "INSERT INTO shore_tax_bills (steward_id, week_id, assessed, paid, tickets_at) "
            "VALUES (?, '2026-W01', 123, 100, 5000)", (sid,)
        )
        await conn.commit()
    path = tmp / "relay.db"
    raw = sqlite3.connect(path)
    raw.execute("DROP TABLE weekly_tide_ledger")
    raw.execute("ALTER TABLE shore_tax_bills RENAME TO _old_bills")
    raw.execute(
        "CREATE TABLE shore_tax_bills (steward_id INTEGER NOT NULL, week_id TEXT NOT NULL, "
        "assessed INTEGER NOT NULL DEFAULT 0, paid INTEGER NOT NULL DEFAULT 0, "
        "tickets_at INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (steward_id, week_id))"
    )
    raw.execute("INSERT INTO shore_tax_bills SELECT steward_id, week_id, assessed, paid, tickets_at FROM _old_bills")
    raw.execute("DROP TABLE _old_bills")
    raw.commit()
    cols = [r[1] for r in raw.execute("PRAGMA table_info(shore_tax_bills)")]
    assert "tide_offset" not in cols
    raw.close()
    await db.init_db()
    await db.init_db()  # 重复启动也不炸
    raw = sqlite3.connect(path)
    cols = [r[1] for r in raw.execute("PRAGMA table_info(shore_tax_bills)")]
    assert {"tide_offset", "cap_cut", "pocket_before"} <= set(cols)
    assert raw.execute("SELECT name FROM sqlite_master WHERE name='weekly_tide_ledger'").fetchone()
    row = raw.execute(
        "SELECT assessed, paid, tide_offset, cap_cut, pocket_before FROM shore_tax_bills WHERE week_id='2026-W01'"
    ).fetchone()
    raw.close()
    assert row == (123, 100, 0, 0, 0)


async def _notice_counts(db) -> dict[str, int]:
    from server import tide_tax_notice as tn

    async with db.connect() as conn:
        notice = (await (await conn.execute("SELECT COUNT(*) FROM hui_notices WHERE body=?", (tn.notice_text(),))).fetchone())[0]
        news = (await (await conn.execute("SELECT COUNT(*) FROM chronicle WHERE action=?", (tn.TIDE_TAX_CAP_ACTION,))).fetchone())[0]
        flag = (await (await conn.execute("SELECT COUNT(*) FROM world_flags WHERE flag_key=?", (tn.TIDE_TAX_CAP_FLAG,))).fetchone())[0]
    return {"notice": int(notice), "news": int(news), "flag": int(flag)}


def test_launch_notice_once_and_fresh_island_silent() -> None:
    asyncio.run(_notice())


async def _notice() -> None:
    from server import tide_tax_notice as tn

    assert tn.TIDE_TAX_CAP_FLAG == "tide_tax_cap_notice_v1"
    text = tn.notice_text()
    assert "抵本周岸税" in text and "50%" in text and "黑潮已冲" in text
    # 全新的岛：不写告示，标记照写
    db = await _boot(Path(tempfile.mkdtemp(prefix="ttc-notice-")))
    assert await _notice_counts(db) == {"notice": 0, "news": 0, "flag": 1}
    # 老岛升级：岛上有人、标记还没有
    await _enroll(db, "n1@example.com", "老岛民")
    async with db.connect() as conn:
        await conn.execute("DELETE FROM world_flags WHERE flag_key=?", (tn.TIDE_TAX_CAP_FLAG,))
        await conn.commit()
    await db.init_db()
    assert await _notice_counts(db) == {"notice": 1, "news": 1, "flag": 1}
    async with db.connect() as conn:
        tag = (await (await conn.execute("SELECT tag FROM hui_notices WHERE body=?", (text,))).fetchone())[0]
    assert tag == "厅示"
    await db.init_db()
    async with db.connect() as conn:
        assert await tn.announce_tide_tax_cap(conn) == 0
        await conn.commit()
    assert await _notice_counts(db) == {"notice": 1, "news": 1, "flag": 1}
