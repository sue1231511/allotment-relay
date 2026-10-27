#!/usr/bin/env python3
"""许愿墙公投 — 点亮（每号每条一次）+ 周榜挂潮生会告示。"""
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


def test_wish_spark() -> None:
    asyncio.run(_test_wish_spark())


async def _test_wish_spark() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="wish-spark-"))
    db = await _boot(tmp)
    from server import lounge
    from server.disaster import cst_week_start

    akid, asid = await _enroll(db, "a@example.com", "许愿人")
    bkid, bsid = await _enroll(db, "b@example.com", "点亮人")

    # 许愿 + 反馈各一条（贴墙有 60 秒冷却，两人各贴一条）
    await lounge.post_board_item(asid, "wish", "想加钓鱼大赛", source="mcp")
    await lounge.post_board_item(bsid, "feedback", "按钮没反应", source="mcp")
    async with db.connect() as conn:
        conn.row_factory = __import__("aiosqlite").Row
        rows = await (await conn.execute(
            "SELECT id, kind FROM lounge_board ORDER BY id"
        )).fetchall()
    wish_id = next(int(r["id"]) for r in rows if r["kind"] == "wish")
    feed_id = next(int(r["id"]) for r in rows if r["kind"] == "feedback")

    # 点亮：每号每条一次；重复拒；反馈墙不点亮
    result = await lounge.spark_board_item(bsid, wish_id)
    assert result["sparks"] == 1, result
    try:
        await lounge.spark_board_item(bsid, wish_id)
        raise AssertionError("重复点亮应被拒")
    except ValueError as exc:
        assert "一次" in str(exc), exc
    await lounge.spark_board_item(asid, wish_id)
    try:
        await lounge.spark_board_item(bsid, feed_id)
        raise AssertionError("反馈墙不能点亮")
    except ValueError as exc:
        assert "反馈墙" in str(exc), exc

    # MCP 点亮路由通（重复点亮按惯例抛错）。注意：这里不读墙，
    # 周榜是「上周窗口」结算，先把愿望挪到上周再第一次读墙触发
    try:
        await lounge.lounge_ops(bkid, f"点亮 {wish_id}")
        raise AssertionError("重复点亮应报错")
    except ValueError as exc:
        assert "已经点亮过" in str(exc), exc
    try:
        await lounge.lounge_ops(bkid, "点亮 99999")
        raise AssertionError("不存在 的愿望应报错")
    except ValueError as exc:
        assert "没有 #99999" in str(exc), exc

    # 周榜：把许愿挪到上周窗口，第一次读墙触发惰性结算
    this_monday = cst_week_start()
    last_monday = this_monday - 7 * 86400
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE lounge_board SET created_at=? WHERE id=?", (last_monday + 3600, wish_id)
        )
        await conn.commit()
    text = await lounge.lounge_ops(bkid, "许愿墙")
    assert "✦2" in text, text
    async with db.connect() as conn:
        conn.row_factory = __import__("aiosqlite").Row
        notice = await (await conn.execute(
            "SELECT tag, body FROM hui_notices WHERE tag=? ORDER BY id DESC",
            (lounge.SPARK_WEEK_TAG,),
        )).fetchone()
        flag = await (await conn.execute(
            "SELECT COUNT(*) FROM world_flags WHERE flag_key LIKE 'wish_top_%'"
        )).fetchone()
    assert notice is not None, "周榜告示没挂上潮生会"
    assert "钓鱼大赛" in notice["body"] and "2 次点亮" in notice["body"], notice["body"]
    assert flag[0] == 1, flag

    # 再读墙不重复发榜
    await lounge.list_board_items(kind="wish")
    async with db.connect() as conn:
        n = (await (await conn.execute(
            "SELECT COUNT(*) FROM hui_notices WHERE tag=?",
            (lounge.SPARK_WEEK_TAG,),
        )).fetchone())[0]
    assert n == 1, n


if __name__ == "__main__":
    test_wish_spark()
    print("ok")
