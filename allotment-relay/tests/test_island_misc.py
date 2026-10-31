#!/usr/bin/env python3
"""衣泊坊接委托、酒吧今晚栏的补全；以及酒吧碗险按钮的前端取值。"""
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


def test_atelier_and_bar_command_translation() -> None:
    from server.v1 import atelier_service, bar_service
    from server.v1.errors import ApiError

    a = atelier_service._command
    assert a("commission", "短褂 海色") == "委托 短褂 海色"
    assert a("commission", "呢衣 墨色 灯塔") == "委托 呢衣 墨色 灯塔"
    for target in ["短褂", "不存在 海色", "短褂 不存在", "短褂 海色 不存在", "短褂 海色 素 多余"]:
        with pytest.raises(ApiError):
            a("commission", target)
    b = bar_service._command
    assert b("tonight", "") == "tonight"
    assert b("staff", "") == "staff"
    assert b("song", "") == "song"
    assert b("lodge", "") == "lodge"
    assert b("request_song", "海阔天空") == "request_song 海阔天空"
    assert b("chat", "") == "chat"
    assert b("chat", "今晚人多不多") == "chat 今晚人多不多"
    assert b("tip", "安 10") == "tip 安 10"
    assert b("tip", "安 10 辛苦了") == "tip 安 10 辛苦了"
    for kind, target in [("request_song", ""), ("tip", "安"), ("tip", "安 0"), ("tip", "安 x"), ("tip", "安 10 " + "x" * 80)]:
        with pytest.raises(ApiError):
            b(kind, target)


def test_atelier_and_bar_over_http() -> None:
    asyncio.run(_http())


async def _http() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="misc-"))
    os.environ["DATA_DIR"] = str(tmp)
    from server import config, db

    config.DATA_DIR = tmp
    config.DB_PATH = tmp / "relay.db"
    db.DATA_DIR = tmp
    db.DB_PATH = tmp / "relay.db"
    db._DB_MUTEX = asyncio.Lock()
    await db.init_db()
    key = await db.create_api_key("misc@example.com")
    from fastapi.testclient import TestClient
    from server.main import app

    client = TestClient(app)
    assert client.post("/api/v1/session", json={"api_key": key, "name": "杂项客"}).status_code == 200
    idx = 0

    def post(path: str, kind: str, target: str = ""):
        nonlocal idx
        idx += 1
        return client.post(f"/api/v1/{path}/act", headers=_auth(key, {"Idempotency-Key": f"misc-{idx}"}),
                           json={"kind": kind, "target": target})

    atelier = client.get("/api/v1/atelier", headers=_auth(key)).json()["atelier"]
    cat = atelier["catalog"]
    assert {c["name"] for c in cat["cuts"]} >= {"短褂", "婚服"}
    assert {c["name"] for c in cat["colors"]} >= {"海色", "墨色"}
    assert {c["name"] for c in cat["motifs"]} >= {"素", "潮纹"}
    # 没布没染料：游戏会拦，但命令已放行（4xx，不是 400「命令不对」之外的崩）
    res = post("atelier", "commission", "短褂 海色")
    assert res.status_code in (200, 400, 409), res.text
    assert res.json().get("ok") is not True or res.json()["event"]["narrative"]
    assert post("atelier", "commission", "短褂").status_code == 400

    for kind in ("tonight", "staff", "song"):
        res = post("bar", kind)
        assert res.status_code == 200, (kind, res.text)
        assert res.json()["event"]["narrative"], kind
    for kind, target in [("request_song", "海阔天空"), ("chat", ""), ("tip", "不存在的人 10"), ("lodge", "")]:
        res = post("bar", kind, target)
        assert res.status_code in (200, 400, 409), (kind, res.status_code, res.text)
    assert post("bar", "tip", "安").status_code == 400


def test_bar_front_end() -> None:
    app = (ROOT / "server/static/island/app.js").read_text(encoding="utf-8")
    # barCan 里按 target 找碗险动作，target 必须是形参，否则点碗险按钮会 ReferenceError
    assert re.search(r"function barCan\(kind, row, target\b", app)
    assert "barCan(kind, row, target)" in app
    bar = (ROOT / "server/static/island/scenes/bar.js").read_text(encoding="utf-8")
    for kind in ("tonight", "staff", "song", "request_song", "tip", "chat", "lodge"):
        assert f'sku("{kind}"' in bar, kind
        assert f'"{kind}"' in app, kind
    atelier = (ROOT / "server/static/island/scenes/atelier.js").read_text(encoding="utf-8")
    assert 'sku("commission"' in atelier and 'kind === "commission"' in app


def test_duty_lock_only_for_real_overdue() -> None:
    from server.v1.errors import classify

    real = ValueError("联盟规定每 2 天必须 bar_ops work 滨海酒吧上工。荔栀：「安，打卡去。份地先停着」")
    assert classify(real).code == "DUTY_LOCKED"
    # 包宿被拒的话里顺带写了 bar_ops work，不是考勤锁，人类要看到的是原话
    lodge = ValueError("「你还没到那个地步。」她朝招聘启事抬了抬下巴，「bar_ops work——那是给还有力气的人准备的。」")
    assert classify(lodge).code != "DUTY_LOCKED"
