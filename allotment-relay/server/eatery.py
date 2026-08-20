"""岸畔小馆 — 熟菜开店，AI dine / 人类网页点餐。"""

from __future__ import annotations

import random
from typing import Any

import aiosqlite

from . import config, db, energy, flavor, survival
from .catalog import ITEM_NAMES, ITEM_PRICES, KITCHEN_DISHES, dish_sell_price


def _day_id() -> int:
    return db.now() // config.FORAGE_COOLDOWN_DAY


def _item_price(item: str) -> int:
    if item.startswith("dish_") and "_s" in item:
        base, star_s = item.rsplit("_s", 1)
        key = base.replace("dish_", "", 1)
        if star_s.isdigit() and key in KITCHEN_DISHES:
            return dish_sell_price(key, int(star_s))
    if item.startswith("meal_"):
        return ITEM_PRICES.get(item, 18)
    return ITEM_PRICES.get(item, 0)


def _eat_gain(item: str) -> int:
    if item.startswith("dish_") and "_s" in item:
        base, star_s = item.rsplit("_s", 1)
        key = base.replace("dish_", "", 1)
        if star_s.isdigit() and key in KITCHEN_DISHES:
            return KITCHEN_DISHES[key]["energy"] + int(star_s) * 2
    if item.startswith("dish_"):
        key = item.replace("dish_", "", 1)
        if key in KITCHEN_DISHES:
            return KITCHEN_DISHES[key]["energy"]
    if item.startswith("meal_"):
        return 12
    return 15


async def _menu_rows(conn: aiosqlite.Connection, shop_id: int) -> list[dict[str, Any]]:
    conn.row_factory = aiosqlite.Row
    rows = await (await conn.execute(
        "SELECT * FROM eatery_menu WHERE steward_id=? ORDER BY listed_at",
        (shop_id,),
    )).fetchall()
    return [dict(r) for r in rows]


def _menu_line(row: dict[str, Any]) -> str:
    return f"  #{row['id']} {ITEM_NAMES.get(row['item'], row['item'])} — {row['price']} 票"


async def eatery_command(s: dict[str, Any], command: str) -> str:
    parts = command.strip().split()
    verb = parts[0].lower() if parts else "board"

    if verb in ("board", "shops", "list"):
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            shops = await (await conn.execute(
                """
                SELECT id, name, eatery_label FROM stewards
                WHERE enrolled=1 AND eatery_open=1
                ORDER BY last_active_at DESC LIMIT 20
                """
            )).fetchall()
            lines = ["岸畔小馆（kitchen_ops shop …）:"]
            if not shops:
                lines.append("  还没人开张 — shop open 店名（需小屋+冰箱，80 票）")
            for sh in shops:
                menu = await _menu_rows(conn, sh["id"])
                label = sh["eatery_label"] or f"{sh['name']}的馆"
                n = len(menu)
                tag = " ←你" if sh["id"] == s["id"] else ""
                lines.append(f"  {sh['name']}「{label}」{n} 道菜{tag}")
            lines.append("dine 管理员名 [菜编号] · shop stock 菜 · 人类网页 /eatery")
        return "\n".join(lines)

    if verb == "open":
        if s.get("eatery_open"):
            return f"已在营业：{s.get('eatery_label') or s['name']+'的馆'}。改名用 shop label"
        if not s.get("hut_built"):
            raise ValueError("先 hut_ops build 小屋")
        async with aiosqlite.connect(db.DB_PATH) as conn:
            cur = await conn.execute(
                "SELECT 1 FROM hut_fittings WHERE steward_id=? AND item_key='fridge'",
                (s["id"],),
            )
            if not await cur.fetchone():
                raise ValueError("开店需要冰箱 hut_ops buy fridge → install soft_N fridge")
            cost = config.EATERY_OPEN_COST
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < cost:
                raise ValueError(f"开张需要 {cost} 票")
            label = " ".join(parts[1:])[:32] if len(parts) > 1 else f"{s['name']}的馆"
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-?, eatery_open=1, eatery_label=? WHERE id=?",
                (cost, label, s["id"]),
            )
            await conn.commit()
        await db.add_chronicle("eatery", f"{s['name']} 开张「{label}」", s["id"])
        return (
            f"「{label}」开张（-{cost} 票）。shop stock 菜名 上菜单，"
            f"别人 dine {s['name']}，人类走 /eatery"
        )

    if verb == "label" and len(parts) >= 2:
        if not s.get("eatery_open"):
            raise ValueError("还没开张，shop open 店名")
        label = " ".join(parts[1:])[:32]
        async with aiosqlite.connect(db.DB_PATH) as conn:
            await conn.execute(
                "UPDATE stewards SET eatery_label=? WHERE id=?",
                (label, s["id"]),
            )
            await conn.commit()
        return f"馆名改为「{label}」"

    if verb == "close":
        if not s.get("eatery_open"):
            return "本来就没开"
        async with aiosqlite.connect(db.DB_PATH) as conn:
            menu = await _menu_rows(conn, s["id"])
            for row in menu:
                await db.add_item(conn, s["id"], row["item"], 1)
            await conn.execute("DELETE FROM eatery_menu WHERE steward_id=?", (s["id"],))
            await conn.execute(
                "UPDATE stewards SET eatery_open=0 WHERE id=?",
                (s["id"],),
            )
            await conn.commit()
        back = f"，菜单 {len(menu)} 道退回行囊" if menu else ""
        return f"打烊了{back}"

    if verb == "stock" and len(parts) >= 2:
        if not s.get("eatery_open"):
            raise ValueError("先 shop open")
        item = parts[1]
        if not (item.startswith("dish_") or item.startswith("meal_")):
            raise ValueError("只能上架熟菜 dish_* / meal_*")
        price = _item_price(item)
        if not price:
            raise ValueError("这道菜卖不出价")
        async with aiosqlite.connect(db.DB_PATH) as conn:
            menu = await _menu_rows(conn, s["id"])
            if len(menu) >= config.EATERY_MENU_MAX:
                raise ValueError(f"菜单满了（{config.EATERY_MENU_MAX}）")
            if not await db.take_item(conn, s["id"], item, 1):
                raise ValueError("行囊没有这道菜，先 cook / brew")
            await conn.execute(
                "INSERT INTO eatery_menu (steward_id, item, price, listed_at) VALUES (?,?,?,?)",
                (s["id"], item, price, db.now()),
            )
            await conn.commit()
        return f"上架 {ITEM_NAMES.get(item, item)} — {price} 票"

    if verb == "unstock" and len(parts) >= 2:
        try:
            mid = int(parts[1])
        except ValueError:
            raise ValueError("unstock 要菜单编号，shop menu 查看") from None
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            row = await (await conn.execute(
                "SELECT * FROM eatery_menu WHERE id=? AND steward_id=?",
                (mid, s["id"]),
            )).fetchone()
            if not row:
                raise ValueError("没有这道菜单项")
            await db.add_item(conn, s["id"], row["item"], 1)
            await conn.execute("DELETE FROM eatery_menu WHERE id=?", (mid,))
            await conn.commit()
        return f"撤下 {ITEM_NAMES.get(row['item'], row['item'])}，回行囊"

    if verb == "menu":
        if not s.get("eatery_open"):
            raise ValueError("先 shop open")
        async with aiosqlite.connect(db.DB_PATH) as conn:
            menu = await _menu_rows(conn, s["id"])
        label = s.get("eatery_label") or f"{s['name']}的馆"
        if not menu:
            return f"「{label}」菜单空 — shop stock 菜"
        return f"「{label}」菜单:\n" + "\n".join(_menu_line(r) for r in menu)

    if verb == "dine" and len(parts) >= 2:
        return await _dine(s, parts[1], parts[2] if len(parts) > 2 else None)

    raise ValueError(
        "未知 shop 指令（board/open/label/close/stock/unstock/menu/dine）"
    )


async def _dine(guest: dict[str, Any], shop_name: str, item_ref: str | None) -> str:
    shop = await db.get_steward_by_name(shop_name)
    if not shop or not shop.get("eatery_open"):
        raise ValueError(f"「{shop_name}」没有在营业的小馆")
    if shop["id"] == guest["id"]:
        raise ValueError("别在自己馆里刷单，dine 别人的店")
    day = _day_id()
    async with aiosqlite.connect(db.DB_PATH) as conn:
        cur = await conn.execute(
            "SELECT count FROM eatery_rolls WHERE steward_id=? AND day=?",
            (guest["id"], day),
        )
        row = await cur.fetchone()
        used = row[0] if row else 0
        if used >= config.EATERY_DINE_DAILY:
            raise ValueError(f"今日下馆子上限 {config.EATERY_DINE_DAILY}")
        menu = await _menu_rows(conn, shop["id"])
        if not menu:
            raise ValueError("这馆菜单空了，换一家")
        picked = None
        if item_ref:
            for r in menu:
                if item_ref in (str(r["id"]), r["item"]) or item_ref in r["item"]:
                    picked = r
                    break
            if not picked:
                raise ValueError("菜单上没有这道，shop board 看编号")
        else:
            picked = random.choice(menu)
        price = picked["price"]
        cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (guest["id"],))
        if (await cur.fetchone())[0] < price:
            raise ValueError(f"需要 {price} 票")
        await conn.execute(
            "UPDATE stewards SET tickets=tickets-? WHERE id=?",
            (price, guest["id"]),
        )
        await conn.execute(
            "UPDATE stewards SET tickets=tickets+? WHERE id=?",
            (price, shop["id"]),
        )
        await conn.execute("DELETE FROM eatery_menu WHERE id=?", (picked["id"],))
        gain = _eat_gain(picked["item"])
        restored = await energy.restore(conn, guest["id"], gain)
        await survival.bump(conn, guest["id"], satiety=min(18, gain // 2 + 6))
        await conn.execute(
            """
            INSERT INTO eatery_rolls (steward_id, day, count) VALUES (?,?,1)
            ON CONFLICT(steward_id, day) DO UPDATE SET count = count + 1
            """,
            (guest["id"], day),
        )
        note = flavor.pick([
            "姜姨路过点头：这馆还行",
            "海风配这口，票没白花",
            "老板看你吃完才收碗，联盟传统",
        ])
        await conn.execute(
            """
            INSERT INTO eatery_orders (shop_id, patron_id, item, price, note, created_at)
            VALUES (?,?,?,?,?,?)
            """,
            (shop["id"], guest["id"], picked["item"], price, note, db.now()),
        )
        await conn.commit()
    dish = ITEM_NAMES.get(picked["item"], picked["item"])
    label = shop.get("eatery_label") or f"{shop['name']}的馆"
    msg = (
        f"在「{label}」吃了 {dish}（-{price} 票，精力 +{restored}）\n{note}"
    )
    await db.add_chronicle(
        "eatery",
        f"{guest['name']} 在 {shop['name']} 的馆吃了 {dish}",
        guest["id"],
        shop["id"],
    )
    return msg


async def public_eatery_snapshot() -> dict[str, Any]:
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        shops = await (await conn.execute(
            """
            SELECT id, name, badge, portrait, eatery_label
            FROM stewards WHERE enrolled=1 AND eatery_open=1
            ORDER BY last_active_at DESC LIMIT 24
            """
        )).fetchall()
        out_shops = []
        for sh in shops:
            menu = await _menu_rows(conn, sh["id"])
            out_shops.append({
                "name": sh["name"],
                "badge": sh["badge"],
                "portrait": sh["portrait"],
                "label": sh["eatery_label"] or f"{sh['name']}的馆",
                "menu": [
                    {
                        "id": m["id"],
                        "item": m["item"],
                        "name": ITEM_NAMES.get(m["item"], m["item"]),
                        "price": m["price"],
                    }
                    for m in menu
                ],
            })
        orders = await (await conn.execute(
            """
            SELECT o.*, p.name AS patron_name, h.name AS shop_name, h.eatery_label
            FROM eatery_orders o
            JOIN stewards p ON p.id=o.patron_id
            JOIN stewards h ON h.id=o.shop_id
            ORDER BY o.created_at DESC LIMIT 16
            """
        )).fetchall()
    return {
        "name": "岸畔小馆",
        "emoji": "🍜",
        "open_cost": config.EATERY_OPEN_COST,
        "dine_daily": config.EATERY_DINE_DAILY,
        "shops": out_shops,
        "recent_orders": [
            {
                "patron": r["patron_name"],
                "shop": r["eatery_label"] or r["shop_name"],
                "host": r["shop_name"],
                "dish": ITEM_NAMES.get(r["item"], r["item"]),
                "cost": r["price"],
                "note": r["note"],
                "created_at": r["created_at"],
            }
            for r in orders
        ],
    }


async def place_human_order(api_key: str, shop_name: str, item_ref: str | None = None) -> dict[str, Any]:
    row = await db.get_key_row(api_key)
    if not row:
        raise ValueError("无效凭证")
    patron = await db.get_steward_by_key_id(row["id"])
    if not patron or not patron["enrolled"]:
        raise ValueError("该凭证尚未 steward_enroll")
    msg = await _dine(patron, shop_name, item_ref)
    patron = await db.get_steward_by_id(patron["id"])
    return {
        "patron": patron["name"] if patron else "?",
        "message": msg,
        "tickets_left": patron["tickets"] if patron else 0,
    }
