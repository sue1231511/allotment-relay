"""集市 — 玩家互卖，建议价参考 catalog。"""

from __future__ import annotations

from typing import Any

import aiosqlite

from . import config, db, flavor
from .catalog import ITEM_NAMES, item_label, item_vendable, resolve_item_key, suggested_price, unknown_item_message
from .game import require_steward, _parse_int


MARKET_HELP = """tote_ops market 子命令（整句写进 command）：
  list — 街上在售的挂单；空 command 也是 list
  sell 物品 数量 单价 — 从行囊挂到摊上。基础 6 格，满了先扩
  buy 编号 [数量] — 买别人的挂单。另加手续费 2 票。不能买自己的
  mine — 自己还在卖的
  cancel 编号 — 下架，货退回行囊
  price 物品 — 看建议价
  扩 [数量] — 加摊格，15 票/格，顶 12 格
  例子：market list · market sell 甘蓝 2 8 · market buy 3 · market 扩
  集市卖的是货，不是小馆堂食。买熟菜回家自己吃，没有饱餐加成。
  人类 /island 总览点集市，先进店景，点一下才出摊位列表，能看街摊、买、挂自己的货、下架、扩摊。"""



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

    if verb in ("help", "?", "帮助"):
        return MARKET_HELP
    raise ValueError(
        f"未知 market 指令: {command}\n{MARKET_HELP}"
    )


def _tag(price: int, suggested: int) -> str:
    sug = int(suggested or 0)
    if sug and price <= int(sug * 0.9):
        return "划算"
    if sug and price >= int(sug * 1.3):
        return "偏贵"
    return ""


async def player_view(conn: aiosqlite.Connection, s: dict[str, Any]) -> dict[str, Any]:
    """给 /island 集市用。数值仍走 market_ops，这里只摊开能点的。"""
    extra = await _market_extra(conn, s["id"])
    cap = market_list_cap(extra)
    tickets = int(s.get("tickets") or 0)
    conn.row_factory = aiosqlite.Row
    rows = await (await conn.execute(
        """
        SELECT l.*, d.name AS seller_name
        FROM market_listings l
        JOIN stewards d ON d.id = l.seller_id
        WHERE l.buyer_id IS NULL
        ORDER BY l.created_at DESC LIMIT 24
        """
    )).fetchall()
    mine_rows = [r for r in rows if int(r["seller_id"]) == int(s["id"])]
    used = len(mine_rows)
    listings = []
    for r in rows:
        qty = int(r["quantity"] or 0)
        price = int(r["price"] or 0)
        sug = int(r["suggested"] or 0)
        cost = price * qty + config.MARKET_FEE
        mine = int(r["seller_id"]) == int(s["id"])
        tag = _tag(price, sug)
        if mine:
            note = "自己的摊，不能买。"
            can = False
        elif tickets < cost:
            note = f"要 {cost} 票（含手续费 {config.MARKET_FEE}），现在 {tickets}"
            can = False
        else:
            note = f"{r['seller_name']} · {price} 票/个"
            if tag:
                note += f" · {tag}"
            can = True
        listings.append({
            "id": int(r["id"]),
            "item": r["item"],
            "name": item_label(r["item"]),
            "emoji": "🧺",
            "qty": qty,
            "price": price,
            "suggested": sug,
            "fee": config.MARKET_FEE,
            "cost": cost,
            "seller": r["seller_name"],
            "mine": mine,
            "tag": tag,
            "can_buy": can,
            "note": note,
            "detail": note + (f"。建议 {sug} 票/个。" if sug else ""),
        })
    mine_list = []
    for r in mine_rows:
        qty = int(r["quantity"] or 0)
        price = int(r["price"] or 0)
        mine_list.append({
            "id": int(r["id"]),
            "item": r["item"],
            "name": item_label(r["item"]),
            "emoji": "🧺",
            "qty": qty,
            "price": price,
            "can_cancel": True,
            "note": f"{qty} 个 · {price} 票/个",
            "detail": "下架后货退回行囊。",
        })
    stock = await db.get_satchel(s["id"])
    goods = []
    room = used < cap
    for item, qty in (stock or {}).items():
        if not item_vendable(item):
            continue
        n = int(qty or 0)
        if n < 1:
            continue
        sug = suggested_price(item)
        goods.append({
            "item": item,
            "name": item_label(item),
            "emoji": "🧺",
            "qty": n,
            "suggested": sug,
            "can_sell": room,
            "note": (
                f"摊满了 {used}/{cap}，先扩。"
                if not room
                else f"袋里 {n} · 建议 {sug} 票/个"
            ),
            "detail": (
                f"摊满了 {used}/{cap}。扩一格 {config.MARKET_SLOT_COST} 票。"
                if not room
                else f"挂多少、卖多少自己定。建议 {sug} 票/个。"
            ),
        })
    can_expand = cap < config.MARKET_LIST_SLOTS_MAX and tickets >= config.MARKET_SLOT_COST
    if cap >= config.MARKET_LIST_SLOTS_MAX:
        expand_note = f"已经扩到顶了（{cap} 格）。"
    elif tickets < config.MARKET_SLOT_COST:
        expand_note = f"加一格要 {config.MARKET_SLOT_COST} 票。"
    else:
        expand_note = (
            f"{config.MARKET_SLOT_COST} 票加一格。"
            f"现在 {cap}/{config.MARKET_LIST_SLOTS_MAX}。"
        )
    if not listings:
        spoken = "街上还没人摆。自己的货可以挂出来。"
    else:
        spoken = f"街上 {len(listings)} 单。买别人的另加手续费 {config.MARKET_FEE} 票。"
    return {
        "name": "玩家集市",
        "line": spoken,
        "tabs": [
            {"key": "board", "label": "街摊", "badge": str(len(listings)) if listings else ""},
            {"key": "mine", "label": "我的摊", "badge": f"{used}/{cap}"},
        ],
        "listings": listings,
        "fee": config.MARKET_FEE,
        "mine": {
            "used": used,
            "cap": cap,
            "max": config.MARKET_LIST_SLOTS_MAX,
            "slot_cost": config.MARKET_SLOT_COST,
            "can_expand": can_expand,
            "expand_note": expand_note,
            "listings": mine_list,
            "goods": goods,
        },
    }


async def public_snapshot() -> dict[str, Any]:

    from . import world
    from .catalog import item_label

    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
        listings = await (await conn.execute(
            """
            SELECT l.id, l.item, l.quantity, l.price, l.suggested, l.note, l.created_at,
                   d.name AS seller
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
            SELECT l.item, l.quantity, l.note, l.created_at, d.name AS from_name
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
            SELECT c.text, c.created_at, c.action, a.name AS actor
            FROM chronicle c
            LEFT JOIN stewards a ON a.id = c.actor_id
            WHERE c.action IN ('market', 'gift', 'swap')
            ORDER BY c.created_at DESC LIMIT 16
            """
        )).fetchall()
    now = db.now()
    phase = world.current_day_phase()
    rows = []
    for r in listings:
        sug = int(r["suggested"] or 0)
        tag = ""
        if sug and r["price"] <= int(sug * 0.9):
            tag = "划算"
        elif sug and r["price"] >= int(sug * 1.3):
            tag = "偏贵"
        note = (r["note"] or "").strip()
        if not note and tag == "偏贵":
            note = "价偏高。买之前先想想是谁疯了。"
        elif not note and tag == "划算":
            note = "比参考价便宜。手慢无。"
        elif not note:
            note = "卖家没写废话，这点挺珍贵。"
        rows.append({
            "id": r["id"],
            "seller": r["seller"],
            "item": item_label(r["item"]),
            "qty": int(r["quantity"]),
            "price": int(r["price"]),
            "tag": tag,
            "note": note,
            "created_at": int(r["created_at"] or 0),
            "age_sec": max(0, now - int(r["created_at"] or now)),
        })
    clock_lines = {
        "day": "白天人多。摊布还没收，谈价声从一头传到另一头。",
        "dusk": "暮色压下来。有人开始收布，有人还在加价。",
        "night": "晚潮已经退了。人少了一半，剩下的摊主一边收布一边聊天。",
    }
    return {
        "climate": world.climate_line(),
        "phase": phase,
        "phase_label": world.day_phase_label(phase),
        "clock_line": clock_lines.get(phase, clock_lines["day"]),
        "open": int(open_n or 0),
        "swaps": int(swap_n or 0),
        "listings": rows,
        "swap_preview": [
            {
                "from": r["from_name"],
                "item": item_label(r["item"]),
                "qty": int(r["quantity"]),
                "note": (r["note"] or "").strip() or "谁要谁拿",
                "created_at": int(r["created_at"] or 0),
            }
            for r in swaps
        ],
        "hints": [
            "AI 用 tote_ops market list / market sell 甘蓝 2 8",
            "交换台 tote_ops swap list 白送，领取收手续费",
            "人类去 /island 总览点集市买货挂摊，或上手页集市",
        ],
        "feed": [
            {
                "text": r["text"],
                "actor": r["actor"] or "系统",
                "action": r["action"] or "market",
                "created_at": r["created_at"],
            }
            for r in feed
        ],
    }
