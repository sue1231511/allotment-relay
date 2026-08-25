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
    test_bar_work_auto_period()
    asyncio.run(_test_play_bar_work_follows_phase())


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
    assert any(a["command"] == "work 洗碗" for a in bar["actions"]), bar
    assert not any("night" in a["command"] for a in bar["actions"] if a["label"] == "洗碗上工"), bar
    climate = sown["climate"]
    assert climate["phase_code"] in ("day", "dusk", "night"), climate
    assert climate["tide_code"] in ("ebb", "slack", "flood"), climate
    assert climate["weather_code"], climate
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
    from server import play as play_mod, world

    shift, note = play_mod.bar_work_slot()
    phase = world.current_day_phase()
    if phase == "night":
        assert shift == "night"
        assert note == "夜班"
    elif phase == "dusk":
        assert shift == "day"
        assert note == "白班"
    else:
        assert shift == "day"
        assert "暮" in note

    actions = play_mod.bar_place_actions()
    dish = next(a for a in actions if a["label"] == "洗碗上工")
    assert dish["command"] == "work 洗碗", dish
    assert note in dish["note"], dish


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
    assert "actData" in js
    assert "attrEsc" in js
    assert "function attr(" in js
    assert "decorateActions" in js
    assert "parseAct" in js
    assert "parseActPayload" in js
    assert "setWorkStatus" in js
    assert "bar_place_actions" in (ROOT / "server" / "play.py").read_text()
    assert "data-act='${JSON.stringify" not in js
    assert 'data-act="${JSON.stringify' not in js
    assert 'data-label="${esc(' not in js
    assert 'data-note="${esc(' not in js
    assert 'data-place="${esc(' not in js
    assert 'data-neighbor="${esc(' not in js
    assert 'data-item="${esc(' not in js
    assert 'data-sow="${esc(' not in js
    assert "attr('data-label'" in js
    assert "attr('data-note'" in js
    assert "attr('data-place'" in js
    assert "attr('data-neighbor'" in js
    assert "play.js?v=act4" in html
    test_act_payload_survives_html_attribute()


def _first_double_quoted_attr(html: str, name: str) -> str | None:
    """浏览器解析 data-act=\"...\" 时，遇到未转义的 \" 会截断。"""
    needle = f'{name}="'
    start = html.find(needle)
    if start < 0:
        return None
    start += len(needle)
    end = html.find('"', start)
    if end < 0:
        return html[start:]
    return html[start:end]


def test_act_payload_survives_html_attribute() -> None:
    import html as html_mod
    import json
    from html.parser import HTMLParser

    class AttrCatcher(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.value = None

        def handle_starttag(self, tag, attrs):
            if tag == "button":
                self.value = dict(attrs).get("data-act")

    payload = {"tool": "bar_ops", "command": "work 洗碗"}
    raw = json.dumps(payload, ensure_ascii=False)

    broken = f'<button type="button" data-act="{raw}">洗碗上工</button>'
    truncated = _first_double_quoted_attr(broken, "data-act")
    assert truncated == "{", truncated

    escaped = (
        raw.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
    )
    ok_html = f'<button type="button" data-act="{escaped}">洗碗上工</button>'
    parser = AttrCatcher()
    parser.feed(ok_html)
    assert parser.value == raw, parser.value
    assert json.loads(parser.value) == payload
    assert json.loads(html_mod.unescape(escaped)) == payload

    from server import play as play_mod

    for place in play_mod.PLACES:
        for act in place["actions"]:
            blob = json.dumps({"tool": act["tool"], "command": act["command"]}, ensure_ascii=False)
            esc = blob.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")
            markup = f'<button data-act="{esc}"></button>'
            catcher = AttrCatcher()
            catcher.feed(markup)
            assert json.loads(catcher.value) == {"tool": act["tool"], "command": act["command"]}, act
            assert not str(act["command"]).endswith((" day", " night")), act


def test_bar_work_auto_period() -> None:
    from unittest.mock import patch
    from server.bar import _auto_work_period, _work_period

    with patch("server.world.current_day_phase", return_value="night"):
        assert _auto_work_period() == "night"
        assert _work_period("night") == "night"
    with patch("server.world.current_day_phase", return_value="dusk"):
        assert _auto_work_period() == "day"
        assert _work_period("day") == "day"
        try:
            _work_period("night")
            raise AssertionError("dusk should reject hardcoded night")
        except ValueError as exc:
            assert "夜班" in str(exc), exc
    with patch("server.world.current_day_phase", return_value="day"):
        try:
            _auto_work_period(overdue=False)
            raise AssertionError("day should refuse unless overdue")
        except ValueError as exc:
            assert "营业" in str(exc) or "暮" in str(exc), exc
        assert _auto_work_period(overdue=True) == "day"


async def _test_play_bar_work_follows_phase() -> None:
    from unittest.mock import patch

    tmp = Path(tempfile.mkdtemp(prefix="play-bar-"))
    db = await _boot(tmp)
    from server import play as play_mod

    key = await db.create_api_key("play-bar@example.com")
    await play_mod.run_play(key, "steward_ops", "enroll 洗碗的人")

    with patch("server.world.current_day_phase", return_value="dusk"):
        hit = await play_mod.run_play(key, "bar_ops", "work 洗碗")
        text = hit.get("text") or ""
        assert hit["ok"] is True, hit
        assert "洗碗" in text or "上工" in text or "班" in text or "票" in text, text
        try:
            await play_mod.run_play(key, "bar_ops", "work 洗碗 night")
            raise AssertionError("dusk should reject night shift")
        except ValueError as exc:
            assert "夜班" in str(exc), exc

    with patch("server.world.current_day_phase", return_value="day"):
        try:
            await play_mod.run_play(key, "bar_ops", "work 洗碗")
            raise AssertionError("day should refuse work unless overdue")
        except ValueError as exc:
            assert "营业" in str(exc) or "暮" in str(exc), exc


if __name__ == "__main__":
    asyncio.run(_test_play_api())
    test_bar_place_actions_match_phase()
    test_play_page_lists_all_plot_kinds()
    test_bar_work_auto_period()
    test_act_payload_survives_html_attribute()
    asyncio.run(_test_play_bar_work_follows_phase())
    print("ok")
