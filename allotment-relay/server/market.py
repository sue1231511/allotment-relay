"""集市 — 玩家互卖，建议价参考 catalog。"""

from __future__ import annotations

import aiosqlite

from . import config, db, flavor
from .catalog import ITEM_NAMES, item_vendable, resolve_item_key, suggested_price, unknown_item_message
from .game import require_steward, _parse_int


def market_list_cap(extra: int = 0) -> int:
    return min(config.MARKET_LIST_SLOTS_MAX, config.MARKET_LIST_MAX + max(0, extra))


async def _market_extra(conn: aiosqlite.Connection, steward_id: int) -> int:
    row = await (await conn.execute(
        "SELECT market_extra FROM stewards WHERE id=?", (steward_id,)
    )).fetchone()
    return int(row[0] or 0) if row else 0


def _expand_hint(extra: int) -> str:
    cap = market_list_cap(extra)
    if cap >= config.MARKET_LIST_SLOTS_MAX:
        return f"（已扩满 {cap}/{config.MARKET_LIST_SLOTS_MAX} 格）"
    return (
        f"（{cap}/{config.MARKET_LIST_SLOTS_MAX} 格；"
        f"market_ops 扩 [数量] 加格，{config.MARKET_SLOT_COST}票/格）"
    )


async def market_expand(s: dict, n: int = 1) -> str:
    n = max(1, int(n))
    async with db.connect() as conn:
        extra = await _market_extra(conn, s["id"])
        cap = market_list_cap(extra)
        room = config.MARKET_LIST_SLOTS_MAX - cap
        if room <= 0:
            raise ValueError(
                f"集市摊格已经扩到顶了（{config.MARKET_LIST_SLOTS_MAX} 格）"
            )
        n = min(n, room)
        cost = n * config.MARKET_SLOT_COST
        cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
        have = (await cur.fetchone())[0]
        if have < cost:
            raise ValueError(
                f"加 {n} 格需要 {cost} 票（每格 {config.MARKET_SLOT_COST}）"
            )
        await conn.execute(
            "UPDATE stewards SET tickets=tickets-?, market_extra=market_extra+? WHERE id=?",
            (cost, n, s["id"]),
        )
        await conn.commit()
        new_cap = market_list_cap(extra + n)
    return (
        f"集市摊格 +{n}（-{cost} 票）。现在 {new_cap}/{config.MARKET_LIST_SLOTS_MAX} 格，"
        f"基础 {config.MARKET_LIST_MAX} 格起。"
    )


async def market_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    parts = command.strip().split(maxsplit=3)
    verb = parts[0].lower() if parts else "list"

    if verb in ("expand", "扩", "扩容", "加格"):
        n = 1
        if len(parts) >= 2:
            n = max(1, _parse_int(parts[1], "数量"))
        return await market_expand(s, n)

    if verb == "list":
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            rows = await (await conn.execute(
                """
                SELECT l.*, d.name AS seller_name
                FROM market_listings l
                JOIN stewards d ON d.id = l.seller_id
                WHERE l.buyer_id IS NULL
                ORDER BY l.created_at DESC LIMIT 20
                """
            )).fetchall()
        if not rows:
            return "集市暂无挂单 — market_ops sell 物品 数量 单价"
        lines = []
        for r in rows:
            sug = r["suggested"]
            hint = ""
            if sug and r["price"] <= int(sug * 0.9):
                hint = " 💚划算"
            elif sug and r["price"] >= int(sug * 1.3):
                hint = " 💸偏贵"
            item_id = r["item"]
            lines.append(
                f"#{r['id']} {r['seller_name']} "
                f"{ITEM_NAMES.get(item_id, item_id)}（{item_id}）x{r['quantity']} "
                f"@{r['price']}票/个（建议{sug}）{hint} {r['note']}"
            )
        return "\n".join(lines)

    if verb == "mine":
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            extra = await _market_extra(conn, s["id"])
            cap = market_list_cap(extra)
            rows = await (await conn.execute(
                """
                SELECT * FROM market_listings
                WHERE seller_id=? AND buyer_id IS NULL ORDER BY created_at DESC
                """,
                (s["id"],),
            )).fetchall()
        if not rows:
            return f"你没有在售挂单 {_expand_hint(extra)}"
        lines = [f"你的挂单 {len(rows)}/{cap}{_expand_hint(extra)}"]
        lines.extend(
            f"#{r['id']} {ITEM_NAMES.get(r['item'], r['item'])}（{r['item']}）"
            f" x{r['quantity']} @{r['price']}票"
            for r in rows
        )
        return "\n".join(lines)

    if verb == "sell" and len(parts) >= 4:
        raw_item, qty_s, price_s = parts[1], parts[2], parts[3]
        item_key = resolve_item_key(raw_item)
        if not item_key:
            raise ValueError(unknown_item_message(raw_item))
        qty, price = _parse_int(qty_s), _parse_int(price_s, "单价")
        note = parts[4] if len(parts) > 4 else ""
        if not item_vendable(item_key):
            raise ValueError(
                f"{ITEM_NAMES.get(item_key, item_key)}（{item_key}）不宜上架"
            )
        sug = suggested_price(item_key)
        async with db.connect() as conn:
            extra = await _market_extra(conn, s["id"])
            cap = market_list_cap(extra)
            cur = await conn.execute(
                "SELECT COUNT(*) FROM market_listings WHERE seller_id=? AND buyer_id IS NULL",
                (s["id"],),
            )
            used = (await cur.fetchone())[0]
            if used >= cap:
                hint = ""
                if cap < config.MARKET_LIST_SLOTS_MAX:
                    hint = (
                        f" market_ops 扩 [数量] 加格"
                        f"（{config.MARKET_SLOT_COST}票/格，顶 {config.MARKET_LIST_SLOTS_MAX}）"
                    )
                raise ValueError(f"挂单已满 {used}/{cap}。{hint}")
            if not await db.take_item(conn, s["id"], item_key, qty):
                raise ValueError(
                    f"行囊数量不足（需要 {item_key} x{qty}）"
                )
            await conn.execute(
                """
                INSERT INTO market_listings
                (seller_id, item, quantity, price, suggested, note, created_at)
                VALUES (?,?,?,?,?,?,?)
                """,
                (s["id"], item_key, qty, price, sug, note[:60], db.now()),
            )
            await conn.commit()
        hint = flavor.pick([
            "建议价仅供参考，别跟票置气",
            "范姐：缺啥买啥，别囤到烂",
            "串门顺便看看邻居卖啥",
        ])
        return (
            f"上架 {ITEM_NAMES.get(item_key, item_key)}（{item_key}）x{qty} "
            f"@{price}票（建议{sug}）— {hint}"
        )

    if verb == "buy" and len(parts) >= 2:
        lot_id = _parse_int(parts[1], "挂单编号")
        qty = _parse_int(parts[2], "数量") if len(parts) > 2 else None
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            lot = dict(await (await conn.execute(
                "SELECT * FROM market_listings WHERE id=? AND buyer_id IS NULL",
                (lot_id,),
            )).fetchone() or {})
            if not lot:
                raise ValueError("挂单不存在或已售出")
            if lot["seller_id"] == s["id"]:
                raise ValueError("不能买自己的挂单")
            buy_qty = qty or lot["quantity"]
            if buy_qty < 1 or buy_qty > lot["quantity"]:
                raise ValueError("数量不对")
            cost = lot["price"] * buy_qty + config.MARKET_FEE
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < cost:
                raise ValueError(f"需要 {cost} 票（含手续费 {config.MARKET_FEE}）")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (cost, s["id"]),
            )
            pay = lot["price"] * buy_qty
            await conn.execute(
                "UPDATE stewards SET tickets=tickets+? WHERE id=?",
                (pay, lot["seller_id"]),
            )
            await db.add_item(conn, s["id"], lot["item"], buy_qty)
            if buy_qty >= lot["quantity"]:
                await conn.execute(
                    "UPDATE market_listings SET buyer_id=?, sold_at=? WHERE id=?",
                    (s["id"], db.now(), lot_id),
                )
            else:
                await conn.execute(
                    "UPDATE market_listings SET quantity=quantity-? WHERE id=?",
                    (buy_qty, lot_id),
                )
            await conn.commit()
        seller = await db.get_steward_by_id(lot["seller_id"])
        msg = (
            f"购入 {ITEM_NAMES.get(lot['item'], lot['item'])}（{lot['item']}）x{buy_qty} "
            f"（-{cost}票，卖家 {seller['name'] if seller else '?'}）"
        )
        await db.add_chronicle(
            "market",
            f"{s['name']} 集市购入 {lot['item']} x{buy_qty}",
            s["id"],
        )
        return msg

    if verb == "cancel" and len(parts) >= 2:
        lot_id = _parse_int(parts[1], "挂单编号")
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            lot = dict(await (await conn.execute(
                "SELECT * FROM market_listings WHERE id=? AND seller_id=? AND buyer_id IS NULL",
                (lot_id, s["id"]),
            )).fetchone() or {})
            if not lot:
                raise ValueError("找不到可取消的挂单")
            await db.add_item(conn, s["id"], lot["item"], lot["quantity"])
            await conn.execute("DELETE FROM market_listings WHERE id=?", (lot_id,))
            await conn.commit()
        return f"已下架 #{lot_id}，物品退回行囊"

    if verb == "price" and len(parts) >= 2:
        item_key = resolve_item_key(parts[1])
        if not item_key:
            raise ValueError(unknown_item_message(parts[1]))
        sug = suggested_price(item_key)
        vend = ITEM_NAMES.get(item_key, item_key)
        return f"{vend}（{item_key}）建议价 {sug} 票/个"

    raise ValueError(
        f"未知 market 指令: {command}"
        f"（list/sell/buy/mine/cancel/price/扩 [数量]）"
    )


async def public_snapshot() -> dict[str, Any]:
    from . import world
    from .catalog import item_label

    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        listings = await (await conn.execute(
            """
            SELECT l.id, l.item, l.quantity, l.price, l.suggested, d.name AS seller
            FROM market_listings l
            JOIN stewards d ON d.id = l.seller_id
            WHERE l.buyer_id IS NULL
            ORDER BY l.created_at DESC LIMIT 16
            """
        )).fetchall()
        open_n = (await (await conn.execute(
            "SELECT COUNT(*) FROM market_listings WHERE buyer_id IS NULL"
        )).fetchone())[0]
        swaps = await (await conn.execute(
            """
            SELECT l.item, l.quantity, d.name AS from_name
            FROM swap_lots l
            JOIN stewards d ON d.id = l.depositor_id
            WHERE l.claimed_by IS NULL
            ORDER BY l.created_at DESC LIMIT 8
            """
        )).fetchall()
        swap_n = (await (await conn.execute(
            "SELECT COUNT(*) FROM swap_lots WHERE claimed_by IS NULL"
        )).fetchone())[0]
        feed = await (await conn.execute(
            """
            SELECT c.text, c.created_at, a.name AS actor
            FROM chronicle c
            LEFT JOIN stewards a ON a.id = c.actor_id
            WHERE c.action IN ('market', 'gift', 'swap')
            ORDER BY c.created_at DESC LIMIT 16
            """
        )).fetchall()
    rows = []
    for r in listings:
        sug = int(r["suggested"] or 0)
        tag = ""
        if sug and r["price"] <= int(sug * 0.9):
            tag = "划算"
        elif sug and r["price"] >= int(sug * 1.3):
            tag = "偏贵"
        rows.append({
            "id": r["id"],
            "seller": r["seller"],
            "item": item_label(r["item"]),
            "qty": int(r["quantity"]),
            "price": int(r["price"]),
            "tag": tag,
        })
    return {
        "climate": world.climate_line(),
        "open": int(open_n or 0),
        "swaps": int(swap_n or 0),
        "listings": rows,
        "swap_preview": [
            {
                "from": r["from_name"],
                "item": item_label(r["item"]),
                "qty": int(r["quantity"]),
            }
            for r in swaps
        ],
        "hints": [
            "AI 用 tote_ops market list / market sell 甘蓝 2 8",
            "交换台 tote_ops swap list 白送，领取收手续费",
            "人类只看热闹，买货还是让管家去点",
        ],
        "feed": [
            {
                "text": r["text"],
                "actor": r["actor"] or "系统",
                "created_at": r["created_at"],
            }
            for r in feed
        ],
    }
