#!/usr/bin/env python3
"""移动端 /api/v1：结构化 JSON、同一存档、防重复。"""
from __future__ import annotations

import asyncio
import os
import re
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
    assert me.json()["me"]["flags"]["hut_built"] is False
    assert me.json()["me"]["flags"]["hut_level"] == 0
    assert me.json()["me"]["hut_build_cost"] == 95
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

    stall0 = client.get("/api/v1/lili", headers=_auth(key))
    assert stall0.status_code == 200, stall0.text
    stall = stall0.json()["lili"]
    assert stall["name"] == "栗栗流动摊", stall
    assert any(t["key"] == "shelf" for t in stall["tabs"]), stall
    assert any(t["key"] == "summon" for t in stall["tabs"]), stall
    miss_summon = client.post(
        "/api/v1/lili/act",
        headers=_auth(key, {"Idempotency-Key": "lili-summon-miss"}),
        json={"kind": "summon", "target": "shell_catseye"},
    )
    assert miss_summon.status_code >= 400, miss_summon.text
    steward = await db.get_steward_by_key_id((await db.get_key_row(key))["id"])
    sid = int(steward["id"])
    async with db.connect() as conn:
        await db.add_item(conn, sid, "shell_catseye", 1)
        await conn.commit()
    hit_summon = client.post(
        "/api/v1/lili/act",
        headers=_auth(key, {"Idempotency-Key": "lili-summon-hit"}),
        json={"kind": "summon", "target": "shell_catseye"},
    )
    assert hit_summon.status_code == 200, hit_summon.text
    assert hit_summon.json()["event"]["kind"] == "lili"
    assert hit_summon.json()["lili"]["here"] is True
    pet = client.post(
        "/api/v1/lili/act",
        headers=_auth(key, {"Idempotency-Key": "lili-pet"}),
        json={"kind": "pet"},
    )
    assert pet.status_code == 200, pet.text

    clinic0 = client.get("/api/v1/clinic", headers=_auth(key))
    assert clinic0.status_code == 200, clinic0.text
    desk = clinic0.json()["clinic"]
    assert desk["name"] == "乔乔诊所", desk
    assert desk["speaker"] == "桥桥", desk
    assert any(t["key"] == "treat" for t in desk["tabs"]), desk
    assert any(t["key"] == "tonic" for t in desk["tabs"]), desk
    assert any(t["key"] == "shelf" for t in desk["tabs"]), desk
    assert any(t["key"] == "dove" for t in desk["tabs"]), desk
    miss_dove = client.post(
        "/api/v1/clinic/act",
        headers=_auth(key, {"Idempotency-Key": "clinic-dove-miss"}),
        json={"kind": "dove", "target": "喂"},
    )
    assert miss_dove.status_code >= 400, miss_dove.text
    hit_buy = client.post(
        "/api/v1/clinic/act",
        headers=_auth(key, {"Idempotency-Key": "clinic-buy-sober"}),
        json={"kind": "buy", "target": "醒酒药"},
    )
    assert hit_buy.status_code == 200, hit_buy.text
    assert hit_buy.json()["event"]["kind"] == "clinic"
    chat = client.post(
        "/api/v1/clinic/act",
        headers=_auth(key, {"Idempotency-Key": "clinic-chat"}),
        json={"kind": "chat"},
    )
    assert chat.status_code == 200, chat.text

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
    assert hall["speaker"] == "小橘", hall
    assert hall["open"] is False, hall
    assert any(t["key"] == "board" for t in hall["tabs"]), hall
    assert any(r["cmd"] == "试镜" and r["can_act"] is False for r in hall["jobs"]), hall
    assert any(r["id"] == "cheer" for r in hall["stars"]), hall
    assert any(r["id"] == "tip" for r in hall["stars"]), hall
    assert any(r["id"] == "watch" for r in hall["stars"]), hall
    assert "打赏小橘仍" not in (hall.get("board") or {}).get("note", "")
    watch_off = client.post(
        "/api/v1/hall/act",
        headers=_auth(key, {"Idempotency-Key": "hall-watch-off"}),
        json={"kind": "watch", "target": ""},
    )
    assert watch_off.status_code >= 400, watch_off.text
    sid = int((await db.get_steward_by_key_id((await db.get_key_row(key))["id"]))["id"])
    async with db.connect() as conn:
        await conn.execute("UPDATE stewards SET tickets=tickets+80 WHERE id=?", (sid,))
        await conn.commit()
    tipped = client.post(
        "/api/v1/hall/act",
        headers=_auth(key, {"Idempotency-Key": "hall-tip"}),
        json={"kind": "tip", "target": "20"},
    )
    assert tipped.status_code == 200, tipped.text
    assert tipped.json()["event"]["kind"] == "hall"
    assert "打赏" in tipped.json()["event"]["narrative"]
    cheered = client.post(
        "/api/v1/hall/act",
        headers=_auth(key, {"Idempotency-Key": "hall-cheer"}),
        json={"kind": "cheer", "target": "今晚很好听"},
    )
    assert cheered.status_code == 200, cheered.text
    fans = client.post(
        "/api/v1/hall/act",
        headers=_auth(key, {"Idempotency-Key": "hall-fans"}),
        json={"kind": "fans", "target": ""},
    )
    assert fans.status_code == 200, fans.text
    audition_off = client.post(
        "/api/v1/hall/act",
        headers=_auth(key, {"Idempotency-Key": "hall-audition-off"}),
        json={"kind": "audition", "target": ""},
    )
    assert audition_off.status_code >= 400, audition_off.text

    stall0 = client.get("/api/v1/eatery", headers=_auth(key))
    assert stall0.status_code == 200, stall0.text
    stall = stall0.json()["eatery"]
    assert stall["name"] == "岸畔小馆", stall
    assert any(t["key"] == "board" for t in stall["tabs"]), stall
    assert any(t["key"] == "mine" for t in stall["tabs"]), stall
    assert stall["mine"]["open"] is False, stall
    dine_miss = client.post(
        "/api/v1/eatery/act",
        headers=_auth(key, {"Idempotency-Key": "eatery-dine-empty"}),
        json={"kind": "dine", "target": ""},
    )
    assert dine_miss.status_code >= 400, dine_miss.text
    host_key = await db.create_api_key("eatery-host@example.com")
    host_open = client.post("/api/v1/session", json={"api_key": host_key, "name": "馆主"})
    assert host_open.status_code == 200, host_open.text
    host = await db.get_steward_by_key_id((await db.get_key_row(host_key))["id"])
    host_sid = int(host["id"])
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET hut_built=1, tickets=200 WHERE id=?",
            (host_sid,),
        )
        await conn.execute(
            "INSERT INTO hut_fittings (steward_id, slot, item_key, installed_at)"
            " VALUES (?, 'soft_1', 'fridge', ?)",
            (host_sid, db.now()),
        )
        await db.add_item(conn, host_sid, "dish_salt_crab_s4", 1)
        await conn.commit()
    opened_shop = client.post(
        "/api/v1/eatery/act",
        headers=_auth(host_key, {"Idempotency-Key": "eatery-open"}),
        json={"kind": "open", "target": ""},
    )
    assert opened_shop.status_code == 200, opened_shop.text
    assert opened_shop.json()["eatery"]["mine"]["open"] is True
    stocked = client.post(
        "/api/v1/eatery/act",
        headers=_auth(host_key, {"Idempotency-Key": "eatery-stock"}),
        json={"kind": "stock", "target": "dish_salt_crab_s4"},
    )
    assert stocked.status_code == 200, stocked.text
    menu = stocked.json()["eatery"]["mine"]["menu"]
    assert menu, stocked.json()["eatery"]
    dish_id = menu[0]["id"]
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET tickets=300 WHERE id=?",
            (sid,),
        )
        await conn.commit()
    guest_board = client.get("/api/v1/eatery", headers=_auth(key))
    assert guest_board.status_code == 200, guest_board.text
    dishes = guest_board.json()["eatery"]["dishes"]
    assert any(row.get("can_dine") for row in dishes), dishes
    dined = client.post(
        "/api/v1/eatery/act",
        headers=_auth(key, {"Idempotency-Key": "eatery-dine-ok"}),
        json={"kind": "dine", "target": f"馆主|{dish_id}"},
    )
    assert dined.status_code == 200, dined.text
    assert dined.json()["event"]["kind"] == "eatery"

    async with db.connect() as conn:
        await db.add_item(conn, sid, "crop_kale", 2)
        await conn.commit()
    bazaar0 = client.get("/api/v1/market", headers=_auth(key))
    assert bazaar0.status_code == 200, bazaar0.text
    bazaar = bazaar0.json()["market"]
    assert bazaar["name"] == "玩家集市", bazaar
    assert any(t["key"] == "board" for t in bazaar["tabs"]), bazaar
    assert any(t["key"] == "mine" for t in bazaar["tabs"]), bazaar
    hung = client.post(
        "/api/v1/market/act",
        headers=_auth(key, {"Idempotency-Key": "market-sell"}),
        json={"kind": "sell", "target": "crop_kale 1 8"},
    )
    assert hung.status_code == 200, hung.text
    assert hung.json()["event"]["kind"] == "market"
    lots = hung.json()["market"]["mine"]["listings"]
    assert lots, hung.json()["market"]
    lot_id = lots[0]["id"]
    own_buy = client.post(
        "/api/v1/market/act",
        headers=_auth(key, {"Idempotency-Key": "market-buy-own"}),
        json={"kind": "buy", "target": str(lot_id)},
    )
    assert own_buy.status_code >= 400, own_buy.text
    guest_buy = client.post(
        "/api/v1/market/act",
        headers=_auth(host_key, {"Idempotency-Key": "market-buy"}),
        json={"kind": "buy", "target": str(lot_id)},
    )
    assert guest_buy.status_code == 200, guest_buy.text

    from server import wall
    wall.COOLDOWN_SEC = 0
    ting0 = client.get("/api/v1/ting", headers=_auth(key))
    assert ting0.status_code == 200, ting0.text
    ting = ting0.json()["ting"]
    assert ting["name"] == "听潮亭", ting
    assert any(t["key"] == "ask" for t in ting["tabs"]), ting
    assert any(t["key"] == "mine" for t in ting["tabs"]), ting
    assert "boards" in ting and "ask" in ting["boards"], ting
    posted = client.post(
        "/api/v1/ting/act",
        headers=_auth(key, {"Idempotency-Key": "ting-post"}),
        json={"kind": "post", "target": "ask|温室怎么建|先 shed erect 再 sow 棚1"},
    )
    assert posted.status_code == 200, posted.text
    assert posted.json()["event"]["kind"] == "ting"
    mine = posted.json()["ting"]["mine"]
    assert mine, posted.json()["ting"]
    note_id = mine[0]["id"]
    looked = client.post(
        "/api/v1/ting/act",
        headers=_auth(key, {"Idempotency-Key": "ting-look"}),
        json={"kind": "look", "target": str(note_id)},
    )
    assert looked.status_code == 200, looked.text
    assert "温室怎么建" in looked.json()["event"]["narrative"]
    replied = client.post(
        "/api/v1/ting/act",
        headers=_auth(host_key, {"Idempotency-Key": "ting-reply"}),
        json={"kind": "reply", "target": f"{note_id}|谢了棚盖好了就能种"},
    )
    assert replied.status_code == 200, replied.text
    torn = client.post(
        "/api/v1/ting/act",
        headers=_auth(key, {"Idempotency-Key": "ting-tear"}),
        json={"kind": "tear", "target": str(note_id)},
    )
    assert torn.status_code == 200, torn.text
    assert not torn.json()["ting"]["mine"], torn.json()["ting"]

    hui0 = client.get("/api/v1/hui", headers=_auth(key))
    assert hui0.status_code == 200, hui0.text
    hall = hui0.json()["hui"]
    assert hall["name"] == "潮生会", hall
    assert any(t["key"] == "tax" for t in hall["tabs"]), hall
    assert any(t["key"] == "fund" for t in hall["tabs"]), hall
    asked = client.post(
        "/api/v1/hui/act",
        headers=_auth(key, {"Idempotency-Key": "hui-look-ask"}),
        json={"kind": "look", "target": "ask"},
    )
    assert asked.status_code == 200, asked.text
    assert asked.json()["event"]["kind"] == "hui"
    taxed = client.post(
        "/api/v1/hui/act",
        headers=_auth(key, {"Idempotency-Key": "hui-look-tax"}),
        json={"kind": "look", "target": "tax"},
    )
    assert taxed.status_code == 200, taxed.text
    noted = client.post(
        "/api/v1/hui/act",
        headers=_auth(key, {"Idempotency-Key": "hui-look-notice"}),
        json={"kind": "look", "target": "notice"},
    )
    assert noted.status_code == 200, noted.text

    lianli0 = client.get("/api/v1/lianli", headers=_auth(key))
    assert lianli0.status_code == 200, lianli0.text
    desk = lianli0.json()["lianli"]
    assert desk["name"] == "连理所", desk
    assert any(t["key"] == "desk" for t in desk["tabs"]), desk
    filed = client.post(
        "/api/v1/lianli/act",
        headers=_auth(key, {"Idempotency-Key": "lianli-look-desk"}),
        json={"kind": "look", "target": "desk"},
    )
    assert filed.status_code == 200, filed.text
    assert filed.json()["event"]["kind"] == "lianli"
    betroth_look = client.post(
        "/api/v1/lianli/act",
        headers=_auth(key, {"Idempotency-Key": "lianli-look-betroth"}),
        json={"kind": "look", "target": "betroth"},
    )
    assert betroth_look.status_code == 200, betroth_look.text
    betroth_text = betroth_look.json()["event"]["narrative"] or ""
    assert "/lianli/" not in betroth_text
    assert "求婚草稿" in betroth_text or "信物" in betroth_text

    shore0 = client.get("/api/v1/shore", headers=_auth(key))
    assert shore0.status_code == 200, shore0.text
    pier = shore0.json()["shore"]
    dock = shore0.json()["port"]
    assert pier["name"] == "海边", pier
    assert any(t["key"] == "beach" for t in pier["tabs"]), pier
    assert all(t["key"] != "cast" for t in pier["tabs"]), pier
    assert dock["name"] == "港口", dock
    assert any(t["key"] == "cast" for t in dock["tabs"]), dock
    assert any(t["key"] == "voyage" for t in dock["tabs"]), dock
    assert all(t["key"] != "chat" for t in dock["tabs"]), dock
    looked_sea = client.post(
        "/api/v1/shore/act",
        headers=_auth(key, {"Idempotency-Key": "shore-look-status"}),
        json={"kind": "look", "target": "status"},
    )
    assert looked_sea.status_code == 200, looked_sea.text
    assert looked_sea.json()["event"]["kind"] == "shore"
    scanned = client.post(
        "/api/v1/shore/act",
        headers=_auth(key, {"Idempotency-Key": "shore-look-beach"}),
        json={"kind": "look", "target": "beach"},
    )
    assert scanned.status_code == 200, scanned.text

    tower0 = client.get("/api/v1/lighthouse", headers=_auth(key))
    assert tower0.status_code == 200, tower0.text
    tower = tower0.json()["lighthouse"]
    assert tower["speaker"] == "不醒", tower
    assert tower["name"] == "灯塔", tower
    assert any(row["id"] == "tea" for row in tower["choices"]), tower
    assert any(row["id"] == "light" for row in tower["choices"]), tower
    tea = client.post(
        "/api/v1/lighthouse/act",
        headers=_auth(key, {"Idempotency-Key": "lh-tea"}),
        json={"kind": "tea", "target": ""},
    )
    assert tea.status_code == 200, tea.text
    assert tea.json()["event"]["kind"] == "lighthouse"
    assert "精力" in tea.json()["event"]["narrative"]
    tea2 = client.post(
        "/api/v1/lighthouse/act",
        headers=_auth(key, {"Idempotency-Key": "lh-tea2"}),
        json={"kind": "tea", "target": ""},
    )
    assert tea2.status_code == 200, tea2.text
    assert "今天喝过了" in tea2.json()["event"]["narrative"]
    light_miss = client.post(
        "/api/v1/lighthouse/act",
        headers=_auth(key, {"Idempotency-Key": "lh-light-empty"}),
        json={"kind": "light", "target": ""},
    )
    assert light_miss.status_code >= 400, light_miss.text
    lit = client.post(
        "/api/v1/lighthouse/act",
        headers=_auth(key, {"Idempotency-Key": "lh-light-ok"}),
        json={"kind": "light", "target": "妈妈 | 平安"},
    )
    assert lit.status_code == 200, lit.text
    assert "第 1 盏" in lit.json()["event"]["narrative"]
    gallery = client.post(
        "/api/v1/lighthouse/act",
        headers=_auth(key, {"Idempotency-Key": "lh-gallery"}),
        json={"kind": "gallery", "target": ""},
    )
    assert gallery.status_code == 200, gallery.text
    assert "给妈妈点的" in gallery.json()["event"]["narrative"]

    desk0 = client.get("/api/v1/shaonian", headers=_auth(key))
    assert desk0.status_code == 200, desk0.text
    desk = desk0.json()["shaonian"]
    assert desk["speaker"] == "韶年", desk
    assert desk["name"] == "韶年望潮人", desk
    assert any(row["id"] == "fortune" for row in desk["choices"]), desk
    assert any(row["id"] == "transfer" for row in desk["choices"]), desk
    seen = client.post(
        "/api/v1/shaonian/act",
        headers=_auth(key, {"Idempotency-Key": "sn-visit"}),
        json={"kind": "visit", "target": ""},
    )
    assert seen.status_code == 200, seen.text
    assert seen.json()["event"]["kind"] == "shaonian"
    assert "韶年" in seen.json()["event"]["narrative"]
    roll = client.post(
        "/api/v1/shaonian/act",
        headers=_auth(key, {"Idempotency-Key": "sn-fortune"}),
        json={"kind": "fortune", "target": ""},
    )
    assert roll.status_code == 200, roll.text
    assert "卦" in roll.json()["event"]["narrative"] or "韶年" in roll.json()["event"]["narrative"]

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
    assert world.json()["world"]["weather_code"] in {"clear", "misty", "gale"}
    assert world.json()["world"]["season"]
    assert world.json()["world"]["season_hint"]

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
    assert built.json()["me"]["flags"]["hut_level"] == 1
    assert built.json()["me"]["flags"]["hut_name"] == "棚屋"
    async with db.connect() as conn:
        await conn.execute(
            "INSERT INTO hut_fittings (steward_id, slot, item_key, installed_at) VALUES (?,?,?,?)",
            (sid, "hard_1", "bed", 1),
        )
        await conn.execute("UPDATE stewards SET energy=20 WHERE id=?", (sid,))
        await conn.commit()
    hut_snap = client.get("/api/v1/hut", headers=_auth(key))
    assert hut_snap.status_code == 200, hut_snap.text
    hut_body = hut_snap.json()["hut"]
    assert hut_body["built"] is True
    assert hut_body["can_sleep"] is True
    assert any(t["key"] == "home" for t in hut_body["tabs"])
    assert any(t["key"] == "cook" for t in hut_body["tabs"])
    assert any(t["key"] == "cabinet" for t in hut_body["tabs"])
    assert any(t["key"] == "compost" for t in hut_body["tabs"])
    assert any(t["key"] == "barn" for t in hut_body["tabs"])
    assert any(row["kind"] == "cook" for row in (hut_body["items"].get("cook") or []))
    slept = client.post(
        "/api/v1/hut/sleep",
        headers=_auth(key, {"Idempotency-Key": "hut-sleep"}),
        json={},
    )
    assert slept.status_code == 200, slept.text
    assert slept.json()["event"]["kind"] == "hut"

    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET tickets=tickets+500 WHERE id=?",
            (sid,),
        )
        await db.add_item(conn, sid, "crop_kale", 3)
        await db.add_item(conn, sid, "fish_mackerel", 2)
        await db.add_item(conn, sid, "manure_sheep", 4)
        await conn.commit()
    cooked = client.post(
        "/api/v1/hut/act",
        headers=_auth(key, {"Idempotency-Key": "hut-cook"}),
        json={"kind": "cook", "target": "甘蓝 鲭鱼"},
    )
    assert cooked.status_code == 200, cooked.text
    assert cooked.json()["event"]["kind"] == "hut"
    assert cooked.json()["event"]["title"] == "出锅了"
    cook_tab = cooked.json()["hut"]["items"]["cook"]
    assert any(row["kind"] == "mix_pick" for row in cook_tab)
    assert any(row["kind"] == "cook_mix" for row in cook_tab)
    looked = client.post(
        "/api/v1/hut/act",
        headers=_auth(key, {"Idempotency-Key": "hut-look"}),
        json={"kind": "look", "target": "status"},
    )
    assert looked.status_code == 200, looked.text
    assert looked.json()["event"]["kind"] == "hut"
    upgraded = client.post(
        "/api/v1/hut/act",
        headers=_auth(key, {"Idempotency-Key": "hut-upgrade"}),
        json={"kind": "upgrade"},
    )
    assert upgraded.status_code == 200, upgraded.text
    assert upgraded.json()["me"]["flags"]["hut_level"] == 2
    assert upgraded.json()["me"]["flags"]["hut_name"] == "岸畔小屋"
    cab = client.post(
        "/api/v1/hut/act",
        headers=_auth(key, {"Idempotency-Key": "hut-cab"}),
        json={"kind": "buy_install", "target": "cabinet"},
    )
    assert cab.status_code == 200, cab.text
    put = client.post(
        "/api/v1/hut/act",
        headers=_auth(key, {"Idempotency-Key": "hut-put"}),
        json={"kind": "put", "target": "甘蓝 2"},
    )
    assert put.status_code == 200, put.text
    bin_on = client.post(
        "/api/v1/hut/act",
        headers=_auth(key, {"Idempotency-Key": "hut-bin"}),
        json={"kind": "buy_install", "target": "compost_bin"},
    )
    assert bin_on.status_code == 200, bin_on.text
    composted = client.post(
        "/api/v1/hut/act",
        headers=_auth(key, {"Idempotency-Key": "hut-compost"}),
        json={"kind": "compost_put", "target": "羊粪 3"},
    )
    assert composted.status_code == 200, composted.text
    erected = client.post(
        "/api/v1/hut/act",
        headers=_auth(key, {"Idempotency-Key": "hut-barn"}),
        json={"kind": "barn_erect"},
    )
    assert erected.status_code == 200, erected.text
    assert erected.json()["hut"]["items"]["barn"]

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

    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET tax_arrears=12, tickets=tickets+40 WHERE id=?",
            (sid,),
        )
        await conn.commit()
    paid_act = client.post(
        "/api/v1/hui/act",
        headers=_auth(key, {"Idempotency-Key": "hui-act-tax"}),
        json={"kind": "pay", "target": "tax"},
    )
    assert paid_act.status_code == 200, paid_act.text
    assert paid_act.json()["event"]["kind"] == "hui"
    assert int(paid_act.json()["me"]["dues"]["tax_arrears"] or 0) == 0
    fund_look = client.post(
        "/api/v1/hui/act",
        headers=_auth(key, {"Idempotency-Key": "hui-look-fund"}),
        json={"kind": "look", "target": "fund"},
    )
    assert fund_look.status_code == 200, fund_look.text

    page = client.get("/island")
    assert page.status_code == 200, page.text
    assert "手机地图" in page.text or "island-root" in page.text


def test_island_page_is_modular() -> None:
    html = (ROOT / "server/templates/island.html").read_text(encoding="utf-8")
    css = (ROOT / "server/static/island/island.css").read_text(encoding="utf-8")
    app = (ROOT / "server/static/island/app.js").read_text(encoding="utf-8")
    api = (ROOT / "server/static/island/api.js").read_text(encoding="utf-8")
    assert "/static/island/app.js" in html
    assert "island-mapbgm1" in app
    assert html.count("island.css?v=island-xiaojucut1") == 1
    assert html.count("app.js?v=island-lilisprite1") == 1
    assert html.count("lounge-embed.css?v=island-portlounge1") == 1
    assert "lounge.js?v=lounge-board-compose6" in html
    assert "island-time.js" in html
    assert 'include "partials/island-lounge.html"' in html
    lounge_embed = (ROOT / "server/templates/partials/island-lounge.html").read_text(encoding="utf-8")
    lounge_css = (ROOT / "server/static/lounge-embed.css").read_text(encoding="utf-8")
    lounge_js = (ROOT / "server/static/lounge.js").read_text(encoding="utf-8")
    assert "id=\"island-lounge\"" in lounge_embed
    assert "id=\"lounge-feed\"" in lounge_embed
    assert "发红包" in lounge_embed
    assert "对暗号" in lounge_embed
    assert "许愿墙" in lounge_embed
    assert "id=\"lounge-packet-btn\"" in lounge_embed
    assert "id=\"lounge-booth-code\"" in lounge_embed
    assert "id=\"lounge-booth-enter\"" in lounge_embed
    assert "id=\"lounge-booth-leave\"" in lounge_embed
    assert 'data-lounge-tool="packet"' in lounge_embed
    assert 'data-lounge-tool="booth"' in lounge_embed
    assert 'data-lounge-tool="board"' in lounge_embed
    assert "lounge-packet-grab" in lounge_js
    assert "lounge-packet-total" in lounge_js
    assert "/api/lounge/packet" in lounge_js
    assert "/api/lounge/grab" in lounge_js
    assert "/api/lounge/booth" in lounge_js
    assert "/api/lounge/board" in lounge_js
    assert "body.island-app.is-port-chat" in lounge_css
    assert ".lounge-booth-bar" in lounge_css
    assert "发红包" in html
    assert "对暗号" in html
    assert "许愿墙" in html
    assert "bgm.js?v=island-burgertown1" in app
    assert "lighthouse.js?v=island-mapbgm1" in app
    assert "hall.js?v=island-mapbgm1" in app
    assert "shop.js?v=island-mapbgm1" in app
    assert "lili.js?v=island-lilisprite1" in app
    assert "clinic.js?v=island-mapbgm1" in app
    assert "market.js?v=island-mapbgm1" in app
    js_blob = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "server/static/island").rglob("*.js"))
    store_vs = set(re.findall(r"store\.js\?v=([^\s\"']+)", js_blob))
    modal_vs = set(re.findall(r"modal\.js\?v=([^\s\"']+)", js_blob))
    assert store_vs == {"island-mapbgm1"}, store_vs
    assert modal_vs == {"island-mapbgm1"}, modal_vs
    assert 'from "../store.js?v=island-mapbgm1"' in (ROOT / "server/static/island/scenes/atelier.js").read_text(encoding="utf-8")
    assert 'from "../store.js?v=island-mapbgm1"' in (ROOT / "server/static/island/scenes/writers.js").read_text(encoding="utf-8")
    assert 'from "../store.js?v=island-mapbgm1"' in (ROOT / "server/static/island/scenes/hall.js").read_text(encoding="utf-8")
    hut_js = (ROOT / "server/static/island/scenes/hut.js").read_text(encoding="utf-8")
    store_js = (ROOT / "server/static/island/store.js").read_text(encoding="utf-8")
    art_js = (ROOT / "server/static/island/ui/art.js").read_text(encoding="utf-8")
    assert "没买房" in hut_js
    assert "棚屋场景还锁着" in hut_js
    assert "点一下看屋里" in hut_js
    assert "能睡、做饭、升级、潮柜、堆肥桶、畜栏" in hut_js
    assert "mix_pick" in hut_js
    assert "cook_mix" in hut_js
    assert "ensureShopFrame" in hut_js
    assert "去上手页" not in hut_js
    assert "api.hutAct" in app
    assert "keepHut" in app
    assert 'hut.js?v=island-hutcook1' in app
    assert "kind === \"cook_mix\"" in app
    assert "openHut" in app
    assert "renderHut" in app
    assert 'name === "hut"' in app
    assert "hutScene" in store_js
    assert '"hut-1"' in art_js and '"hut-4"' in art_js
    for name in ("hut-1.png", "hut-2.png", "hut-3.png", "hut-4.png"):
        assert (ROOT / "server/static/island/assets/scenes" / name).exists(), name
    assert "island-mapbgm1" in html
    assert "boot.js?v=island-mapbgm1" in html
    assert 'id="island-boot-veil"' in html
    assert "正在进入" in html
    assert "fonts.googleapis.com" not in html
    assert "/static/island/tap.js" in html
    assert "/static/island/boot.js" in html
    assert 'id="island-enter"' in html
    assert "novalidate" in html
    assert "island-dock" in html
    assert 'id="island-bag-chip"' in html
    assert 'id="island-back-chip"' in html
    assert 'id="island-bgm-chip"' in html
    assert ">静音<" not in html
    assert "chip-bgm-pause.png" in html
    assert "chip-bgm-play.png" in html
    assert ' data-src="/static/island/assets/chip-bgm-pause.png"' in html
    assert ' data-play="/static/island/assets/chip-bgm-play.png"' in html
    assert 'src="/static/island/assets/chip-bgm-pause.png"' not in html.replace("data-src=", "x=").replace("data-pause=", "x=")
    assert 'src="/static/island/assets/chip-bgm-play.png"' not in html.replace("data-src=", "x=").replace("data-play=", "x=")
    assert ' data-src="/static/island/assets/chip-bag.png"' in html
    assert ' data-src="/static/island/assets/chip-back.png"' in html
    assert html.count("/static/island/assets/chip-bag.png") == 1
    assert 'src="/static/island/assets/chip-bag.png"' not in html.replace("data-src=", "x=")
    assert 'src="/static/island/assets/chip-back.png"' not in html.replace("data-src=", "x=")
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
    map_jpg = ROOT / "server/static/island/assets/scenes/island-map.jpg"
    assert map_png.exists()
    assert map_jpg.exists()
    assert map_jpg.stat().st_size < 500_000
    try:
        from PIL import Image
        assert Image.open(map_png).size == (972, 1619)
        assert Image.open(map_jpg).size == (972, 1619)
    except ImportError:
        pass
    assert "min-height: 48px" in css
    assert "overflow-x: hidden" in css
    assert "island-plot-tile" in css
    assert "island-plot-bed" in css
    assert "island-yards" in css
    assert "island-yards-board" in css
    assert ".island-yards.is-peek" in css
    assert ".island-yards .island-scene-tap" in css
    assert "island-slot" in css
    assert "island-hot" in css
    assert "island-map-board" in css
    assert "is-playing" in css
    assert "island-boot-veil" in css
    assert "island-boot-spin" in css
    assert "is-entering" in css
    assert "正在进入" in app
    assert "waitScenePics" in app
    assert "await waitScenePics" in app
    assert "enterGen" in app
    assert 'from "./ui/modal.js?v=island-mapbgm1"' in app
    modal_src = (ROOT / "server/static/island/ui/modal.js").read_text(encoding="utf-8")
    assert "export function showFormSheet" in modal_src
    assert "export function showPickSheet" in modal_src
    assert "铺满一屏" in css
    assert "底下不漏色" in css
    assert "max-width: 480px" in css
    art_js = (ROOT / "server/static/island/ui/art.js").read_text(encoding="utf-8")
    assert "sW = cw / iw" in art_js
    assert "Math.max(sW, sH" in art_js
    assert "decoding=\"async\"" in art_js
    assert "scenePicUrl" in art_js
    assert "island-map.jpg" in art_js or 'ext: "jpg"' in art_js
    assert "layoutCoverBoard" in map_js
    assert "layoutCoverBoard" in art_js
    assert "is-playing" in (ROOT / "server/static/island/boot.js").read_text(encoding="utf-8")
    assert "island-place" in css
    assert "is-locked" in css
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
    assert "AbortController" in api
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
    assert "island-map.jpg" in boot
    assert "VEIL_MS" in boot
    assert "PIC_MS" in boot
    assert "25000" in boot
    assert "30000" in boot
    assert "8000" in boot
    assert "picHasPixels" in boot
    assert "naturalWidth" in boot
    assert "is-entering" in boot
    assert "showVeil" in boot
    assert "waitPics" in boot
    assert "waitOnePic" in boot
    assert "img.decode" in boot
    assert "正在进入" in boot
    assert "thirstyYard" in (ROOT / "server/static/island/store.js").read_text(encoding="utf-8")
    assert "plotToken" in app
    assert "renderYards" in app
    assert "yardsShelf" in app
    assert "enterScene(\"yards\"" in app
    assert 'name === "home"' in app
    assert "backChipMarkup" not in (ROOT / "server/static/island/scenes/home.js").read_text(encoding="utf-8")
    back_js = (ROOT / "server/static/island/ui/back-map.js").read_text(encoding="utf-8")
    assert "setBackChip" in back_js
    assert "data-src" in back_js
    assert "revealChipSrc" in back_js
    assert "setBagChip" in app
    assert "setBagChip(name !== \"map\")" in app
    assert "left: 0" in css
    assert "min(196px, 58%)" in css
    assert "min(88px, 24%)" in css
    assert "right: min(58px, 16%)" in css
    assert "min(46px, 13%)" in css
    assert "height: 33px" not in css
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
    modal_js = (ROOT / "server/static/island/ui/modal.js").read_text(encoding="utf-8")
    assert "url(\"/static/island/assets/prompt-frame.png\")" not in css
    assert "prompt-frame.png" in modal_js
    assert "island-card-inner" in css
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
    assert (ROOT / "server/static/island/assets/chip-bgm-pause.png").exists()
    assert (ROOT / "server/static/island/assets/chip-bgm-play.png").exists()
    try:
        from PIL import Image
        back = Image.open(ROOT / "server/static/island/assets/chip-back.png")
        assert back.size == (2000, 667)
        assert back.mode == "RGBA"
        assert back.getpixel((0, 0))[3] == 0
        pause = Image.open(ROOT / "server/static/island/assets/chip-bgm-pause.png")
        play = Image.open(ROOT / "server/static/island/assets/chip-bgm-play.png")
        assert pause.size == (420, 285)
        assert play.size == (420, 295)
        assert pause.mode == "RGBA" and play.mode == "RGBA"
        assert pause.getpixel((0, 0))[3] == 0
        assert play.getpixel((0, 0))[3] == 0
    except ImportError:
        pass
    assert "is-yards .island-actionbar" in css
    assert not (ROOT / "server/static/island/assets/back-map.png").exists()
    assert "buySeed" not in app
    assert "api.buy(" not in app
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
    assert "ensureShopFrame" in (ROOT / "server/static/island/scenes/shore.js").read_text(encoding="utf-8")
    plaza_js = (ROOT / "server/static/island/scenes/plaza.js").read_text(encoding="utf-8")
    assert "发言" not in plaza_js
    assert "洗碗" not in plaza_js
    assert "杂货铺" in plaza_js
    assert "灯塔" in plaza_js
    assert "乔乔诊所" in plaza_js
    assert "岸工坊" not in plaza_js
    assert "潮汐公告" in plaza_js
    assert 'go: "shop"' in plaza_js
    assert 'go: "lighthouse"' in plaza_js
    assert 'go: "clinic"' in plaza_js
    assert 'go: "workshop"' not in plaza_js
    assert 'go: "notice"' in plaza_js
    assert 'go: "lili"' in plaza_js
    assert "栗栗流动摊" in plaza_js
    assert "/api/v1/farm/buy" in api
    assert "/tend" in api
    assert "/fertilize" in api
    assert "api.tend" in app
    assert "api.fertilize" in app
    assert "/api/v1/hut/sleep" in api
    assert "/api/v1/hut" in api
    assert "api.hutAct" in app
    assert (ROOT / "server/v1/hut_service.py").exists()
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
    assert "scenes/island-map.jpg" in (ROOT / "server/static/island/assets/ART.md").read_text(encoding="utf-8")
    assert "scenes/yards.png" in (ROOT / "server/static/island/assets/ART.md").read_text(encoding="utf-8")
    assert "scenes/eatery.png" in (ROOT / "server/static/island/assets/ART.md").read_text(encoding="utf-8")
    assert "点一下才出菜单" in (ROOT / "server/static/island/assets/ART.md").read_text(encoding="utf-8")
    assert "scenes/hui.png" in (ROOT / "server/static/island/assets/ART.md").read_text(encoding="utf-8")
    assert "scenes/market.png" in (ROOT / "server/static/island/assets/ART.md").read_text(encoding="utf-8")
    assert "scenes/ting.png" in (ROOT / "server/static/island/assets/ART.md").read_text(encoding="utf-8")
    assert "scenes/lianli.png" in (ROOT / "server/static/island/assets/ART.md").read_text(encoding="utf-8")
    art_md = (ROOT / "server/static/island/assets/ART.md").read_text(encoding="utf-8")
    assert "bar-opt-frame.png" not in art_md
    assert "scene-tap-frame.png" not in art_md
    assert "scenes/workshop.png" in art_md
    assert "scenes/shop.png" in art_md
    assert "scenes/lili.png" in art_md
    assert "scenes/clinic.png" in art_md
    assert "scenes/beach.png" in art_md
    assert "scenes/port.png" in art_md
    assert "audio/island.mp3" in art_md
    assert "audio/clinic.mp3" not in art_md
    assert "chip-bgm-pause.png" in art_md
    assert "chip-bgm-play.png" in art_md
    assert "贝壳音乐钮" in art_md
    assert "摊车特写" in art_md
    assert "scenes/lighthouse.png" in art_md
    assert "scenes/notice.png" in art_md
    assert "climate-frame.png" in art_md
    assert "天气 / 潮汐 / 时辰 / 季节" in art_md
    assert "杂货铺" in art_md and "潮汐公告" in art_md
    climate_js = (ROOT / "server/static/island/ui/climate.js").read_text(encoding="utf-8")
    assert "function showClimateSheet" in climate_js
    assert "function renderNotice" not in climate_js
    assert "climate-frame.png" in climate_js
    assert "island-climate-val" in climate_js
    assert "时辰" in climate_js
    assert "island-climate-title" not in climate_js
    assert "rgba(35, 48, 56, .28)" in css
    assert "1536 / 1024" in css
    assert "island-climate-lab" in climate_js
    assert 'left: 36%' in css
    assert 'left: 64%' in css
    assert "top: 46%" in css
    climate_frame = ROOT / "server/static/island/assets/climate-frame.png"
    assert climate_frame.exists()
    try:
        from PIL import Image
        frame = Image.open(climate_frame)
        assert frame.size == (1536, 1024)
        assert frame.mode == "RGBA"
        corner = frame.getpixel((0, 0))
        assert corner[3] == 0
    except ImportError:
        pass
    assert "island-climate-chip" in (ROOT / "server/templates/island.html").read_text(encoding="utf-8")
    assert ".island-climate" in css
    assert "renderNotice" not in app
    assert "openClimateSheet" in app
    assert 'go === "notice"' in app
    assert "setClimateChip" in app
    assert "潮汐公告进了只显示地名" not in (ROOT / "server/templates/partials/island-manual-content.html").read_text(encoding="utf-8")
    assert "scenes/quarry.png" in (ROOT / "server/static/island/assets/ART.md").read_text(encoding="utf-8")
    try:
        from PIL import Image
        for place in ("eatery", "hui", "market", "ting", "lianli", "workshop", "quarry", "shop", "lighthouse", "clinic"):
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
    plant_js = (ROOT / "server/static/island/ui/plant-panel.js").read_text(encoding="utf-8")
    assert "data-act=\"buy\"" not in plant_js
    assert "island-plant-buy" not in plant_js
    assert "onBuy" not in plant_js
    assert "种植面板只出背包里有的种" in plant_js
    home_js = (ROOT / "server/static/island/scenes/home.js").read_text(encoding="utf-8")
    assert "island-plot-grid" in home_js
    assert "island-plot-bed" in home_js
    assert "island-garden-hot" in home_js
    assert "renderYards" in home_js
    assert "点一下看地" in home_js
    assert "is-peek" in home_js
    assert "island-yards-board" in home_js
    assert "yardsShelf" in home_js
    assert "grass.png" in home_js
    assert "plot.png" in home_js
    assert "PAGE_SIZE = 9" in home_js
    assert "data-act=\"expand\"" in home_js
    assert "onTapGrass" in home_js
    assert "n % PAGE_SIZE === 0" in home_js
    store_js = (ROOT / "server/static/island/store.js").read_text(encoding="utf-8")
    assert "yardsShelf" in store_js
    assert "点草地开垦第一座" in store_js
    assert "seed_qty || 0) > 0" in store_js
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
    assert "ensureShopFrame" in (ROOT / "server/static/island/scenes/shore.js").read_text(encoding="utf-8")
    plaza_js = (ROOT / "server/static/island/scenes/plaza.js").read_text(encoding="utf-8")
    assert "island-plaza-board" in plaza_js
    assert "layoutCoverBoard" in plaza_js
    assert 'shop: "杂货铺"' in app
    shop_js = (ROOT / "server/static/island/scenes/shop.js").read_text(encoding="utf-8")
    frame_js = (ROOT / "server/static/island/ui/shop-frame.js").read_text(encoding="utf-8")
    assert "ensureShopFrame" in shop_js
    assert "island-shop-shelf" in frame_js
    assert "boardW" in frame_js
    assert "boardH" in frame_js
    assert "不换裁切" in frame_js
    assert "不重载底图" in frame_js
    assert "和灯塔选项一个样子" in css
    assert "底下深色金边框" in css
    assert "grid-template-columns: 1fr 1fr" in css.split(".island-shop-list")[1].split(".island-shop-sku")[0]
    assert "island-shop-meta" in shop_js
    assert "setShopPeek" in shop_js
    assert "is-peek" in frame_js
    assert "点一下看货架" in shop_js
    assert "island-shop-card" not in shop_js
    assert "data-sku" in shop_js
    assert "去上手页" not in shop_js
    assert "api.shopBuy" in app
    assert "showBuySheet" in app
    assert "renderShop" in app
    assert "listTop" in shop_js
    assert "paintShopList" in shop_js
    assert ".island-shop:not(.island-workshop)" in shop_js
    assert ":not(.island-eatery)" in shop_js
    assert ":not(.island-market)" in shop_js
    assert ":not(.island-lili)" in shop_js
    assert ":not(.island-clinic)" in shop_js
    assert "refreshScene: true" not in app
    assert 'LIVE_SCENES = ["home", "yards", "hut"]' in app
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
    assert "api.eateryAct" in app
    assert "/api/v1/lili" in api
    assert "api.liliAct" in app
    assert "keepLili" in app
    assert "renderLili" in app
    lili_js = (ROOT / "server/static/island/scenes/lili.js").read_text(encoding="utf-8")
    assert "island-lili" in lili_js
    assert "island-vn" in lili_js
    assert "island-vn-stand" in lili_js
    assert "is-half" in lili_js
    assert "sprites/lili.png" in lili_js
    assert "点一下见栗栗" in lili_js
    assert "ensureShopFrame" not in lili_js
    assert "点一下看摊" not in lili_js
    assert "island-shop-shelf" not in lili_js
    assert "去上手页" not in lili_js
    assert "liliMeet" in app
    assert "meetLili" in app
    assert "speakLili" in app
    assert (ROOT / "server/static/island/assets/sprites/lili.png").exists()
    try:
        from PIL import Image
        sprite = Image.open(ROOT / "server/static/island/assets/sprites/lili.png")
        assert sprite.size == (1024, 1536)
        assert sprite.mode == "RGBA"
        assert sprite.getpixel((0, 0))[3] == 0
    except ImportError:
        pass
    tap_lili = app.split("function tapLili")[1].split("async function runLili")[0]
    assert "speakLili" in tap_lili
    assert "showHintSheet" not in tap_lili
    assert "showActSheet" not in tap_lili
    assert "/api/v1/clinic" in api
    assert "api.clinicAct" in app
    assert "keepClinic" in app
    assert "renderClinic" in app
    clinic_js = (ROOT / "server/static/island/scenes/clinic.js").read_text(encoding="utf-8")
    assert "island-clinic" in clinic_js
    assert "island-vn" in clinic_js
    assert "island-vn-stand" in clinic_js
    assert "is-half" in clinic_js
    assert "sprites/qiaoqiao.png" in clinic_js
    assert "点一下见桥桥" in clinic_js
    assert "ensureShopFrame" not in clinic_js
    assert "点一下看诊" not in clinic_js
    assert "island-shop-shelf" not in clinic_js
    assert "去上手页" not in clinic_js
    assert "island-vn-mute" not in clinic_js
    assert "bgm.js" not in clinic_js
    assert "clinicMeet" in app
    assert "meetClinic" in app
    assert "speakClinic" in app
    assert "/api/v1/shaonian" in api
    assert "api.shaonianAct" in app
    assert "keepShaonian" in app
    assert "renderShaonian" in app
    shaonian_js = (ROOT / "server/static/island/scenes/shaonian.js").read_text(encoding="utf-8")
    assert "island-shaonian" in shaonian_js
    assert "island-vn" in shaonian_js
    assert "island-vn-stand" in shaonian_js
    assert "is-half" in shaonian_js
    assert "sprites/shaonian.png" in shaonian_js
    assert 'sceneArt("beach")' in shaonian_js
    assert "点一下见韶年" in shaonian_js
    assert "点一下看沙滩" not in shaonian_js
    assert "去赶海" in shaonian_js
    assert "renderBeachHub" not in shaonian_js
    assert "island-beach-hub" not in shaonian_js
    assert "ensureShopFrame" not in shaonian_js
    assert "去上手页" not in shaonian_js
    assert "shaonianMeet" in app
    assert "beachPeek" in app
    assert "renderBeachHub" in app
    assert "meetShaonian" in app
    assert "speakShaonian" in app
    assert (ROOT / "server/static/island/assets/sprites/shaonian.png").exists()
    try:
        from PIL import Image
        sprite = Image.open(ROOT / "server/static/island/assets/sprites/shaonian.png")
        assert sprite.size == (941, 1672)
        assert sprite.mode == "RGBA"
        assert sprite.getpixel((0, 0))[3] == 0
    except ImportError:
        pass
    tap_sn = app.split("function tapShaonian")[1].split("async function runShaonian")[0]
    assert "speakShaonian" in tap_sn
    assert "showHintSheet" not in tap_sn
    assert "showActSheet" not in tap_sn
    paint_beach = app.split("function paintBeach")[1].split("function shoreShop")[0]
    assert "renderBeachHub" in paint_beach
    assert paint_beach.index("if (state.shoreShelf)") < paint_beach.index("if (state.shaonianMeet)")
    assert paint_beach.index("if (state.shaonianMeet)") < paint_beach.index("renderBeachHub")
    assert "beachPeek = true" in paint_beach
    port_enter = app.split('name === "port"')[1].split('name === "beach"')[0]
    assert "state.portPeek = true" in port_enter
    assert "state.portPeek = false" not in port_enter
    beach_enter = app.split('name === "beach"')[1].split('name === "plaza"')[0]
    assert "state.beachPeek = true" in beach_enter
    assert "state.beachPeek = false" not in beach_enter
    assert 'shaonian.js?v=island-shorescenes1' in app
    assert "startIslandBgm" in app
    assert "paintBgmChip" in app
    assert "bindBgmChip" in app
    paint_fn = app.split("function paintBgmChip")[1].split("function bindBgmChip")[0]
    assert "textContent" not in paint_fn
    assert "静音" not in paint_fn
    assert "出声" not in paint_fn
    assert "data-play" in paint_fn
    assert "data-pause" in paint_fn
    bgm_js = (ROOT / "server/static/island/ui/bgm.js").read_text(encoding="utf-8")
    assert 'playBgm("island")' in bgm_js
    assert "audio/island" in bgm_js
    assert "audio/clinic" not in bgm_js
    assert (ROOT / "server/static/island/assets/audio/island.mp3").exists()
    assert (ROOT / "server/static/island/assets/audio/island.ogg").exists()
    assert (ROOT / "server/static/island/assets/audio/island.mp3").stat().st_size > 1_000_000
    assert "island-burgertown1" in bgm_js
    assert "Magical Burger Town" in art_md
    assert not (ROOT / "server/static/island/assets/audio/clinic.mp3").exists()
    enter_fn = app.split("async function enterScene")[1].split("try {")[0]
    assert "stopBgm" not in enter_fn
    meet_fn = app.split("function meetClinic")[1].split("function speakClinic")[0]
    assert "playBgm" not in meet_fn
    assert "startIslandBgm" not in meet_fn
    clinic_fn = app.split("function tapClinic")[1].split("async function runClinic")[0]
    assert "speakClinic" in clinic_fn
    assert "showHintSheet" not in clinic_fn
    assert "showActSheet" not in clinic_fn
    assert "showEvent" not in app.split("async function openClinic")[1].split("function paintClinic")[0]
    assert "keepWorkshop" in app
    workshop_js = (ROOT / "server/static/island/scenes/workshop.js").read_text(encoding="utf-8")
    assert "island-workshop" in workshop_js
    assert "setShopPeek" in workshop_js
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
    assert "hallMeet" in app
    assert "clinicMeet" in app
    assert "lighthouseMeet" in app
    assert "meetHall" in app
    assert "meetClinic" in app
    assert "meetLighthouse" in app
    assert "keepEatery" in app
    assert "quarryShelf" in app
    assert "barShelf" in app
    assert "writersShelf" in app
    assert "atelierShelf" in app
    assert "eateryShelf" in app
    assert "renderWorkshop" in app
    assert "renderBar" in app
    assert "renderTheater" in app
    assert "renderWriters" in app
    assert "renderAtelier" in app
    assert "renderHall" in app
    assert "renderEatery" in app
    assert "renderMarket" in app
    bar_js = (ROOT / "server/static/island/scenes/bar.js").read_text(encoding="utf-8")
    assert "island-bar" in bar_js
    assert "ensureShopFrame" in bar_js
    assert "island-bar-tray" not in bar_js
    assert "island-bar-opt" not in bar_js
    assert "setShopPeek" in bar_js
    assert "点一下看吧台" in bar_js
    assert "洗碗" in bar_js
    assert "data-act" in bar_js
    assert "去上手页" not in bar_js
    assert "disabled" not in bar_js
    assert "bar-opt-frame.png" not in css
    assert ".island-bar-tray" not in css
    assert ".island-bar-opt" not in css
    assert not (ROOT / "server/static/island/assets/bar-opt-frame.png").exists()
    assert "scene-tap-frame.png" not in css
    assert not (ROOT / "server/static/island/assets/scene-tap-frame.png").exists()
    assert "showCheerSheet" in app
    assert "showPitchSheet" in app
    assert (ROOT / "server/v1/bar_service.py").exists()
    assert (ROOT / "server/v1/writers_service.py").exists()
    assert (ROOT / "server/v1/atelier_service.py").exists()
    assert (ROOT / "server/v1/hall_service.py").exists()
    assert (ROOT / "server/v1/eatery_service.py").exists()
    assert (ROOT / "server/v1/market_service.py").exists()
    assert (ROOT / "server/v1/ting_service.py").exists()
    theater_js = (ROOT / "server/static/island/scenes/theater.js").read_text(encoding="utf-8")
    writers_js = (ROOT / "server/static/island/scenes/writers.js").read_text(encoding="utf-8")
    atelier_js = (ROOT / "server/static/island/scenes/atelier.js").read_text(encoding="utf-8")
    hall_js = (ROOT / "server/static/island/scenes/hall.js").read_text(encoding="utf-8")
    eatery_js = (ROOT / "server/static/island/scenes/eatery.js").read_text(encoding="utf-8")
    market_js = (ROOT / "server/static/island/scenes/market.js").read_text(encoding="utf-8")
    ting_js = (ROOT / "server/static/island/scenes/ting.js").read_text(encoding="utf-8")
    assert 'go: "writers"' in theater_js
    assert 'go: "atelier"' in theater_js
    assert 'go: "hall"' in theater_js
    assert "island-hot" in theater_js
    assert "island-scene-tap" not in theater_js
    assert "island-theater-picks" not in theater_js
    assert "点一下看编剧社" not in theater_js
    assert "编剧社" in theater_js
    assert "衣泊坊" in theater_js
    assert "剧场" in theater_js
    assert "点一下看收稿台" in writers_js
    assert "点一下看坊" in atelier_js
    assert "island-vn" in hall_js
    assert "island-vn-stand" in hall_js
    assert "is-half" in hall_js
    assert "sprites/xiaoju.png" in hall_js
    assert "island-vn-talk" in hall_js
    assert "is-line" in hall_js
    assert "is-picks" in hall_js
    assert "island-vn-advance" in hall_js
    assert "island-vn-choice" in hall_js
    assert "点一下见小橘" in hall_js
    assert "is-peek" in hall_js
    assert "island-scene-tap" in hall_js
    assert "ensureShopFrame" not in hall_js
    assert "点一下看看板" not in hall_js
    assert "island-shop-shelf" not in hall_js
    hall_fn = app.split("function tapHall")[1].split("async function runHall")[0]
    assert "speakHall" in app
    assert "showFormSheet" in hall_fn
    assert "cheer" in hall_fn
    assert "showHintSheet" not in hall_fn
    assert "showActSheet" not in hall_fn
    assert "打赏小橘仍" not in hall_fn
    assert "stars" in hall_js
    assert "应援" in hall_fn
    assert "打赏" in hall_fn
    assert "点歌" in hall_fn
    assert "showEvent" not in app.split("async function openHall")[1].split("function paintHall")[0]
    assert "点一下看菜单" in eatery_js
    assert "点一下看摊" in market_js
    assert "island-market" in market_js
    assert "ensureShopFrame" in market_js
    assert "去上手页" not in market_js
    assert "/api/v1/market" in api
    assert "api.marketAct" in app
    assert "keepMarket" in app
    assert "点一下看木牌" in ting_js
    assert "island-ting" in ting_js
    assert "ensureShopFrame" in ting_js
    assert "去上手页" not in ting_js
    assert "renderTing" in app
    assert "keepTing" in app
    assert "/api/v1/ting" in api
    assert "api.tingAct" in app
    hui_js = (ROOT / "server/static/island/scenes/hui.js").read_text(encoding="utf-8")
    lianli_js = (ROOT / "server/static/island/scenes/lianli.js").read_text(encoding="utf-8")
    assert "点一下看会厅" in hui_js
    assert "island-hui" in hui_js
    assert "ensureShopFrame" in hui_js
    assert "去上手页" not in hui_js
    assert "renderHui" in app
    assert "keepHui" in app
    assert "/api/v1/hui" in api
    assert "api.huiAct" in app
    assert (ROOT / "server/v1/hui_service.py").exists()
    hut_js = (ROOT / "server/static/island/scenes/hut.js").read_text(encoding="utf-8")
    assert "点一下看屋里" in hut_js
    assert "mix_pick" in hut_js
    assert "island-hut" in hut_js
    assert "ensureShopFrame" in hut_js
    assert "去上手页" not in hut_js
    assert "renderHut" in app
    assert "keepHut" in app
    assert "/api/v1/hut" in api
    assert "api.hutAct" in app
    assert (ROOT / "server/v1/hut_service.py").exists()
    assert "点一下看登记处" in lianli_js
    assert "island-lianli" in lianli_js
    assert "ensureShopFrame" in lianli_js
    assert "去上手页" not in lianli_js
    assert "renderLianli" in app
    assert "keepLianli" in app
    assert "/api/v1/lianli" in api
    assert "api.lianliAct" in app
    assert (ROOT / "server/v1/lianli_service.py").exists()
    shore_js = (ROOT / "server/static/island/scenes/shore.js").read_text(encoding="utf-8")
    assert "点一下看码头" in shore_js
    assert "点一下看沙滩" in shore_js
    assert "renderShoreYard" in shore_js
    assert 'go: "port"' in shore_js
    assert 'go: "beach"' in shore_js
    assert "island-shore-yard" in shore_js
    assert "island-hot" in shore_js
    assert "island-shore" in shore_js
    assert "ensureShopFrame" in shore_js
    assert "去上手页" not in shore_js
    assert "renderPortHub" in shore_js
    assert "renderBeachHub" in shore_js
    assert "island-port-hub-list" in shore_js
    assert "island-beach-hub-list" in shore_js
    assert 'sceneId: "port"' in shore_js
    assert 'sceneId: "beach"' in shore_js
    assert "boardW: 941" in shore_js
    assert "boardH: 1672" in shore_js
    assert "boardW: 1086" in shore_js
    assert "boardH: 1448" in shore_js
    assert "island-shop-sku" in shore_js
    assert "data-pick=" in shore_js
    assert 'querySelectorAll("[data-pick]")' in shore_js
    sku_line = [ln for ln in shore_js.splitlines() if "island-shop-sku" in ln][0]
    assert "data-go" not in sku_line
    pick_fn = shore_js.split('querySelectorAll("[data-pick]")')[1].split("export function")[0]
    assert "stopPropagation" in pick_fn
    assert "闲聊" in shore_js
    assert "看码头" in shore_js
    assert "去见韶年" in shore_js
    assert "去赶海" in shore_js
    assert "island-vn-choice" not in shore_js
    assert "paintChat" not in shore_js
    assert "island-port-say" not in shore_js
    assert "renderShore" in app
    assert "renderShoreYard" in app
    assert "renderPortHub" in app
    assert "keepShore" in app
    assert "keepPort" in app
    assert "showIslandLounge" in app
    assert "hideIslandLounge" in app
    assert "playLounge" in app
    assert "portChatOpen" in app
    assert "portPeek" in app
    assert 'shore.js?v=island-shorepick1' in app
    paint_port = app.split("function paintPort")[1].split("async function openBeach")[0]
    assert paint_port.index("state.portChatOpen") < paint_port.index("state.portShelf")
    assert paint_port.index("state.portShelf") < paint_port.index("renderPortHub")
    assert "openPortChat" in app
    assert "closePortChat" in app
    assert "function isIslandScene" in app
    scene_click = app.split('getElementById("island-scene")')[1].split("const ribbon")[0]
    assert "isIslandScene" in scene_click
    assert "api.say" not in app
    assert "renderChat" not in app
    store_src = (ROOT / "server/static/island/store.js").read_text(encoding="utf-8")
    assert "portPeek: false" in store_src
    assert "portChatOpen: false" in store_src
    assert "state.portPeek = false" in app
    assert "state.portChatOpen = false" in app
    assert "/api/v1/shore" in api
    assert "api.shoreAct" in app
    assert "field.type === \"textarea\"" in modal_src or 'field.type === "textarea"' in modal_src
    assert "island-eatery" in eatery_js
    assert "ensureShopFrame" in eatery_js
    assert "island-bar-tray" not in eatery_js
    assert "去上手页" not in eatery_js
    assert "disabled" not in eatery_js
    assert "island-bar-tray" not in writers_js
    assert "island-bar-tray" not in atelier_js
    assert "island-bar-tray" not in hall_js
    assert "去上手页" not in writers_js
    assert "去上手页" not in atelier_js
    assert "去上手页" not in hall_js
    assert "/api/v1/writers" in api
    assert "/api/v1/atelier" in api
    assert "/api/v1/hall" in api
    assert "/api/v1/eatery" in api
    assert "/api/v1/lighthouse" in api
    assert "api.lighthouseAct" in app
    assert "keepLighthouse" in app
    assert 'import { renderLighthouse }' not in app
    assert 'import("./scenes/lighthouse.js' in app
    assert (ROOT / "server/v1/lighthouse_service.py").exists()
    lighthouse_js = (ROOT / "server/static/island/scenes/lighthouse.js").read_text(encoding="utf-8")
    assert "island-vn" in lighthouse_js
    assert "island-vn-stand" in lighthouse_js
    assert "sprites/buxing.png" in lighthouse_js
    assert "island-vn-talk" in lighthouse_js
    assert "is-line" in lighthouse_js
    assert "is-picks" in lighthouse_js
    assert "island-vn-advance" in lighthouse_js
    assert "island-vn-choice" in lighthouse_js
    assert "点一下见不醒" in lighthouse_js
    assert "is-peek" in lighthouse_js
    assert "island-scene-tap" in lighthouse_js
    assert "row.price || row.note" not in lighthouse_js
    assert "去上手页" not in lighthouse_js
    assert "island-shop-shelf" not in lighthouse_js
    assert (ROOT / "server/static/island/assets/sprites/buxing.png").exists()
    assert (ROOT / "server/static/island/assets/sprites/xiaoju.png").exists()
    assert (ROOT / "server/static/island/assets/sprites/qiaoqiao.png").exists()
    assert "sprites/buxing.png" in art_md
    assert "sprites/xiaoju.png" in art_md
    assert "sprites/qiaoqiao.png" in art_md
    assert "sprites/shaonian.png" in art_md
    assert "sprites/lili.png" in art_md
    assert "点一下才出人栗栗" in art_md
    assert "立绘对话" in art_md
    assert "点一下才出人不醒" in art_md
    assert "点一下才出人小橘" in art_md
    assert "点一下才出人桥桥" in art_md
    assert "点一下才出人栗栗" in art_md
    assert "去见韶年才出人韶年" in art_md
    assert "scenes/beach.png" in art_md
    assert "scenes/port.png" in art_md
    assert "点海边就出列表" in art_md
    assert "点港口就出列表" in art_md
    assert "先进沙滩景，点一下看沙滩" not in art_md
    assert "全身的二分之一" in art_md
    assert ".island-vn-talk" in css
    assert ".island-vn-box" in css
    assert ".island-vn.is-peek" in css
    peek_stand = css.split(".island-vn.is-peek .island-vn-stand")[1].split(".island-vn.is-peek .island-vn-talk")[0]
    assert "visibility: hidden" in peek_stand
    assert "display: none" not in peek_stand
    assert ".island-app.is-entering .island-vn-sprite" not in css
    assert "点一下才出人" in css
    assert "点一下对话框才变成选项" in css
    assert "不吃底图 line-height:0" in css
    assert "人靠左下移" in css
    assert ".island-vn-line" in css
    assert "overflow-y: auto" not in css.split(".island-vn-line")[1].split(".island-vn-more")[0]
    assert ".island-vn-talk.is-picks" in css
    assert ".island-vn-talk.is-line" in css
    assert ".island-vn-stand" in css
    assert ".island-vn-sprite" in css
    assert "下沿渐变淡出" in css
    assert "mask-image: linear-gradient" in css
    assert "-webkit-mask-image: linear-gradient" in css
    assert "只要头和胸" in css
    assert "矮一半" in css
    assert ".island-vn-stand.is-half" in css
    assert ".island-shaonian .island-vn-stand.is-half .island-vn-sprite" in css
    assert ".island-lili .island-vn-stand.is-half .island-vn-sprite" in css
    assert "left: -12%" in css
    assert ".island-lili .island-vn-stand.is-half {" in css
    lili_stand = css.split(".island-lili .island-vn-stand.is-half {")[1].split("}")[0]
    assert "width: 100%" in lili_stand
    lili_sprite = css.split(".island-lili .island-vn-stand.is-half .island-vn-sprite")[1].split("}")[0]
    assert "left: 12%" not in lili_sprite
    assert "left: 0" in lili_sprite
    assert "width: 100%" in lili_sprite
    assert "height: auto" in lili_sprite
    assert ".island-hall .island-vn-stand.is-half {" in css
    hall_stand = css.split(".island-hall .island-vn-stand.is-half {")[1].split("}")[0]
    assert "width: 100%" in hall_stand
    hall_sprite = css.split(".island-hall .island-vn-stand.is-half .island-vn-sprite")[1].split("}")[0]
    assert "left: 0" in hall_sprite
    assert "width: 100%" in hall_sprite
    assert "height: auto" in hall_sprite
    assert ".island-bgm-chip" in css
    assert "island-vn-mute" not in css
    assert "全身的二分之一" in css
    assert ".island-theater-board" in css
    assert ".island-theater-picks" not in css
    assert ".island-theater .island-hot span" in css
    assert ".island-shore-board" in css
    assert ".island-shop-tabs:empty" in css
    assert ".island-shore-yard .island-hot span" in css
    assert ".island-port-say" in css
    assert ".island-port-msg" in css
    assert 'lighthouse: "灯塔"' in app
    assert 'lili: "栗栗流动摊"' in app
    assert 'clinic: "乔乔诊所"' in app
    assert 'notice: "潮汐公告"' in app
    assert "state.backTo" in app
    assert (ROOT / "server/static/island/assets/scenes/shore.png").exists()
    assert (ROOT / "server/static/island/assets/scenes/beach.png").exists()
    assert (ROOT / "server/static/island/assets/scenes/port.png").exists()
    assert (ROOT / "server/static/island/assets/scenes/bar.png").exists()
    assert (ROOT / "server/static/island/assets/scenes/plaza.png").exists()
    assert (ROOT / "server/static/island/assets/scenes/lili.png").exists()
    assert (ROOT / "server/static/island/assets/scenes/clinic.png").exists()
    assert (ROOT / "server/static/island/assets/scenes/theater.png").exists()
    assert (ROOT / "server/static/island/assets/scenes/writers.png").exists()
    assert (ROOT / "server/static/island/assets/scenes/atelier.png").exists()
    assert (ROOT / "server/static/island/assets/scenes/hall.png").exists()
    art_js = (ROOT / "server/static/island/ui/art.js").read_text(encoding="utf-8")
    assert 'writers: { label: "编剧社", size: "941×1672" }' in art_js
    assert 'atelier: { label: "衣泊坊", size: "941×1672" }' in art_js
    assert 'hall: { label: "剧场看台", size: "941×1672" }' in art_js
    assert 'file: "theater"' not in art_js
    assert 'lili: { label: "栗栗流动摊", size: "1086×1448" }' in art_js
    assert 'clinic: { label: "乔乔诊所", size: "941×1672" }' in art_js
    assert 'port: { label: "码头", size: "941×1672" }' in art_js
    assert 'beach: { label: "沙滩", size: "1086×1448" }' in art_js
    assert 'file: "shore"' not in art_js
    assert 'file: "plaza"' not in art_js
    art_md = (ROOT / "server/static/island/assets/ART.md").read_text(encoding="utf-8")
    assert "暂用院景" not in art_md
    try:
        from PIL import Image
        for place in ("writers", "atelier", "hall"):
            pic = ROOT / f"server/static/island/assets/scenes/{place}.png"
            assert Image.open(pic).size == (941, 1672), place
        lili_pic = ROOT / "server/static/island/assets/scenes/lili.png"
        assert Image.open(lili_pic).size == (1086, 1448)
        beach_pic = ROOT / "server/static/island/assets/scenes/beach.png"
        port_pic = ROOT / "server/static/island/assets/scenes/port.png"
        assert Image.open(beach_pic).size == (1086, 1448)
        assert Image.open(port_pic).size == (941, 1672)
    except ImportError:
        pass
    assert "海边" in (ROOT / "server/static/island/map.js").read_text(encoding="utf-8")
    assert "港口" in (ROOT / "server/static/island/scenes/shore.js").read_text(encoding="utf-8")
    assert "剧场" in (ROOT / "server/static/island/map.js").read_text(encoding="utf-8")
    assert "is-theater" in css
    assert "island-plaza-board" in css
    assert ".island-lili .island-shop-board" in css
    assert ".island-beach-hub .island-shop-board" in css
    assert ".island-port-hub .island-shop-board" in css
    assert "1086 / 1448" in css
    assert "941 / 1672" in css
    assert ".island-shop:not(.is-peek) .island-scene-tap" in css
    assert "店景不换裁切" in css
    assert "island-shop-meta" in css
    assert "island-scene-tap" in css
    assert ".island-shop.is-peek" in css
    assert "island-item-acts" in css
    assert "island-bag-grid" in css
    assert "url(\"/static/island/assets/bag-frame.png\")" not in css
    assert "bag-frame.png" in bag_js
    assert ".island-sheet.is-bag" in css
    assert "object-fit: fill" in css
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
