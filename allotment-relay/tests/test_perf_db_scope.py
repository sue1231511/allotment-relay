#!/usr/bin/env python3
"""性能改造的回归：请求内复用连接（语义与「每块新开连接」一致）、旧送礼补收礼人一次性迁移、
任务目录请求路径不再写、纪事/集市索引。"""
from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import aiosqlite


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


async def _enroll(db, email: str, name: str) -> int:
    key = await db.create_api_key(email)
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], name, "", "naturalist", "")
    return int((await db.get_steward_by_key_id(row["id"]))["id"])


def _count_connects(monkeypatch) -> list[int]:
    hits: list[int] = []
    real = aiosqlite.connect

    def counting(*a, **k):
        hits.append(1)
        return real(*a, **k)

    monkeypatch.setattr(aiosqlite, "connect", counting)
    return hits


def test_scope_shares_one_connection(monkeypatch) -> None:
    async def run() -> None:
        db = await _boot(Path(tempfile.mkdtemp(prefix="scope-")))
        hits = _count_connects(monkeypatch)
        async with db.request_scope():
            for _ in range(5):
                async with db.connect() as conn:
                    await (await conn.execute("SELECT 1")).fetchone()
        assert len(hits) == 1, hits
        hits.clear()
        for _ in range(5):  # 没有请求域：老路，每块各开一个
            async with db.connect() as conn:
                await (await conn.execute("SELECT 1")).fetchone()
        assert len(hits) == 5
        assert not db._DB_MUTEX.locked()

    asyncio.run(run())


def test_scope_without_db_never_takes_the_lock() -> None:
    async def run() -> None:
        db = await _boot(Path(tempfile.mkdtemp(prefix="scope-nodb-")))
        async with db.request_scope():
            assert not db._DB_MUTEX.locked()
        assert not db._DB_MUTEX.locked()

    asyncio.run(run())


def test_scope_block_semantics_match_fresh_connection() -> None:
    """块里没提交的写入，块结束就丢（以前是关连接）；row_factory 每块复位；异常照抛且回滚。"""
    async def run() -> None:
        db = await _boot(Path(tempfile.mkdtemp(prefix="scope-sem-")))
        sid = await _enroll(db, "a@x.com", "甲方岛民")
        async with db.request_scope():
            async with db.connect() as conn:
                await conn.execute("UPDATE stewards SET tickets=777 WHERE id=?", (sid,))
                # 故意不提交
            async with db.connect() as conn:
                row = await (await conn.execute("SELECT tickets FROM stewards WHERE id=?", (sid,))).fetchone()
                assert row[0] != 777, "没提交的写入不许漏到下一个块"
            async with db.connect() as conn:
                conn.row_factory = aiosqlite.Row
            async with db.connect() as conn:
                assert conn.row_factory is None, "row_factory 每块复位"
            try:
                async with db.connect() as conn:
                    await conn.execute("UPDATE stewards SET tickets=888 WHERE id=?", (sid,))
                    raise ValueError("票不够")
            except ValueError:
                pass
            async with db.connect() as conn:
                row = await (await conn.execute("SELECT tickets FROM stewards WHERE id=?", (sid,))).fetchone()
                assert row[0] != 888, "块内异常要回滚"
            async with db.connect() as conn:
                await conn.execute("UPDATE stewards SET tickets=999 WHERE id=?", (sid,))
                await conn.commit()
        async with db.connect() as conn:
            row = await (await conn.execute("SELECT tickets FROM stewards WHERE id=?", (sid,))).fetchone()
            assert row[0] == 999
        assert not db._DB_MUTEX.locked()

    asyncio.run(run())


def test_nested_connect_inside_block_still_shares() -> None:
    async def run() -> None:
        db = await _boot(Path(tempfile.mkdtemp(prefix="scope-nest-")))
        sid = await _enroll(db, "b@x.com", "乙方岛民")
        async with db.request_scope():
            async with db.connect() as outer:
                await outer.execute("UPDATE stewards SET tickets=321 WHERE id=?", (sid,))
                async with db.connect() as inner:
                    assert inner is outer
                    row = await (await inner.execute("SELECT tickets FROM stewards WHERE id=?", (sid,))).fetchone()
                    assert row[0] == 321, "嵌套块看得到外层没提交的写入（老行为）"
                await outer.commit()
        async with db.connect() as conn:
            assert (await (await conn.execute("SELECT tickets FROM stewards WHERE id=?", (sid,))).fetchone())[0] == 321

    asyncio.run(run())


def test_http_request_uses_single_connection_and_releases_lock_before_sending(monkeypatch) -> None:
    async def run() -> None:
        db = await _boot(Path(tempfile.mkdtemp(prefix="scope-http-")))
        key = await db.create_api_key("c@x.com")
        row = await db.get_key_row(key)
        await db.enroll_steward(row["id"], "丙方岛民", "", "naturalist", "")
        from server.main import app

        hits = _count_connects(monkeypatch)
        sent: list[dict] = []
        locked_when_sent: list[bool] = []

        async def send(message):
            locked_when_sent.append(db._DB_MUTEX.locked())
            sent.append(message)

        body = b""

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        scope = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET",
            "scheme": "http", "path": "/api/v1/world", "raw_path": b"/api/v1/world", "query_string": b"",
            "headers": [(b"authorization", f"Bearer {key}".encode()), (b"host", b"t")],
            "client": ("127.0.0.1", 1), "server": ("t", 80),
        }
        await app(scope, receive, send)
        assert sent and sent[0]["status"] == 200, sent[:1]
        assert len(hits) == 1, f"一次请求只该开 1 个连接，实际 {len(hits)}"
        assert not any(locked_when_sent), "发响应时数据库锁必须已放掉"

    asyncio.run(run())


def test_post_body_replayed_and_static_skipped() -> None:
    from fastapi.testclient import TestClient

    tmp = Path(tempfile.mkdtemp(prefix="scope-post-"))
    asyncio.run(_boot(tmp))
    from server.main import app

    c = TestClient(app)
    r = c.post("/api/v1/session", json={"api_key": "ar_sk_bogus", "name": ""})
    assert r.status_code in (200, 400, 401, 403), r.status_code
    assert "INVALID" in r.text or "error" in r.text or r.status_code == 200
    assert c.get("/static/island/boot.js").status_code == 200


def test_two_scoped_requests_do_not_deadlock() -> None:
    async def run() -> None:
        db = await _boot(Path(tempfile.mkdtemp(prefix="scope-par-")))

        async def one() -> int:
            async with db.request_scope():
                async with db.connect() as conn:
                    await asyncio.sleep(0.01)
                    return (await (await conn.execute("SELECT 1")).fetchone())[0]

        got = await asyncio.wait_for(asyncio.gather(*[one() for _ in range(8)]), timeout=20)
        assert got == [1] * 8

    asyncio.run(run())


def test_gift_targets_backfilled_once_and_reads_do_not_write() -> None:
    async def run() -> None:
        from server import gift_target_backfill as gb

        db = await _boot(Path(tempfile.mkdtemp(prefix="gift-bf-")))
        a = await _enroll(db, "g1@x.com", "送礼人")
        b = await _enroll(db, "g2@x.com", "收礼人")
        async with db.connect() as conn:
            await db.add_chronicle("gift", "送礼人 送礼给 收礼人：萝卜x3", a, None, conn=conn)
            await db.add_chronicle("gift_inbox", "萝卜x3", a, None, conn=conn)
            await db.add_chronicle("gift", "送礼人 送礼给 路人：萝卜x1", a, None, conn=conn)
            await conn.execute("DELETE FROM world_flags WHERE flag_key=?", (gb.GIFT_TARGET_FLAG,))
            await conn.commit()
        async with db.connect() as conn:
            n = await gb.backfill_gift_targets(conn)
            await conn.commit()
        assert n == 1, "只有正文里点到在册岛民的补上；gift_inbox 正文没有名字，不猜"
        async with db.connect() as conn:
            rows = await (await conn.execute(
                "SELECT action, target_id FROM chronicle WHERE action IN ('gift','gift_inbox') ORDER BY id")).fetchall()
            assert [tuple(r) for r in rows] == [("gift", b), ("gift_inbox", None), ("gift", None)]
            assert (await (await conn.execute("SELECT COUNT(*) FROM world_flags WHERE flag_key=?", (gb.GIFT_TARGET_FLAG,))).fetchone())[0] == 1
        async with db.connect() as conn:
            assert await gb.backfill_gift_targets(conn) == 0, "有标记就不再扫"
        # 读路径不再顺手补：标记已写之后再来一条漏写收礼人的旧纪事，读「收到的礼物」不会改它
        async with db.connect() as conn:
            await db.add_chronicle("gift", "送礼人 送礼给 收礼人：萝卜x9", a, None, conn=conn)
            await conn.commit()
        assert isinstance(await db.list_received_gifts(b, 5), list)
        async with db.connect() as conn:
            row = await (await conn.execute(
                "SELECT target_id FROM chronicle WHERE text LIKE '%萝卜x9%'")).fetchone()
            assert row[0] is None

    asyncio.run(run())


def test_tale_catalog_request_path_is_read_only_when_full() -> None:
    async def run() -> None:
        from server import tale

        db = await _boot(Path(tempfile.mkdtemp(prefix="tale-cat-")))
        async with db.connect() as conn:
            n = (await (await conn.execute("SELECT COUNT(*) FROM tale_catalog")).fetchone())[0]
            assert n == len(tale.TALE_CATALOG), "启动已把目录刷满"
            await conn.commit()
            before = conn.total_changes
            await tale._ensure_catalog(conn)
            assert conn.total_changes == before, "目录是满的，请求路径不许写"
            await conn.execute("DELETE FROM tale_catalog")
            await tale._ensure_catalog(conn)
            n2 = (await (await conn.execute("SELECT COUNT(*) FROM tale_catalog")).fetchone())[0]
            assert n2 == len(tale.TALE_CATALOG), "表被清空时要兜底补回"
            await conn.commit()

    asyncio.run(run())


def test_chronicle_and_market_indexes_exist_and_are_used() -> None:
    async def run() -> None:
        db = await _boot(Path(tempfile.mkdtemp(prefix="idx-")))
        async with db.connect() as conn:
            names = {r[1] for r in await (await conn.execute("PRAGMA index_list(chronicle)")).fetchall()}
            for n in ("idx_chronicle_actor", "idx_chronicle_target", "idx_chronicle_action", "idx_chronicle_created"):
                assert n in names, names
            mk = {r[1] for r in await (await conn.execute("PRAGMA index_list(market_listings)")).fetchall()}
            assert {"idx_market_listings_open", "idx_market_listings_seller"} <= mk
            async def plan(sql: str) -> str:
                return " | ".join(r[3] for r in await (await conn.execute("EXPLAIN QUERY PLAN " + sql)).fetchall())
            assert "idx_chronicle_actor" in await plan("SELECT 1 FROM chronicle WHERE actor_id=1 AND action='voyage' LIMIT 1")
            assert "idx_chronicle_target" in await plan(
                "SELECT text FROM chronicle WHERE target_id=1 AND action IN ('gift','gift_inbox') ORDER BY created_at DESC LIMIT 5")
            assert "idx_chronicle_created" in await plan(
                "SELECT c.*, a.name FROM chronicle c LEFT JOIN stewards a ON a.id=c.actor_id ORDER BY c.created_at DESC LIMIT 40")

    asyncio.run(run())
