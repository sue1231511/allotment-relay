"""岸畔小馆 — 熟菜开店，AI dine / 人类在 /play 点餐。"""

from __future__ import annotations

import random
from math import ceil
from typing import Any

import aiosqlite

from . import config, db, energy, flavor, survival
from .catalog import (
    ITEM_PRICES,
    dish_energy,
    eatery_reference_price,
    item_label,
    resolve_item_key,
    suggested_price,
)


def _day_id() -> int:
    return db.day_id()


def _age_text(seconds: int | None) -> str:
    if seconds is None:
        return "开张日不明"
    sec = max(0, int(seconds))
    if sec < 3600:
        mins = max(1, sec // 60)
        return f"开了 {mins} 分钟"
    if sec < 86400:
        return f"开了 {sec // 3600} 小时"
    days = sec / 86400
    if days < 10:
        return f"开了 {days:.1f} 天".replace(".0", "")
    return f"开了 {int(days)} 天"


def eatery_sell_quote(opened_at: int | None, now: int | None = None) -> dict[str, Any]:
    """开张费按折旧回收。刚开约 62%，随天数掉到 25%。"""
    now = db.now() if now is None else now
    cost = config.EATERY_OPEN_COST
    opened = int(opened_at or 0)
    if opened <= 0:
        rate = (config.EATERY_SELL_RATE_START + config.EATERY_SELL_RATE_FLOOR) / 2
        age_s = None
        note = "开张日未记，按中档折旧"
    else:
        age_s = max(0, now - opened)
        days = age_s / 86400
        rate = max(
            config.EATERY_SELL_RATE_FLOOR,
            config.EATERY_SELL_RATE_START - days * config.EATERY_SELL_DECAY_PER_DAY,
        )
        if days < 0.5:
            note = "刚开张，二手盘也要折一截"
        elif days < 2:
            note = "开了没几天，桌椅还新"
        elif days < 7:
            note = "招牌旧了，按折旧收"
        else:
            note = "老馆了，残值见底"
    refund = max(1, int(round(cost * rate)))
    return {
        "cost": cost,
        "rate": rate,
        "refund": refund,
        "age_s": age_s,
        "note": note,
        "pct": int(round(rate * 100)),
    }


def _quote_lines(label: str, quote: dict[str, Any], menu_n: int) -> list[str]:
    return [
        f"变卖「{label}」",
        f"开张费 {quote['cost']} 票 · {_age_text(quote['age_s'])} · "
        f"折旧回收 {quote['refund']} 票（{quote['pct']}%）",
        quote["note"],
        f"菜单 {menu_n} 道退回行囊" if menu_n else "菜单是空的",
        "冰箱还在小屋里。要拆装件：hut_ops remove",
        "确认：kitchen_ops shop 卖掉 确认",
    ]


def _eat_gain(item: str, price: int | None = None) -> int:
    gain = dish_energy(item)
    if gain is None:
        gain = 18 if item.startswith("meal_") else 15
    if price and price > 0:
        scaled = int(ceil(price / config.EATERY_TICKETS_PER_ENERGY))
        gain = max(gain, scaled)
    return min(50, gain)


async def _menu_rows(conn: aiosqlite.Connection, shop_id: int) -> list[dict[str, Any]]:
    conn.row_factory = aiosqlite.Row
    rows = await (await conn.execute(
        "SELECT * FROM eatery_menu WHERE steward_id=? ORDER BY listed_at",
        (shop_id,),
    )).fetchall()
    return [dict(r) for r in rows]


def _menu_line(row: dict[str, Any]) -> str:
    energy = dish_energy(row["item"])
    extra = f" · 精力+{energy}" if energy else ""
    return f"  #{row['id']} {item_label(row['item'])} — {row['price']} 票{extra}"


async def eatery_command(s: dict[str, Any], command: str) -> str:
    parts = command.strip().split()
    verb = parts[0].lower() if parts else "board"

    if verb in ("board", "shops", "list"):
        async with db.connect() as conn:
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
            lines.append("dine 管理员名 [菜编号] · shop stock 菜 · 不想开了 shop 卖掉 · 人类网页 /play 点餐")
            if s.get("eatery_open"):
                quote = eatery_sell_quote(s.get("eatery_opened_at"))
                mine = s.get("eatery_label") or f"{s['name']}的馆"
                lines.append(
                    f"你的馆「{mine}」现在卖掉可回收 {quote['refund']} 票（{quote['pct']}% 开张费）"
                )
        return "\n".join(lines)

    if verb == "open":
        if s.get("eatery_open"):
            return f"已在营业：{s.get('eatery_label') or s['name']+'的馆'}。改名用 shop label"
        if not s.get("hut_built"):
            raise ValueError("先 hut_ops build 小屋")
        async with db.connect() as conn:
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
                "UPDATE stewards SET tickets=tickets-?, eatery_open=1, eatery_label=?, eatery_opened_at=? WHERE id=?",
                (cost, label, db.now(), s["id"]),
            )
            await conn.commit()
        await db.add_chronicle("eatery", f"{s['name']} 开张「{label}」", s["id"])
        return (
            f"「{label}」开张（-{cost} 票）。shop stock 菜名 上菜单，"
            f"别人 dine {s['name']}，人类走 /play"
        )

    if verb == "label" and len(parts) >= 2:
        if not s.get("eatery_open"):
            raise ValueError("还没开张，shop open 店名")
        label = " ".join(parts[1:])[:32]
        async with db.connect() as conn:
            await conn.execute(
                "UPDATE stewards SET eatery_label=? WHERE id=?",
                (label, s["id"]),
            )
            await conn.commit()
        return f"馆名改为「{label}」"

    if verb == "close":
        if not s.get("eatery_open"):
            return "本来就没开"
        async with db.connect() as conn:
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
        return (
            f"打烊了{back}。开张费不退。"
            f"要变卖家产按折旧回收：kitchen_ops shop 卖掉"
        )

    if verb in ("sell", "卖掉", "变卖", "出售"):
        if not s.get("eatery_open"):
            raise ValueError("没有在开的馆。打烊过的开张费已经没了，下次开张后再卖掉。")
        confirm = len(parts) >= 2 and parts[1].lower() in (
            "确认", "ok", "yes", "confirm", "卖",
        )
        label = s.get("eatery_label") or f"{s['name']}的馆"
        async with db.connect() as conn:
            menu = await _menu_rows(conn, s["id"])
            quote = eatery_sell_quote(s.get("eatery_opened_at"))
            if not confirm:
                return "\n".join(_quote_lines(label, quote, len(menu)))
            for row in menu:
                await db.add_item(conn, s["id"], row["item"], 1)
            await conn.execute("DELETE FROM eatery_menu WHERE steward_id=?", (s["id"],))
            await conn.execute(
                """
                UPDATE stewards SET tickets=tickets+?, eatery_open=0, eatery_label='',
                eatery_opened_at=0 WHERE id=?
                """,
                (quote["refund"], s["id"]),
            )
            # 票数上涨会触发入账经验；变卖是回本，把刚加上的经验扣回去
            await conn.execute(
                "UPDATE stewards SET xp = MAX(0, COALESCE(xp, 0) - ?) WHERE id=?",
                (quote["refund"], s["id"]),
            )
            await conn.commit()
        await db.add_chronicle(
            "eatery",
            f"{s['name']} 变卖「{label}」，折旧回收 {quote['refund']} 票",
            s["id"],
        )
        back = f"菜单 {len(menu)} 道退回行囊。" if menu else ""
        return (
            f"「{label}」卖掉了。{back}"
            f"{quote['note']} 折旧回收 {quote['refund']} 票（开张费 {quote['cost']} 的 {quote['pct']}%）。"
            f"冰箱还在小屋里。"
        )

    if verb == "stock" and len(parts) >= 2:
        if not s.get("eatery_open"):
            raise ValueError("先 shop open")
        token = parts[1]
        item = resolve_item_key(token) or token
        if not (item.startswith("dish_") or item.startswith("meal_")):
            from . import kitchen as kitchen_mod
            cooked = kitchen_mod._resolve_cooked_token(token)
            if cooked and (cooked.startswith("dish_") or cooked.startswith("meal_")):
                item = cooked
        if not (item.startswith("dish_") or item.startswith("meal_")):
            raise ValueError("只能上架熟菜 dish_* / meal_*")
        async with db.connect() as conn:
            menu = await _menu_rows(conn, s["id"])
            if len(menu) >= config.EATERY_MENU_MAX:
                raise ValueError(f"菜单满了（{config.EATERY_MENU_MAX}）")
            if item.startswith("dish_"):
                from . import kitchen as kitchen_mod
                try:
                    item = await kitchen_mod._pick_cooked_satchel(conn, s["id"], item)
                except ValueError:
                    pass
            if not await db.take_item(conn, s["id"], item, 1):
                raise ValueError("行囊没有这道菜，先 cook / brew")
            ref = eatery_reference_price(item)
            price = ref
            if len(parts) >= 3:
                try:
                    price = int(parts[2])
                except ValueError:
                    raise ValueError(
                        f"价格要写正整数。{item_label(item)} 参考价约 {ref} 票（可自定，不限区间）"
                    ) from None
                if price < 1:
                    raise ValueError("价格至少 1 票")
            await conn.execute(
                "INSERT INTO eatery_menu (steward_id, item, price, listed_at) VALUES (?,?,?,?)",
                (s["id"], item, price, db.now()),
            )
            await conn.commit()
        vend = suggested_price(item)
        energy = dish_energy(item)
        energy_note = f" · 精力+{energy}" if energy else ""
        return (
            f"上架 {item_label(item)} — {price} 票"
            f"（参考约 {ref}{energy_note} · 系统回收 {vend}）"
        )

    if verb == "unstock" and len(parts) >= 2:
        try:
            mid = int(parts[1])
        except ValueError:
            raise ValueError("unstock 要菜单编号，shop menu 查看") from None
        async with db.connect() as conn:
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
        return f"撤下 {item_label(row['item'])}，回行囊"

    if verb == "menu":
        if not s.get("eatery_open"):
            raise ValueError("先 shop open")
        async with db.connect() as conn:
            menu = await _menu_rows(conn, s["id"])
        label = s.get("eatery_label") or f"{s['name']}的馆"
        if not menu:
            return f"「{label}」菜单空 — shop stock 菜"
        return f"「{label}」菜单:\n" + "\n".join(_menu_line(r) for r in menu)

    if verb == "dine" and len(parts) >= 2:
        return await _dine(s, parts[1], parts[2] if len(parts) > 2 else None)

    raise ValueError(
        "未知 shop 指令（board/open/label/close/卖掉/stock/unstock/menu/dine）"
    )


async def _dine(guest: dict[str, Any], shop_name: str, item_ref: str | None) -> str:
    shop = await db.get_steward_by_name(shop_name)
    if not shop or not shop.get("eatery_open"):
        raise ValueError(f"「{shop_name}」没有在营业的小馆")
    if shop["id"] == guest["id"]:
        raise ValueError("别在自己馆里刷单，dine 别人的店")
    day = _day_id()
    async with db.connect() as conn:
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
        gain = _eat_gain(picked["item"], price)
        from . import kitchen as kitchen_mod
        cured_line = await kitchen_mod.ate_cooked_meal(conn, guest["id"])
        restored = await energy.restore(conn, guest["id"], gain)
        # 堂食「饱餐」：行动精力 -1 一段时间 + 雾智/档信小加成——家里自己吃没有，
        # 这是饭馆相对集市（买货回家吃只有基础精力）的溢价来源
        await conn.execute(
            "UPDATE stewards SET dine_buff_until=? WHERE id=?",
            (db.now() + config.DINE_BUFF_SECONDS, guest["id"]),
        )
        await survival.bump(
            conn,
            guest["id"],
            satiety=min(18, gain // 2 + 6),
            mist_wit=config.DINE_BUFF_MIST_WIT,
            standing=config.DINE_BUFF_STANDING,
        )
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
    dish = item_label(picked["item"])
    label = shop.get("eatery_label") or f"{shop['name']}的馆"
    msg = (
        f"在「{label}」吃了 {dish}（-{price} 票，精力 +{restored}）\n{note}"
    )
    hours = config.DINE_BUFF_SECONDS // 3600
    msg += (
        f"\n堂食「饱餐」{hours} 小时：行动精力 -1（steward_ops sheet 可见剩余）；"
        f"雾智 +{config.DINE_BUFF_MIST_WIT}、档信 +{config.DINE_BUFF_STANDING}。"
        "家里自己吃没有这些——下海干活前来一顿才值。"
    )
    if cured_line:
        msg += f"\n{cured_line}"
    await db.add_chronicle(
        "eatery",
        f"{guest['name']} 在 {shop['name']} 的馆吃了 {dish}",
        guest["id"],
        shop["id"],
    )
    return msg


async def public_eatery_snapshot() -> dict[str, Any]:
    async with db.connect() as conn:
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
                        "name": item_label(m["item"]),
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
                "dish": item_label(r["item"]),
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
        raise ValueError("该凭证尚未 steward_ops enroll")
    msg = await _dine(patron, shop_name, item_ref)
    patron = await db.get_steward_by_id(patron["id"])
    return {
        "patron": patron["name"] if patron else "?",
        "message": msg,
        "tickets_left": patron["tickets"] if patron else 0,
    }
