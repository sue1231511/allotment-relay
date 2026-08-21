#!/usr/bin/env python3
"""渔排多池：stock/feed/harvest/label 能指定第 2 池。"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def _expect_error(coro, *needles: str) -> str:
    try:
        out = await coro
    except ValueError as exc:
        msg = str(exc)
        for needle in needles:
            assert needle in msg, f"{needle!r} not in {msg!r}"
        return msg
    raise AssertionError(f"expected ValueError, got {out!r}")


def test_slot_parse() -> None:
    from server.marine import _extract_slot_and_rest, _parse_slot_token, _resolve_pen_species

    assert _parse_slot_token("2") == 2
    assert _parse_slot_token("#2") == 2
    assert _parse_slot_token("池2") == 2
    assert _parse_slot_token("pool2") == 2
    assert _parse_slot_token("第2池") == 2
    assert _parse_slot_token("蚯蚓饵") is None
    assert _parse_slot_token("薄荷池") is None

    assert _extract_slot_and_rest(["herring", "2"]) == (2, ["herring"])
    assert _extract_slot_and_rest(["2", "herring"]) == (2, ["herring"])
    assert _extract_slot_and_rest(["herring", "#2"]) == (2, ["herring"])
    assert _extract_slot_and_rest(["sandeel", "2", "1"]) == (2, ["sandeel"])
    assert _extract_slot_and_rest(["2", "sandeel", "2"]) == (2, ["sandeel"])
    assert _extract_slot_and_rest(["herring", "pool2"]) == (2, ["herring"])
    assert _extract_slot_and_rest(["2", "薄荷池"]) == (2, ["薄荷池"])
    assert _extract_slot_and_rest(["蚯蚓饵"]) == (None, ["蚯蚓饵"])

    assert _resolve_pen_species("灰鲱") == "herring"
    assert _resolve_pen_species("fish_herring") == "herring"
    assert _resolve_pen_species("深秋刀") == "deepsaury"
    assert _resolve_pen_species("fish_deepsaury") == "deepsaury"


async def test_pen_ops() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="pen-slot-"))
    os.environ["DATA_DIR"] = str(tmp)
    from server import commons, config, db, events, flavor
    from server import marine

    config.DATA_DIR = tmp
    config.DB_PATH = tmp / "relay.db"
    db.DATA_DIR = tmp
    db.DB_PATH = tmp / "relay.db"
    await db.init_db()

    async def _quiet(*_a, **_k):
        return None

    events.roll_after_action = _quiet  # type: ignore[assignment]
    commons.roll_discovery = _quiet  # type: ignore[assignment]
    flavor.maybe_suffix = lambda *_a, **_k: ""  # type: ignore[assignment]

    api_key = await db.create_api_key("pen-slot@example.com")
    key_row = await db.get_key_row(api_key)
    assert key_row
    kid = key_row["id"]
    await db.enroll_steward(kid, "池测员", "", "naturalist", "")
    async with db.connect() as conn:
        await conn.execute("UPDATE stewards SET tickets=800 WHERE key_id=?", (kid,))
        sid = (await (await conn.execute(
            "SELECT id FROM stewards WHERE key_id=?", (kid,)
        )).fetchone())[0]
        await db.add_item(conn, sid, "compost", 6)
        await conn.commit()

    erected = await marine.pen_ops(kid, "erect")
    assert "渔排就绪" in erected, erected
    expanded = await marine.pen_ops(kid, "expand")
    assert "第 2 池" in expanded, expanded

    stock1 = await marine.pen_ops(kid, "stock herring")
    assert "#1" in stock1 and "灰鲱" in stock1, stock1

    status = await marine.pen_ops(kid, "status")
    assert "#1" in status and "灰鲱" in status, status
    assert "#2: 空池" in status, status

    stock_auto = await marine.pen_ops(kid, "stock sandeel")
    assert "#2" in stock_auto and "沙鳗" in stock_auto, stock_auto

    async with db.connect() as conn:
        await conn.execute(
            "UPDATE fish_pens SET species=NULL, stocked_at=NULL, fed=0 "
            "WHERE steward_id=? AND slot=2",
            (sid,),
        )
        await conn.commit()

    stock_n = await marine.pen_ops(kid, "stock herring 2")
    assert "#2" in stock_n and "灰鲱" in stock_n, stock_n

    async with db.connect() as conn:
        await conn.execute(
            "UPDATE fish_pens SET species=NULL, stocked_at=NULL, fed=0 "
            "WHERE steward_id=? AND slot=2",
            (sid,),
        )
        await conn.commit()

    stock_hash = await marine.pen_ops(kid, "stock herring #2")
    assert "#2" in stock_hash, stock_hash

    async with db.connect() as conn:
        await conn.execute(
            "UPDATE fish_pens SET species=NULL, stocked_at=NULL, fed=0 "
            "WHERE steward_id=? AND slot=2",
            (sid,),
        )
        await conn.commit()

    stock_front = await marine.pen_ops(kid, "stock 2 sandeel")
    assert "#2" in stock_front and "沙鳗" in stock_front, stock_front

    async with db.connect() as conn:
        await conn.execute(
            "UPDATE fish_pens SET species=NULL, stocked_at=NULL, fed=0 "
            "WHERE steward_id=? AND slot=2",
            (sid,),
        )
        await conn.commit()

    stock_cn = await marine.pen_ops(kid, "stock #2 沙鳗")
    assert "#2" in stock_cn and "沙鳗" in stock_cn, stock_cn

    async with db.connect() as conn:
        await conn.execute(
            "UPDATE fish_pens SET species=NULL, stocked_at=NULL, fed=0 "
            "WHERE steward_id=? AND slot=2",
            (sid,),
        )
        await conn.commit()

    stock_qty = await marine.pen_ops(kid, "stock sandeel 2 1")
    assert "#2" in stock_qty and "沙鳗" in stock_qty, stock_qty

    await _expect_error(marine.pen_ops(kid, "stock herring 2"), "已有鱼苗", "#2")
    await _expect_error(marine.pen_ops(kid, "stock 2 herring"), "已有鱼苗")

    await _expect_error(
        marine.pen_ops(kid, "stock 深秋刀"),
        "深秋刀",
        "不能投进渔排",
        "tote_ops vend fish_deepsaury",
        "kitchen_ops eat fish_deepsaury",
    )
    await _expect_error(
        marine.pen_ops(kid, "stock fish_deepsaury"),
        "不能投进渔排",
        "卖掉或吃掉",
    )

    label_bare = await _expect_error(marine.pen_ops(kid, "label"), "用法: pen label")
    assert "未知 pen 指令" not in label_bare

    named = await marine.pen_ops(kid, "label 2 薄荷池")
    assert "薄荷池" in named and "#2" in named, named
    status2 = await marine.pen_ops(kid, "status")
    assert "#2 薄荷池" in status2, status2
    assert "#1" in status2 and "灰鲱" in status2
    assert ": 2 薄荷池" not in status2

    feed2 = await marine.pen_ops(kid, "feed 2")
    assert "#2" in feed2 and "沙鳗" in feed2, feed2
    already = await marine.pen_ops(kid, "feed 2")
    assert "今日已投饵" in already and "#2" in already, already

    feed1 = await marine.pen_ops(kid, "feed 蚯蚓饵")
    assert "#1" in feed1 and "灰鲱" in feed1, feed1

    await _expect_error(marine.pen_ops(kid, "harvest 2"), "#2 薄荷池", "尚未长成")
    await _expect_error(marine.pen_ops(kid, "harvest 1"), "#1", "尚未长成")

    async with db.connect() as conn:
        await conn.execute(
            "UPDATE fish_pens SET stocked_at=? WHERE steward_id=? AND slot=2",
            (db.now() - 100_000, sid),
        )
        await conn.commit()

    harvested = await marine.pen_ops(kid, "harvest 2")
    assert "#2" in harvested and "沙鳗" in harvested, harvested
    status3 = await marine.pen_ops(kid, "status")
    assert "#2 薄荷池: 空池" in status3, status3
    assert "灰鲱" in status3


def main() -> None:
    test_slot_parse()
    asyncio.run(test_pen_ops())
    print("pen slot tests ok")


if __name__ == "__main__":
    main()
