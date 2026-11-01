#!/usr/bin/env python3
"""/api/v1/undertide：井口、深坑、酒馆、监牢、K 室，以及后室铺/恩怨墙/赌场/钱庄补上的指令。
每个动作都翻成已有的 undertide_ops 指令，不另算数值。"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _quiet_events(monkeypatch):
    """井下每次操作后有概率掷随机事件（掏包、涨价…）；这里测翻译和流程，不靠运气。"""
    from server import undertide

    async def _none(conn, s, ut):
        return ""

    monkeypatch.setattr(undertide, "_maybe_event", _none)


def _client():
    from fastapi.testclient import TestClient
    from server.main import app

    return TestClient(app)


def _auth(key: str, extra: dict | None = None) -> dict:
    headers = {"Authorization": f"Bearer {key}"}
    if extra:
        headers.update(extra)
    return headers


def test_command_translation() -> None:
    from server.v1 import undertide_service as svc
    from server.v1.errors import ApiError

    cmd = svc._command
    assert cmd("well_look", "") == "well"
    assert cmd("well_descend", "") == "descend"
    assert cmd("well_enter", "") == "enter"
    assert cmd("well_guide", "") == "guide"
    assert cmd("well_clean", "") == "清井"
    assert cmd("well_status", "") == "status"
    assert cmd("pit_list", "") == "pit"
    assert cmd("pit_board", "") == "pit board"
    assert cmd("pit_fight", "老疤") == "fight 老疤"
    assert cmd("pit_fight", "老疤 Guard") == "fight 老疤 guard"
    assert cmd("tavern_visit", "") == "tavern"
    assert cmd("tavern_chat", "") == "tavern chat"
    assert cmd("tavern_ruby", "") == "tavern ruby"
    assert cmd("tavern_ruby", "confirm") == "tavern ruby 确认"
    assert cmd("tavern_bleed", "确认") == "tavern bleed 确认"
    assert cmd("jail_status", "") == "jail status"
    assert cmd("jail_ransom", "") == "jail ransom"
    assert cmd("jail_work", "") == "jail work"
    assert cmd("kroom_status", "") == "kroom status"
    assert cmd("kroom_settle", "") == "kroom settle"
    assert cmd("kroom_vr", "") == "kroom vr"
    assert cmd("street", "") == "street"
    assert cmd("muscle", "阿标") == "muscle 阿标"
    assert cmd("push", "阿标 鲭鱼") == "push 阿标 鲭鱼"
    assert cmd("hijack", "某人") == "hijack 某人"
    assert cmd("grudge", "pay") == "grudge pay"
    assert cmd("lottery", "") == "lottery"
    assert cmd("refine_list", "") == "炼 list"
    assert cmd("refine", "brine_crystal") == "炼 brine_crystal"
    assert cmd("sell", "鲭鱼") == "sell 鲭鱼"
    assert cmd("sell", "鲭鱼 3") == "sell 鲭鱼 3"
    assert cmd("cheer", "辛苦了") == "cheer 辛苦了"
    # 旧的几条照旧
    assert cmd("market_desk", "") == "market"
    assert cmd("medic", "sprain") == "medic sprain"

    bad = [
        ("pit_fight", ""), ("pit_fight", "老疤 smash"), ("pit_fight", "a b c"),
        ("tavern_ruby", "now"), ("muscle", ""), ("muscle", "a\nb"), ("push", "only"),
        ("hijack", "a;b"), ("grudge", "dance"), ("refine", ""), ("sell", "鲭鱼 0"),
        ("sell", "鲭鱼 x"), ("sell", ""), ("cheer", ""), ("nope", ""),
    ]
    for kind, target in bad:
        with pytest.raises(ApiError):
            cmd(kind, target)


def test_desks_over_http() -> None:
    asyncio.run(_desks_over_http())


async def _desks_over_http() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="ut-desks-"))
    os.environ["DATA_DIR"] = str(tmp)
    from server import config, db

    config.DATA_DIR = tmp
    config.DB_PATH = tmp / "relay.db"
    db.DATA_DIR = tmp
    db.DB_PATH = tmp / "relay.db"
    db._DB_MUTEX = asyncio.Lock()
    await db.init_db()
    key = await db.create_api_key("ut-desks@example.com")
    client = _client()
    assert client.post("/api/v1/session", json={"api_key": key, "name": "井下客"}).status_code == 200
    row = await db.get_key_row(key)
    sid = int((await db.get_steward_by_key_id(row["id"]))["id"])

    base = client.get("/api/v1/undertide", headers=_auth(key)).json()["undertide"]
    assert base["access"] is False
    assert "pit_text" not in base and "tavern_text" not in base  # 不带 desk 只取老五处

    bad_desk = client.get("/api/v1/undertide?desk=nowhere", headers=_auth(key))
    assert bad_desk.status_code == 400, bad_desk.text

    well = client.get("/api/v1/undertide?desk=well", headers=_auth(key)).json()["undertide"]
    assert well["well_text"]

    # 没下过井：深坑、酒馆给出「不让进」的话，不是报错
    pit_locked = client.get("/api/v1/undertide?desk=pit", headers=_auth(key)).json()["undertide"]
    assert pit_locked["pit_text"] and pit_locked["pit"] == []
    denied = client.post("/api/v1/undertide/act", headers=_auth(key, {"Idempotency-Key": "ut-d1"}),
                         json={"kind": "tavern_chat"})
    assert denied.status_code >= 400, denied.text

    # 监牢、K 室不用下井也能看
    for i, (kind, desk) in enumerate([("jail_status", "jail"), ("kroom_status", "kroom")]):
        ok = client.post("/api/v1/undertide/act", headers=_auth(key, {"Idempotency-Key": f"ut-s{i}"}),
                         json={"kind": kind})
        assert ok.status_code == 200, ok.text
        assert ok.json()["event"]["narrative"], ok.text
        got = client.get(f"/api/v1/undertide?desk={desk}", headers=_auth(key)).json()["undertide"]
        assert got[f"{desk}_text"]

    async with db.connect() as conn:
        from server import undertide

        await undertide._ensure_ut(conn, sid)
        await conn.execute("UPDATE steward_undertide SET well_hint=1 WHERE steward_id=?", (sid,))
        await conn.execute("UPDATE stewards SET tickets=500, energy=100, health=100 WHERE id=?", (sid,))
        await conn.commit()

    idx = 0

    def act(kind: str, target: str = ""):
        nonlocal idx
        idx += 1
        return client.post("/api/v1/undertide/act", headers=_auth(key, {"Idempotency-Key": f"ut-a{idx}"}),
                           json={"kind": kind, "target": target})

    r = act("well_descend")
    assert r.status_code == 200, r.text
    assert r.json()["undertide"]["access"] is True
    assert r.json()["event"]["title"] == "下井"
    assert act("well_enter").status_code == 200
    assert act("well_status").status_code == 200
    assert act("well_guide").status_code == 200

    pit = client.get("/api/v1/undertide?desk=pit", headers=_auth(key)).json()["undertide"]
    assert pit["pit"], pit
    fighter = pit["pit"][0]
    assert {"name", "level", "entry", "prize", "wins", "losses"} <= set(fighter)
    assert act("pit_board").status_code == 200

    tav = client.get("/api/v1/undertide?desk=tavern", headers=_auth(key)).json()["undertide"]
    assert tav["tavern_text"]
    for kind in ("tavern_chat", "tavern_whisper", "tavern_ai"):
        assert act(kind).status_code in (200, 400, 409), kind
    quote = act("tavern_ruby")
    assert quote.status_code == 200, quote.text
    assert "确认" in quote.json()["event"]["narrative"] or "红宝石" in quote.json()["event"]["narrative"]

    assert act("street").status_code == 200
    assert act("refine_list").status_code == 200
    assert act("jail_status").status_code == 200
    assert act("kroom_status").status_code == 200

    # 写错的入参在适配层就挡下，不进游戏
    assert act("pit_fight", "").status_code == 400
    assert act("pit_fight", "老疤 smash").status_code == 400
    assert act("grudge", "dance").status_code == 400
    assert act("sell", "鲭鱼 0").status_code == 400


def test_island_js_wires_every_new_desk() -> None:
    js = (ROOT / "server/static/island/scenes/undertide.js").read_text(encoding="utf-8")
    for spot in ("undertide-well", "undertide-pit", "undertide-tavern", "undertide-jail", "undertide-kroom"):
        assert f'id: "{spot}"' in js, spot
    # 页面上每个能点的 kind 都必须是适配层认得的
    from server.v1 import undertide_service as svc
    import re

    kinds = set(re.findall(r'kind: "([a-z_]+)"', js))
    local_only = {"menu", "goto"}
    for kind in sorted(kinds - local_only):
        assert kind in svc.TITLES or kind in {"menu"}, f"前端按钮 {kind} 后端没有"
    # 每个 kind 都要能被 chooseDeskAction 接住：要么直接办（RUN_NOW），要么先填表（FORMS）
    run_now = set(re.findall(r'"([a-z_]+)"', js[js.index("const RUN_NOW"):js.index("/** 要填东西的动作")]))
    forms = set(re.findall(r"^  ([a-z_]+): \(", js[js.index("const FORMS"):js.index("function amountForm")], re.M))
    for kind in sorted(kinds - local_only):
        assert kind in run_now or kind in forms, f"按钮 {kind} 点了没人接（chooseDeskAction 会报「没接上」）"
    art = (ROOT / "server/static/island/ui/art.js").read_text(encoding="utf-8")
    for spot in ("undertide-well", "undertide-pit", "undertide-tavern", "undertide-jail", "undertide-kroom"):
        assert f'"{spot}"' in art
    arts = (ROOT / "server/static/island/assets/ART.md").read_text(encoding="utf-8")
    for spot in ("undertide-well", "undertide-pit", "undertide-tavern", "undertide-jail", "undertide-kroom"):
        assert f"scenes/{spot}.png" in arts, spot
