#!/usr/bin/env python3
"""作物月令：买种/下地看当月，温室种菜豁免，已种继续长。"""
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


def test_year_round_and_windows() -> None:
    from server import season
    from server.catalog import CROPS

    with season.pinned_month(8):
        for key in ("kale", "beet", "fogpea", "kelp"):
            assert season.crop_in_season(key), key
            assert CROPS[key].get("months") in (None, (), [])
        assert season.crop_in_season("mango")
        assert season.crop_in_season("chili")
        assert not season.crop_in_season("garlic")
        assert not season.crop_in_season("blueberry")
        assert not season.crop_in_season("lime")
        assert season.next_in_season_month("garlic") == 11
        assert "当月可种" in season.season_tag("kale")
        assert "休市" in season.season_tag("garlic")
        assert "十一月" in season.season_tag("garlic")

    with season.pinned_month(1):
        assert season.crop_in_season("garlic")
        assert season.crop_in_season("lime")
        assert not season.crop_in_season("mango")
        assert not season.crop_in_season("chili")


def test_catalog_marks_month() -> None:
    from server import season
    from server.catalog import crop_catalog_line

    with season.pinned_month(8):
        kale = crop_catalog_line("kale")
        garlic = crop_catalog_line("garlic")
        assert "全年" in kale and "当月可种" in kale
        assert "休市" in garlic and "十一月" in garlic


async def test_public_stats_include_month() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="season-stats-"))
    await _boot(tmp)
    from server import db, season

    with season.pinned_month(8):
        stats = await db.public_stats()
    assert stats["month"] == 8
    assert stats["month_label"] == "八月"
    assert "月令" in stats["climate"]
    assert "八月" in (stats.get("climate_notes") or {}).get("season", "")


def test_league_skips_off_season_crop() -> None:
    from server import season
    from server.multi import _pick_league_goal

    with season.pinned_month(8):
        assert _pick_league_goal(4)["key"] == "honey"
        assert _pick_league_goal(2)["key"] == "crop_kale"
    with season.pinned_month(5):
        assert _pick_league_goal(4)["key"] == "crop_blueberry"


async def test_sow_and_buy_lock() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="season-sow-"))
    db = await _boot(tmp)
    from server import game, season

    kid, sid = await _enroll(db, "sz@example.com", "月令人")
    async with db.connect() as conn:
        await db.add_item(conn, sid, "seed_garlic", 3)
        await db.add_item(conn, sid, "seed_kale", 2)
        await conn.execute("UPDATE stewards SET tickets=tickets+400 WHERE id=?", (sid,))
        await conn.commit()

    with season.pinned_month(8):
        blocked = await game.plot_ops(kid, "sow 1 大蒜")
        assert "不在当月" in blocked or "休市" in blocked or "⚠" in blocked, blocked

        kale = await game.plot_ops(kid, "sow 2 甘蓝")
        assert "甘蓝" in kale and "⚠" not in kale, kale

        buy_off = await game.plot_ops(kid, "buy 1 大蒜")
        assert "不在当月" in buy_off or "⚠" in buy_off, buy_off

        buy_ok = await game.plot_ops(kid, "buy 1 甘蓝")
        assert "购入" in buy_ok and "⚠" not in buy_ok, buy_ok

        weather = await game.plot_ops(kid, "weather")
        assert "月令" in weather and "八月" in weather, weather
        catalog = await game.plot_ops(kid, "catalog")
        assert "当月可种" in catalog and "休市" in catalog, catalog

        from server import tt
        try:
            await tt.tt_ops(kid, "buy 大蒜种 1")
            raise AssertionError("tt should refuse off-season garlic seed")
        except ValueError as exc:
            assert "不在当月" in str(exc), exc
        tt_ok = await tt.tt_ops(kid, "buy 甘蓝种 1")
        assert "购入" in tt_ok, tt_ok
        tt_cat = await tt.tt_ops(kid, "catalog")
        assert "当月可种" in tt_cat and "休市" in tt_cat, tt_cat


async def test_greenhouse_ignores_month() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="season-gh-"))
    db = await _boot(tmp)
    from server import game, season

    kid, sid = await _enroll(db, "gh@example.com", "温室人")
    async with db.connect() as conn:
        await db.add_item(conn, sid, "seed_garlic", 2)
        await conn.execute("UPDATE stewards SET tickets=tickets+400, greenhouse=1 WHERE id=?", (sid,))
        await conn.execute(
            "INSERT INTO parcels (steward_id, slot, orchard, greenhouse, tended) VALUES (?, 1, 0, 1, 0)",
            (sid,),
        )
        await conn.execute(
            "UPDATE stewards SET greenhouse_count=1 WHERE id=?", (sid,)
        )
        await conn.commit()

    with season.pinned_month(8):
        planted = await game.plot_ops(kid, "sow 99 大蒜")
        assert "棚1" in planted and "大蒜" in planted, planted
        assert "不在当月" not in planted, planted
        outdoor = await game.plot_ops(kid, "sow 1 大蒜")
        assert "⚠" in outdoor or "不在当月" in outdoor, outdoor


async def test_planted_off_season_keeps_growing() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="season-keep-"))
    db = await _boot(tmp)
    from server import game, season

    kid, sid = await _enroll(db, "keep@example.com", "过季人")
    async with db.connect() as conn:
        await conn.execute(
            """
            UPDATE parcels SET crop='garlic', planted_at=?, tended=1, greenhouse=0,
            grow_target=60, grow_pace=1, harvest_left=0
            WHERE steward_id=? AND slot=1 AND COALESCE(orchard,0)=0
            """,
            (db.now() - 10_000, sid),
        )
        await conn.commit()

    with season.pinned_month(8):
        status = await game.plot_ops(kid, "status")
        assert "大蒜" in status, status
        gathered = await game.plot_ops(kid, "gather 1")
        assert "大蒜" in gathered or "蒜" in gathered, gathered


def main() -> None:
    test_year_round_and_windows()
    test_catalog_marks_month()
    test_league_skips_off_season_crop()
    asyncio.run(test_public_stats_include_month())
    asyncio.run(test_sow_and_buy_lock())
    asyncio.run(test_greenhouse_ignores_month())
    asyncio.run(test_planted_off_season_keeps_growing())
    print("season tests ok")


if __name__ == "__main__":
    main()
