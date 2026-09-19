"""batch67：品质因子、薄荷窜地、特殊料理、木筌/钓位别名、难产、留种履历。"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_catalog_fish_boats_dishes_craft():
    from server.catalog import CRAFT_ITEMS, CRAFT_RECIPES, CROPS, HEARTH_RECIPES, KITCHEN_DISHES, SEA_CATCH
    from server.config import BOATS, VOYAGE_ROUTES, resolve_boat_key
    from server.kitchen_special import SPECIAL_DISH_KEYS
    from server.sea_layer_pref import resolve_layer

    for key in (
        "needlefish", "mudskipper", "horse_mackerel", "black_seabream",
        "hairtail", "skipjack", "angler", "fogfin",
    ):
        assert key in SEA_CATCH, key
    assert 50 <= len(SEA_CATCH) <= 60
    assert "raft" in BOATS
    assert BOATS["raft"]["rank"] == 0
    assert resolve_boat_key("木筌") == "raft"
    assert resolve_boat_key("舠板") == "skiff"
    assert resolve_boat_key("帆船") == "smack"
    assert resolve_boat_key("小渔船") == "watch_hoy"
    assert resolve_boat_key("双标") == "drifter"
    assert resolve_boat_key("雾海") == "longliner"
    assert VOYAGE_ROUTES["near"]["min_boat"] == "raft"
    assert resolve_layer("栈桥") == "shore"
    assert resolve_layer("礁") == "near"
    assert resolve_layer("船尾") == "near"
    assert resolve_layer("浅湾") == "near"
    assert len(SPECIAL_DISH_KEYS) >= 15
    for key in (
        "tide_bone_soup", "moon_bean_cake", "red_algae_soup", "night_lantern_tea",
        "black_salt_fish", "fog_mushroom_soup",
    ):
        assert key in SPECIAL_DISH_KEYS
        assert key in KITCHEN_DISHES
    assert "proc_candied_fruit" in CRAFT_ITEMS
    assert "proc_fruit_vinegar" in CRAFT_ITEMS
    assert "candied_fruit" in CRAFT_RECIPES
    assert "fruit_vinegar" in CRAFT_RECIPES
    names = {r.get("name") for r in HEARTH_RECIPES.values()}
    assert "糖渍梨" in names
    assert "醋渍李" in names
    assert "柠檬醋" in names
    assert "蜜桃糖浆" in names
    assert CROPS["garden_mint"]["name"] == "薄荷"


def test_crop_quality_factors_and_fish_state():
    from server import item_traits as traits
    from server import world

    plot = {
        "watered": 1, "tended": 1, "fertilized": 1, "greenhouse": 0,
        "soil_fertility": 90, "crop": "tomato", "last_crop": "kale",
    }
    with patch.object(world, "current_weather", return_value="misty"), patch.object(
        world, "field_climate_effect", return_value=""
    ):
        q = traits.roll_crop_quality(plot)
    assert q in traits.CROP_QUALITY_KEYS

    same = dict(plot)
    same["last_crop"] = "tomato"
    with patch.object(world, "current_weather", return_value="gale"), patch.object(
        world, "field_climate_effect", return_value="heatwave"
    ):
        q2 = traits.roll_crop_quality(same)
    assert q2 in traits.CROP_QUALITY_KEYS

    with patch.object(world, "current_weather", return_value="gale"):
        st = traits.roll_fish_state("sardine", layer="deep", weather="gale")
    assert st in traits.FISH_STATE_KEYS


def test_mint_spread_and_leaf_water():
    from server import farming, world

    with patch.object(world, "current_weather", return_value="calm"), patch.object(
        world, "field_climate_effect", return_value=""
    ), patch.object(world, "grow_multiplier", return_value=1.0), patch.object(
        world, "climate_grow_mult", return_value=1.0
    ):
        dry = farming.effective_grow(
            {
                "crop": "spinach", "greenhouse": 0, "tended": 1, "fertilized": 0,
                "watered": 0, "grow_target": 55 * 60, "soil_fertility": 70,
            },
            "spinach",
        )
        wet = farming.effective_grow(
            {
                "crop": "spinach", "greenhouse": 0, "tended": 1, "fertilized": 0,
                "watered": 1, "grow_target": 55 * 60, "soil_fertility": 70,
            },
            "spinach",
        )
    assert dry > wet

    async def run():
        from server import db

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("m@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "薄荷", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    cur = await conn.execute(
                        "SELECT id, slot FROM parcels WHERE steward_id=? AND orchard=0 AND greenhouse=0 ORDER BY slot LIMIT 2",
                        (s["id"],),
                    )
                    plots = await cur.fetchall()
                    pid, slot = plots[0]
                    pid2, slot2 = plots[1]
                    await conn.execute(
                        "UPDATE parcels SET crop='garden_mint', slot=? WHERE id=?",
                        (slot, pid),
                    )
                    await conn.execute(
                        "UPDATE parcels SET crop=NULL WHERE id=?",
                        (pid2,),
                    )
                    plot = {
                        "id": pid, "slot": slot, "crop": "garden_mint",
                        "orchard": 0, "greenhouse": 0,
                    }
                    with patch("server.farming.random.random", lambda: 0.01):
                        msg = await farming.maybe_mint_spread(conn, s["id"], plot)
                    assert msg and "薄荷窜" in msg
                    cur = await conn.execute(
                        "SELECT crop FROM parcels WHERE id=?", (pid2,)
                    )
                    assert (await cur.fetchone())[0] == "garden_mint"
                    await conn.commit()

    asyncio.run(run())


def test_dystocia_and_seed_ledger():
    async def run():
        from server import barn_breeding as breed, barn_disease as disease, db, seed_lineage

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("b@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "牧人", "", "naturalist", "")
                s = await db.get_steward_by_key_id(row["id"])
                async with db.connect() as conn:
                    await conn.execute(
                        "INSERT OR IGNORE INTO barn_animals (steward_id, slot, species, fed) VALUES (?,?,NULL,0)",
                        (s["id"], 1),
                    )
                    await conn.execute(
                        "UPDATE barn_animals SET species='chicken', stocked_at=?, born_at=?, fed=1, ailment='' WHERE steward_id=? AND slot=1",
                        (db.now() - 10 * 86400, db.now() - 10 * 86400, s["id"]),
                    )
                    await db.add_item(conn, s["id"], "feed_animal", 4)
                    cur = await conn.execute(
                        "SELECT id FROM barn_animals WHERE steward_id=? AND slot=1",
                        (s["id"],),
                    )
                    aid = int((await cur.fetchone())[0])
                    with patch("server.barn_breeding.random.random", side_effect=[0.01, 0.01]):
                        msg = await breed.try_breed(conn, s, 1)
                    assert "配种" in msg
                    assert "难产" in msg
                    cur = await conn.execute(
                        "SELECT ailment FROM barn_animals WHERE id=?", (aid,)
                    )
                    assert (await cur.fetchone())[0] == "dystocia"
                    assert "dystocia" in disease.BARN_AILMENTS
                    await db.add_item(conn, s["id"], "crop_kale", 1)
                    with patch("server.seed_lineage.random.random", lambda: 0.6):
                        note = await seed_lineage.save_from_crop(conn, s, "kale")
                    assert "第1代" in note
                    cur = await conn.execute(
                        "SELECT lines_json FROM item_ledgers WHERE owner_id=? AND item='seed_kale' AND alive=1",
                        (s["id"],),
                    )
                    row = await cur.fetchone()
                    assert row and "第1代" in (row[0] or "")
                    await conn.commit()

    asyncio.run(run())


def test_pests_chicken_and_docs():
    from server.plot_pests import PEST_META
    from pathlib import Path

    assert "wind_scorch" in PEST_META
    assert "rats" in PEST_META
    root = Path(__file__).resolve().parents[1]
    help_txt = (root / "server/mcp_dispatch.py").read_text(encoding="utf-8")
    assert "木筌" in help_txt
    assert "栈桥" in help_txt
    assert "难产" in help_txt
    readme = (root.parent / "README.md").read_text(encoding="utf-8")
    assert "voyage buy raft" in readme
    assert "栈桥" in readme
    game = (root / "server/game.py").read_text(encoding="utf-8")
    assert "木筌" in game
    manual = (root / "server/templates/partials/island-manual-content.html").read_text(
        encoding="utf-8"
    )
    assert "木筌" in manual
    assert "难产" in manual
    assert "栈桥" in manual
    assert "alliance_ops" not in manual
    track = (root.parent / "docs/TIDE_FULL_EXPANSION.md").read_text(encoding="utf-8")
    assert "木筌" in track
    assert "特殊料理 15～20" in track and "✅ | 特殊料理" in track
