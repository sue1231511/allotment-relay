#!/usr/bin/env python3
"""天灾削票 + 撒网收益下调。"""
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
        sid = (
            await (
                await conn.execute(
                    "SELECT id FROM stewards WHERE key_id=?", (row["id"],)
                )
            ).fetchone()
        )[0]
    return row["id"], sid


def test_levy_math() -> None:
    from server.disaster import levy_amount, surge_levy_amount

    assert levy_amount(120) == 0
    assert levy_amount(2000) == 0
    assert levy_amount(5000) == int(3000 * 0.15)
    rich = levy_amount(90000)
    remain = 90000 - rich
    assert 12000 <= remain <= 18000, remain
    assert rich > 70000
    assert surge_levy_amount(8000) == 0
    assert surge_levy_amount(18000) == int(10000 * 0.22)


def test_net_payout_no_sell_cut() -> None:
    from server.gear import fish_catch_payout

    stats = {
        "bait": {"tier": 1, "catch": 0.0},
        "rod": {"tier": 1, "catch": 0.04},
        "net": {"tier": 5, "catch": 0.34},
    }
    mult, bonus = fish_catch_payout(stats, mode="net")
    assert mult == 1.0
    assert bonus == 5
    cast_mult, _ = fish_catch_payout(stats, mode="cast")
    assert cast_mult > 1.0


def test_net_ev_below_old_t5() -> None:
    """旧 T5 ≈45 票/网；新 T5 应掉到大约一半以下（仍比 T1 强）。"""
    from server import config
    from server.catalog import GEAR_TIERS, SEA_CATCH

    def ev_sell(cap: int) -> float:
        total = 0.0
        for tide in ("ebb", "slack", "flood"):
            pool = []
            for key, meta in SEA_CATCH.items():
                if tide not in meta.get("tides", []):
                    continue
                if meta.get("rarity", 1) > cap:
                    continue
                pool.append((meta["sell"], max(1, 7 - meta.get("rarity", 1))))
            tw = sum(w for _, w in pool)
            total += sum(s * w for s, w in pool) / tw
        return total / 3

    net = next(x for x in GEAR_TIERS["net"] if x["tier"] == 5)
    cap = min(config.NET_RARITY_BASE + net["rarity"], config.NET_RARITY_HARD_CAP)
    assert cap <= 3
    empty = max(
        config.NET_EMPTY_MIN,
        config.NET_EMPTY_BASE - net["empty"] - net["catch"] * 0.4,
    )
    sell = ev_sell(cap)
    ev = (1 - empty) * (sell + net["tier"]) - config.NET_TICKET_COST
    assert ev < 25, ev
    assert ev > 8, ev
    assert ev / net["energy"] < 3.5


async def _test_black_tide_hits_rich() -> None:
    from server import disaster

    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        db = await _boot(tmp)
        _, sid = await _enroll(db, "rich@t.test", "富户")
        _, poor_id = await _enroll(db, "poor@t.test", "穷户")
        async with db.connect() as conn:
            await conn.execute("DELETE FROM world_flags")
            await conn.execute("DELETE FROM world_pulse")
            await conn.execute(
                "UPDATE stewards SET tickets=90000 WHERE id=?", (sid,)
            )
            await conn.execute(
                "UPDATE stewards SET tickets=800 WHERE id=?", (poor_id,)
            )
            await conn.execute(
                """
                INSERT INTO satchel (steward_id, item, quantity) VALUES (?,?,?)
                ON CONFLICT(steward_id, item) DO UPDATE SET quantity=10
                """,
                (sid, "fish_mackerel", 10),
            )
            await conn.commit()
            result = await disaster.ensure_black_tide(conn)
            await conn.commit()
            rich = await (
                await conn.execute(
                    "SELECT tickets FROM stewards WHERE id=?", (sid,)
                )
            ).fetchone()
            poor = await (
                await conn.execute(
                    "SELECT tickets FROM stewards WHERE id=?", (poor_id,)
                )
            ).fetchone()
            fish = await (
                await conn.execute(
                    "SELECT quantity FROM satchel WHERE steward_id=? AND item=?",
                    (sid, "fish_mackerel"),
                )
            ).fetchone()
            pulse = await (
                await conn.execute(
                    "SELECT effect_type FROM world_pulse WHERE effect_type='black_tide'"
                )
            ).fetchone()
            again = await disaster.ensure_black_tide(conn)
        assert result and result["hit"] == 1
        assert again is None
        assert 12000 <= rich[0] <= 18000
        assert poor[0] == 800
        assert fish[0] < 10
        assert pulse is not None


def test_black_tide_hits_rich() -> None:
    asyncio.run(_test_black_tide_hits_rich())


async def _test_surge_only_over_cap() -> None:
    from server import disaster

    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        db = await _boot(tmp)
        _, sid = await _enroll(db, "mid@t.test", "中产")
        async with db.connect() as conn:
            await conn.execute(
                "UPDATE stewards SET tickets=18000 WHERE id=?", (sid,)
            )
            await conn.commit()
            result = await disaster.apply_surge_levy(conn)
            await conn.commit()
            left = (
                await (
                    await conn.execute(
                        "SELECT tickets FROM stewards WHERE id=?", (sid,)
                    )
                ).fetchone()
            )[0]
        assert result["hit"] == 1
        assert left == 18000 - int(10000 * 0.22)


def test_surge_only_over_cap() -> None:
    asyncio.run(_test_surge_only_over_cap())


async def _test_net_costs_eight() -> None:
    from server import game

    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        db = await _boot(tmp)
        kid, sid = await _enroll(db, "net@t.test", "网民")
        async with db.connect() as conn:
            await conn.execute(
                """
                INSERT OR REPLACE INTO steward_gear
                    (steward_id, bait_tier, rod_tier, net_tier)
                VALUES (?,?,?,?)
                """,
                (sid, 1, 0, 1),
            )
            await conn.execute(
                "UPDATE stewards SET tickets=5, energy=80, last_bar_shift_at=? WHERE id=?",
                (db.now(), sid),
            )
            await conn.commit()
        try:
            await game.tide_ops(kid, "net")
            raise AssertionError("5 票不该能撒网")
        except ValueError as exc:
            assert "8" in str(exc)
        async with db.connect() as conn:
            await conn.execute(
                "UPDATE stewards SET tickets=30 WHERE id=?", (sid,)
            )
            await conn.commit()
        out = await game.tide_ops(kid, "net")
        async with db.connect() as conn:
            tickets = (
                await (
                    await conn.execute(
                        "SELECT tickets FROM stewards WHERE id=?", (sid,)
                    )
                ).fetchone()
            )[0]
        assert "8" in out or "空网" in out or "网到" in out or "T1" in out
        assert tickets <= 23  # 至少扣 8，最多再加档位 1 票 + 偶发


def test_net_costs_eight() -> None:
    asyncio.run(_test_net_costs_eight())


if __name__ == "__main__":
    test_levy_math()
    test_net_payout_no_sell_cut()
    test_net_ev_below_old_t5()
    test_black_tide_hits_rich()
    test_surge_only_over_cap()
    test_net_costs_eight()
    print("ok")
