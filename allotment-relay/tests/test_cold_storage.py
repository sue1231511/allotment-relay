#!/usr/bin/env python3
"""保鲜期：存潮柜/冰箱只是变慢，不是永远不坏，存取一下也不会重新计时；转手变质时间跟着货走。"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

import pytest

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


async def _enroll(db, email: str, name: str, *, fittings: bool = False) -> tuple[int, int]:
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
        if fittings:
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


async def _duty(db, *sids: int) -> None:
    async with db.connect() as conn:
        for sid in sids:
            await conn.execute(
                "UPDATE stewards SET last_active_at=?, last_bar_shift_at=? WHERE id=?",
                (db.now(), db.now(), sid),
            )
        await conn.commit()


async def _steward(db, sid: int) -> dict:
    return await db.get_steward_by_id(sid)


async def _life_left(db, sid: int, item: str, loc: str = "satchel") -> list[tuple[int, float]]:
    """每一批 (件数, 剩余寿命小时)。"""
    async with db.connect() as conn:
        rows = await (await conn.execute(
            "SELECT qty, spoil_at FROM item_trait_batches WHERE steward_id=? AND loc=? AND item=? ORDER BY id",
            (sid, loc, item))).fetchall()
    now = db.now()
    return [(int(q), (int(s) - now) / H) for q, s in rows]


async def _qty(db, sid: int, item: str) -> int:
    async with db.connect() as conn:
        row = await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item=?", (sid, item))).fetchone()
    return int(row[0]) if row else 0


# ── 潮柜 ──────────────────────────────────────────────────────────────

def test_cabinet_slows_spoilage_but_does_not_reset_or_stop_it(monkeypatch) -> None:
    asyncio.run(_cabinet(monkeypatch))


async def _cabinet(monkeypatch) -> None:
    from server import hut, item_traits

    db = await _boot(Path(tempfile.mkdtemp(prefix="cold-cab-")))
    k, a = await _enroll(db, "a@x.com", "柜主", fittings=True)
    async with db.connect() as conn:
        await item_traits.grant_satchel(conn, a, "fish_herring", 5)       # 鱼 36 小时
        await conn.commit()
    put = await hut.cabinet_command(await _steward(db, a), ["存", "fish_herring", "5"])
    assert "入柜" in put and await _qty(db, a, "fish_herring") == 0
    (qty, left), = await _life_left(db, a, "fish_herring", "cabinet")
    assert qty == 5 and abs(left - 36 * 1.8) < 0.05, "柜里寿命按 ×1.8 放慢"
    _travel(monkeypatch, db, 30)
    await _duty(db, a)
    out = await hut.cabinet_command(await _steward(db, a), ["取", "fish_herring", "5"])
    assert "取出" in out and await _qty(db, a, "fish_herring") == 5
    (qty, left), = await _life_left(db, a, "fish_herring")
    assert qty == 5 and abs(left - (36 - 30 / 1.8)) < 0.05, f"取出来只剩 {left:.2f} 小时（不是重新计时的 36）"


def test_cabinet_store_take_loop_does_not_refresh(monkeypatch) -> None:
    asyncio.run(_loop(monkeypatch))


async def _loop(monkeypatch) -> None:
    from server import hut, item_traits

    db = await _boot(Path(tempfile.mkdtemp(prefix="cold-loop-")))
    k, a = await _enroll(db, "a@x.com", "反复存取", fittings=True)
    async with db.connect() as conn:
        await item_traits.grant_satchel(conn, a, "fish_herring", 4)
        await conn.commit()
    _travel(monkeypatch, db, 20)                 # 鱼已经放了 20 小时，还剩 16
    await _duty(db, a)
    for _ in range(6):
        await hut.cabinet_command(await _steward(db, a), ["存", "fish_herring", "4"])
        await hut.cabinet_command(await _steward(db, a), ["取", "fish_herring", "4"])
    (qty, left), = await _life_left(db, a, "fish_herring")
    assert qty == 4 and left < 16.01, f"来回存取不能让鱼变新鲜（剩 {left:.2f}h，原本最多 16h）"
    assert left > 15.9


def test_cabinet_goods_eventually_spoil_and_player_is_told(monkeypatch) -> None:
    asyncio.run(_cabinet_spoils(monkeypatch))


async def _cabinet_spoils(monkeypatch) -> None:
    from server import hut, item_traits

    db = await _boot(Path(tempfile.mkdtemp(prefix="cold-rot-")))
    k, a = await _enroll(db, "a@x.com", "放太久", fittings=True)
    async with db.connect() as conn:
        await item_traits.grant_satchel(conn, a, "fish_herring", 5)
        await item_traits.grant_satchel(conn, a, "crop_kale", 6)
        await conn.commit()
    await hut.cabinet_command(await _steward(db, a), ["存", "fish_herring", "5"])
    await hut.cabinet_command(await _steward(db, a), ["存", "crop_kale", "6"])
    _travel(monkeypatch, db, 70)                  # 鱼 36×1.8=64.8h 到期；甘蓝 72×1.8=129.6h 没到
    await _duty(db, a)
    status = await hut.cabinet_command(await _steward(db, a), [])
    assert "变质丢弃" in status and "×5" in status and "放坏了" in status, status
    assert "甘蓝" in status and "fish_herring" not in status.split("变质丢弃")[1].split("潮柜 ")[1]
    async with db.connect() as conn:
        rows = dict(await (await conn.execute(
            "SELECT item, quantity FROM hut_cabinet WHERE steward_id=?", (a,))).fetchall())
        spoil_log = await (await conn.execute(
            "SELECT text FROM chronicle WHERE action='spoil' AND actor_id=?", (a,))).fetchall()
    assert rows == {"crop_kale": 6}
    assert spoil_log, "变质丢弃要留纪事"


def test_cabinet_take_reports_spoilage_even_when_nothing_left(monkeypatch) -> None:
    asyncio.run(_cabinet_take_report(monkeypatch))


async def _cabinet_take_report(monkeypatch) -> None:
    from server import hut, item_traits

    db = await _boot(Path(tempfile.mkdtemp(prefix="cold-take-")))
    k, a = await _enroll(db, "a@x.com", "取空了", fittings=True)
    async with db.connect() as conn:
        await item_traits.grant_satchel(conn, a, "fish_herring", 3)
        await conn.commit()
    await hut.cabinet_command(await _steward(db, a), ["存", "fish_herring", "3"])
    _travel(monkeypatch, db, 70)
    await _duty(db, a)
    with pytest.raises(ValueError) as exc:
        await hut.cabinet_command(await _steward(db, a), ["取", "fish_herring", "3"])
    assert "变质丢弃" in str(exc.value) and "×3" in str(exc.value)


def test_removing_cabinet_returns_goods_with_scaled_life(monkeypatch) -> None:
    asyncio.run(_dump(monkeypatch))


async def _dump(monkeypatch) -> None:
    from server import hut, item_traits

    db = await _boot(Path(tempfile.mkdtemp(prefix="cold-dump-")))
    k, a = await _enroll(db, "a@x.com", "拆柜", fittings=True)
    async with db.connect() as conn:
        await item_traits.grant_satchel(conn, a, "fish_herring", 2)
        await conn.commit()
    await hut.cabinet_command(await _steward(db, a), ["存", "fish_herring", "2"])
    _travel(monkeypatch, db, 18)
    async with db.connect() as conn:
        await hut.dump_cabinet(conn, a)
        await conn.commit()
    (qty, left), = await _life_left(db, a, "fish_herring")
    assert qty == 2 and abs(left - (36 - 18 / 1.8)) < 0.05


# ── 冰箱 ──────────────────────────────────────────────────────────────

def test_fridge_slows_cooked_food_but_it_still_spoils(monkeypatch) -> None:
    asyncio.run(_fridge(monkeypatch))


async def _fridge(monkeypatch) -> None:
    from server import item_traits, kitchen
    from server.catalog import KITCHEN_DISHES, dish_item

    db = await _boot(Path(tempfile.mkdtemp(prefix="cold-fridge-")))
    k, a = await _enroll(db, "a@x.com", "冰箱主", fittings=True)
    dish = dish_item(next(iter(KITCHEN_DISHES)), 3)
    async with db.connect() as conn:
        await item_traits.grant_satchel(conn, a, dish, 3)
        await conn.commit()
    base = (await _life_left(db, a, dish))[0][1]            # 熟菜在行囊里的总寿命（小时）
    put = await kitchen.fridge_put(await _steward(db, a), dish, 3)
    assert "入冰箱" in put
    (_, left), = await _life_left(db, a, dish, "fridge")
    assert abs(left - base * 3.5) < 0.05
    _travel(monkeypatch, db, 10)
    await _duty(db, a)
    out = await kitchen.fridge_take(await _steward(db, a), dish, 2)
    assert "回行囊" in out
    (qty, left), = await _life_left(db, a, dish)
    assert qty == 2 and abs(left - (base - 10 / 3.5)) < 0.05, "取出来按冰箱里过的时间折算，不是重新计时"
    # 剩下的 1 份放到冰箱也会坏
    _travel(monkeypatch, db, base * 3.5)
    await _duty(db, a)
    status = await kitchen.fridge_status_text(await _steward(db, a))
    assert "变质丢弃" in status and "放坏了" in status, status


# ── 转手：变质时间跟着货走 ────────────────────────────────────────────

CHANNELS = ("gift", "market", "swap", "larder", "handoff_online", "handoff_offline", "contract")


@pytest.mark.parametrize("channel", CHANNELS)
def test_freshness_follows_the_goods_through_every_channel(channel: str, monkeypatch) -> None:
    from server import market_stall_gust

    async def _no_gust(conn, steward_id):
        return ""

    monkeypatch.setattr(market_stall_gust, "maybe_after_sell", _no_gust)
    asyncio.run(_transfer(channel, monkeypatch))


async def _transfer(channel: str, monkeypatch) -> None:
    from server import item_traits, market, multi
    from server.game import shed, tide, tote

    db = await _boot(Path(tempfile.mkdtemp(prefix=f"cold-{channel}-")))
    ka, a = await _enroll(db, "a@x.com", "转手甲")
    kb, b = await _enroll(db, "b@x.com", "转手乙")
    item, qty = "fish_herring", 5
    async with db.connect() as conn:
        await item_traits.grant_satchel(conn, a, item, qty)
        await conn.commit()
    _travel(monkeypatch, db, 30)                      # 鱼已经放了 30 小时，还剩 6
    await _duty(db, a, b)

    if channel == "gift":
        await tote.tote_ops(ka, f"gift 转手乙 {item} {qty}")
    elif channel == "market":
        await market.market_ops(ka, f"sell {item} {qty} 10")
        await market.market_ops(kb, "buy 1")
    elif channel == "swap":
        await shed.swap_ops(ka, f"offer {item} {qty}")
        await shed.swap_ops(kb, "claim 1")
    elif channel == "larder":
        await multi.alliance_ops(ka, f"donate {item} {qty}")
        await multi.alliance_ops(kb, f"draw {item} {qty}")
    elif channel in ("handoff_online", "handoff_offline"):
        async with db.connect() as conn:
            await conn.execute(
                "UPDATE stewards SET last_active_at=? WHERE id=?",
                (db.now() if channel == "handoff_online" else 0, b))
            await conn.commit()
        await shed.shed_ops(ka, f"handoff 转手乙 {item} {qty}")
        if channel == "handoff_offline":
            async with db.connect() as conn:
                await tide._collect_handoffs(conn, b)
                await conn.commit()
    elif channel == "contract":
        await multi.contract_ops(kb, f"post {item} {qty} 20")
        await multi.contract_ops(ka, "fill 1")

    assert await _qty(db, b, item) == qty
    (got_qty, left), = await _life_left(db, b, item)
    assert got_qty == qty and 5.9 < left < 6.01, f"{channel}: 收货人拿到的应是只剩 6 小时的货，实际 {left:.2f}h"
    assert await _life_left(db, a, item) == [], "送出的批次不能留在原主账上"
    _travel(monkeypatch, db, 7)                       # 再过 7 小时：总共 37 小时，鱼该坏了
    await _duty(db, b)
    listing = await tote.tote_ops(kb, "list")
    assert "变质丢弃" in listing and "×5" in listing, f"{channel}: 收到的货也会变质\n{listing}"
    assert await _qty(db, b, item) == 0
