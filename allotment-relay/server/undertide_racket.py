"""后室铺收账鬼 — 黑市强买强卖 AI（阿标）。"""

from __future__ import annotations

import json
import random
from typing import Any

import aiosqlite

from . import db
from . import undertide_catalog as cat
from . import undertide_config as utcfg
from . import undertide_copy as utcopy


ENFORCER_NAME = "收账鬼阿标"
RACKET_KINDS = ("buy", "sell")


def _day_id() -> int:
    return db.day_id()


def _item_label(item_key: str) -> str:
    base = item_key[3:] if item_key.startswith("ut_") else item_key
    meta = cat.RARE_GOODS.get(base) or cat.COMMON_GOODS.get(base) or {}
    return meta.get("name") or base


def _vend(item_key: str) -> int:
    base = item_key[3:] if item_key.startswith("ut_") else item_key
    meta = cat.RARE_GOODS.get(base) or cat.COMMON_GOODS.get(base) or {}
    return int(meta.get("vend", 12))


async def _load_deal(conn: aiosqlite.Connection, steward_id: int) -> tuple[int, dict[str, Any] | None]:
    conn.row_factory = aiosqlite.Row
    row = await (await conn.execute(
        "SELECT racket_day, racket_json FROM steward_undertide WHERE steward_id=?",
        (steward_id,),
    )).fetchone()
    if not row:
        return 0, None
    day = int(row["racket_day"] or 0)
    raw = (row["racket_json"] or "").strip()
    if not raw:
        return day, None
    try:
        return day, json.loads(raw)
    except json.JSONDecodeError:
        return day, None


async def _save_deal(conn: aiosqlite.Connection, steward_id: int, day: int, deal: dict[str, Any]) -> None:
    await conn.execute(
        "UPDATE steward_undertide SET racket_day=?, racket_json=? WHERE steward_id=?",
        (day, json.dumps(deal, ensure_ascii=False), steward_id),
    )


async def ensure_racket_deal(
    conn: aiosqlite.Connection, steward_id: int, *, force: bool = False
) -> dict[str, Any] | None:
    """每日一笔强买/强卖；已成交则返回 None。"""
    day = _day_id()
    saved_day, deal = await _load_deal(conn, steward_id)
    if saved_day == day and deal:
        if deal.get("done"):
            return None
        return deal
    if saved_day == day and not force:
        return None

    rng = random.Random(day * 31337 + steward_id)
    if rng.random() > utcfg.UT_RACKET_CHANCE and not force:
        await _save_deal(conn, steward_id, day, {"done": 1, "skipped": True})
        return None

    kind = rng.choice(RACKET_KINDS)
    keys = list(cat.COMMON_GOODS.keys())
    if rng.random() < 0.12 and cat.RARE_GOODS:
        keys = list(cat.RARE_GOODS.keys())
    item_base = rng.choice(keys)
    item_key = f"ut_{item_base}"
    qty = 1
    vend = _vend(item_key)
    if kind == "buy":
        price = max(8, int(vend * utcfg.UT_RACKET_BUY_MULT))
        deal = {
            "kind": "buy",
            "item": item_key,
            "qty": qty,
            "price": price,
            "done": 0,
            "label": _item_label(item_key),
        }
    else:
        price = max(3, int(vend * utcfg.UT_RACKET_SELL_MULT))
        deal = {
            "kind": "sell",
            "item": item_key,
            "qty": qty,
            "price": price,
            "done": 0,
            "label": _item_label(item_key),
        }
    await _save_deal(conn, steward_id, day, deal)
    return deal


def format_racket_line(deal: dict[str, Any] | None) -> str:
    if not deal:
        return f"  🗡️ {ENFORCER_NAME}：今天没盯上你（或已结清）。"
    if deal.get("skipped"):
        return ""
    if deal.get("kind") == "buy":
        return (
            f"  🗡️ {ENFORCER_NAME}：强卖给你 {deal['label']} x{deal['qty']} — "
            f"{deal['price']} 票（undertide_ops racket accept|refuse）"
        )
    return (
        f"  🗡️ {ENFORCER_NAME}：强收你的 {deal['label']} x{deal['qty']} — "
        f"出价 {deal['price']} 票（undertide_ops racket accept|refuse）"
    )


def format_racket_detail(deal: dict[str, Any]) -> str:
    if deal.get("kind") == "buy":
        body = utcopy.pick(utcopy.RACKET_FORCE_BUY).format(
            name=ENFORCER_NAME,
            item=deal["label"],
            qty=deal["qty"],
            price=deal["price"],
        )
    else:
        body = utcopy.pick(utcopy.RACKET_FORCE_SELL).format(
            name=ENFORCER_NAME,
            item=deal["label"],
            qty=deal["qty"],
            price=deal["price"],
        )
    return (
        f"«{ENFORCER_NAME}·强买强卖»\n{body}\n"
        "  racket accept — 认栽成交\n"
        "  racket refuse — 硬扛（战力判定，败了更亏）"
    )


async def racket_ops(
    conn: aiosqlite.Connection, s: dict[str, Any], ut: dict[str, Any], rest: str
) -> str:
    parts = rest.split()
    sub = (parts[0].lower() if parts else "scan")
    deal = await ensure_racket_deal(conn, s["id"])
    if sub in ("scan", "status", ""):
        if not deal:
            return f"{ENFORCER_NAME} 靠在货架阴影里抽烟：「今天放过你。」"
        return format_racket_detail(deal)

    if not deal:
        raise ValueError(f"{ENFORCER_NAME} 今天没找你麻烦。")

    if sub in ("accept", "认", "成交"):
        return await _accept(conn, s, ut, deal)
    if sub in ("refuse", "拒", "扛"):
        return await _refuse(conn, s, ut, deal)
    raise ValueError("用法: undertide_ops racket [accept|refuse]")


async def _accept(
    conn: aiosqlite.Connection, s: dict[str, Any], ut: dict[str, Any], deal: dict[str, Any]
) -> str:
    sid = s["id"]
    if deal["kind"] == "buy":
        cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (sid,))
        have = (await cur.fetchone())[0]
        price = int(deal["price"])
        if have < price:
            raise ValueError(f"票不够 {price}，阿标冷笑：「赊账？找恶猫去。」")
        await conn.execute("UPDATE stewards SET tickets=tickets-? WHERE id=?", (price, sid))
        await db.add_item(conn, sid, deal["item"], int(deal["qty"]))
        rep_delta = -2
        msg = utcopy.pick(utcopy.RACKET_ACCEPT_BUY).format(
            item=deal["label"], price=price, name=ENFORCER_NAME
        )
    else:
        item, qty = deal["item"], int(deal["qty"])
        if not await db.take_item(conn, sid, item, qty):
            fine = max(10, int(deal["price"]) // 2)
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (sid,))
            have = (await cur.fetchone())[0]
            pay = min(have, fine)
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?", (pay, sid)
            )
            rep_delta = -5
            msg = utcopy.pick(utcopy.RACKET_ACCEPT_SELL_FAIL).format(
                item=deal["label"], fine=pay, name=ENFORCER_NAME
            )
        else:
            price = int(deal["price"])
            await conn.execute(
                "UPDATE stewards SET tickets=tickets+? WHERE id=?", (price, sid)
            )
            rep_delta = -3
            msg = utcopy.pick(utcopy.RACKET_ACCEPT_SELL).format(
                item=deal["label"], price=price, name=ENFORCER_NAME
            )
    await conn.execute(
        "UPDATE steward_undertide SET shadow_rep=MAX(0, MIN(100, shadow_rep+?)) WHERE steward_id=?",
        (rep_delta, sid),
    )
    deal["done"] = 1
    await _save_deal(conn, sid, _day_id(), deal)
    await db.add_chronicle(
        "undertide",
        f"{s['name']} 被{ENFORCER_NAME}{'强买' if deal['kind'] == 'buy' else '强卖'}成交",
        sid,
        conn=conn,
    )
    await conn.commit()
    return msg


async def _refuse(
    conn: aiosqlite.Connection, s: dict[str, Any], ut: dict[str, Any], deal: dict[str, Any]
) -> str:
    from . import undertide_muscle as um
    from . import undertide_pit as pit

    sid = s["id"]
    my = await um._my_power(conn, sid)
    his = utcfg.UT_RACKET_POWER + random.randint(1, 18)
    margin = my - his
    deal["done"] = 1
    await _save_deal(conn, sid, _day_id(), deal)

    if margin >= 8:
        await pit.pit_record(conn, sid, "racket", "win", ENFORCER_NAME)
        await conn.execute(
            "UPDATE steward_undertide SET shadow_rep=MIN(100, shadow_rep+2) WHERE steward_id=?",
            (sid,),
        )
        bonus = random.randint(5, 12)
        await conn.execute(
            "UPDATE stewards SET tickets=tickets+? WHERE id=?", (bonus, sid)
        )
        msg = utcopy.pick(utcopy.RACKET_REFUSE_WIN).format(
            name=ENFORCER_NAME, bonus=bonus
        )
    elif margin >= 0:
        await pit.pit_record(conn, sid, "racket", "win", ENFORCER_NAME)
        fine = random.randint(4, 10)
        cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (sid,))
        pay = min((await cur.fetchone())[0], fine)
        await conn.execute("UPDATE stewards SET tickets=tickets-? WHERE id=?", (pay, sid))
        await conn.execute(
            "UPDATE steward_undertide SET shadow_rep=MAX(0, shadow_rep-3) WHERE steward_id=?",
            (sid,),
        )
        msg = utcopy.pick(utcopy.RACKET_REFUSE_DRAW).format(
            name=ENFORCER_NAME, fine=pay
        )
    else:
        await pit.pit_record(conn, sid, "racket", "lose", ENFORCER_NAME)
        fine = random.randint(12, 22)
        cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (sid,))
        pay = min((await cur.fetchone())[0], fine)
        await conn.execute("UPDATE stewards SET tickets=tickets-? WHERE id=?", (pay, sid))
        await conn.execute(
            "UPDATE steward_undertide SET shadow_rep=MAX(0, shadow_rep-6) WHERE steward_id=?",
            (sid,),
        )
        if deal["kind"] == "buy" and random.random() < 0.45:
            await db.add_item(conn, sid, deal["item"], 1)
            extra = f"还被塞了 {deal['label']} x1。"
        else:
            extra = ""
        msg = utcopy.pick(utcopy.RACKET_REFUSE_LOSE).format(
            name=ENFORCER_NAME, fine=pay, extra=extra
        )
    await conn.commit()
    return msg
