#!/usr/bin/env python3
"""/api/v1/neighbors、/api/v1/field/act、小屋里补上的家维/杂务/吉祥物/起名/闹脾气/兽医。
全部翻成已有的 alliance_ops / steward_ops / plot_ops / hut_ops / barn_ops / visit_ops / mascot 子命令。"""
from __future__ import annotations

import asyncio
import os
import re
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _auth(key: str, extra: dict | None = None) -> dict:
    headers = {"Authorization": f"Bearer {key}"}
    if extra:
        headers.update(extra)
    return headers


def test_neighbor_command_translation() -> None:
    from server.v1 import neighbor_service as svc
    from server.v1.errors import ApiError

    c = svc._command
    assert c("peer", "安") == ("steward", "peer 安")
    assert c("assist", "安") == ("alliance", "assist 安")
    assert c("rapport", "安") == ("alliance", "rapport 安")
    assert c("steal", "安") == ("plot", "偷菜 安")
    assert c("steal", "安 园1") == ("plot", "偷菜 安 园1")
    assert c("amends", "安") == ("plot", "amends 安")
    assert c("loan_give", "安") == ("alliance", "借船 给 安")
    assert c("loan_status", "") == ("alliance", "借船 状态")
    assert c("share_open", "漂航船") == ("alliance", "合伙 开 漂航船")
    assert c("share_join", "安") == ("alliance", "合伙 入 安")
    assert c("share_end", "") == ("alliance", "合伙 散")
    assert c("foster_out", "安 2") == ("alliance", "托养 送出 安 2")
    assert c("foster_back", "安 2") == ("alliance", "托养 接回 安 2")
    assert c("foster_list", "") == ("alliance", "托养 列表")
    assert c("basket_open", "") == ("alliance", "菜篮 开")
    assert c("basket_order", "安") == ("alliance", "菜篮 订 安")
    assert c("basket_claim", "") == ("alliance", "菜篮 领")
    assert c("cofarm_order", "安") == ("alliance", "共耕 订 安")
    assert c("cofarm_end", "安") == ("alliance", "共耕 解 安")
    assert c("league_status", "") == ("alliance", "league status")
    assert c("league_contribute", "甘蓝 3") == ("alliance", "league contribute 甘蓝 3")
    assert c("larder_donate", "甘蓝 3") == ("alliance", "donate 甘蓝 3")
    assert c("larder_draw", "甘蓝 3") == ("alliance", "draw 甘蓝 3")
    assert c("contract_take", "12") == ("alliance", "contract take 12")
    assert c("contract_post", "石蟹王 1 40") == ("alliance", "contract post 石蟹王 1 40")
    assert c("contract_post_labor", "3 60") == ("alliance", "contract post 看护 3 60")
    for kind, target in [
        ("peer", ""), ("peer", "a b"), ("peer", "a;b"), ("steal", ""), ("steal", "安 9x"), ("steal", "a b c"),
        ("share_open", "小木筏"), ("foster_out", "安"), ("foster_out", "安 0"), ("league_contribute", "甘蓝 0"),
        ("larder_draw", "甘蓝"), ("contract_take", "x"), ("contract_post", "a 1"), ("contract_post_labor", "3"),
        ("nope", ""),
    ]:
        with pytest.raises(ApiError):
            c(kind, target)


def test_field_command_translation() -> None:
    from server.v1 import field_service as svc
    from server.v1.errors import ApiError

    c = svc._command
    assert c("soil", "") == "肥力"
    assert c("seed_list", "") == "留种 status"
    assert c("seed_keep", "甘蓝") == "留种 甘蓝"
    assert c("scarecrow", "2") == "scarecrow 2"
    assert c("camera_install", "园1") == "camera install 园1"
    assert c("camera_remove", "棚1") == "camera remove 棚1"
    assert c("camera_check", "") == "camera check"
    assert c("camera_check", "3") == "camera check 3"
    assert c("chop", "园2") == "chop 园2"
    assert c("gather", "") == "gather"
    assert c("forage", "") == "forage"
    assert c("incident_history", "") == "incident history"
    assert c("incident_history", "30") == "incident history 30"
    for kind, target in [("scarecrow", ""), ("chop", "x"), ("seed_keep", ""), ("incident_history", "99"), ("nope", "")]:
        with pytest.raises(ApiError):
            c(kind, target)


def test_hut_extra_command_translation() -> None:
    from server.v1 import hut_service as svc
    from server.v1.errors import ApiError

    c = svc._command
    assert c("chore_pay", "") == ("hut", "家维 交")
    assert c("chore_task", "自修") == ("hut", "杂务 自修")
    assert c("mascot_adopt", "scout|咕咕") == ("bundle", "mascot adopt 咕咕 scout")
    assert c("mascot_upkeep", "") == ("bundle", "mascot upkeep")
    assert c("mascot_diet", "") == ("bundle", "mascot 减肥")
    assert c("barn_name", "2|豆花") == ("barn", "起名 2 豆花")
    assert c("barn_fuss", "哄") == ("barn", "闹脾气 哄")
    assert c("vet_treat", "3") == ("visit", "兽医 treat 3")
    assert c("vet_fumes", "通风") == ("visit", "兽医 棚险 通风")
    assert c("vet_catalog", "") == ("visit", "兽医 catalog")
    for kind, target in [
        ("chore_task", "打人"), ("mascot_adopt", "wolf|x"), ("mascot_adopt", "scout|"), ("mascot_adopt", "scout|a b"),
        ("barn_name", "x|豆花"), ("barn_name", "1|"), ("barn_fuss", "炸了"), ("vet_treat", "x"), ("vet_fumes", "烧"),
    ]:
        with pytest.raises(ApiError):
            c(kind, target)


def test_neighbors_field_hut_over_http() -> None:
    asyncio.run(_http())


async def _http() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="home-neighbors-"))
    os.environ["DATA_DIR"] = str(tmp)
    from server import config, db

    config.DATA_DIR = tmp
    config.DB_PATH = tmp / "relay.db"
    db.DATA_DIR = tmp
    db.DB_PATH = tmp / "relay.db"
    db._DB_MUTEX = asyncio.Lock()
    await db.init_db()
    key = await db.create_api_key("hn-a@example.com")
    other = await db.create_api_key("hn-b@example.com")
    from fastapi.testclient import TestClient
    from server.main import app

    client = TestClient(app)
    assert client.post("/api/v1/session", json={"api_key": key, "name": "邻居甲"}).status_code == 200
    assert client.post("/api/v1/session", json={"api_key": other, "name": "邻居乙"}).status_code == 200
    row = await db.get_key_row(key)
    sid = int((await db.get_steward_by_key_id(row["id"]))["id"])
    idx = 0

    def post(path: str, kind: str, target: str = ""):
        nonlocal idx
        idx += 1
        return client.post(f"/api/v1/{path}/act", headers=_auth(key, {"Idempotency-Key": f"hn-{idx}"}),
                           json={"kind": kind, "target": target})

    roster = client.get("/api/v1/neighbors", headers=_auth(key)).json()["neighbors"]
    assert roster["total"] == 2 and roster["listed"] == 1
    person = roster["people"][0]
    assert person["name"] == "邻居乙" and {"title", "ripe", "home", "rapport", "motto"} <= set(person)
    assert roster["boats"] == ["切波艇", "近海帆撬", "漂航船", "延绳船"]

    for kind, target in [
        ("peer", "邻居乙"), ("rapport", "邻居乙"), ("loan_status", ""), ("share_status", ""), ("foster_list", ""),
        ("cofarm_status", ""), ("league_status", ""), ("league_board", ""), ("contract_list", ""),
        ("contract_mine", ""), ("larder_list", ""),
    ]:
        res = post("neighbors", kind, target)
        assert res.status_code == 200, (kind, res.text)
        assert res.json()["event"]["narrative"], kind
    # 规则拦下的是 4xx，不是 500；命令本身在适配层被放行
    for kind, target in [("assist", "邻居乙"), ("loan_give", "邻居乙"), ("steal", "邻居乙"), ("amends", "邻居乙"),
                         ("basket_order", "邻居乙"), ("cofarm_order", "邻居乙"), ("share_open", "漂航船")]:
        res = post("neighbors", kind, target)
        assert res.status_code in (200, 400, 409), (kind, res.status_code, res.text)
    assert post("neighbors", "steal", "").status_code == 400
    assert post("neighbors", "share_open", "木筏").status_code == 400

    for kind, target in [("soil", ""), ("seed_list", ""), ("camera_check", ""), ("incident_history", "")]:
        res = post("field", kind, target)
        assert res.status_code == 200, (kind, res.text)
    for kind, target in [("scarecrow", "1"), ("camera_install", "1"), ("camera_remove", "1"), ("gather", ""),
                         ("forage", ""), ("seed_keep", "甘蓝"), ("chop", "园1")]:
        res = post("field", kind, target)
        assert res.status_code in (200, 400, 409), (kind, res.status_code, res.text)
    assert post("field", "scarecrow", "").status_code == 400

    # 小屋：没房时这些都不出现；买了房再看
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET tickets=2000, energy=100, hut_built=1, hut_level=2, barn_built=1 WHERE id=?", (sid,))
        await conn.commit()
    hut = client.get("/api/v1/hut", headers=_auth(key)).json()["hut"]
    home = {r["kind"] for r in hut["items"]["home"]}
    assert {"mascot_adopt"} <= home, home
    assert "chore_pay" in home  # Lv2 起交灯油
    barn = {r["kind"] for r in hut["items"]["barn"]}
    assert {"vet_catalog", "vet_status"} <= barn, barn
    assert not re.search("[\U0001F300-\U0001FAFF☀-➿]", str([r for r in hut["items"]["home"] if r["kind"].startswith(("chore", "mascot"))]))

    adopted = post("hut", "mascot_adopt", "scout|咕噜")
    assert adopted.status_code == 200, adopted.text
    home2 = {r["kind"] for r in client.get("/api/v1/hut", headers=_auth(key)).json()["hut"]["items"]["home"]}
    assert {"mascot_upkeep", "mascot_train", "mascot_status"} <= home2
    assert post("hut", "mascot_upkeep").status_code in (200, 400, 409)
    assert post("hut", "chore_pay").status_code in (200, 400, 409)
    for kind in ("vet_catalog", "vet_status"):
        assert post("hut", kind).status_code == 200, kind
    assert post("hut", "barn_name", "1|豆花").status_code in (200, 400, 409)
    assert post("hut", "mascot_adopt", "wolf|x").status_code == 400
    assert post("hut", "chore_task", "打人").status_code == 400


def test_front_end_wiring() -> None:
    js = {n: (ROOT / f"server/static/island/ui/{n}.js").read_text(encoding="utf-8") for n in ("desk", "neighbors", "field", "profile")}
    api = (ROOT / "server/static/island/api.js").read_text(encoding="utf-8")
    for route in ("/api/v1/neighbors", "/api/v1/neighbors/act", "/api/v1/field/act"):
        assert route in api, route
    from server.v1 import field_service, neighbor_service

    for kind in set(re.findall(r'kind: "([a-z_]+)"', js["neighbors"])):
        assert kind in neighbor_service.TITLES, kind
    for kind in set(re.findall(r'kind: "([a-z_]+)"', js["field"])):
        assert kind in field_service.TITLES, kind
    assert "openNeighbors" in js["profile"]
    home = (ROOT / "server/static/island/scenes/home.js").read_text(encoding="utf-8")
    assert "island-field-open" in home and "onOpenField" in home
    app = (ROOT / "server/static/island/app.js").read_text(encoding="utf-8")
    assert "openField" in app and "onOpenField" in app
    for name, src in js.items():
        assert not re.search("[\U0001F300-\U0001FAFF☀-➿]", src), name


def test_no_lone_surrogates_in_game_text() -> None:
    """源码里把 emoji 写成成对的 \\udXXX 转义会得到两个孤立代理项，一输出（JSON / MCP）就 UnicodeEncodeError。
    曾经 barn_disease 里四个图标这样写，兽医价目一点就崩。"""
    import asyncio as aio
    import os as _os
    import tempfile as _tf

    bad = []
    for path in (ROOT / "server").rglob("*.py"):
        if re.search(r"\\u[dD][89a-fA-F][0-9a-fA-F]{2}", path.read_text(encoding="utf-8")):
            bad.append(str(path.relative_to(ROOT)))
    assert not bad, bad

    async def go():
        tmp = Path(_tf.mkdtemp(prefix="surrogate-"))
        _os.environ["DATA_DIR"] = str(tmp)
        from server import config, db, mcp_dispatch

        config.DATA_DIR = tmp
        config.DB_PATH = tmp / "relay.db"
        db.DATA_DIR = tmp
        db.DB_PATH = tmp / "relay.db"
        db._DB_MUTEX = aio.Lock()
        await db.init_db()
        key = await db.create_api_key("surrogate@example.com")
        row = await db.get_key_row(key)
        await db.enroll_steward(row["id"], "兽医客", "", "naturalist", "")
        text = await mcp_dispatch.visit_bundle(row["id"], "兽医 catalog")
        text.encode("utf-8")  # 不能抛 UnicodeEncodeError

    aio.run(go())
