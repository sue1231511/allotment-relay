#!/usr/bin/env python3
"""移动端 /api/v1：结构化 JSON、同一存档、防重复。"""
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


def _client():
    from fastapi.testclient import TestClient
    from server.main import app

    return TestClient(app)


def _auth(key: str, extra: dict | None = None) -> dict:
    headers = {"Authorization": f"Bearer {key}"}
    if extra:
        headers.update(extra)
    return headers


def test_island_v1_api() -> None:
    asyncio.run(_test_island_v1_api())
    test_island_page_is_modular()


async def _test_island_v1_api() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="island-v1-"))
    db = await _boot(tmp)
    key = await db.create_api_key("island@example.com")
    client = _client()

    bad = client.get("/api/v1/me", headers=_auth("ar_sk_not_real"))
    assert bad.status_code == 401, bad.text
    assert bad.json()["error"]["code"] == "INVALID_KEY"

    opened = client.post("/api/v1/session", json={"api_key": key, "name": "地图人"})
    assert opened.status_code == 200, opened.text
    body = opened.json()
    assert body["ok"] is True
    assert body["enrolled"] is True
    assert body["me"]["name"] == "地图人"
    assert len(body["farm"]["home"]) == 3, body["farm"]["home"]
    assert len(body["farm"]["orchard"]) == 3, body["farm"]["orchard"]
    assert isinstance(body["farm"]["greenhouse"], list)
    assert body["farm"]["home"][0]["appearance"] == "empty"
    assert body["farm"]["home"][0]["kind"] == "home"
    assert body["farm"]["orchard"][0]["token"] == "园1"
    assert body["farm"]["orchard"][0]["kind"] == "orchard"

    me = client.get("/api/v1/me", headers=_auth(key))
    assert me.status_code == 200, me.text
    tickets0 = me.json()["me"]["tickets"]
    assert "duty" in me.json()["me"]
    assert "flags" in me.json()["me"]
    assert "satiety" in me.json()["me"]

    missing_item = client.post(
        "/api/v1/farm/parcels/1/sow",
        headers=_auth(key, {"Idempotency-Key": "sow-empty"}),
        json={"crop": "榴莲"},
    )
    assert missing_item.status_code == 409, missing_item.text
    assert missing_item.json()["error"]["code"] == "ITEM_REQUIRED"

    farm0 = client.get("/api/v1/farm", headers=_auth(key))
    assert farm0.status_code == 200, farm0.text
    farm_body = farm0.json()["farm"]
    panel = farm_body["panel"]
    labels = [c["label"] for c in panel]
    assert panel[0]["key"] == "kale" and panel[0]["label"] == "白菜", panel[0]
    assert "胡萝卜" in labels and "番茄" in labels
    assert any(c["key"] == "chili" for c in panel)
    assert not any(c["key"] == "durian" for c in panel)
    orchard_panel = farm_body["panels"]["orchard"]
    assert any(c["key"] == "durian" for c in orchard_panel), orchard_panel
    assert not any(c["key"] == "kale" for c in orchard_panel)
    shed_panel = farm_body["panels"]["greenhouse"]
    assert any(c["key"] == "kale" for c in shed_panel) and any(c["key"] == "durian" for c in shed_panel)
    offer = ((farm_body.get("land") or {}).get("plots") or {}).get("offer")
    assert offer and int(offer["cost"]) > 0, farm_body.get("land")

    shop0 = client.get("/api/v1/shop", headers=_auth(key))
    assert shop0.status_code == 200, shop0.text
    shelf = shop0.json()["shop"]
    assert "Tt酱" in (shelf.get("name") or ""), shelf
    sku_ids = [row["id"] for row in shelf["items"]]
    assert "seed_kale" in sku_ids and "tool_hoe" in sku_ids, sku_ids
    kale = next(row for row in shelf["items"] if row["id"] == "seed_kale")
    assert kale["can_buy"] is True and int(kale["price"]) > 0, kale
    shop_buy = client.post(
        "/api/v1/shop/buy",
        headers=_auth(key, {"Idempotency-Key": "shop-kale-1"}),
        json={"item": "seed_kale", "qty": 1},
    )
    assert shop_buy.status_code == 200, shop_buy.text
    assert shop_buy.json()["event"]["kind"] == "shop"
    assert any(row["id"] == "seed_kale" for row in shop_buy.json()["shop"]["items"])
    seed_row = next(
        it for it in (shop_buy.json()["me"]["stock"] or [])
        if it.get("item") == "seed_kale"
    )
    assert seed_row["can_vend"] is True
    assert seed_row["can_eat"] is False
    assert int(seed_row.get("vend_price") or 0) > 0

    ws0 = client.get("/api/v1/workshop", headers=_auth(key))
    assert ws0.status_code == 200, ws0.text
    forge = ws0.json()["workshop"]
    assert any(t["key"] == "anvil" for t in forge["tabs"]), forge
    nails = next(r for r in forge["recipes"] if r["id"] == "copper_nails")
    assert nails["can_craft"] is False
    copper = next(n for n in nails["need"] if n["item"] == "quarry_copper_bar")
    assert copper["where"] == "盐风崖洗铜"
    assert "盐风崖" in (nails.get("detail") or "")
    assert all("badge" in t for t in forge["tabs"])
    miss_nail = client.post(
        "/api/v1/workshop/act",
        headers=_auth(key, {"Idempotency-Key": "ws-nail-miss"}),
        json={"kind": "craft", "target": "铜钉"},
    )
    assert miss_nail.status_code >= 400, miss_nail.text
    steward = await db.get_steward_by_key_id((await db.get_key_row(key))["id"])
    sid = int(steward["id"])
    async with db.connect() as conn:
        await db.add_item(conn, sid, "quarry_copper_bar", 1)
        await db.add_item(conn, sid, "drift_twine", 1)
        await conn.commit()
    hit_nail = client.post(
        "/api/v1/workshop/act",
        headers=_auth(key, {"Idempotency-Key": "ws-nail-hit"}),
        json={"kind": "craft", "target": "铜钉"},
    )
    assert hit_nail.status_code == 200, hit_nail.text
    job = hit_nail.json()["workshop"]["job"]
    assert job and job["id"] == "copper_nails"
    early_take = client.post(
        "/api/v1/workshop/act",
        headers=_auth(key, {"Idempotency-Key": "ws-take-early"}),
        json={"kind": "take"},
    )
    assert early_take.status_code >= 400, early_take.text
    async with db.connect() as conn:
        await conn.execute("UPDATE steward_craft SET job_ready_at=1 WHERE steward_id=?", (sid,))
        await conn.commit()
    took = client.post(
        "/api/v1/workshop/act",
        headers=_auth(key, {"Idempotency-Key": "ws-take-ok"}),
        json={"kind": "take"},
    )
    assert took.status_code == 200, took.text
    assert took.json()["event"]["kind"] == "workshop"
    assert took.json()["workshop"]["job"] is None
    bag = took.json()["me"]["stock"]
    assert any(it.get("item") == "craft_copper_nails" for it in bag), bag

    cliff0 = client.get("/api/v1/quarry", headers=_auth(key))
    assert cliff0.status_code == 200, cliff0.text
    cliff = cliff0.json()["quarry"]
    assert cliff["pick"]["tier"] == 0
    assert any(t["key"] == "pits" for t in cliff["tabs"]), cliff
    bought = client.post(
        "/api/v1/quarry/act",
        headers=_auth(key, {"Idempotency-Key": "qy-pick"}),
        json={"kind": "buy_pick"},
    )
    assert bought.status_code == 200, bought.text
    assert bought.json()["quarry"]["pick"]["tier"] == 1
    empty_hew = client.post(
        "/api/v1/quarry/act",
        headers=_auth(key, {"Idempotency-Key": "qy-hew-empty"}),
        json={"kind": "hew", "target": "1"},
    )
    assert empty_hew.status_code >= 400, empty_hew.text
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE quarry_claims SET vein='salt', strikes_left=3, last_hew_at=0 WHERE steward_id=?",
            (sid,),
        )
        await db.add_item(conn, sid, "quarry_salt_sand", 2)
        await conn.commit()
    hit_hew = client.post(
        "/api/v1/quarry/act",
        headers=_auth(key, {"Idempotency-Key": "qy-hew-ok"}),
        json={"kind": "hew", "target": "1"},
    )
    assert hit_hew.status_code == 200, hit_hew.text
    assert hit_hew.json()["event"]["kind"] == "quarry"
    washed = client.post(
        "/api/v1/quarry/act",
        headers=_auth(key, {"Idempotency-Key": "qy-wash"}),
        json={"kind": "wash", "target": "海盐砂 2"},
    )
    assert washed.status_code == 200, washed.text

    tap0 = client.get("/api/v1/bar", headers=_auth(key))
    assert tap0.status_code == 200, tap0.text
    tap = tap0.json()["bar"]
    assert any(t["key"] == "work" for t in tap["tabs"]), tap
    assert any(t["key"] == "menu" for t in tap["tabs"]), tap
    assert any(t["key"] == "tonight" for t in tap["tabs"]), tap
    dish = next(r for r in tap["jobs"] if r["cmd"] == "洗碗")
    assert dish["name"] == "洗碗工", dish
    assert "海盐拉格" in [r["name"] for r in tap["drinks"]], tap["drinks"]
    assert tap["tonight"]["singer"]
    cheer_miss = client.post(
        "/api/v1/bar/act",
        headers=_auth(key, {"Idempotency-Key": "bar-cheer-empty"}),
        json={"kind": "cheer", "target": ""},
    )
    assert cheer_miss.status_code >= 400, cheer_miss.text
    cheered = client.post(
        "/api/v1/bar/act",
        headers=_auth(key, {"Idempotency-Key": "bar-cheer-ok"}),
        json={"kind": "cheer", "target": "今晚生意好"},
    )
    assert cheered.status_code == 200, cheered.text
    assert cheered.json()["event"]["kind"] == "bar"
    assert cheered.json()["bar"]["tonight"]["can_cheer"] is False
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET last_bar_shift_at=1, energy=80 WHERE id=?",
            (sid,),
        )
        await conn.commit()
    worked_act = client.post(
        "/api/v1/bar/act",
        headers=_auth(key, {"Idempotency-Key": "bar-act-work"}),
        json={"kind": "work", "target": "洗碗"},
    )
    assert worked_act.status_code == 200, worked_act.text
    assert worked_act.json()["event"]["kind"] == "bar"

    writers0 = client.get("/api/v1/writers", headers=_auth(key))
    assert writers0.status_code == 200, writers0.text
    desk = writers0.json()["writers"]
    assert desk["name"] == "编剧社", desk
    assert desk["can_submit"] is True, desk
    assert any(t["key"] == "desk" for t in desk["tabs"]), desk
    pitch_miss = client.post(
        "/api/v1/writers/act",
        headers=_auth(key, {"Idempotency-Key": "writers-empty"}),
        json={"kind": "submit", "target": ""},
    )
    assert pitch_miss.status_code >= 400, pitch_miss.text
    pitched = client.post(
        "/api/v1/writers/act",
        headers=_auth(key, {"Idempotency-Key": "writers-submit"}),
        json={"kind": "submit", "target": "岸上旧收音机 | " + "第一幕海边有人把旧收音机打开，潮水把字迹冲淡。" * 2},
    )
    assert pitched.status_code == 200, pitched.text
    assert pitched.json()["event"]["kind"] == "writers"
    assert pitched.json()["writers"]["scripts"], pitched.json()["writers"]
    script_id = pitched.json()["writers"]["scripts"][0]["id"]
    withdrawn = client.post(
        "/api/v1/writers/act",
        headers=_auth(key, {"Idempotency-Key": "writers-withdraw"}),
        json={"kind": "withdraw", "target": str(script_id)},
    )
    assert withdrawn.status_code == 200, withdrawn.text

    hall0 = client.get("/api/v1/hall", headers=_auth(key))
    assert hall0.status_code == 200, hall0.text
    hall = hall0.json()["hall"]
    assert hall["name"] == "剧场看台", hall
    assert hall["open"] is False, hall
    assert any(t["key"] == "board" for t in hall["tabs"]), hall
    assert any(r["cmd"] == "试镜" and r["can_act"] is False for r in hall["jobs"]), hall
    audition_off = client.post(
        "/api/v1/hall/act",
        headers=_auth(key, {"Idempotency-Key": "hall-audition-off"}),
        json={"kind": "audition", "target": ""},
    )
    assert audition_off.status_code >= 400, audition_off.text

    atelier0 = client.get("/api/v1/atelier", headers=_auth(key))
    assert atelier0.status_code == 200, atelier0.text
    atelier = atelier0.json()["atelier"]
    assert atelier["name"] == "衣泊坊", atelier
    assert any(t["key"] == "shop" for t in atelier["tabs"]), atelier
    assert any(r["cmd"] == "婚服 海色" for r in atelier["goods"]), atelier
    buy_miss = client.post(
        "/api/v1/atelier/act",
        headers=_auth(key, {"Idempotency-Key": "atelier-buy-empty"}),
        json={"kind": "buy", "target": ""},
    )
    assert buy_miss.status_code >= 400, buy_miss.text

    wrong_yard = client.post(
        "/api/v1/farm/parcels/园1/sow",
        headers=_auth(key, {"Idempotency-Key": "sow-orchard-kale"}),
        json={"crop": "甘蓝"},
    )
    assert wrong_yard.status_code >= 400, wrong_yard.text
    idle = sorted(
        (p for p in farm0.json()["farm"]["home"] if p["can_sow"]),
        key=lambda p: int(p["slot"]),
    )
    assert idle and int(idle[0]["slot"]) == 1, idle

    sown = client.post(
        f"/api/v1/farm/parcels/{idle[0]['slot']}/sow",
        headers=_auth(key, {"Idempotency-Key": "sow-kale-1"}),
        json={"crop": panel[0]["name"]},
    )
    assert sown.status_code == 200, sown.text
    one = next(p for p in sown.json()["farm"]["home"] if int(p["slot"]) == 1)
    assert one["state"] != "fallow", one
    assert one["appearance"] in ("seedling", "growing"), one
    assert one["remain_sec"] > 0, one
    assert one["can_tend"] is True, one
    assert one["can_water"] is True, one
    assert one["can_fertilize"] is True, one
    assert sown.json()["event"]["kind"] == "farm"
    assert "sow 1" not in (sown.json()["event"]["narrative"] or "")

    tended = client.post(
        "/api/v1/farm/parcels/1/tend",
        headers=_auth(key, {"Idempotency-Key": "tend-1"}),
        json={},
    )
    assert tended.status_code == 200, tended.text
    assert tended.json()["event"]["title"] == "打理"
    assert "打理了" in (tended.json()["event"]["narrative"] or ""), tended.json()["event"]
    tplot = next(p for p in tended.json()["farm"]["home"] if int(p["slot"]) == 1)
    # 小虫过境可能把打理打回去，再读一次地况；还没沾上就再打理一次。
    if not tplot["tended"]:
        again = client.get("/api/v1/farm", headers=_auth(key))
        tplot = next(p for p in again.json()["farm"]["home"] if int(p["slot"]) == 1)
    if not tplot["tended"] and tplot.get("can_tend"):
        tended = client.post(
            "/api/v1/farm/parcels/1/tend",
            headers=_auth(key, {"Idempotency-Key": "tend-1-retry"}),
            json={},
        )
        assert tended.status_code == 200, tended.text
        tplot = next(p for p in tended.json()["farm"]["home"] if int(p["slot"]) == 1)
    assert tplot["tended"] is True or "小虫" in (tended.json()["event"]["narrative"] or ""), tplot
    if tplot["tended"]:
        assert tplot["can_tend"] is False, tplot

    fert_ok = client.post(
        "/api/v1/farm/parcels/1/fertilize",
        headers=_auth(key, {"Idempotency-Key": "fert-1"}),
        json={},
    )
    assert fert_ok.status_code == 200, fert_ok.text
    fplot = next(p for p in fert_ok.json()["farm"]["home"] if int(p["slot"]) == 1)
    assert fplot["fertilized"] is True, fplot
    assert fplot["can_fertilize"] is False, fplot

    fert_again = client.post(
        "/api/v1/farm/parcels/1/fertilize",
        headers=_auth(key, {"Idempotency-Key": "fert-2"}),
        json={},
    )
    assert fert_again.status_code == 409, fert_again.text
    assert fert_again.json()["error"]["code"] == "ALREADY_DONE"

    refreshed = client.get("/api/v1/farm", headers=_auth(key))
    again_plot = next(p for p in refreshed.json()["farm"]["home"] if int(p["slot"]) == 1)
    assert again_plot["crop"] == one["crop"]
    assert again_plot["remain_sec"] > 0

    again = client.post(
        "/api/v1/farm/parcels/1/sow",
        headers=_auth(key, {"Idempotency-Key": "sow-kale-1"}),
        json={"crop": "甘蓝"},
    )
    assert again.status_code == 200, again.text
    assert again.json()["farm"]["home"][0]["crop"] == sown.json()["farm"]["home"][0]["crop"]

    unripe = client.post(
        "/api/v1/farm/parcels/1/harvest",
        headers=_auth(key, {"Idempotency-Key": "harvest-early"}),
        json={},
    )
    assert unripe.status_code == 409, unripe.text
    assert unripe.json()["error"]["code"] == "NOT_READY"

    watered = client.post(
        "/api/v1/farm/parcels/1/water",
        headers=_auth(key, {"Idempotency-Key": "water-1"}),
        json={},
    )
    assert watered.status_code == 200, watered.text
    wplot = next(p for p in watered.json()["farm"]["home"] if int(p["slot"]) == 1)
    assert wplot["watered"] is True, wplot

    water_again = client.post(
        "/api/v1/farm/parcels/1/water",
        headers=_auth(key, {"Idempotency-Key": "water-1"}),
        json={},
    )
    assert water_again.status_code == 200, water_again.text

    water_dup = client.post(
        "/api/v1/farm/parcels/1/water",
        headers=_auth(key, {"Idempotency-Key": "water-2"}),
        json={},
    )
    assert water_dup.status_code == 409, water_dup.text
    assert water_dup.json()["error"]["code"] == "ALREADY_DONE"

    # 人类客户端写下的地，MCP 立刻看见同一份。
    row = await db.get_key_row(key)
    from server import game

    status = await game.plot_ops(row["id"], "status")
    assert "甘蓝" in status or "羽衣" in status, status

    from server import play as play_mod

    snap = await play_mod.run_play(key, "plot_ops", "status")
    planted = [
        p for p in snap["dashboard"]["parcels"]
        if not p.get("orchard") and not p.get("greenhouse") and p.get("token") == "1"
    ]
    assert planted and planted[0]["state"] != "fallow", planted

    # 未成熟收获强制熟后，收成进同一行囊。
    parcels = await db.get_parcels(row["id"])
    target = next(
        p for p in parcels
        if int(p["slot"]) == 1 and not p.get("orchard") and not p.get("greenhouse")
    )
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE parcels SET planted_at=planted_at-? WHERE id=?",
            (200000, target["id"]),
        )
        await conn.commit()
    harvested = client.post(
        "/api/v1/farm/parcels/1/harvest",
        headers=_auth(key, {"Idempotency-Key": "harvest-ok"}),
        json={},
    )
    assert harvested.status_code == 200, harvested.text
    bag = harvested.json()["me"]["stock"]
    assert any(
        str(it.get("item") or "").startswith("kale") or "甘蓝" in str(it.get("name") or "")
        for it in bag
    ), bag
    kale_row = next(
        it for it in bag
        if it.get("item") in ("crop_kale", "seed_kale")
    )
    assert kale_row["can_vend"] is True
    assert kale_row["can_eat"] is False

    mcp_bag = await play_mod.run_play(key, "tote_ops", "list")
    assert "甘蓝" in (mcp_bag.get("text") or ""), mcp_bag.get("text")

    sold = client.post(
        "/api/v1/tote/vend",
        headers=_auth(key, {"Idempotency-Key": "vend-kale-1"}),
        json={"item": kale_row["name"], "qty": 1},
    )
    assert sold.status_code == 200, sold.text
    assert sold.json()["event"]["kind"] == "tote"
    sold_bag = sold.json()["me"]["stock"]
    leftover = next(
        (
            it for it in sold_bag
            if it.get("item") == kale_row["item"]
        ),
        None,
    )
    assert leftover is None or int(leftover.get("qty") or 0) < int(kale_row.get("qty") or 0)

    # 点哪块种哪块：按 slot 顺序把三块都种上，就没有 can_sow。
    empty = sorted(
        (p for p in harvested.json()["farm"]["home"] if p["can_sow"]),
        key=lambda p: int(p["slot"]),
    )
    assert len(empty) == 3, empty
    last_sow = harvested
    for plot, crop, idem in zip(
        empty,
        ("甘蓝", "甜菜", "雾豌豆"),
        ("sow-fill-1", "sow-fill-2", "sow-fill-3"),
    ):
        last_sow = client.post(
            f"/api/v1/farm/parcels/{plot['slot']}/sow",
            headers=_auth(key, {"Idempotency-Key": idem}),
            json={"crop": crop},
        )
        if last_sow.status_code == 409 and last_sow.json().get("error", {}).get("code") == "ITEM_REQUIRED":
            bought_fill = client.post(
                "/api/v1/farm/buy",
                headers=_auth(key, {"Idempotency-Key": f"buy-{idem}"}),
                json={"crop": crop, "qty": 1},
            )
            assert bought_fill.status_code == 200, bought_fill.text
            last_sow = client.post(
                f"/api/v1/farm/parcels/{plot['slot']}/sow",
                headers=_auth(key, {"Idempotency-Key": f"{idem}-after-buy"}),
                json={"crop": crop},
            )
        assert last_sow.status_code == 200, last_sow.text
    assert not any(p["can_sow"] for p in last_sow.json()["farm"]["home"])

    parcels = await db.get_parcels(row["id"])
    home_ids = [
        p for p in parcels
        if not p.get("orchard") and not p.get("greenhouse")
    ]
    async with db.connect() as conn:
        for plot in home_ids:
            await conn.execute(
                "UPDATE parcels SET planted_at=planted_at-? WHERE id=?",
                (200000, plot["id"]),
            )
        await conn.commit()
    ripe_farm = client.get("/api/v1/farm", headers=_auth(key))
    ripe = [p for p in ripe_farm.json()["farm"]["home"] if p["can_harvest"]]
    assert ripe, ripe_farm.text
    last_harvest = None
    for plot in ripe:
        last_harvest = client.post(
            f"/api/v1/farm/parcels/{plot['slot']}/harvest",
            headers=_auth(key, {"Idempotency-Key": f"harvest-all-{plot['slot']}"}),
            json={},
        )
        assert last_harvest.status_code == 200, last_harvest.text
    assert last_harvest is not None
    assert not any(p["can_harvest"] for p in last_harvest.json()["farm"]["home"])

    # 点草地开垦：起步 3 块时下一块是 #4（80 票），不能等到后面被扩成 22 块再测。
    steward = await db.get_steward_by_key_id(row["id"])
    sid = int(steward["id"])
    tickets_before_expand = int(steward["tickets"] or 0)
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET tickets=tickets+200 WHERE id=?",
            (sid,),
        )
        await conn.commit()
    n0 = len(last_harvest.json()["farm"]["home"])
    assert n0 == 3, n0
    expanded = client.post(
        "/api/v1/farm/expand",
        headers=_auth(key, {"Idempotency-Key": "expand-home-1"}),
        json={"kind": "home"},
    )
    assert expanded.status_code == 200, expanded.text
    assert len(expanded.json()["farm"]["home"]) == n0 + 1
    assert any(p["state"] == "clearing" for p in expanded.json()["farm"]["home"])
    expand_again = client.post(
        "/api/v1/farm/expand",
        headers=_auth(key, {"Idempotency-Key": "expand-home-2"}),
        json={"kind": "home"},
    )
    assert expand_again.status_code == 409, expand_again.text
    assert expand_again.json()["error"]["code"] == "NOT_READY"
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET tickets=? WHERE id=?",
            (tickets_before_expand, sid),
        )
        await conn.commit()

    # 扩到二十几块时，三类地都要整份回给前端，不能只画画面上的三块。
    steward = await db.get_steward_by_key_id(row["id"])
    sid_for_yards = int(steward["id"])
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET parcel_count=22, orchard_count=22, greenhouse_count=22, greenhouse=1 WHERE id=?",
            (sid_for_yards,),
        )
        await db.ensure_parcels(conn, sid_for_yards, 22)
        await db.ensure_orchard_parcels(conn, sid_for_yards, 22)
        await db.ensure_greenhouse_parcels(conn, sid_for_yards, 22)
        await conn.commit()
    many = client.get("/api/v1/farm", headers=_auth(key))
    assert many.status_code == 200, many.text
    yards = many.json()["farm"]
    assert len(yards["home"]) == 22, len(yards["home"])
    assert len(yards["orchard"]) == 22, len(yards["orchard"])
    assert len(yards["greenhouse"]) == 22, len(yards["greenhouse"])
    assert yards["home"][-1]["token"] == "22"
    assert yards["orchard"][-1]["token"] == "园22"
    assert yards["greenhouse"][-1]["token"] == "棚22"

    steward = await db.get_steward_by_key_id(row["id"])
    sid = int(steward["id"])
    async with db.connect() as conn:
        await conn.execute(
            "INSERT OR REPLACE INTO steward_gear (steward_id, bait_tier, rod_tier, net_tier) VALUES (?,?,?,?)",
            (sid, 1, 0, 1),
        )
        await conn.execute("UPDATE stewards SET energy=0 WHERE id=?", (sid,))
        await conn.commit()
    tired = client.post(
        "/api/v1/shore/cast",
        headers=_auth(key, {"Idempotency-Key": "net-tired"}),
        json={"mode": "net"},
    )
    assert tired.status_code == 409, tired.text
    assert tired.json()["error"]["code"] == "ENERGY_LOW"
    assert "tide_ops" not in tired.json()["error"]["message"]

    async with db.connect() as conn:
        await conn.execute("UPDATE stewards SET energy=80 WHERE id=?", (sid,))
        await conn.commit()
    tickets_pre_fish = int(
        (await db.get_steward_by_key_id(row["id"]))["tickets"] or 0
    )
    fished = client.post(
        "/api/v1/shore/cast",
        headers=_auth(key, {"Idempotency-Key": "net-ok"}),
        json={"mode": "net"},
    )
    assert fished.status_code == 200, fished.text
    assert fished.json()["event"]["kind"] == "shore"
    assert fished.json()["me"]["tickets"] <= tickets_pre_fish + 40

    from server import mcp_dispatch as mux

    tide_text = await mux.tide_bundle(row["id"], "")
    assert "net" in tide_text or "cast" in tide_text

    hall = client.get("/api/v1/lounge/messages", headers=_auth(key))
    assert hall.status_code == 200, hall.text
    said = client.post(
        "/api/v1/lounge/messages",
        headers=_auth(key, {"Idempotency-Key": "say-1"}),
        json={"text": "地图这边也能说话"},
    )
    assert said.status_code == 200, said.text
    assert any("地图这边也能说话" in (m.get("text") or "") for m in said.json()["messages"])

    said2 = client.post(
        "/api/v1/lounge/messages",
        headers=_auth(key, {"Idempotency-Key": "say-1"}),
        json={"text": "地图这边也能说话"},
    )
    assert said2.status_code == 200, said2.text

    from server import lounge

    mcp_scan = await lounge.lounge_ops(row["id"], "scan")
    assert "地图这边也能说话" in mcp_scan

    world = client.get("/api/v1/world", headers=_auth(key))
    assert world.status_code == 200, world.text
    assert world.json()["world"]["tide"]

    bought = client.post(
        "/api/v1/farm/buy",
        headers=_auth(key, {"Idempotency-Key": "buy-kale"}),
        json={"crop": "甘蓝", "qty": 1},
    )
    assert bought.status_code == 200, bought.text
    assert bought.json()["event"]["kind"] == "farm"
    assert bought.json()["event"]["title"] == "买种"

    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET tickets=tickets+200, energy=80 WHERE id=?",
            (sid,),
        )
        await conn.commit()
    built = client.post(
        "/api/v1/hut/build",
        headers=_auth(key, {"Idempotency-Key": "hut-build"}),
        json={},
    )
    assert built.status_code == 200, built.text
    assert built.json()["event"]["kind"] == "hut"
    assert built.json()["me"]["flags"]["hut_built"] is True
    async with db.connect() as conn:
        await conn.execute(
            "INSERT INTO hut_fittings (steward_id, slot, item_key, installed_at) VALUES (?,?,?,?)",
            (sid, "hard_1", "bed", 1),
        )
        await conn.execute("UPDATE stewards SET energy=20 WHERE id=?", (sid,))
        await conn.commit()
    slept = client.post(
        "/api/v1/hut/sleep",
        headers=_auth(key, {"Idempotency-Key": "hut-sleep"}),
        json={},
    )
    assert slept.status_code == 200, slept.text
    assert slept.json()["event"]["kind"] == "hut"

    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET last_bar_shift_at=1, energy=80 WHERE id=?",
            (sid,),
        )
        await conn.commit()
    worked = client.post(
        "/api/v1/bar/work",
        headers=_auth(key, {"Idempotency-Key": "bar-work"}),
        json={},
    )
    assert worked.status_code == 200, worked.text
    assert worked.json()["event"]["kind"] == "bar"

    async with db.connect() as conn:
        await db.add_item(conn, sid, "crop_mango", 1)
        await conn.commit()
    ate = client.post(
        "/api/v1/kitchen/eat",
        headers=_auth(key, {"Idempotency-Key": "eat-mango"}),
        json={"item": "芒果"},
    )
    assert ate.status_code == 200, ate.text
    assert ate.json()["event"]["kind"] == "eatery"

    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET tax_arrears=20, upkeep_arrears=15, tickets=tickets+80 WHERE id=?",
            (sid,),
        )
        await conn.commit()
    paid_tax = client.post(
        "/api/v1/hui/pay",
        headers=_auth(key, {"Idempotency-Key": "hui-tax"}),
        json={"kind": "tax"},
    )
    assert paid_tax.status_code == 200, paid_tax.text
    assert paid_tax.json()["event"]["kind"] == "hui"
    assert int(paid_tax.json()["me"]["dues"]["tax_arrears"] or 0) == 0
    paid_upkeep = client.post(
        "/api/v1/hui/pay",
        headers=_auth(key, {"Idempotency-Key": "hui-upkeep"}),
        json={"kind": "upkeep"},
    )
    assert paid_upkeep.status_code == 200, paid_upkeep.text
    assert int(paid_upkeep.json()["me"]["dues"]["upkeep_arrears"] or 0) == 0

    page = client.get("/island")
    assert page.status_code == 200, page.text
    assert "手机地图" in page.text or "island-root" in page.text


def test_island_page_is_modular() -> None:
    html = (ROOT / "server/templates/island.html").read_text(encoding="utf-8")
    css = (ROOT / "server/static/island/island.css").read_text(encoding="utf-8")
    app = (ROOT / "server/static/island/app.js").read_text(encoding="utf-8")
    api = (ROOT / "server/static/island/api.js").read_text(encoding="utf-8")
    assert "/static/island/app.js" in html
    assert "island-theater3" in html
    assert "/static/island/tap.js" in html
    assert "/static/island/boot.js" in html
    assert 'id="island-enter"' in html
    assert "novalidate" in html
    assert "island-dock" in html
    assert 'id="island-bag-chip"' in html
    assert 'id="island-back-chip"' in html
    assert "chip-bag.png" in html
    assert "chip-back.png" in html
    assert 'data-tab="bag"' not in html
    assert 'data-tab="map"' not in html
    assert 'data-tab="quest"' not in html
    assert 'data-tab="chat"' not in html
    assert ">任务<" not in html
    assert ">聊天<" not in html
    assert ">地图<" not in html
    assert "renderQuest" not in app
    assert "renderChat" not in app
    assert "island-ribbon" in html
    assert "island-gate-hint" in html
    map_js = (ROOT / "server/static/island/map.js").read_text(encoding="utf-8")
    assert "家园" in map_js
    assert "份地" in map_js
    assert 'go: "yards"' in map_js
    assert "小屋" in map_js
    assert "酒吧" in map_js
    assert "island-hot" in map_js
    assert "data-href" in map_js
    assert 'go: "workshop"' in map_js
    assert 'go: "quarry"' in map_js
    assert '"/workshop"' not in map_js
    assert '"/quarry"' not in map_js
    assert 'go: "market"' in map_js
    assert 'go: "ting"' in map_js
    assert 'go: "lianli"' in map_js
    assert 'go: "eatery"' in map_js
    assert 'go: "hui"' in map_js
    assert '"/market"' not in map_js
    assert '"/ting"' not in map_js
    assert '"/lianli"' not in map_js
    assert '"/undertide"' in map_js
    assert "岸畔小馆" in map_js
    assert "972" in map_js
    assert "1619" in map_js
    map_png = ROOT / "server/static/island/assets/scenes/island-map.png"
    assert map_png.exists()
    try:
        from PIL import Image
        assert Image.open(map_png).size == (972, 1619)
    except ImportError:
        pass
    assert "min-height: 48px" in css
    assert "overflow-x: hidden" in css
    assert "island-plot-tile" in css
    assert "island-plot-bed" in css
    assert "island-yards" in css
    assert "island-slot" in css
    assert "island-hot" in css
    assert "island-map-board" in css
    assert "is-playing" in css
    assert "铺满一屏" in css
    assert "底下不漏色" in css
    assert "max-width: 480px" in css
    art_js = (ROOT / "server/static/island/ui/art.js").read_text(encoding="utf-8")
    assert "sW = cw / iw" in art_js
    assert "Math.max(sW, sH" in art_js
    assert "layoutCoverBoard" in map_js
    assert "layoutCoverBoard" in art_js
    assert "is-playing" in (ROOT / "server/static/island/boot.js").read_text(encoding="utf-8")
    assert "island-place" in css
    assert "island-plant-buy" in css
    assert "is-hui" in css
    assert "#7fa24a" not in css
    assert "#8faf4a" not in css
    assert "海边草地底图" in css
    assert 'sceneArt("yards")' in (ROOT / "server/static/island/scenes/home.js").read_text(encoding="utf-8")
    yards_png = ROOT / "server/static/island/assets/scenes/yards.png"
    assert yards_png.exists()
    try:
        from PIL import Image
        assert Image.open(yards_png).size == (941, 1672)
    except ImportError:
        pass
    assert "top: auto" in css
    assert "/static/style.css" not in html
    assert "/api/v1/" in api
    assert "Authorization" in api
    assert "encodeURIComponent" in api
    assert "api_key=" not in api
    assert "浇水 1" not in app
    assert "菜地已经种满了" in (ROOT / "server/static/island/store.js").read_text(encoding="utf-8")
    assert "plotByToken" in app
    assert "tapPlot" in app
    assert "showCareSheet" in app
    assert "__islandStart" in app
    assert "bindGate" not in app
    boot = (ROOT / "server/static/island/boot.js").read_text(encoding="utf-8")
    assert "/api/v1/session" in boot
    assert "正在进入" in boot
    assert "island-enter" in boot
    assert "thirstyYard" in (ROOT / "server/static/island/store.js").read_text(encoding="utf-8")
    assert "plotToken" in app
    assert "renderYards" in app
    assert "enterScene(\"yards\")" in app
    assert 'name === "home"' in app
    assert "backChipMarkup" not in (ROOT / "server/static/island/scenes/home.js").read_text(encoding="utf-8")
    assert "setBackChip" in (ROOT / "server/static/island/ui/back-map.js").read_text(encoding="utf-8")
    assert "setBagChip" in app
    assert "setBagChip(name !== \"map\")" in app
    assert "left: 0" in css
    assert "min(196px, 58%)" in css
    assert "min(88px, 24%)" in css
    assert "translateX(-22%)" in css
    assert "height: 66px" in css
    assert "align-items: center" in css
    home_js = (ROOT / "server/static/island/scenes/home.js").read_text(encoding="utf-8")
    yards_js = home_js.split("export function renderYards", 1)[1].split("export function", 1)[0]
    assert "island-back-map" not in yards_js
    assert "back-map.png" not in yards_js
    assert "backChipMarkup" not in yards_js
    assert 'data-act="back">返回地图' not in yards_js
    assert "去上手页" not in app
    assert "去上手页" not in html
    assert 'href="/play"' not in html
    assert "去上手页" not in boot
    assert 'href="/play"' not in boot
    assert (ROOT / "server/static/island/ui/back-map.js").exists()
    assert "island-yard-acts" not in yards_js
    assert "data-act=\"water\"" not in yards_js
    assert "onTapPlot" in yards_js
    assert "data-token" in home_js
    assert "onWaterAll" not in home_js
    assert "#island-actionbar [data-act=water]" not in home_js
    assert "#island-actionbar [data-act=garden]" not in home_js
    assert "setYardsChrome" in app
    assert "is-yards" in app
    assert "classList.remove(\"is-yards\")" in app
    assert "name === \"map\" || name === \"yards\"" in app
    assert "is-yards" in boot
    assert "is-yards" in css
    assert ".island-back-map" not in css
    assert ".island-care-acts" in css
    assert "prompt-frame.png" in css
    assert "island-card-inner" in css
    modal_js = (ROOT / "server/static/island/ui/modal.js").read_text(encoding="utf-8")
    assert "island-card-inner" in modal_js
    assert "cardMarkup" in modal_js
    frame = ROOT / "server/static/island/assets/prompt-frame.png"
    assert frame.exists()
    try:
        from PIL import Image
        assert Image.open(frame).size == (840, 840)
    except ImportError:
        pass
    assert ".island-yard-acts" not in css
    assert ".island-float-chip" in css
    assert ".island-back-chip" not in css
    assert (ROOT / "server/static/island/assets/chip-back.png").exists()
    assert (ROOT / "server/static/island/assets/chip-bag.png").exists()
    try:
        from PIL import Image
        back = Image.open(ROOT / "server/static/island/assets/chip-back.png")
        assert back.size == (2000, 667)
        assert back.mode == "RGBA"
        assert back.getpixel((0, 0))[3] == 0
    except ImportError:
        pass
    assert "is-yards .island-actionbar" in css
    assert not (ROOT / "server/static/island/assets/back-map.png").exists()
    assert "api.buy" in app
    assert "api.eat" in app
    assert "api.vend" in app
    assert "keepShop" in app
    assert "shopShelf" in app
    assert "workshopShelf" in app
    assert "showVendSheet" in app
    bag_js = (ROOT / "server/static/island/ui/bag.js").read_text(encoding="utf-8")
    assert "data-eat" in bag_js
    assert "data-vend" in bag_js
    assert "bag-frame.png" in bag_js or "bag-frame.png" in css
    assert "island-bag-grid" in bag_js
    assert "data-page" in bag_js
    assert "const PAGE = 20" in bag_js
    assert "左边吃，右边卖" not in bag_js
    assert "island-item" not in bag_js
    assert "data-vend" in bag_js
    bag_frame = ROOT / "server/static/island/assets/bag-frame.png"
    assert bag_frame.exists()
    try:
        from PIL import Image
        frame = Image.open(bag_frame)
        assert frame.size == (941, 1672)
        assert frame.mode == "RGBA"
    except ImportError:
        pass
    tap_js = (ROOT / "server/static/island/tap.js").read_text(encoding="utf-8")
    assert "island-spark" in tap_js
    assert "is-tap" in tap_js
    assert "pointerdown" in tap_js
    assert "island-spark" in css
    assert ".is-tap" in css
    assert "island-spark-fly" in css
    assert "island-pop-in" in css
    assert "island-pop-out" in css
    pop_js = (ROOT / "server/static/island/ui/pop.js").read_text(encoding="utf-8")
    assert "function popIn" in pop_js
    assert "function popOut" in pop_js
    modal_js = (ROOT / "server/static/island/ui/modal.js").read_text(encoding="utf-8")
    assert "paintModal" in modal_js
    assert "popOut" in modal_js
    assert "交岸税" not in app
    assert "只铺图和地名" in (ROOT / "server/static/island/scenes/place.js").read_text(encoding="utf-8")
    assert "data-act=\"net\"" not in (ROOT / "server/static/island/scenes/shore.js").read_text(encoding="utf-8")
    plaza_js = (ROOT / "server/static/island/scenes/plaza.js").read_text(encoding="utf-8")
    assert "发言" not in plaza_js
    assert "洗碗" not in plaza_js
    assert "杂货铺" in plaza_js
    assert "灯塔" in plaza_js
    assert "岸工坊" in plaza_js
    assert "潮汐公告" in plaza_js
    assert 'go: "shop"' in plaza_js
    assert 'go: "lighthouse"' in plaza_js
    assert 'go: "workshop"' in plaza_js
    assert 'go: "notice"' in plaza_js
    assert "/api/v1/farm/buy" in api
    assert "/tend" in api
    assert "/fertilize" in api
    assert "api.tend" in app
    assert "api.fertilize" in app
    assert "/api/v1/hut/sleep" in api
    assert "/api/v1/bar/work" in api
    assert "/api/v1/kitchen/eat" in api
    assert "/api/v1/tote/vend" in api
    assert "/api/v1/hui/pay" in api
    assert (ROOT / "server/static/island/scenes/home.js").exists()
    assert (ROOT / "server/static/island/scenes/place.js").exists()
    assert (ROOT / "server/static/island/ui/art.js").exists()
    assert (ROOT / "server/static/island/assets/ART.md").exists()
    assert "sceneArt" in (ROOT / "server/static/island/ui/art.js").read_text(encoding="utf-8")
    assert "插图位" in (ROOT / "server/static/island/ui/art.js").read_text(encoding="utf-8")
    assert "scenes/island-map.png" in (ROOT / "server/static/island/assets/ART.md").read_text(encoding="utf-8")
    assert "scenes/yards.png" in (ROOT / "server/static/island/assets/ART.md").read_text(encoding="utf-8")
    assert "scenes/eatery.png" in (ROOT / "server/static/island/assets/ART.md").read_text(encoding="utf-8")
    assert "scenes/hui.png" in (ROOT / "server/static/island/assets/ART.md").read_text(encoding="utf-8")
    assert "scenes/market.png" in (ROOT / "server/static/island/assets/ART.md").read_text(encoding="utf-8")
    assert "scenes/ting.png" in (ROOT / "server/static/island/assets/ART.md").read_text(encoding="utf-8")
    assert "scenes/lianli.png" in (ROOT / "server/static/island/assets/ART.md").read_text(encoding="utf-8")
    art_md = (ROOT / "server/static/island/assets/ART.md").read_text(encoding="utf-8")
    assert "bar-opt-frame.png" in art_md
    assert "scenes/workshop.png" in art_md
    assert "scenes/shop.png" in art_md
    assert "scenes/lighthouse.png" in art_md
    assert "scenes/notice.png" in art_md
    assert "杂货铺" in art_md and "潮汐公告" in art_md
    assert "scenes/quarry.png" in (ROOT / "server/static/island/assets/ART.md").read_text(encoding="utf-8")
    try:
        from PIL import Image
        for place in ("eatery", "hui", "market", "ting", "lianli", "workshop", "quarry", "shop"):
            pic = ROOT / f"server/static/island/assets/scenes/{place}.png"
            assert pic.exists(), place
            assert Image.open(pic).size == (941, 1672)
    except ImportError:
        pass
    assert 'market: "集市"' in app
    assert 'ting: "听潮亭"' in app
    assert 'lianli: "连理所"' in app
    assert 'workshop: "岸工坊"' in app
    assert 'quarry: "盐风崖"' in app
    assert (ROOT / "server/static/island/ui/plant-panel.js").exists()
    assert (ROOT / "server/static/island/ui/crops.js").exists()
    assert "island-crop-fallback" in (ROOT / "server/static/island/ui/crops.js").read_text(encoding="utf-8")
    assert (ROOT / "server/static/island/assets/crops/kale.png").exists()
    assert (ROOT / "server/static/island/assets/crops/beet.png").exists()
    assert (ROOT / "server/static/island/assets/crops/fogpea.png").exists()
    assert "data-act=\"prev\"" in (ROOT / "server/static/island/ui/plant-panel.js").read_text(encoding="utf-8")
    assert "data-act=\"buy\"" in (ROOT / "server/static/island/ui/plant-panel.js").read_text(encoding="utf-8")
    home_js = (ROOT / "server/static/island/scenes/home.js").read_text(encoding="utf-8")
    assert "island-plot-grid" in home_js
    assert "island-plot-bed" in home_js
    assert "island-garden-hot" in home_js
    assert "renderYards" in home_js
    assert "grass.png" in home_js
    assert "plot.png" in home_js
    assert "PAGE_SIZE = 9" in home_js
    assert "data-act=\"expand\"" in home_js
    assert "onTapGrass" in home_js
    assert "n % PAGE_SIZE === 0" in home_js
    store_js = (ROOT / "server/static/island/store.js").read_text(encoding="utf-8")
    assert "点草地开垦第一座" in store_js
    assert "/api/v1/farm/expand" in api
    assert "api.expand" in app
    assert "showExpandSheet" in app
    assert "yardPage" in home_js
    assert "island-plot-pager" in home_js
    assert "bindSwipe" in home_js
    assert "左右滑" in home_js
    assert "data-yard" in home_js
    assert "onTapPlot" in home_js
    assert "sceneArt" in home_js
    assert (ROOT / "server/static/island/scenes/shore.js").exists()
    assert (ROOT / "server/static/island/scenes/plaza.js").exists()
    assert "renderPlace" in (ROOT / "server/static/island/scenes/shore.js").read_text(encoding="utf-8")
    plaza_js = (ROOT / "server/static/island/scenes/plaza.js").read_text(encoding="utf-8")
    assert "island-plaza-board" in plaza_js
    assert "layoutCoverBoard" in plaza_js
    assert 'shop: "杂货铺"' in app
    shop_js = (ROOT / "server/static/island/scenes/shop.js").read_text(encoding="utf-8")
    assert "island-shop-shelf" in shop_js
    assert "island-shop-meta" in shop_js
    assert "is-peek" in shop_js
    assert "点一下看货架" in shop_js
    assert "island-shop-card" not in shop_js
    assert "data-sku" in shop_js
    assert "去上手页" not in shop_js
    assert "api.shopBuy" in app
    assert "showBuySheet" in app
    assert "renderShop" in app
    assert "listTop" in shop_js
    assert "paintShopList" in shop_js
    assert "querySelector(\".island-shop\")" in shop_js
    assert "refreshScene: true" not in app
    assert "/api/v1/shop/buy" in api
    assert "/api/v1/tote/vend" in api
    assert "/api/v1/workshop" in api
    assert "/api/v1/quarry" in api
    assert "/api/v1/bar" in api
    assert "api.workshopAct" in app
    assert "api.quarryAct" in app
    assert "api.barAct" in app
    assert "api.writersAct" in app
    assert "api.atelierAct" in app
    assert "api.hallAct" in app
    assert "keepWorkshop" in app
    workshop_js = (ROOT / "server/static/island/scenes/workshop.js").read_text(encoding="utf-8")
    assert "island-workshop" in workshop_js
    assert "is-peek" in workshop_js
    assert "点一下看砧上" in workshop_js
    assert "data-act" in workshop_js
    assert "去上手页" not in workshop_js
    assert "disabled" not in workshop_js
    assert "showHintSheet" in app
    assert "quiet: true" in app
    quarry_js = (ROOT / "server/static/island/scenes/quarry.js").read_text(encoding="utf-8")
    assert "island-quarry" in quarry_js
    assert "点一下看矿坑" in quarry_js
    assert "data-act" in quarry_js
    assert "去上手页" not in quarry_js
    assert "keepQuarry" in app
    assert "keepBar" in app
    assert "keepWriters" in app
    assert "keepAtelier" in app
    assert "keepHall" in app
    assert "quarryShelf" in app
    assert "barShelf" in app
    assert "writersShelf" in app
    assert "atelierShelf" in app
    assert "hallShelf" in app
    assert "renderWorkshop" in app
    assert "renderBar" in app
    assert "renderTheater" in app
    assert "renderWriters" in app
    assert "renderAtelier" in app
    assert "renderHall" in app
    bar_js = (ROOT / "server/static/island/scenes/bar.js").read_text(encoding="utf-8")
    assert "island-bar" in bar_js
    assert "island-bar-tray" in bar_js
    assert "island-bar-opt" not in bar_js
    assert "is-peek" in bar_js
    assert "点一下看吧台" in bar_js
    assert "洗碗" in bar_js
    assert "data-act" in bar_js
    assert "去上手页" not in bar_js
    assert "disabled" not in bar_js
    assert "bar-opt-frame.png" in css
    assert ".island-bar-tray" in css
    assert ".island-bar-opt" not in css
    bar_frame = ROOT / "server/static/island/assets/bar-opt-frame.png"
    assert bar_frame.exists()
    try:
        from PIL import Image
        frame = Image.open(bar_frame)
        assert frame.size == (2000, 750)
        assert frame.mode == "RGBA"
    except ImportError:
        pass
    assert "showCheerSheet" in app
    assert "showPitchSheet" in app
    assert (ROOT / "server/v1/bar_service.py").exists()
    assert (ROOT / "server/v1/writers_service.py").exists()
    assert (ROOT / "server/v1/atelier_service.py").exists()
    assert (ROOT / "server/v1/hall_service.py").exists()
    theater_js = (ROOT / "server/static/island/scenes/theater.js").read_text(encoding="utf-8")
    writers_js = (ROOT / "server/static/island/scenes/writers.js").read_text(encoding="utf-8")
    atelier_js = (ROOT / "server/static/island/scenes/atelier.js").read_text(encoding="utf-8")
    hall_js = (ROOT / "server/static/island/scenes/hall.js").read_text(encoding="utf-8")
    assert 'go: "writers"' in theater_js
    assert 'go: "atelier"' in theater_js
    assert 'go: "hall"' in theater_js
    assert "island-hot" in theater_js
    assert "island-theater-picks" not in theater_js
    assert "点一下看编剧社" not in theater_js
    assert "编剧社" in theater_js
    assert "衣泊坊" in theater_js
    assert "剧场" in theater_js
    assert "点一下看收稿台" in writers_js
    assert "点一下看坊" in atelier_js
    assert "点一下看看板" in hall_js
    assert "去上手页" not in writers_js
    assert "去上手页" not in atelier_js
    assert "去上手页" not in hall_js
    assert "/api/v1/writers" in api
    assert "/api/v1/atelier" in api
    assert "/api/v1/hall" in api
    assert ".island-theater-board" in css
    assert ".island-theater-picks" not in css
    assert ".island-theater .island-hot span" in css
    assert 'lighthouse: "灯塔"' in app
    assert 'notice: "潮汐公告"' in app
    assert "state.backTo" in app
    assert (ROOT / "server/static/island/assets/scenes/shore.png").exists()
    assert (ROOT / "server/static/island/assets/scenes/bar.png").exists()
    assert (ROOT / "server/static/island/assets/scenes/plaza.png").exists()
    assert (ROOT / "server/static/island/assets/scenes/theater.png").exists()
    assert "港口" in (ROOT / "server/static/island/map.js").read_text(encoding="utf-8")
    assert "剧场" in (ROOT / "server/static/island/map.js").read_text(encoding="utf-8")
    assert "is-theater" in css
    assert "island-plaza-board" in css
    assert "941 / 1672" in css
    assert ".island-shop .island-slot" in css
    assert "island-shop-meta" in css
    assert "island-scene-tap" in css
    assert ".island-shop.is-peek" in css
    assert "island-item-acts" in css
    assert "island-bag-grid" in css
    assert "bag-frame.png" in css
    assert ".island-sheet.is-bag" in css
    assert "object-position: center 38%" in css
    assert "/play?go=star" not in app
    assert (ROOT / "server/static/island/assets/plot.png").exists()
    assert (ROOT / "server/static/island/assets/grass.png").exists()
    try:
        from PIL import Image
        grass = Image.open(ROOT / "server/static/island/assets/grass.png")
        plot = Image.open(ROOT / "server/static/island/assets/plot.png")
        assert grass.size == (512, 512) and grass.mode == "RGBA"
        assert plot.size == (512, 512) and plot.mode == "RGBA"
    except ImportError:
        pass
    assert (ROOT / "server/static/island/assets/scenes/.gitkeep").exists()
    main_py = (ROOT / "server/main.py").read_text(encoding="utf-8")
    assert '@app.get("/play"' in main_py
    assert '@app.get("/island"' in main_py
    assert "island_v1_router" in main_py


if __name__ == "__main__":
    test_island_v1_api()
    print("ok")
