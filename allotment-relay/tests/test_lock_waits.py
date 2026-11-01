#!/usr/bin/env python3
"""数据库锁：等锁超时要报清楚的错、占锁过久打 WARNING、慢事（AI / 图片 / 文件）不许占着锁做。"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
import threading
from io import BytesIO
from pathlib import Path


async def _boot(tmp: Path):
    os.environ["DATA_DIR"] = str(tmp)
    from server import config, db

    config.DATA_DIR = tmp
    config.DB_PATH = tmp / "relay.db"
    db.DATA_DIR = tmp
    db.DB_PATH = tmp / "relay.db"
    db._DB_MUTEX = asyncio.Lock()
    await db.init_db()
    return db


async def _enroll(db, email: str, name: str):
    key = await db.create_api_key(email)
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], name, "", "naturalist", "")
    s = await db.get_steward_by_key_id(row["id"])
    return key, row["id"], int(s["id"])


async def _call(app, method: str, path: str, *, key: str = "", query: bytes = b"", body: bytes = b"", ctype: str = ""):
    sent: list[dict] = []

    async def send(message):
        sent.append(message)

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    headers = [(b"host", b"t")]
    if key:
        headers.append((b"authorization", f"Bearer {key}".encode()))
    if ctype:
        headers.append((b"content-type", ctype.encode()))
        headers.append((b"content-length", str(len(body)).encode()))
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method,
        "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": query,
        "headers": headers, "client": ("127.0.0.1", 1), "server": ("t", 80),
    }
    await app(scope, receive, send)
    start = next(m for m in sent if m["type"] == "http.response.start")
    data = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return start["status"], dict((k.decode().lower(), v.decode()) for k, v in start["headers"]), data


def test_lock_wait_timeout_raises_clear_error_and_logs_holder(monkeypatch, caplog) -> None:
    monkeypatch.setenv("DB_LOCK_WAIT_TIMEOUT_SECONDS", "1")

    async def run() -> None:
        db = await _boot(Path(tempfile.mkdtemp(prefix="lockwait-")))
        started = asyncio.Event()

        async def holder() -> None:
            async with db.request_scope("GET /api/慢请求"):
                async with db.connect():
                    started.set()
                    await asyncio.sleep(2.6)

        task = asyncio.create_task(holder())
        await started.wait()
        t0 = asyncio.get_running_loop().time()
        with caplog.at_level(logging.WARNING):
            try:
                async with db.request_scope("POST /api/等锁的"):
                    async with db.connect():
                        raise AssertionError("不该拿到锁")
            except db.DbBusyError as exc:
                waited = asyncio.get_running_loop().time() - t0
                assert 0.8 <= waited < 2.0, waited
                assert str(exc) == db.DB_BUSY_MSG
                assert exc.label == "POST /api/等锁的" and exc.holder == "GET /api/慢请求"
        await task
        text = caplog.text
        assert "等数据库锁超时" in text and "POST /api/等锁的" in text and "GET /api/慢请求" in text
        assert not db._DB_MUTEX.locked()

    asyncio.run(run())


def test_hold_longer_than_threshold_logs_warning_with_route(monkeypatch, caplog) -> None:
    monkeypatch.setenv("DB_LOCK_HOLD_WARN_SECONDS", "0.3")

    async def run() -> None:
        db = await _boot(Path(tempfile.mkdtemp(prefix="lockhold-")))
        with caplog.at_level(logging.WARNING):
            async with db.request_scope("GET /api/v1/hall"):
                async with db.connect():
                    await asyncio.sleep(0.6)
            async with db.request_scope("GET /api/快的"):
                async with db.connect():
                    pass
        warn = [r.getMessage() for r in caplog.records if "占用过久" in r.getMessage()]
        assert len(warn) == 1 and "GET /api/v1/hall" in warn[0] and "占用=0.6" in warn[0], warn
        assert not any("GET /api/快的" in m for m in warn)

    asyncio.run(run())


def test_call_ops_turns_busy_into_plain_message_without_retrying() -> None:
    async def run() -> None:
        from server import db, mcp_dispatch as mux

        calls = []

        async def fn(*a, **k):
            calls.append(1)
            raise db.DbBusyError(20.0, "x", "y", 5.0)

        try:
            await mux._call_ops(fn, 1, "")
        except ValueError as exc:
            assert str(exc) == db.DB_BUSY_MSG
        else:
            raise AssertionError("应当抛 ValueError")
        assert len(calls) == 1, "等锁超时不重试"

    asyncio.run(run())


def test_http_returns_503_with_error_code_when_lock_wait_times_out(monkeypatch) -> None:
    monkeypatch.setenv("DB_LOCK_WAIT_TIMEOUT_SECONDS", "1")

    async def run() -> None:
        db = await _boot(Path(tempfile.mkdtemp(prefix="lock503-")))
        key, _kid, _sid = await _enroll(db, "k@x.com", "忙碌岛民")
        from server.main import app

        started = asyncio.Event()

        async def holder() -> None:
            async with db.connect():
                started.set()
                await asyncio.sleep(2.2)

        task = asyncio.create_task(holder())
        await started.wait()
        status, headers, data = await _call(app, "GET", "/api/v1/world", key=key)
        await task
        assert status == 503, (status, data[:200])
        body = json.loads(data)
        assert body["ok"] is False and body["error"]["code"] == "DB_BUSY"
        assert body["error"]["message"] == db.DB_BUSY_MSG and body["detail"] == db.DB_BUSY_MSG
        assert headers.get("retry-after") == "10"

    asyncio.run(run())


def test_vet_model_call_runs_outside_the_lock(monkeypatch) -> None:
    async def run() -> None:
        from server import vet, vet_npc

        db = await _boot(Path(tempfile.mkdtemp(prefix="vetlock-")))
        _key, kid, _sid = await _enroll(db, "v@x.com", "牲口主人")
        seen: list[bool] = []

        async def fake_speak(ctx):
            seen.append(db._DB_MUTEX.locked())
            await asyncio.sleep(0.05)
            return "今天栏里安静。", True

        monkeypatch.setattr(vet_npc, "speak", fake_speak)
        async with db.request_scope("MCP vet_ops"):
            out = await vet.vet_ops(kid, "chat 你好")
        assert seen == [False], "调模型时不许占着数据库锁"
        assert "今天栏里安静。" in out and "霍衡" in out
        assert not db._DB_MUTEX.locked()

    asyncio.run(run())


def _png(color=(200, 30, 30), size=(400, 400)) -> bytes:
    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def test_sticker_upload_processing_runs_off_lock_and_off_loop(monkeypatch) -> None:
    async def run() -> None:
        from server import lounge, lounge_stickers as st

        db = await _boot(Path(tempfile.mkdtemp(prefix="stlock-")))
        key, _kid, sid = await _enroll(db, "s@x.com", "贴纸岛民")
        main_thread = threading.get_ident()
        seen: list[tuple[bool, bool]] = []
        real = st._compress_sticker

        def spy(data, ext):
            seen.append((db._DB_MUTEX.locked(), threading.get_ident() != main_thread))
            return real(data, ext)

        monkeypatch.setattr(st, "_compress_sticker", spy)
        async with db.request_scope("POST /api/lounge/stickers"):
            items = await lounge.human_upload_stickers(key, [("a.png", "image/png", _png()), ("b.png", "image/png", _png((1, 2, 3)))])
        assert len(items) == 2
        assert seen == [(False, True), (False, True)], seen
        folder = st.sticker_dir_for(sid)
        assert len(list(folder.iterdir())) == 2
        # 校验文案不变
        try:
            await st.save_uploaded_stickers(sid, [("x.png", "image/png", b"")])
        except ValueError as exc:
            assert "是空文件" in str(exc)
        else:
            raise AssertionError

    asyncio.run(run())


def test_sticker_upload_db_failure_cleans_files(monkeypatch) -> None:
    async def run() -> None:
        from server import lounge_stickers as st

        db = await _boot(Path(tempfile.mkdtemp(prefix="stfail-")))
        _key, _kid, sid = await _enroll(db, "f@x.com", "清理岛民")
        real_connect = db.connect
        calls = {"n": 0}

        import contextlib

        @contextlib.asynccontextmanager
        async def flaky():
            calls["n"] += 1
            if calls["n"] >= 2:  # 第 1 次是 list_stickers，第 2 次是入库
                raise RuntimeError("入库炸了")
            async with real_connect() as c:
                yield c

        monkeypatch.setattr(db, "connect", flaky)
        try:
            await st.save_uploaded_stickers(sid, [("a.png", "image/png", _png())])
        except RuntimeError:
            pass
        else:
            raise AssertionError
        assert list(st.sticker_dir_for(sid).iterdir()) == [], "入库失败不留孤儿文件"

    asyncio.run(run())


def test_sticker_file_variant_built_off_lock_and_off_loop(monkeypatch) -> None:
    async def run() -> None:
        from server import lounge, lounge_stickers as st
        from server.main import app

        db = await _boot(Path(tempfile.mkdtemp(prefix="stfile-")))
        key, _kid, _sid = await _enroll(db, "t@x.com", "缩略岛民")
        items = await lounge.human_upload_stickers(key, [("a.png", "image/png", _png(size=(900, 900)))])
        main_thread = threading.get_ident()
        seen: list[tuple[bool, bool]] = []
        real = st.ensure_variant

        def spy(path, variant="full"):
            seen.append((db._DB_MUTEX.locked(), threading.get_ident() != main_thread))
            return real(path, variant)

        monkeypatch.setattr(st, "ensure_variant", spy)
        status, _h, data = await _call(app, "GET", f"/api/lounge/stickers/{items[0]['id']}/file", query=b"variant=thumb")
        assert status == 200 and len(data) > 100
        assert seen == [(False, True)], seen
        assert not db._DB_MUTEX.locked()

    asyncio.run(run())
