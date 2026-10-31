#!/usr/bin/env python3
"""/api/v1/story、/api/v1/profile：潮闻与故事、「这一号」。

动作只翻成已有的 tale_ops / story_ops / steward_ops；写操作先对着当前列表验证，前端不能自己编指令。"""
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


def test_profile_command_translation() -> None:
    from server.v1 import profile_service as svc
    from server.v1.errors import ApiError

    cmd = svc._command
    assert cmd("sheet", "") == "sheet"
    assert cmd("bond", "") == "岛缘"
    assert cmd("titles", "") == "成就"
    assert cmd("title_wear", "逾篱客") == "称呼 逾篱客"
    assert cmd("title_off", "") == "卸"
    assert cmd("collection", "") == "收集"
    assert cmd("invite", "") == "引航"
    assert cmd("invite_bind", "AB12CD34") == "绑定 AB12CD34"
    assert cmd("tierlog", "") == "灾档"
    assert cmd("choice", "barn_fuss 哄") == "灾选 barn_fuss 哄"
    assert cmd("gazette", "") == "周报"
    assert cmd("repair", "") == "维修"
    assert cmd("gifts", "") == "收礼"
    assert cmd("revise", "潮声不断|") == "revise 潮声不断"
    assert cmd("revise", "|戴草帽") == "revise portrait 戴草帽"
    assert cmd("revise", "潮声不断|戴草帽") == "revise 潮声不断 portrait 戴草帽"
    for kind, target in [
        ("title_wear", ""), ("title_wear", "a\nb"), ("invite_bind", "x"), ("invite_bind", "AB 12"),
        ("choice", "only"), ("choice", "a b c"), ("choice", "a;b c"), ("revise", "|"), ("revise", "a\nb|"),
        ("revise", "x" * 201), ("nope", ""),
    ]:
        with pytest.raises(ApiError):
            cmd(kind, target)


def test_story_and_profile_over_http() -> None:
    asyncio.run(_story_and_profile_over_http())


async def _story_and_profile_over_http() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="story-profile-"))
    os.environ["DATA_DIR"] = str(tmp)
    from server import config, db

    config.DATA_DIR = tmp
    config.DB_PATH = tmp / "relay.db"
    db.DATA_DIR = tmp
    db.DB_PATH = tmp / "relay.db"
    db._DB_MUTEX = asyncio.Lock()
    await db.init_db()
    key = await db.create_api_key("story-profile@example.com")
    other = await db.create_api_key("story-other@example.com")
    from fastapi.testclient import TestClient
    from server.main import app

    client = TestClient(app)
    assert client.post("/api/v1/session", json={"api_key": key, "name": "故事客"}).status_code == 200
    assert client.post("/api/v1/session", json={"api_key": other, "name": "别人家"}).status_code == 200
    idx = 0

    def post(path: str, kind: str, target: str = ""):
        nonlocal idx
        idx += 1
        return client.post(f"/api/v1/{path}/act", headers=_auth(key, {"Idempotency-Key": f"sp-{idx}"}),
                           json={"kind": kind, "target": target})

    # ---- 故事 ----
    listing = client.get("/api/v1/story", headers=_auth(key))
    assert listing.status_code == 200, listing.text
    story = listing.json()["story"]
    assert story["active"] == [] and story["done"] == []
    keys = {(r["kind"], r["key"]) for r in story["available"]}
    assert ("tale", "black_box_lover") in keys
    assert ("story", "cinderella") in keys

    # 没出现在列表里的、乱编的、还没开始的下一步，一律拒绝，不进游戏
    assert post("story", "accept", "no_such_tale").status_code == 409
    assert post("story", "accept", "Bad Key!").status_code == 400
    assert post("story", "start", "black_box_lover").status_code == 409  # 潮闻不能用 start
    assert post("story", "step", "tale_ops|explore beach").status_code == 409  # 还没接
    assert post("story", "step", "shell_ops|rm -rf").status_code == 400
    assert post("story", "wat", "").status_code == 400
    assert post("story", "review", "tale|black_box_lover").status_code >= 400  # 没走完不能回看

    accepted = post("story", "accept", "black_box_lover")
    assert accepted.status_code == 200, accepted.text
    body = accepted.json()
    assert body["event"]["kind"] == "story" and body["event"]["narrative"]
    active = body["story"]["active"]
    assert len(active) == 1 and active[0]["key"] == "black_box_lover"
    step = active[0]["actions"][0]
    assert step["place"] == "tide"
    assert step["hint"] == "", "阶段提示写给模型，带指令，不给人类"
    assert "tale_ops" not in str(body["story"]["active"][0]["blurb"])
    assert post("story", "accept", "black_box_lover").status_code == 409  # 已经接了

    # 当前一步可走：命令必须和列表里的一字不差
    assert post("story", "step", "tale_ops|explore shore").status_code == 409
    ran = post("story", "step", f"{step['tool']}|{step['command']}")
    assert ran.status_code in (200, 409), ran.text  # 精力、天气可能拦，但不是 400（命令本身被放行了）
    # 另一个号看不到这个号的进度
    mine = client.get("/api/v1/story", headers=_auth(other)).json()["story"]
    assert mine["active"] == []

    # ---- 这一号 ----
    prof = client.get("/api/v1/profile", headers=_auth(key))
    assert prof.status_code == 200, prof.text
    info = prof.json()["profile"]
    assert info["name"] == "故事客"
    assert info["invite"]["code"] and info["invite"]["link"].endswith(info["invite"]["code"])
    assert info["choices"] == []
    for kind in ("sheet", "bond", "titles", "collection", "invite", "tierlog", "gazette", "repair", "gifts"):
        res = post("profile", kind)
        assert res.status_code == 200, (kind, res.text)
        assert res.json()["event"]["narrative"], kind
    assert post("profile", "title_off").status_code in (200, 400, 409)
    assert post("profile", "choice", "barn_fuss 哄").status_code >= 400  # 没有待选

    revised = post("profile", "revise", "潮声不断|戴草帽")
    assert revised.status_code == 200, revised.text
    assert revised.json()["profile"]["motto"] == "潮声不断"
    assert revised.json()["profile"]["portrait"] == "戴草帽"
    assert post("profile", "revise", "|").status_code == 400

    renamed = post("profile", "rename", "新名字安")
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["profile"]["name"] == "新名字安"
    assert renamed.json()["me"]["name"] == "新名字安"
    assert post("profile", "rename", "别人家").status_code >= 400  # 重名
    assert post("profile", "rename", "安").status_code >= 400  # 太短

    # 引航：不能绑自己的码；别人的码只能绑一次
    mine_code = info["invite"]["code"]
    assert post("profile", "invite_bind", mine_code).status_code >= 400
    other_code = client.get("/api/v1/profile", headers=_auth(other)).json()["profile"]["invite"]["code"]
    bound = post("profile", "invite_bind", other_code)
    assert bound.status_code == 200, bound.text
    assert bound.json()["profile"]["invite"]["bound"] is True
    assert post("profile", "invite_bind", other_code).status_code >= 400


def test_island_front_end_wiring() -> None:
    html = (ROOT / "server/templates/island.html").read_text(encoding="utf-8")
    assert 'id="island-panel"' in html and 'id="island-story-hook"' in html
    app = (ROOT / "server/static/island/app.js").read_text(encoding="utf-8")
    assert "bindProfileChips" in app and "openProfile" in app
    assert "mountStoryHook(name)" in app
    assert "onStories" in app and "openStories" in app
    climate = (ROOT / "server/static/island/ui/climate.js").read_text(encoding="utf-8")
    assert "data-open-stories" in climate
    api = (ROOT / "server/static/island/api.js").read_text(encoding="utf-8")
    for route in ("/api/v1/story", "/api/v1/story/act", "/api/v1/profile", "/api/v1/profile/act"):
        assert route in api, route
    stories = (ROOT / "server/static/island/ui/stories.js").read_text(encoding="utf-8")
    profile = (ROOT / "server/static/island/ui/profile.js").read_text(encoding="utf-8")
    # 人类界面不出现 MCP 工具名
    for name, src in (("stories", stories), ("profile", profile)):
        code = re.sub(r"/\*.*?\*/|^\s*//.*$", "", src, flags=re.S | re.M)  # 注释里可以写
        shown = code.replace('"tale_ops"', "").replace('"story_ops"', "")  # 故事列表里 tool 名只是分发标记，不显示
        assert not re.search(r"[a-z]+_ops", shown), name
    # 前端用到的每个 profile kind，后端都认
    from server.v1 import profile_service

    for kind in set(re.findall(r'act\("([a-z_]+)"', profile)):
        assert kind in profile_service.TITLES, kind
    # 没有 emoji 当图标：面板和故事册里的图标都是手绘 SVG
    for src in (stories, profile, (ROOT / "server/static/island/ui/panel.js").read_text(encoding="utf-8")):
        assert not re.search("[\U0001F300-\U0001FAFF☀-➿]", src)
    assert "<svg" in stories
