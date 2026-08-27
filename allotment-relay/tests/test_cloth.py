#!/usr/bin/env python3
"""衣泊坊：委托→取→穿、季节加减、衣物故事、纤维拒下锅、不卖成衣。"""
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


async def _stock(db, sid: int, *pairs: tuple[str, int]) -> None:
    async with db.connect() as conn:
        for item, qty in pairs:
            await db.add_item(conn, sid, item, qty)
        await conn.commit()


async def _energy(db, sid: int) -> int:
    async with db.connect() as conn:
        row = await (await conn.execute(
            "SELECT energy FROM stewards WHERE id=?", (sid,)
        )).fetchone()
    return int(row[0])


def test_wear_energy_delta() -> None:
    from server import cloth

    assert cloth.wear_energy_delta("jacket", "cloth_sun", "夏") == -1
    assert cloth.wear_energy_delta("coat", "cloth_frost", "冬") == -1
    assert cloth.wear_energy_delta("coat", "cloth_frost", "夏") == 1
    assert cloth.wear_energy_delta("skirt", "cloth_drift", "冬") == 1
    assert cloth.wear_energy_delta("robe", "cloth_old", "夏") == 0


def test_help_and_empty() -> None:
    asyncio.run(_test_help_and_empty())


async def _test_help_and_empty() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="cloth-help-"))
    db = await _boot(tmp)
    from server import cloth

    kid, _ = await _enroll(db, "cloth-help@example.com", "裁衣甲")
    empty = await cloth.cloth_ops(kid, "")
    help_text = await cloth.cloth_ops(kid, "help")
    assert empty == help_text
    assert "空 command" in empty
    assert "不是看坊" in empty
    assert "漾漾" in empty
    assert "不卖成衣" in empty
    assert "不绝版" in empty
    assert "委托 短褂 海色" in empty
    assert "台上：" not in empty
    assert "tale_ops" in empty
    assert "forage" in empty or "边际" in empty
    assert "NPC/潮闻" not in empty

    status = await cloth.cloth_ops(kid, "status")
    assert "衣泊坊" in status and "漾漾" in status
    assert "台上" in status
    catalog = await cloth.cloth_ops(kid, "图鉴")
    assert "不绝版" in catalog
    assert "梅雨" in catalog and "盛夏" in catalog
    assert "台风季" in catalog and "冬潮" in catalog

    try:
        await cloth.cloth_ops(kid, "买衣服")
        raise AssertionError("buy finished clothes should fail")
    except ValueError as exc:
        assert "不要发明" in str(exc) or "未知" in str(exc), exc


def test_sew_claim_wear() -> None:
    asyncio.run(_test_sew_claim_wear())


async def _test_sew_claim_wear() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="cloth-sew-"))
    db = await _boot(tmp)
    from server import cloth, kitchen, game

    kid, sid = await _enroll(db, "cloth-sew@example.com", "裁衣乙")
    await _stock(db, sid, ("cloth_drift", 4), ("dye_sea", 2), ("cloth_old", 2), ("dye_ink", 1))

    sewn = await cloth.cloth_ops(kid, "委托 短褂 海色")
    assert "海色短褂" in sewn and "取" in sewn, sewn
    try:
        await cloth.cloth_ops(kid, "取")
        raise AssertionError("claim before ready should fail")
    except ValueError as exc:
        assert "还在裁" in str(exc), exc

    async with db.connect() as conn:
        await conn.execute(
            "UPDATE steward_atelier SET job_ready_at=1 WHERE steward_id=?", (sid,)
        )
        await conn.commit()
    claimed = await cloth.cloth_ops(kid, "取")
    assert "进衣橱" in claimed and "不能卖" in claimed, claimed
    assert "海色短褂" in claimed, claimed

    wardrobe = await cloth.cloth_ops(kid, "衣橱")
    assert "海色短褂" in wardrobe, wardrobe
    worn = await cloth.cloth_ops(kid, "穿 1")
    assert "换上" in worn and "海色短褂" in worn, worn
    off = await cloth.cloth_ops(kid, "脱")
    assert "脱下" in off, off

    story_job = await cloth.cloth_ops(kid, "委托 呢衣 墨色 旧衣料")
    assert "灯塔守夜人的旧呢衣" in story_job, story_job
    async with db.connect() as conn:
        await conn.execute(
            "UPDATE steward_atelier SET job_ready_at=1 WHERE steward_id=?", (sid,)
        )
        satchel = await (await conn.execute(
            "SELECT item FROM satchel WHERE steward_id=? AND item LIKE 'garment%'",
            (sid,),
        )).fetchall()
        await conn.commit()
    assert not satchel, satchel
    story_claim = await cloth.cloth_ops(kid, "取")
    assert "灯塔守夜人的旧呢衣" in story_claim, story_claim
    await cloth.cloth_ops(kid, "穿 灯塔守夜人的旧呢衣")

    async with db.connect() as conn:
        s = await db.get_steward_by_id(sid)
        echo = await cloth.try_echo(conn, s, "lighthouse")
        await conn.commit()
    assert "不醒" in echo and "衣物来历已记下" in echo, echo
    again = ""
    async with db.connect() as conn:
        s = await db.get_steward_by_id(sid)
        again = await cloth.try_echo(conn, s, "lighthouse", silent=True)
        await conn.commit()
    assert again == "", again
    stories = await cloth.cloth_ops(kid, "故事")
    assert "灯油与呢衣" in stories or "灯塔守夜人的旧呢衣" in stories, stories

    try:
        await game.tote_ops(kid, "vend 灯塔守夜人的旧呢衣 1")
        raise AssertionError("finished clothes should not vend")
    except ValueError as exc:
        assert "无法识别" in str(exc) or "未知" in str(exc) or "没有" in str(exc), exc

    await _stock(db, sid, ("crop_cotton", 2))
    try:
        await kitchen.kitchen_ops(kid, "eat 潮棉")
        raise AssertionError("fiber should not be eaten")
    except ValueError as exc:
        assert "衣料" in str(exc), exc
    try:
        await kitchen.kitchen_ops(kid, "cook 潮棉 甘蓝")
        raise AssertionError("fiber should not be cooked")
    except ValueError as exc:
        assert "衣料" in str(exc), exc


def test_season_energy_and_duty() -> None:
    asyncio.run(_test_season_energy_and_duty())


async def _test_season_energy_and_duty() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="cloth-energy-"))
    db = await _boot(tmp)
    from server import cloth, energy, season as season_mod

    kid, sid = await _enroll(db, "cloth-en@example.com", "裁衣丙")
    async with db.connect() as conn:
        await cloth.ensure_profile(conn, sid)
        cur = await conn.execute(
            """
            INSERT INTO steward_wardrobe (
                steward_id, cut_key, color_key, motif_key, fabric_key, story_key,
                name, origin, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (sid, "coat", "ink", "plain", "cloth_frost", "", "冬潮呢衣", "", db.now()),
        )
        gid = int(cur.lastrowid or 0)
        await conn.execute(
            "UPDATE steward_atelier SET worn_id=? WHERE steward_id=?", (gid, sid)
        )
        await conn.commit()

    old_season = season_mod.current_season
    try:
        season_mod.current_season = lambda: "冬"
        before = await _energy(db, sid)
        async with db.connect() as conn:
            await energy.spend(conn, sid, 10, action="试穿")
            await conn.commit()
        after = await _energy(db, sid)
        assert before - after == 9, (before, after)

        season_mod.current_season = lambda: "夏"
        before = await _energy(db, sid)
        async with db.connect() as conn:
            await energy.spend(conn, sid, 10, action="试穿")
            await conn.commit()
        after = await _energy(db, sid)
        assert before - after == 11, (before, after)

        async with db.connect() as conn:
            await conn.execute(
                "UPDATE steward_atelier SET worn_id=0 WHERE steward_id=?", (sid,)
            )
            await conn.commit()
        before = await _energy(db, sid)
        async with db.connect() as conn:
            await energy.spend(conn, sid, 10, action="试穿")
            await conn.commit()
        after = await _energy(db, sid)
        assert before - after == 10, (before, after)
    finally:
        season_mod.current_season = old_season

    async with db.connect() as conn:
        await conn.execute(
            "UPDATE stewards SET last_bar_shift_at=1 WHERE id=?", (sid,)
        )
        await conn.commit()
    await _stock(db, sid, ("cloth_drift", 2), ("dye_sea", 1))
    try:
        await cloth.cloth_ops(kid, "委托 短褂 海色")
        raise AssertionError("overdue duty should lock sew")
    except ValueError as exc:
        assert "上工" in str(exc) or "打卡" in str(exc), exc
    closet = await cloth.cloth_ops(kid, "衣橱")
    assert "衣橱" in closet or "冬潮呢衣" in closet, closet
    worn = await cloth.cloth_ops(kid, f"穿 {gid}")
    assert "换上" in worn, worn


def test_mcp_description() -> None:
    from server.mcp_app import mcp

    tool = mcp._tool_manager.get_tool("cloth_ops")
    blob = (
        f"{tool.description}\n"
        f"{(tool.parameters.get('properties') or {}).get('command', {}).get('description', '')}"
    )
    for word in ("漾漾", "委托 短褂 海色", "看坊", "tailor_ops"):
        assert word in blob, word


def test_fiber_flags() -> None:
    from server.catalog import is_fiber_item, is_vegetable_item, resolve_item_key

    assert resolve_item_key("潮棉") == "crop_cotton"
    assert resolve_item_key("岸麻") == "crop_hemp"
    assert resolve_item_key("漂布") == "cloth_drift"
    assert resolve_item_key("海色染料") == "dye_sea"
    assert is_fiber_item("crop_cotton")
    assert is_fiber_item("cloth_drift")
    assert not is_vegetable_item("crop_cotton")
    assert is_vegetable_item("crop_kale")


def main() -> None:
    test_wear_energy_delta()
    test_fiber_flags()
    test_mcp_description()
    test_help_and_empty()
    test_sew_claim_wear()
    test_season_energy_and_duty()
    print("cloth tests ok")


if __name__ == "__main__":
    main()
