#!/usr/bin/env python3
"""季节气候干旱、果树/牲口寿尽、新鱼种当季。"""
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


async def _test_drought_does_not_levy_and_delays_unwatered() -> None:
    from server import disaster

    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        db = await _boot(tmp)
        _, sid = await _enroll(db, "dry@t.test", "旱户")
        planted = db.now() - 400
        async with db.connect() as conn:
            await conn.execute("DELETE FROM world_flags")
            await conn.execute("DELETE FROM world_pulse")
            await conn.execute("UPDATE stewards SET tickets=90000 WHERE id=?", (sid,))
            await conn.execute(
                """
                UPDATE parcels SET crop='kale', planted_at=?, tended=1, watered=0,
                    greenhouse=0, orchard=0
                WHERE steward_id=? AND slot=1 AND COALESCE(orchard,0)=0
                  AND COALESCE(greenhouse,0)=0
                """,
                (planted, sid),
            )
            await conn.execute(
                """
                INSERT INTO parcels (
                    steward_id, slot, crop, planted_at, tended, greenhouse, orchard, watered
                ) VALUES (?, 1, 'kale', ?, 1, 1, 0, 0)
                """,
                (sid, planted),
            )
            await conn.execute(
                "UPDATE stewards SET greenhouse_count=1 WHERE id=?", (sid,)
            )
            await conn.commit()
            result = await disaster.apply_season_climate(
                conn, week_id="2026-W80", effect="drought", intensity="high"
            )
            await conn.commit()
            tickets = (
                await (
                    await conn.execute(
                        "SELECT tickets FROM stewards WHERE id=?", (sid,)
                    )
                ).fetchone()
            )[0]
            outdoor = (
                await (
                    await conn.execute(
                        """
                        SELECT planted_at, crop FROM parcels
                        WHERE steward_id=? AND slot=1 AND COALESCE(orchard,0)=0
                          AND COALESCE(greenhouse,0)=0
                        """,
                        (sid,),
                    )
                ).fetchone()
            )
            indoor = (
                await (
                    await conn.execute(
                        """
                        SELECT planted_at, crop FROM parcels
                        WHERE steward_id=? AND slot=1 AND COALESCE(greenhouse,0)=1
                        """,
                        (sid,),
                    )
                ).fetchone()
            )
        assert result["effect"] == "drought"
        assert tickets == 90000
        assert indoor[0] == planted
        assert indoor[1] == "kale"
        if outdoor[1] == "kale":
            assert outdoor[0] == planted + 2400
        else:
            assert outdoor[0] is None


async def _test_tree_died_of_age() -> None:
    from server import farming

    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        db = await _boot(tmp)
        _, sid = await _enroll(db, "tree@t.test", "树户")
        async with db.connect() as conn:
            conn.row_factory = __import__("aiosqlite").Row
            await conn.execute(
                """
                UPDATE parcels SET crop='orange', planted_at=?, tended=1,
                    tree_born_at=?, tree_harvests=0, tree_harvest_max=6, watered=1
                WHERE steward_id=? AND slot=1 AND COALESCE(orchard,0)=1
                """,
                (db.now() - 100, db.now() - 20 * 86400, sid),
            )
            await conn.commit()
            notes = await farming.tick_tree_age(conn, sid)
            await conn.commit()
            row = await (
                await conn.execute(
                    """
                    SELECT crop, tree_born_at FROM parcels
                    WHERE steward_id=? AND slot=1 AND COALESCE(orchard,0)=1
                    """,
                    (sid,),
                )
            ).fetchone()
            timber = await (
                await conn.execute(
                    "SELECT quantity FROM satchel WHERE steward_id=? AND item='craft_timber'",
                    (sid,),
                )
            ).fetchone()
        assert notes, notes
        assert row["crop"] is None
        assert int(row["tree_born_at"] or 0) == 0
        assert timber and timber[0] >= 1


async def _test_animal_died_of_age() -> None:
    from server import barn

    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        db = await _boot(tmp)
        _, sid = await _enroll(db, "barn@t.test", "栏户")
        async with db.connect() as conn:
            await conn.execute(
                "UPDATE stewards SET barn_built=1 WHERE id=?", (sid,)
            )
            await conn.execute(
                """
                INSERT INTO barn_animals (steward_id, slot, species, fed, stocked_at, born_at)
                VALUES (?, 1, 'rabbit', 1, ?, ?)
                """,
                (sid, db.now() - 100, db.now() - 4 * 86400),
            )
            await conn.commit()
            notes = await barn.tick_animal_age(conn, sid)
            await conn.commit()
            row = await (
                await conn.execute(
                    "SELECT species FROM barn_animals WHERE steward_id=? AND slot=1",
                    (sid,),
                )
            ).fetchone()
        assert notes, notes
        assert row is None or row[0] is None


def test_new_fish_and_seasonal_pool() -> None:
    from server.catalog import SEA_CATCH, weighted_fish_pick
    from server import season

    for key in (
        "sardine", "whitebait", "yellowcroaker", "oyster", "swimmingcrab",
        "seabream", "spanishmack", "flyingfish", "shad", "icefish",
        "grouper", "octopus", "abalone", "lobster", "tuna", "swordfish",
    ):
        assert key in SEA_CATCH, key
    with season.pinned_season("夏"):
        seen = {
            weighted_fish_pick(zones={"near", "far"})
            for _ in range(400)
        }
        assert "flyingfish" in seen
    with season.pinned_season("冬"):
        winter = {
            weighted_fish_pick(zones={"near", "far", "shore"})
            for _ in range(120)
        }
        assert "flyingfish" not in winter
        assert "icefish" in {
            weighted_fish_pick(zones={"shore", "near"})
            for _ in range(300)
        }


def test_new_dishes_listed() -> None:
    from server.catalog import HEARTH_RECIPES, KITCHEN_DISHES

    assert any(r["name"] == "沙丁叶汤" for r in HEARTH_RECIPES.values())
    for name in ("沙丁甘蓝锅", "蒜蓉龙虾", "旗鱼排", "清蒸黄鱼"):
        assert any(d["name"] == name for d in KITCHEN_DISHES.values()), name


def test_drought_does_not_levy_and_delays_unwatered() -> None:
    asyncio.run(_test_drought_does_not_levy_and_delays_unwatered())


def test_tree_died_of_age() -> None:
    asyncio.run(_test_tree_died_of_age())


def test_animal_died_of_age() -> None:
    asyncio.run(_test_animal_died_of_age())


if __name__ == "__main__":
    test_new_fish_and_seasonal_pool()
    test_new_dishes_listed()
    test_drought_does_not_levy_and_delays_unwatered()
    test_tree_died_of_age()
    test_animal_died_of_age()
    print("ok")
