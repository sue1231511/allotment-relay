#!/usr/bin/env python3
"""小馆上菜参考价提示；床（hut_ops 睡）回精力。"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_reference_price_anchor() -> None:
    from server.catalog import (
        KITCHEN_DISHES,
        dish_energy,
        dish_item,
        eatery_reference_price,
        suggested_price,
    )

    for key in ("garlic_oyster", "salt_crab", "durian_mousse", "mussel_garlic"):
        for stars in (1, 3, 5):
            item = dish_item(key, stars)
            ref = eatery_reference_price(item)
            vend = suggested_price(item)
            energy = dish_energy(item)
            # 参考价 ≥ 系统回收×1.25 且 ≥ 精力×3 —— 卖食客明显比 vend 赚
            assert ref >= vend * 1.2, (key, stars, ref, vend)
            assert ref >= energy * 3 - 1, (key, stars, ref, energy)
    r1 = eatery_reference_price(dish_item("garlic_oyster", 1))
    r3 = eatery_reference_price(dish_item("garlic_oyster", 3))
    r5 = eatery_reference_price(dish_item("garlic_oyster", 5))
    assert r1 < r3 < r5, (r1, r3, r5)
    # 系统回收压得低：3★ 约材料价 +10%
    from server.catalog import dish_ingredient_cost, dish_sell_price
    cost = dish_ingredient_cost("garlic_oyster")
    v3 = dish_sell_price("garlic_oyster", 3)
    assert cost <= v3 <= cost * 1.2, (cost, v3)


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


def test_stock_pricing_flow() -> None:
    asyncio.run(_test_stock_pricing_flow())


async def _test_stock_pricing_flow() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="eatery-price-"))
    db = await _boot(tmp)
    from server import eatery

    kid, sid = await _enroll(db, "owner@example.com", "掌柜")
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET hut_built=1, tickets=200 WHERE id=?", (sid,)
        )
        await conn.execute(
            "INSERT INTO hut_fittings (steward_id, slot, item_key, installed_at)"
            " VALUES (?, 'soft_1', 'fridge', ?)",
            (sid, db.now()),
        )
        await db.add_item(conn, sid, "dish_salt_crab_s4", 3)
        await conn.commit()
    s = await db.get_steward_by_id(sid)
    await eatery.eatery_command(s, "open 潮线小馆")

    s = await db.get_steward_by_id(sid)
    default = await eatery.eatery_command(s, "stock dish_salt_crab_s4")
    assert "参考" in default, default

    custom_high = await eatery.eatery_command(s, "stock dish_salt_crab_s4 999")
    assert "999 票" in custom_high, custom_high
    custom_low = await eatery.eatery_command(s, "stock dish_salt_crab_s4 5")
    assert "5 票" in custom_low, custom_low
    async with db.connect() as conn:
        rows = await (await conn.execute(
            "SELECT price FROM eatery_menu WHERE steward_id=? ORDER BY id", (sid,)
        )).fetchall()
    prices = [r[0] for r in rows]
    assert len(prices) == 3, prices
    from server.catalog import eatery_reference_price
    ref = eatery_reference_price("dish_salt_crab_s4")
    assert prices[0] == ref, (prices, ref)
    assert prices[1] == 999 and prices[2] == 5, prices


def test_bed_rest() -> None:
    asyncio.run(_test_bed_rest())


async def _test_bed_rest() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="bed-rest-"))
    db = await _boot(tmp)
    from server import hut

    kid, sid = await _enroll(db, "sleeper@example.com", "觉主")

    try:
        await hut.hut_ops(kid, "睡")
        raise AssertionError("sleep without hut should refuse")
    except ValueError as exc:
        assert "小屋" in str(exc), exc

    async with db.connect() as conn:
        await conn.execute("UPDATE stewards SET hut_built=1 WHERE id=?", (sid,))
        await conn.commit()
    try:
        await hut.hut_ops(kid, "睡")
        raise AssertionError("sleep without bed should refuse")
    except ValueError as exc:
        assert "床" in str(exc), exc

    async with db.connect() as conn:
        await conn.execute(
            "INSERT INTO hut_fittings (steward_id, slot, item_key, installed_at)"
            " VALUES (?, 'hard_1', 'bed', ?)",
            (sid, db.now()),
        )
        await conn.execute("UPDATE stewards SET energy=10 WHERE id=?", (sid,))
        await conn.commit()
    msg = await hut.hut_ops(kid, "睡")
    assert "精力 +50" in msg, msg
    async with db.connect() as conn:
        energy_now = (await (await conn.execute(
            "SELECT energy FROM stewards WHERE id=?", (sid,)
        )).fetchone())[0]
    assert energy_now == 60, energy_now

    try:
        await hut.hut_ops(kid, "睡")
        raise AssertionError("cooldown should refuse")
    except ValueError as exc:
        assert "换班" in str(exc) or "今天" in str(exc), exc

    async with db.connect() as conn:
        await conn.execute("UPDATE stewards SET bed_rest_at=0, energy=100 WHERE id=?", (sid,))
        await conn.commit()
    try:
        await hut.hut_ops(kid, "睡")
        raise AssertionError("full energy should refuse")
    except ValueError as exc:
        assert "不困" in str(exc), exc


def test_low_energy_hint_mentions_eatery() -> None:
    from server.energy import low_energy_hint

    text = low_energy_hint(3, 100, 12)
    assert "精力不足（3/100）" in text
    assert "这次要 12" in text
    assert "下馆子" in text
    assert "kitchen_ops shop board" in text
    assert "kitchen_ops shop dine 店主名" in text
    assert "kitchen_ops eat 熟菜" in text
    assert "hut_ops 睡" in text
    assert "bar_ops lodge" in text


def test_spend_low_energy_points_to_eatery() -> None:
    asyncio.run(_test_spend_low_energy_points_to_eatery())


async def _test_spend_low_energy_points_to_eatery() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="energy-hint-"))
    db = await _boot(tmp)
    from server import energy

    _, sid = await _enroll(db, "tired@example.com", "饿鬼")
    async with db.connect() as conn:
        await conn.execute("UPDATE stewards SET energy=2 WHERE id=?", (sid,))
        await conn.commit()
        try:
            await energy.spend(conn, sid, 10)
            raise AssertionError("should refuse when energy is too low")
        except ValueError as exc:
            msg = str(exc)
            assert "精力不足" in msg and "下馆子" in msg, msg
            assert "shop dine" in msg and "shop board" in msg, msg


def test_dine_buff() -> None:
    asyncio.run(_test_dine_buff())


async def _test_dine_buff() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="dine-buff-"))
    db = await _boot(tmp)
    from server import energy, eatery

    kid_o, sid_o = await _enroll(db, "owner@example.com", "掌柜")
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET hut_built=1, tickets=200 WHERE id=?", (sid_o,)
        )
        await conn.execute(
            "INSERT INTO hut_fittings (steward_id, slot, item_key, installed_at)"
            " VALUES (?, 'soft_1', 'fridge', ?)",
            (sid_o, db.now()),
        )
        await db.add_item(conn, sid_o, "dish_salt_crab_s4", 1)
        await conn.commit()
    o = await db.get_steward_by_id(sid_o)
    await eatery.eatery_command(o, "open 潮线小馆")
    o = await db.get_steward_by_id(sid_o)
    await eatery.eatery_command(o, "stock dish_salt_crab_s4")

    kid_g, sid_g = await _enroll(db, "guest@example.com", "食客")
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET tickets=150, energy=30, mist_wit=50, standing=60"
            " WHERE id=?",
            (sid_g,),
        )
        await conn.commit()
    g = await db.get_steward_by_id(sid_g)
    msg = await eatery.eatery_command(g, "dine 掌柜")
    assert "饱餐" in msg and "行动精力 -1" in msg, msg

    s = await db.get_steward_by_id(sid_g)
    assert int(s["dine_buff_until"]) > db.now(), s["dine_buff_until"]
    assert "饱餐" in energy.meter_line(s, []), energy.meter_line(s, [])
    assert s["mist_wit"] > 50 and s["standing"] > 60, (s["mist_wit"], s["standing"])

    async with db.connect() as conn:
        before = (await (await conn.execute(
            "SELECT energy FROM stewards WHERE id=?", (sid_g,)
        )).fetchone())[0]
        await energy.spend(conn, sid_g, 5)
        buffed = (await (await conn.execute(
            "SELECT energy FROM stewards WHERE id=?", (sid_g,)
        )).fetchone())[0]
        assert before - buffed == 4, (before, buffed)  # 饱餐：5-1
        await conn.execute(
            "UPDATE stewards SET dine_buff_until=1 WHERE id=?", (sid_g,)
        )
        await energy.spend(conn, sid_g, 5)
        plain = (await (await conn.execute(
            "SELECT energy FROM stewards WHERE id=?", (sid_g,)
        )).fetchone())[0]
        assert buffed - plain == 5, (buffed, plain)  # buff 过期恢复原消耗


def main() -> None:
    test_reference_price_anchor()
    test_low_energy_hint_mentions_eatery()
    asyncio.run(_test_stock_pricing_flow())
    asyncio.run(_test_bed_rest())
    asyncio.run(_test_dine_buff())
    asyncio.run(_test_spend_low_energy_points_to_eatery())
    print("eatery pricing / bed rest / dine buff / energy hint tests ok")


if __name__ == "__main__":
    main()
