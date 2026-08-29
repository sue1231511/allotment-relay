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
    assert body["farm"]["home"][0]["appearance"] == "empty"

    me = client.get("/api/v1/me", headers=_auth(key))
    assert me.status_code == 200, me.text
    tickets0 = me.json()["me"]["tickets"]

    missing_item = client.post(
        "/api/v1/farm/parcels/1/sow",
        headers=_auth(key, {"Idempotency-Key": "sow-empty"}),
        json={"crop": "榴莲"},
    )
    assert missing_item.status_code == 409, missing_item.text
    assert missing_item.json()["error"]["code"] == "ITEM_REQUIRED"

    farm0 = client.get("/api/v1/farm", headers=_auth(key))
    assert farm0.status_code == 200, farm0.text
    panel = farm0.json()["farm"]["panel"]
    assert [c["label"] for c in panel] == ["白菜", "胡萝卜", "番茄"], panel
    assert {c["name"] for c in panel} == {"甘蓝", "甜菜", "雾豌豆"}, panel
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
    page = client.get("/island")
    assert page.status_code == 200, page.text
    assert "手机地图" in page.text or "island-root" in page.text


def test_island_page_is_modular() -> None:
    html = (ROOT / "server/templates/island.html").read_text(encoding="utf-8")
    css = (ROOT / "server/static/island/island.css").read_text(encoding="utf-8")
    app = (ROOT / "server/static/island/app.js").read_text(encoding="utf-8")
    api = (ROOT / "server/static/island/api.js").read_text(encoding="utf-8")
    assert "/static/island/app.js" in html
    assert "island-dock" in html
    assert "菜园" in (ROOT / "server/static/island/map.js").read_text(encoding="utf-8")
    assert "min-height: 48px" in css
    assert "overflow-x: hidden" in css
    assert "home-garden.png" in css
    assert "top: auto" in css
    assert "/static/style.css" not in html
    assert "/api/v1/" in api
    assert "Authorization" in api
    assert "api_key=" not in api
    assert "浇水 1" not in app
    assert "菜园已经种满了" in app
    assert "firstIdleHome" in app
    assert (ROOT / "server/static/island/scenes/home.js").exists()
    assert (ROOT / "server/static/island/ui/plant-panel.js").exists()
    assert (ROOT / "server/static/island/ui/crops.js").exists()
    assert "data-act=\"prev\"" in (ROOT / "server/static/island/ui/plant-panel.js").read_text(encoding="utf-8")
    assert "island-beds" in (ROOT / "server/static/island/scenes/home.js").read_text(encoding="utf-8")
    assert (ROOT / "server/static/island/scenes/shore.js").exists()
    assert (ROOT / "server/static/island/scenes/plaza.js").exists()
    assert (ROOT / "server/static/island/assets/island-map.png").exists()
    assert (ROOT / "server/static/island/assets/home-garden.png").exists()
    main_py = (ROOT / "server/main.py").read_text(encoding="utf-8")
    assert '@app.get("/play"' in main_py
    assert '@app.get("/island"' in main_py
    assert "island_v1_router" in main_py


if __name__ == "__main__":
    test_island_v1_api()
    print("ok")
