#!/usr/bin/env python3
"""作物季节：买种/下地看当季（一周一季），温室种菜种树豁免，已种继续长。"""
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


def test_week_maps_to_season() -> None:
    from server import season

    epoch = season.SEASON_EPOCH
    assert season.current_season(epoch) == "春"
    week = 7 * 24 * 3600
    from datetime import timedelta

    assert season.current_season(epoch + timedelta(days=7)) == "夏"
    assert season.current_season(epoch + timedelta(days=14)) == "秋"
    assert season.current_season(epoch + timedelta(days=21)) == "冬"
    assert season.current_season(epoch + timedelta(days=28)) == "春"
    assert 1 <= season.season_remaining_days(epoch) <= 7


def test_year_round_and_windows() -> None:
    from server import season
    from server.catalog import CROPS

    with season.pinned_season("夏"):
        for key in ("kale", "beet", "fogpea", "kelp"):
            assert season.crop_in_season(key), key
            assert CROPS[key].get("seasons") in (None, (), [])
        assert season.crop_in_season("mango")
        assert season.crop_in_season("chili")
        assert season.crop_in_season("blueberry")
        assert not season.crop_in_season("garlic")
        assert not season.crop_in_season("lime")
        assert not season.crop_in_season("orange")
        assert season.next_in_season("garlic") == "秋"
        assert "当季可种" in season.season_tag("kale")
        assert "休市" in season.season_tag("garlic")
        assert "秋" in season.season_tag("garlic")

    with season.pinned_season("冬"):
        assert season.crop_in_season("garlic")
        assert season.crop_in_season("lime")
        assert season.crop_in_season("orange")
        assert not season.crop_in_season("mango")
        assert not season.crop_in_season("chili")
    with season.pinned_season("春"):
        assert season.crop_in_season("orange")
        assert season.crop_in_season("lime")
        assert not season.crop_in_season("durian")


def test_catalog_marks_season() -> None:
    from server import season
    from server.catalog import crop_catalog_line

    with season.pinned_season("夏"):
        kale = crop_catalog_line("kale")
        garlic = crop_catalog_line("garlic")
        orange = crop_catalog_line("orange")
        assert "全年" in kale and "当季可种" in kale
        assert "休市" in garlic and "秋" in garlic
        assert "果园或温室" in orange


async def test_public_stats_include_season() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="season-stats-"))
    await _boot(tmp)
    from server import db, season

    with season.pinned_season("夏"):
        stats = await db.public_stats()
    assert stats["season"] == "夏"
    assert stats["season_label"] == "夏"
    assert stats["month_label"] == "夏"
    assert "季节" in stats["climate"] or "一周一季" in stats["climate"]
    assert "夏" in (stats.get("climate_notes") or {}).get("season", "")
    assert "一周一季" in (stats.get("climate_notes") or {}).get("season", "")


def test_league_skips_off_season_crop() -> None:
    from server import season
    from server.multi import _pick_league_goal

    with season.pinned_season("冬"):
        assert _pick_league_goal(4)["key"] == "honey"
        assert _pick_league_goal(2)["key"] == "crop_kale"
    with season.pinned_season("春"):
        assert _pick_league_goal(4)["key"] == "crop_blueberry"


async def test_sow_and_buy_lock() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="season-sow-"))
    db = await _boot(tmp)
    from server import game, season

    kid, sid = await _enroll(db, "sz@example.com", "季节人")
    async with db.connect() as conn:
        await db.add_item(conn, sid, "seed_garlic", 3)
        await db.add_item(conn, sid, "seed_kale", 2)
        await conn.execute("UPDATE stewards SET tickets=tickets+400 WHERE id=?", (sid,))
        await conn.commit()

    with season.pinned_season("夏"):
        blocked = await game.plot_ops(kid, "sow 1 大蒜")
        assert "不在当季" in blocked or "休市" in blocked or "⚠" in blocked, blocked

        kale = await game.plot_ops(kid, "sow 2 甘蓝")
        assert "甘蓝" in kale and "⚠" not in kale, kale

        buy_off = await game.plot_ops(kid, "buy 1 大蒜")
        assert "不在当季" in buy_off or "⚠" in buy_off, buy_off

        buy_ok = await game.plot_ops(kid, "buy 1 甘蓝")
        assert "购入" in buy_ok and "⚠" not in buy_ok, buy_ok

        weather = await game.plot_ops(kid, "weather")
        assert "季节" in weather and "夏" in weather and "一周一季" in weather, weather
        catalog = await game.plot_ops(kid, "catalog")
        assert "当季可种" in catalog and "休市" in catalog, catalog

        from server import tt
        try:
            await tt.tt_ops(kid, "buy 大蒜种 1")
            raise AssertionError("tt should refuse off-season garlic seed")
        except ValueError as exc:
            assert "不在当季" in str(exc), exc
        tt_ok = await tt.tt_ops(kid, "buy 甘蓝种 1")
        assert "购入" in tt_ok, tt_ok
        tt_cat = await tt.tt_ops(kid, "catalog")
        assert "当季可种" in tt_cat and "休市" in tt_cat, tt_cat


async def test_greenhouse_ignores_season() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="season-gh-"))
    db = await _boot(tmp)
    from server import game, season

    kid, sid = await _enroll(db, "gh@example.com", "温室人")
    async with db.connect() as conn:
        await db.add_item(conn, sid, "seed_garlic", 2)
        await db.add_item(conn, sid, "seed_orange", 1)
        await conn.execute("UPDATE stewards SET tickets=tickets+400, greenhouse=1 WHERE id=?", (sid,))
        await conn.execute(
            "INSERT INTO parcels (steward_id, slot, orchard, greenhouse, tended) VALUES (?, 1, 0, 1, 0)",
            (sid,),
        )
        await conn.execute(
            "UPDATE stewards SET greenhouse_count=1 WHERE id=?", (sid,)
        )
        await conn.commit()

    with season.pinned_season("夏"):
        planted = await game.plot_ops(kid, "sow 99 大蒜")
        assert "棚1" in planted and "大蒜" in planted, planted
        assert "不在当季" not in planted, planted
        outdoor = await game.plot_ops(kid, "sow 1 大蒜")
        assert "⚠" in outdoor or "不在当季" in outdoor, outdoor


async def test_greenhouse_trees_ignore_season() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="season-gh-tree-"))
    db = await _boot(tmp)
    from server import game, season

    kid, sid = await _enroll(db, "ghtree@example.com", "棚橘人")
    async with db.connect() as conn:
        await db.add_item(conn, sid, "seed_orange", 2)
        await conn.execute("UPDATE stewards SET tickets=tickets+400, greenhouse=1 WHERE id=?", (sid,))
        await conn.execute(
            "INSERT INTO parcels (steward_id, slot, orchard, greenhouse, tended) VALUES (?, 1, 0, 1, 0)",
            (sid,),
        )
        await conn.execute("UPDATE stewards SET greenhouse_count=1 WHERE id=?", (sid,))
        await conn.commit()

    with season.pinned_season("夏"):
        orchard_block = await game.plot_ops(kid, "sow 园1 橘子")
        assert "不在当季" in orchard_block or "⚠" in orchard_block, orchard_block
        planted = await game.plot_ops(kid, "sow 棚1 橘子")
        assert "棚1" in planted and "橘子" in planted, planted
        assert "不在当季" not in planted and "温室不种" not in planted, planted
        async with db.connect() as conn:
            row = await (await conn.execute(
                "SELECT crop FROM parcels WHERE steward_id=? AND COALESCE(greenhouse,0)=1 AND slot=1",
                (sid,),
            )).fetchone()
        assert row[0] == "orange"


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

    with season.pinned_season("夏"):
        status = await game.plot_ops(kid, "status")
        assert "大蒜" in status, status
        gathered = await game.plot_ops(kid, "gather 1")
        assert "大蒜" in gathered or "蒜" in gathered, gathered


def test_climate_bits_include_panel_fields() -> None:
    from server import play, season, world

    with season.pinned_season("秋"):
        bits = play.climate_bits()
    assert bits["season"] == "秋"
    assert bits["season_left"]
    assert bits["weather_code"] in {"clear", "misty", "gale"}
    assert bits["tide_code"] in {"ebb", "slack", "flood"}
    assert bits["phase_code"] in {"day", "dusk", "night"}
    assert bits["weather"] == world.weather_label(bits["weather_code"])
    assert bits["tide"] == world.tide_label(bits["tide_code"])
    assert bits["phase"] == world.day_phase_label(bits["phase_code"])
    assert "一周一季" in bits["season_hint"]
    assert bits["weather_hint"]
    from server.v1 import views
    view = views.world_view(bits)
    assert view["weather_code"] == bits["weather_code"]
    assert view["season"] == "秋"


def main() -> None:
    test_week_maps_to_season()
    test_climate_bits_include_panel_fields()
    test_year_round_and_windows()
    test_catalog_marks_season()
    test_league_skips_off_season_crop()
    asyncio.run(test_public_stats_include_season())
    asyncio.run(test_sow_and_buy_lock())
    asyncio.run(test_greenhouse_ignores_season())
    asyncio.run(test_greenhouse_trees_ignore_season())
    asyncio.run(test_planted_off_season_keeps_growing())
    print("season tests ok")


if __name__ == "__main__":
    main()
