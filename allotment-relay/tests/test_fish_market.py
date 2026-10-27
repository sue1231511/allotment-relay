#!/usr/bin/env python3
"""渔市行情 — 供给压力调价、行情牌、韶年卦象、vend 端到端。"""
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


def test_fish_market() -> None:
    asyncio.run(_test_fish_market())


async def _test_fish_market() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="fish-market-"))
    db = await _boot(tmp)
    from server import fish_market
    from server.catalog import suggested_price

    mack = "fish_mackerel"
    base = int(suggested_price(mack))
    assert base > 0
    norm = fish_market.week_norm(base)
    assert fish_market.week_norm(6) > fish_market.week_norm(80), "便宜鱼吸收量应更大"

    kid, sid = await _enroll(db, "fish@example.com", "渔人")

    async with db.connect() as conn:
        # 无流量：轻稀缺溢价顶格
        mult, note = await fish_market.mult_for(conn, mack)
        assert mult == 1.20 and note == "稀少看涨", (mult, note)

        # 灌到一倍 norm：平价
        await fish_market.record_sale(conn, mack, norm)
        mult, note = await fish_market.mult_for(conn, mack)
        assert abs(mult - 1.0) < 0.01 and note == "", (mult, note)

        # record_sale 聚合（第二次累加），3 倍 norm 跌停
        await fish_market.record_sale(conn, mack, norm * 2)
        mult, note = await fish_market.mult_for(conn, mack)
        assert mult == 0.65 and "走低" in note, (mult, note)

        # 非海产不受影响
        mult, note = await fish_market.mult_for(conn, "crop_kale")
        assert mult == 1.0 and note == "", (mult, note)

        # 行情牌与韶年卦象能渲染
        board = await fish_market.market_board(conn)
        assert "渔市行情" in board and "鲭鱼" in board, board
        hint = await fish_market.fortune_hint(conn)
        assert "渔市卦象" in hint and "鲭鱼" in hint, hint
        await conn.commit()

    # vend 端到端：行情 0.65 折进回收价
    from server.game import tote

    async with db.connect() as conn:
        tickets0 = (await (await conn.execute(
            "SELECT tickets FROM stewards WHERE id=?", (sid,)
        )).fetchone())[0]
        await db.add_item(conn, sid, mack, 1)
        await db.add_item(conn, sid, "crop_kale", 1)
        await conn.commit()
    msg = await tote.tote_ops(kid, f"vend 鲭鱼 1")
    assert "鲭鱼" in msg and "走低" in msg, msg
    async with db.connect() as conn:
        tickets = (await (await conn.execute(
            "SELECT tickets FROM stewards WHERE id=?", (sid,)
        )).fetchone())[0]
    assert tickets == tickets0 + max(1, int(base * 0.65)), (tickets, tickets0, base)

    # 潮生会行情子命令
    from server import chaoshen

    board = await chaoshen.chaoshen_ops(kid, "行情")
    assert "渔市行情" in board, board


if __name__ == "__main__":
    test_fish_market()
    print("ok")
