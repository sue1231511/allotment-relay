#!/usr/bin/env python3
"""周潮天灾：一周一次、低中高随机、只冲 3 万以上；撒网恢复原数值。"""
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
    from server.disaster import levy_amount

    assert levy_amount(120, "high") == 0
    assert levy_amount(29999, "high") == 0
    assert levy_amount(30000, "high") == 0
    assert levy_amount(40000, "low") == int(10000 * 0.20)
    assert levy_amount(40000, "mid") == int(10000 * 0.45)
    assert levy_amount(40000, "high") == int(10000 * 0.75)
    rich = levy_amount(90000, "high")
    assert rich == int(60000 * 0.75)
    assert 90000 - rich == 45000


def test_human_week_id_cst_monday() -> None:
    from server.disaster import human_week_id, week_flag_key

    # 2026-08-23 15:00 UTC = 2026-08-23 23:00 CST, Sunday of ISO week 34
    assert human_week_id(1787497200) == "2026-W34"
    # 2026-08-23 16:00 UTC = 2026-08-24 00:00 CST, Monday week 35
    assert human_week_id(1787500800) == "2026-W35"
    assert week_flag_key("2026-W35") == "weekly_tide:2026-W35"


def test_net_payout_uses_sell_cut() -> None:
    from server.gear import fish_catch_payout

    stats = {
        "bait": {"tier": 1, "catch": 0.0},
        "rod": {"tier": 1, "catch": 0.04},
        "net": {"tier": 5, "catch": 0.34},
    }
    mult, bonus = fish_catch_payout(stats, mode="net")
    assert mult == 1.0 + 0.34 * 1.25 + 5 * 0.05
    assert bonus == 10
    cast_mult, _ = fish_catch_payout(stats, mode="cast")
    assert cast_mult > 1.0


async def _test_weekly_tide_only_over_30k() -> None:
    from server import disaster

    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        db = await _boot(tmp)
        _, sid = await _enroll(db, "rich@t.test", "富户")
        _, poor_id = await _enroll(db, "poor@t.test", "穷户")
        _, mid_id = await _enroll(db, "mid@t.test", "刚满")
        async with db.connect() as conn:
            await conn.execute("DELETE FROM world_flags")
            await conn.execute("DELETE FROM world_pulse")
            await conn.execute(
                "UPDATE stewards SET tickets=90000 WHERE id=?", (sid,)
            )
            await conn.execute(
                "UPDATE stewards SET tickets=8000 WHERE id=?", (poor_id,)
            )
            await conn.execute(
                "UPDATE stewards SET tickets=30000 WHERE id=?", (mid_id,)
            )
            await conn.commit()
            result = await disaster.ensure_weekly_tide(
                conn, week_id="2026-W90", intensity="high"
            )
            await conn.commit()
            rich = (
                await (
                    await conn.execute(
                        "SELECT tickets FROM stewards WHERE id=?", (sid,)
                    )
                ).fetchone()
            )[0]
            poor = (
                await (
                    await conn.execute(
                        "SELECT tickets FROM stewards WHERE id=?", (poor_id,)
                    )
                ).fetchone()
            )[0]
            mid = (
                await (
                    await conn.execute(
                        "SELECT tickets FROM stewards WHERE id=?", (mid_id,)
                    )
                ).fetchone()
            )[0]
            pulse = await (
                await conn.execute(
                    "SELECT effect_type, label FROM world_pulse WHERE effect_type='weekly_tide'"
                )
            ).fetchone()
            again = await disaster.ensure_weekly_tide(
                conn, week_id="2026-W90", intensity="low"
            )
            next_week = await disaster.ensure_weekly_tide(
                conn, week_id="2026-W91", intensity="low"
            )
        assert result and result["hit"] == 1
        assert result["intensity"] == "high"
        assert again is None
        assert rich == 90000 - int(60000 * 0.75)
        assert poor == 8000
        assert mid == 30000
        assert pulse is not None
        assert "黑潮" in pulse[1]
        assert next_week and next_week["intensity"] == "low"
        assert next_week["hit"] == 1


def test_weekly_tide_only_over_30k() -> None:
    asyncio.run(_test_weekly_tide_only_over_30k())


async def _test_net_costs_four() -> None:
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
                "UPDATE stewards SET tickets=3, energy=80, last_bar_shift_at=? WHERE id=?",
                (db.now(), sid),
            )
            await conn.commit()
        try:
            await game.tide_ops(kid, "net")
            raise AssertionError("3 票不该能撒网")
        except ValueError as exc:
            assert "4" in str(exc)
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
        assert "空网" in out or "网到" in out or "T1" in out
        # 先扣 4，渔具加成可能加回一部分，不应还停在 3
        assert tickets != 3


def test_net_costs_four() -> None:
    asyncio.run(_test_net_costs_four())


if __name__ == "__main__":
    test_levy_math()
    test_human_week_id_cst_monday()
    test_net_payout_uses_sell_cut()
    test_weekly_tide_only_over_30k()
    test_net_costs_four()
    print("ok")
