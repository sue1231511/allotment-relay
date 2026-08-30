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
    assert sown.json()["event"]["kind"] == "farm"
    assert "sow 1" not in (sown.json()["event"]["narrative"] or "")

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

    mcp_bag = await play_mod.run_play(key, "tote_ops", "list")
    assert "甘蓝" in (mcp_bag.get("text") or ""), mcp_bag.get("text")

    # 前端自动找空地：按 slot 顺序把三块都种上，就没有 can_sow。
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
    fished = client.post(
        "/api/v1/shore/cast",
        headers=_auth(key, {"Idempotency-Key": "net-ok"}),
        json={"mode": "net"},
    )
    assert fished.status_code == 200, fished.text
    assert fished.json()["event"]["kind"] == "shore"
    assert fished.json()["me"]["tickets"] <= tickets0 + 40

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
    assert "sW = cw / iw" in map_js
    assert "Math.max(sW, sH" in map_js
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
    assert "firstIdleYard" in app
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
    assert "island-yard-acts" in yards_js
    assert "data-act=\"water\"" in yards_js
    assert "#island-actionbar [data-act=water]" not in home_js
    assert "#island-actionbar [data-act=garden]" not in home_js
    assert "setYardsChrome" in app
    assert "is-yards" in app
    assert "classList.remove(\"is-yards\")" in app
    assert "name === \"map\" || name === \"yards\"" in app
    assert "is-yards" in boot
    assert "is-yards" in css
    assert ".island-back-map" not in css
    assert ".island-yard-acts" in css
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
    assert "交岸税" not in app
    assert "洗碗" not in app
    assert "只铺图和地名" in (ROOT / "server/static/island/scenes/place.js").read_text(encoding="utf-8")
    assert "data-act=\"net\"" not in (ROOT / "server/static/island/scenes/shore.js").read_text(encoding="utf-8")
    assert "发言" not in (ROOT / "server/static/island/scenes/plaza.js").read_text(encoding="utf-8")
    assert "/api/v1/farm/buy" in api
    assert "/api/v1/hut/sleep" in api
    assert "/api/v1/bar/work" in api
    assert "/api/v1/kitchen/eat" in api
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
    assert "scenes/workshop.png" in (ROOT / "server/static/island/assets/ART.md").read_text(encoding="utf-8")
    assert "scenes/quarry.png" in (ROOT / "server/static/island/assets/ART.md").read_text(encoding="utf-8")
    try:
        from PIL import Image
        for place in ("eatery", "hui", "market", "ting", "lianli", "workshop", "quarry"):
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
    assert "yardPage" in home_js
    assert "island-plot-pager" in home_js
    assert "bindSwipe" in home_js
    assert "左右滑" in home_js
    assert "data-yard" in home_js
    assert "onWaterAll" in home_js
    assert "sceneArt" in home_js
    assert (ROOT / "server/static/island/scenes/shore.js").exists()
    assert (ROOT / "server/static/island/scenes/plaza.js").exists()
    assert "renderPlace" in (ROOT / "server/static/island/scenes/shore.js").read_text(encoding="utf-8")
    assert "renderPlace" in (ROOT / "server/static/island/scenes/plaza.js").read_text(encoding="utf-8")
    assert (ROOT / "server/static/island/assets/scenes/shore.png").exists()
    assert (ROOT / "server/static/island/assets/scenes/bar.png").exists()
    assert (ROOT / "server/static/island/assets/scenes/plaza.png").exists()
    assert (ROOT / "server/static/island/assets/scenes/theater.png").exists()
    assert "港口" in (ROOT / "server/static/island/map.js").read_text(encoding="utf-8")
    assert "剧场" in (ROOT / "server/static/island/map.js").read_text(encoding="utf-8")
    assert "is-theater" in css
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
