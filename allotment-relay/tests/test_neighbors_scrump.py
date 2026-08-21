#!/usr/bin/env python3
"""邻居名册、在线名单、手动偷菜。"""
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
    return row["id"], sid


async def test_neighbors_and_scrump() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="neighbors-"))
    db = await _boot(tmp)
    from server import events, multi

    thief_kid, thief_sid = await _enroll(db, "thief@example.com", "邻甲")
    vic_kid, vic_sid = await _enroll(db, "vic@example.com", "邻乙")

    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET last_active_at=? WHERE id=?",
            (db.now() - 4000, vic_sid),
        )
        await conn.execute(
            """
            UPDATE parcels SET crop='kale', planted_at=?, tended=1, greenhouse=0,
            grow_target=120 WHERE steward_id=? AND slot=1
            """,
            (db.now() - 10_000, vic_sid),
        )
        await conn.commit()

    thief = await db.get_steward_by_id(thief_sid)
    roster = await multi.list_neighbors(thief, online_only=False)
    assert "邻乙" in roster, roster
    assert "熟地" in roster, roster
    assert "plot_ops 偷菜 邻乙" in roster, roster

    online = await multi.list_neighbors(thief, online_only=True)
    assert "邻乙" not in online or "没有别人" in online or "全员邻居" in online

    # 对方不在档口：强制得手
    events.random.random = lambda: 0.99  # type: ignore[method-assign]
    msg = await events.manual_scrump(thief, "邻乙", 1)
    assert "入袋" in msg and "羽衣甘蓝" in msg, msg
    async with db.connect() as conn:
        qty = (await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item='crop_kale'",
            (thief_sid,),
        )).fetchone())
        assert qty and qty[0] >= 1, qty
        crop = (await (await conn.execute(
            "SELECT crop FROM parcels WHERE steward_id=? AND slot=1",
            (vic_sid,),
        )).fetchone())[0]
        assert crop in (None, ""), crop

    from server import game as game_mod
    empty = await game_mod.plot_ops(thief_kid, "邻居")
    assert "邻乙" in empty, empty

    online_cmd = await game_mod.plot_ops(thief_kid, "在线")
    assert "档口" in online_cmd, online_cmd

    # 同一人当天不能再摘
    try:
        await events.manual_scrump(thief, "邻乙")
        raise AssertionError("expected daily per-target limit")
    except ValueError as exc:
        assert "已经摘过" in str(exc), exc


def main() -> None:
    asyncio.run(test_neighbors_and_scrump())
    print("neighbors/scrump tests ok")


if __name__ == "__main__":
    main()
