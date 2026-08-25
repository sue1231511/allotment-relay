#!/usr/bin/env python3
"""人类上手页 /api/play — 同一张凭证、同一套 command。"""
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


def test_play_api() -> None:
    asyncio.run(_test_play_api())
    test_bar_place_actions_match_phase()
    test_play_page_lists_all_plot_kinds()


async def _test_play_api() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="play-"))
    db = await _boot(tmp)
    from server import play as play_mod

    key = await db.create_api_key("play@example.com")
    try:
        await play_mod.run_play("bad_key", "", "")
        raise AssertionError("bad key should fail")
    except ValueError as exc:
        assert "无效" in str(exc), exc

    snap = await play_mod.run_play(key, "", "")
    assert snap["ok"] is True, snap
    assert snap["enrolled"] is False, snap
    assert snap["places"] and snap["places"][0]["name"] == "海边", snap["places"]

    enrolled = await play_mod.run_play(key, "steward_ops", "enroll 岸边的人")
    assert enrolled["enrolled"] is True, enrolled
    assert enrolled["dashboard"]["name"] == "岸边的人", enrolled
    assert "欢迎" in (enrolled.get("text") or ""), enrolled
    assert enrolled["neighbors"]["total"] == 1, enrolled["neighbors"]
    assert enrolled["neighbors"]["people"] == [], enrolled["neighbors"]
    start_plots = enrolled["dashboard"]["parcels"]
    start_veg = [p for p in start_plots if not p.get("orchard") and not p.get("greenhouse")]
    start_orch = [p for p in start_plots if p.get("orchard") and not p.get("greenhouse")]
    assert len(start_veg) == 3, start_plots
    assert len(start_orch) == 3, start_plots
    assert {p["token"] for p in start_orch} == {"园1", "园2", "园3"}, start_orch
    land = enrolled["dashboard"].get("land") or {}
    assert land.get("plots", {}).get("count") == 3, land
    assert land.get("orchard", {}).get("count") == 3, land
    assert "island_bond" in enrolled["dashboard"], enrolled["dashboard"]
    assert enrolled["dashboard"]["dues"]["upkeep_arrears"] == 0, enrolled["dashboard"]

    other = await db.create_api_key("play-b@example.com")
    await play_mod.run_play(other, "steward_ops", "enroll 对岸的人")
    seen = await play_mod.run_play(key, "", "")
    assert seen["neighbors"]["total"] == 2, seen["neighbors"]
    names = [p["name"] for p in seen["neighbors"]["people"]]
    assert "对岸的人" in names, seen["neighbors"]

    sown = await play_mod.run_play(key, "plot_ops", "sow 1 甘蓝")
    assert sown["ok"] is True, sown
    plots = sown["dashboard"]["parcels"]
    one = next(p for p in plots if p.get("token") == "1" and not p.get("orchard") and not p.get("greenhouse"))
    assert one["state"] != "fallow", one

    ids = {p["id"] for p in sown["places"]}
    assert {"bar", "eatery", "star", "clinic", "hut", "hui"} <= ids, ids
    week1 = [p["id"] for p in sown["places"] if p.get("week1")]
    assert week1 == ["tide", "hut", "bar", "eatery", "lounge", "hui"], week1
    clinic = next(p for p in sown["places"] if p["id"] == "clinic")
    assert clinic["week1"] is False, clinic
    assert any(a["command"] == "clinic treat all" for a in clinic["actions"]), clinic
    bar = next(p for p in sown["places"] if p["id"] == "bar")
    assert "点单" in bar["blurb"], bar
    work = next(a for a in bar["actions"] if str(a.get("command") or "").startswith("work "))
    from server import world
    phase = world.current_day_phase()
    assert work["command"] == "work 洗碗", work
    if phase == "night":
        assert "夜" in (work.get("note") or ""), work
        assert not work.get("disabled"), work
    elif phase == "dusk":
        assert "暮" in (work.get("note") or "") or "白班" in (work.get("note") or ""), work
        assert not work.get("disabled"), work
    else:
        assert work.get("disabled") is True, work
        assert "开门" in (work.get("note") or ""), work
    assert sown["climate"].get("phase_code") in ("day", "dusk", "night"), sown["climate"]
    assert sown["climate"].get("tide_code") in ("ebb", "slack", "flood"), sown["climate"]
    tide_place = next(p for p in sown["places"] if p["id"] == "tide")
    dig = next(a for a in tide_place["actions"] if a.get("command") == "dig")
    if sown["climate"]["tide_code"] == "flood":
        assert dig.get("disabled") is True, dig
    else:
        assert not dig.get("disabled"), dig
    well = next(p for p in sown["places"] if p["id"] == "undertide")
    assert "岛缘" in well["blurb"], well
    assert sown["dashboard"]["island_bond"] is not None, sown["dashboard"]
    assert "bond_flavor" in sown["dashboard"], sown["dashboard"]

    bought = await play_mod.run_play(key, "plot_ops", "buy 1 甘蓝")
    assert bought["ok"] is True, bought
    assert "甘蓝" in (bought.get("text") or ""), bought.get("text")

    clinic_hit = await play_mod.run_play(key, "visit_ops", "clinic status")
    assert clinic_hit["ok"] is True, clinic_hit
    clinic_text = clinic_hit.get("text") or ""
    assert "桥桥" in clinic_text or "诊所" in clinic_text, clinic_text

    try:
        await play_mod.run_play(key, "not_a_tool", "status")
        raise AssertionError("unknown tool should fail")
    except ValueError as exc:
        assert "未知工具" in str(exc), exc


def test_bar_place_actions_match_phase() -> None:
    from server import bar, play as play_mod, world

    phase = world.current_day_phase()
    btn = bar.work_button_for(None)
    assert btn["command"] == "work 洗碗", btn
    if phase == "night":
        assert not btn.get("disabled"), btn
        assert "夜" in (btn.get("note") or ""), btn
    elif phase == "dusk":
        assert not btn.get("disabled"), btn
        assert "白班" in (btn.get("note") or "") or "暮" in (btn.get("note") or ""), btn
    else:
        assert btn.get("disabled") is True, btn

    places = play_mod.places_for(None)
    bar_place = next(p for p in places if p["id"] == "bar")
    dish = next(a for a in bar_place["actions"] if str(a.get("command") or "").startswith("work "))
    assert dish["command"] == "work 洗碗", dish
    assert dish.get("note") == btn.get("note"), (dish, btn)


def test_play_page_lists_all_plot_kinds() -> None:
    html = (ROOT / "server" / "templates" / "play.html").read_text()
    js = (ROOT / "server" / "static" / "play.js").read_text()
    assert "最多展示 6 块" not in html
    assert "parcels.slice(0, 6)" not in js
    assert "places.slice(0, 6)" not in js
    assert ".filter((pl) => pl.week1)" in js
    assert "plotGroupHtml(`菜地" in js
    assert "plotGroupHtml(`果园" in js
    assert "还没有温室" in js
    assert 'data-buy-seed' in html
    assert "seedBuyHtml" in js
    assert 'id="play-bond"' in html
    assert "duesUrgent" in js
    assert "去潮生会" in js
    assert "交岸维" in js
    assert "orderedPlaces" in js
    assert "b.week1" in js
    assert "parseActPayload" in js
    assert "setWorkStatus" in js
    assert "places_for" in (ROOT / "server" / "play.py").read_text()
    assert "work_button_for" in (ROOT / "server" / "bar.py").read_text()
    assert "focusPlaceResult" in js
    assert "is-disabled" in js


if __name__ == "__main__":
    asyncio.run(_test_play_api())
    test_bar_place_actions_match_phase()
    test_play_page_lists_all_plot_kinds()
    print("ok")
