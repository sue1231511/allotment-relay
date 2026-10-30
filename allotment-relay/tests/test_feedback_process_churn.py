#!/usr/bin/env python3
"""反馈：网页搅羊奶份数被吃掉；craft help 漏配方；proc_ 加工品没有产出途径。"""
from __future__ import annotations

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
        await conn.execute(
            "UPDATE stewards SET last_bar_shift_at=?, energy=100, tickets=800, "
            "hut_built=1, hut_level=2, barn_built=1 WHERE id=?",
            (db.now(), sid),
        )
        await conn.commit()
    return row["id"], sid


async def _qty(db, sid: int, item: str) -> int:
    async with db.connect() as conn:
        row = await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item=?",
            (sid, item),
        )).fetchone()
    return int(row[0] if row else 0)


async def _give(db, sid: int, item: str, qty: int) -> None:
    async with db.connect() as conn:
        await db.add_item(conn, sid, item, qty)
        await conn.commit()


async def _expect_error(coro) -> str:
    try:
        out = await coro
    except ValueError as exc:
        return str(exc)
    raise AssertionError(f"expected error, got: {out}")


def test_web_qty_targets_parse_last_number() -> None:
    from server.v1 import hut_service

    # 前端弹份数框后拼出「<旧target> <份数>」；纯数字 target 也不能把份数吃掉
    assert hut_service._command("barn_churn", "6 3") == ("barn", "churn 3")
    assert hut_service._command("barn_churn", "4") == ("barn", "churn 4")
    assert hut_service._command("barn_churn", "") == ("barn", "churn 2")
    assert hut_service._command("expand", "1 3") == ("hut", "潮柜 扩 3")
    assert hut_service._command("expand", "") == ("hut", "潮柜 扩 1")
    assert hut_service._command("compost_take", "6 3") == ("hut", "堆肥桶 取 堆肥 3")
    assert hut_service._command("compost_take", "6") == ("hut", "堆肥桶 取 堆肥 6")
    assert hut_service._command("compost_take", "") == ("hut", "堆肥桶 取 堆肥")


async def test_churn_uses_requested_milk() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="churn-qty-"))
    db = await _boot(tmp)
    kid, sid = await _enroll(db, "churn@example.com", "搅奶人")
    from server import barn

    await _give(db, sid, "goat_milk", 8)
    out = await barn.barn_ops(kid, "churn 4")
    assert "山羊奶 x4" in out and "x2" in out, out
    assert await _qty(db, sid, "goat_milk") == 4
    assert await _qty(db, sid, "goat_cheese") == 2
    bad = await _expect_error(barn.barn_ops(kid, "churn 大量"))
    assert "份数" in bad, bad


def test_craft_help_and_catalog_list_every_recipe() -> None:
    from server import craft
    from server.catalog import CRAFT_RECIPES, PROCESS_RECIPES

    help_txt = craft.CRAFT_HELP
    catalog = craft._catalog_text()
    for meta in CRAFT_RECIPES.values():
        assert f"打 {meta['name']}" in help_txt, meta["name"]
        assert meta["name"] in catalog, meta["name"]
    for meta in PROCESS_RECIPES.values():
        assert f"加工 {meta['name']}" in help_txt, meta["name"]
        assert meta["name"] in catalog, meta["name"]


def test_every_proc_item_and_dish_is_obtainable() -> None:
    from server import catalog
    from server.undertide_refine import RECIPES as REFINE

    producers: dict[str, dict[str, int]] = {}
    for meta in catalog.CRAFT_RECIPES.values():
        producers.setdefault(meta["out"], meta["need"])
    for meta in catalog.PROCESS_RECIPES.values():
        producers.setdefault(meta["out"], meta["need"])
    for meta in REFINE.values():
        out_item, _qty_out = meta["out"]
        producers.setdefault(out_item, {i: q for i, q in meta["ings"]})

    reachable: set[str] = set()
    for _ in range(8):
        for out, need in producers.items():
            if all(not k.startswith("proc_") or k in reachable for k in need):
                reachable.add(out)
    procs = {k for k in catalog.ITEM_NAMES if k.startswith("proc_")}
    assert not (procs - reachable), f"没有产出途径的加工品: {sorted(procs - reachable)}"
    stuck = {
        key: [i for i in meta["ings"] if i.startswith("proc_") and i not in reachable]
        for key, meta in catalog.KITCHEN_DISHES.items()
    }
    stuck = {k: v for k, v in stuck.items() if v}
    assert not stuck, f"做不出来的定点菜: {stuck}"


def test_process_recipes_never_print_money() -> None:
    from server import catalog

    for key, meta in catalog.PROCESS_RECIPES.items():
        cost = sum(catalog.ITEM_PRICES.get(i, 0) * q for i, q in meta["need"].items())
        got = catalog.ITEM_PRICES.get(meta["out"], 0) * int(meta["qty"])
        assert got <= 2 * cost, (key, cost, got)
        assert meta["out"] in catalog.ITEM_NAMES, key
        for item in meta["need"]:
            assert item in catalog.ITEM_NAMES, (key, item)


async def test_process_flow() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="process-flow-"))
    db = await _boot(tmp)
    kid, sid = await _enroll(db, "proc@example.com", "磨坊人")
    from server import craft

    listing = await craft.craft_ops(kid, "加工")
    assert "面粉" in listing and "细盐" in listing, listing

    miss = await _expect_error(craft.craft_ops(kid, "加工 面粉 2"))
    assert "缺材料" in miss and "小麦" in miss, miss

    await _give(db, sid, "crop_wheat", 6)
    out = await craft.craft_ops(kid, "加工 面粉 2")
    assert "面粉" in out and "x4" in out, out
    assert await _qty(db, sid, "crop_wheat") == 2
    assert await _qty(db, sid, "proc_flour") == 4

    # 不占砧：加工之后砧上仍能开打
    await _give(db, sid, "quarry_copper_bar", 1)
    await _give(db, sid, "drift_twine", 1)
    started = await craft.craft_ops(kid, "打 铜钉")
    assert "开打" in started, started
    # 内部键名也认；这批用掉剩下的 2 小麦 → 面粉共 6
    again = await craft.craft_ops(kid, "加工 proc_flour")
    assert "面粉" in again, again
    assert await _qty(db, sid, "proc_flour") == 6

    # 链：先加工面粉才有面条
    noodles = await craft.craft_ops(kid, "加工 面条 2")
    assert await _qty(db, sid, "proc_noodles") == 2
    assert await _qty(db, sid, "proc_flour") == 2, noodles

    await _give(db, sid, "crop_rice", 2)
    await craft.craft_ops(kid, "加工 米酒")
    await craft.craft_ops(kid, "加工 醋")
    assert await _qty(db, sid, "proc_vinegar") == 2

    too_many = await _expect_error(craft.craft_ops(kid, "加工 面粉 99"))
    assert "批数" in too_many, too_many
    unknown = await _expect_error(craft.craft_ops(kid, "加工 山羊奶酪"))
    assert "山羊奶酪" in unknown and "churn" in unknown, unknown

    await _give(db, sid, "quarry_salt", 1)
    await craft.craft_ops(kid, "加工 细盐")
    assert await _qty(db, sid, "proc_salt") == 2


async def test_process_energy_and_view() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="process-view-"))
    db = await _boot(tmp)
    kid, sid = await _enroll(db, "procv@example.com", "看台人")
    from server import craft
    from server.v1 import workshop_service

    await _give(db, sid, "crop_wheat", 2)
    async with db.connect() as conn:
        s = await (await conn.execute("SELECT * FROM stewards WHERE id=?", (sid,))).fetchone()
        cols = [c[0] for c in (await conn.execute("SELECT * FROM stewards LIMIT 0")).description]
        s = dict(zip(cols, s))
        view = await craft.player_view(conn, s)
    rows = {r["name"]: r for r in view["process"]}
    assert rows["面粉"]["can_process"] is True, rows["面粉"]
    assert rows["大米"]["can_process"] is False and "缺" in rows["大米"]["note"]
    assert any(t["key"] == "process" for t in view["tabs"])
    assert workshop_service._command("process", "面粉 2") == "加工 面粉 2"

    async with db.connect() as conn:
        await conn.execute("UPDATE stewards SET energy=0 WHERE id=?", (sid,))
        await conn.commit()
    tired = await _expect_error(craft.craft_ops(kid, "加工 面粉"))
    assert "精力" in tired, tired
    assert await _qty(db, sid, "crop_wheat") == 2
    assert await _qty(db, sid, "proc_flour") == 0


def test_lili_pool_has_no_processed_goods() -> None:
    from server import lili_catalog

    for domain, pool in lili_catalog.DOMAIN_POOLS.items():
        bad = [item for item, _p, _t in pool if item.startswith("proc_")]
        assert not bad, (domain, bad)
