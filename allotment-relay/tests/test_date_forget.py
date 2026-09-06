#!/usr/bin/env python3
"""companion_date forget removes ended date memories only."""
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


async def _enroll(db, email: str, name: str) -> tuple[int, int]:
    key = await db.create_api_key(email)
    row = await db.get_key_row(key)
    await db.enroll_steward(row["id"], name, "", "naturalist", "")
    async with db.connect() as conn:
        sid = (await (await conn.execute(
            "SELECT id FROM stewards WHERE key_id=?", (row["id"],)
        )).fetchone())[0]
        await conn.execute("UPDATE stewards SET tickets=5000 WHERE id=?", (sid,))
        await conn.commit()
    return row["id"], sid


def test_date_forget() -> None:
    asyncio.run(_test_date_forget())


async def _test_date_forget() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="date-forget-"))
    db = await _boot(tmp)
    from server import companion_date, memory_archive

    kid, sid = await _enroll(db, "d@example.com", "约会人")
    now = db.now()
    state = '{"history":[{"title":"一幕","narrative":"测试旁白","options":[]}],"seq":1,"kind_label":"约会","partner":"人类","seen":[]}'
    async with db.connect() as conn:
        for i, status in enumerate(("exited", "completed", "completed"), start=1):
            await conn.execute(
                """
                INSERT INTO companion_dates(
                  steward_id, place, title, token_hash, expires_at, state_json,
                  special, total_spent, status, completed_at, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    sid, "小馆", f"测试约会{i}", f"tok{i}", now + 86400, state,
                    0, 100 if i == 3 else 10, status, now, now, now,
                ),
            )
        await conn.commit()
        ids = [r[0] for r in await (await conn.execute(
            "SELECT id FROM companion_dates WHERE steward_id=? ORDER BY id", (sid,)
        )).fetchall()]

    keep = ids[2]
    for drop in ids[:2]:
        msg = await companion_date.forget(sid, drop)
        assert f"#{drop}" in msg, msg

    blocked = False
    async with db.connect() as conn:
        await conn.execute(
            """
            INSERT INTO companion_dates(
              steward_id, place, title, token_hash, expires_at, state_json,
              special, total_spent, status, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (sid, "灯塔", "进行中", "live", now + 86400, "{}", 0, 198, "active", now, now),
        )
        await conn.commit()
        live_id = (await (await conn.execute(
            "SELECT id FROM companion_dates WHERE status='active' AND steward_id=?",
            (sid,),
        )).fetchone())[0]
    try:
        await companion_date.forget(sid, live_id)
    except ValueError as exc:
        blocked = "进行" in str(exc) or "应邀" in str(exc)
    assert blocked

    async with db.connect() as conn:
        left = await (await conn.execute(
            "SELECT id, status FROM companion_dates WHERE steward_id=? ORDER BY id",
            (sid,),
        )).fetchall()
    assert {r[0] for r in left} == {keep, live_id}

    async with db.connect() as conn:
        mems = await memory_archive.list_memories(conn, sid)
    date_keys = {m["key"] for m in mems if m["kind"] == "date"}
    assert str(keep) in date_keys
    assert str(ids[0]) not in date_keys


if __name__ == "__main__":
    test_date_forget()
