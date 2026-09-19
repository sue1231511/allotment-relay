"""batch66：合伙船、拔除灰肥、风暴残骸、岸上地陷、方案缺树、鱼拓/船模。"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch


def test_catalog_trees_craft_collections():
    from server.catalog import CROPS, CRAFT_ITEMS, CRAFT_RECIPES, HEARTH_RECIPES, ITEM_NAMES
    from server.island_collections import ENTRIES
    from server.home_drinks import RECIPES

    for key in ("pomelo", "lemon", "olive", "mulberry", "coffee", "cacao"):
        assert key in CROPS, key
        assert CROPS[key].get("tree")
    assert "柚子" in CROPS["pomelo"]["name"]
    assert "craft_gyotaku" in CRAFT_ITEMS
    assert "craft_boat_model" in CRAFT_ITEMS
    assert "ash_fert" in CRAFT_ITEMS
    assert "wreck_scrap" in CRAFT_ITEMS
    assert "gyotaku" in CRAFT_RECIPES
    assert "boat_model" in CRAFT_RECIPES
    keys = {e[0] for e in ENTRIES}
    assert "craft_gyotaku" in keys
    assert "craft_boat_model" in keys
    assert "pomelo_tea" in RECIPES
    assert "lemon_water" in RECIPES
    assert "mint_tea" in RECIPES
    assert "pear_soup" in RECIPES
    assert len(RECIPES) >= 20
    assert "病株灰肥" in ITEM_NAMES.get("ash_fert", "")
    assert "craft_shell_case" in CRAFT_ITEMS
    assert "craft_seed_box" in CRAFT_ITEMS
    assert "shell_case" in CRAFT_RECIPES
    assert "seed_box" in CRAFT_RECIPES
    assert "贝壳柜" in ITEM_NAMES.get("craft_shell_case", "")
    assert "苹果酒" in {r.get("name") for r in HEARTH_RECIPES.values()}
    keys = {e[0] for e in ENTRIES}
    assert "craft_gyotaku" in keys
    assert "craft_boat_model" in keys
    assert "craft_shell_case" in keys
    assert "craft_seed_box" in keys
    assert "wreck_scrap" in keys


def test_docs_name_partner_boat():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    help_txt = (root / "server/mcp_dispatch.py").read_text(encoding="utf-8")
    assert "合伙 开 漂航船" in help_txt
    readme = (root.parent / "README.md").read_text(encoding="utf-8")
    assert "合伙 开 漂航船" in readme
    game = (root / "server/game.py").read_text(encoding="utf-8")
    assert "合伙 开 漂航船" in game
    manual = (root / "server/templates/partials/island-manual-content.html").read_text(
        encoding="utf-8"
    )
    assert "合伙" in manual
    assert "alliance_ops" not in manual
    track = (root.parent / "docs/TIDE_FULL_EXPANSION.md").read_text(encoding="utf-8")
    assert "tide-full-expansion-source.md" in track
    assert "SEA_CATCH" in track


def test_partner_boat_open_join_payout_repair():
    async def run():
        from server import db, neighbor_boat_share as share, neighbor_links as nl

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                k1 = await db.create_api_key("a@example.com")
                k2 = await db.create_api_key("b@example.com")
                r1 = await db.get_key_row(k1)
                r2 = await db.get_key_row(k2)
                await db.enroll_steward(r1["id"], "发起", "", "naturalist", "")
                await db.enroll_steward(r2["id"], "入伙", "", "naturalist", "")
                s1 = await db.get_steward_by_key_id(r1["id"])
                s2 = await db.get_steward_by_key_id(r2["id"])
                async with db.connect() as conn:
                    await conn.execute(
                        "UPDATE stewards SET tickets=400, boat_key='skiff' WHERE id=?",
                        (s1["id"],),
                    )
                    await conn.execute(
                        "UPDATE stewards SET tickets=400 WHERE id=?",
                        (s2["id"],),
                    )
                    a, b = sorted((s1["id"], s2["id"]))
                    await conn.execute(
                        "INSERT INTO rapport (steward_a, steward_b, score) VALUES (?,?,55)",
                        (a, b),
                    )
                    open_msg = await share.open_share(conn, s1, "漂航船")
                    assert "合伙" in open_msg
                    join_msg = await share.join_share(conn, s2, "发起")
                    assert "下水" in join_msg
                    s1 = await db.get_steward_by_id(s1["id"])
                    assert s1["boat_key"] == "drifter"
                    key2 = await nl.effective_boat_key(conn, s2)
                    assert key2 == "drifter"
                    pay = await share.after_voyage_payout(
                        conn, s1, ["fish_sardine", "fish_mackerel"]
                    )
                    assert pay and "分红" in pay
                    leftover, note = await share.split_repair(conn, s1["id"], 45)
                    assert leftover == 0
                    assert "平摊" in note
                    st = await share.status_report(conn, s1["id"])
                    assert "漂航" in st
                    dissolve = await share.dissolve(conn, s1)
                    assert "散" in dissolve
                    await conn.commit()

    asyncio.run(run())


def test_blight_pull_ash_and_sinkhole():
    async def run():
        from server import db, plot_pests as pests, event_opportunity as opp

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            with patch.object(db, "DATA_DIR", folder), patch.object(db, "DB_PATH", folder / "relay.db"):
                await db.init_db()
                key = await db.create_api_key("p@example.com")
                row = await db.get_key_row(key)
                await db.enroll_steward(row["id"], "园丁", "", "naturalist", "")
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
                        "UPDATE parcels SET crop='kale', pest_key='blight', pest_level=1 WHERE id=?",
                        (pid,),
                    )
                    await conn.execute(
                        "UPDATE parcels SET crop='kale', pest_key='sinkhole', pest_level=1 WHERE id=?",
                        (pid2,),
                    )
                    await conn.execute(
                        "UPDATE stewards SET tickets=80 WHERE id=?", (s["id"],)
                    )
                    await db.add_item(conn, s["id"], "compost", 4)
                    plot = {
                        "id": pid, "slot": slot, "orchard": 0, "greenhouse": 0,
                        "crop": "kale", "pest_key": "blight", "pest_level": 1,
                    }
                    with patch("server.event_opportunity.random.random", lambda: 0.01):
                        msg = await pests.handle(conn, s, plot, "拔除")
                    assert "拔除" in msg
                    stock = await db.get_satchel(s["id"])
                    assert stock.get("ash_fert", 0) >= 1
                    hole = {
                        "id": pid2, "slot": slot2, "orchard": 0, "greenhouse": 0,
                        "crop": "kale", "pest_key": "sinkhole", "pest_level": 1,
                    }
                    fill = await pests.handle(conn, s, hole, "填土")
                    assert "填平" in fill
                    cur = await conn.execute(
                        "SELECT pest_key FROM parcels WHERE id=?", (pid2,)
                    )
                    assert not (await cur.fetchone())[0]
                    acts = pests.ui_actions(
                        {"slot": 1, "pest_key": "sinkhole"},
                        tickets=20,
                        stock={"compost": 2},
                    )
                    assert any(a["action"] == "填土" for a in acts)
                    with patch("server.event_opportunity.random.random", lambda: 0.01):
                        wreck = await opp.maybe_storm_wreck_luck(
                            conn, s["id"], storm=True
                        )
                    assert wreck and "残件" in wreck
                    await conn.commit()

    asyncio.run(run())


def test_tree_traits_coffee_grape():
    from server import farming, world

    with patch.object(world, "field_climate_effect", return_value="frost"):
        plot = {
            "crop": "coffee", "greenhouse": 0, "tended": 0, "fertilized": 0,
            "watered": 0, "grow_target": 280 * 60, "soil_fertility": 70,
        }
        frost = farming.effective_grow(plot, "coffee")
    with patch.object(world, "field_climate_effect", return_value=""):
        plot2 = dict(plot)
        mild = farming.effective_grow(plot2, "coffee")
    assert frost > mild

    with patch.object(world, "current_weather", return_value="gale"), patch.object(
        world, "field_climate_effect", return_value=""
    ):
        n = farming.harvest_pool({"crop": "grape", "tended": 1})
    assert n == 3

    with patch.object(world, "current_weather", return_value="gale"), patch.object(
        world, "field_climate_effect", return_value=""
    ):
        coco = farming.harvest_pool({"crop": "coconut", "tended": 1})
    assert coco == 3
    with patch.object(world, "field_climate_effect", return_value=""), patch.object(
        world, "current_weather", return_value="gale"
    ):
        plot3 = {
            "crop": "coconut", "greenhouse": 0, "tended": 0, "fertilized": 0,
            "watered": 0, "grow_target": 270 * 60, "soil_fertility": 70,
        }
        coco_g = farming.effective_grow(plot3, "coconut")
        other = dict(plot3)
        other["crop"] = "cacao"
        cacao_g = farming.effective_grow(other, "cacao")
    assert coco_g < cacao_g
