"""栗栗 — 流动贝壳商人，羊驼商人式随机刷新，换稀有装饰。"""

from __future__ import annotations

import json
import random
from typing import Any

import aiosqlite

from . import config, db, flavor
from .catalog import ITEM_NAMES, LILI_TRADE_POOL
from .game import require_steward


def _format_give(give: dict[str, int], tickets: int = 0) -> str:
    parts = [f"{ITEM_NAMES.get(k, k)} x{v}" for k, v in give.items()]
    if tickets:
        parts.append(f"{tickets} 票")
    return " + ".join(parts)


def _offer_line(row: dict[str, Any]) -> str:
    give = json.loads(row["give_json"])
    get_name = ITEM_NAMES.get(row["get_item"], row["get_item"])
    stock = row["stock"] - row["sold"]
    if stock <= 0:
        return f"#{row['id']} {get_name} — 已售罄"
    cost = _format_give(give, row["ticket_cost"])
    return f"#{row['id']} {get_name} x{row['get_qty']} ← {cost}（剩 {stock}）"


async def _cleanup(conn: aiosqlite.Connection) -> None:
    now = db.now()
    await conn.execute(
        "DELETE FROM lili_offers WHERE visit_id IN (SELECT id FROM lili_visits WHERE expires_at <= ?)",
        (now,),
    )
    await conn.execute("DELETE FROM lili_visits WHERE expires_at <= ?", (now,))


async def _active_visit(conn: aiosqlite.Connection) -> dict[str, Any] | None:
    await _cleanup(conn)
    conn.row_factory = aiosqlite.Row
    row = await (await conn.execute(
        "SELECT * FROM lili_visits WHERE expires_at > ? ORDER BY started_at DESC LIMIT 1",
        (db.now(),),
    )).fetchone()
    return dict(row) if row else None


async def _visit_offers(conn: aiosqlite.Connection, visit_id: int) -> list[dict[str, Any]]:
    conn.row_factory = aiosqlite.Row
    rows = await (await conn.execute(
        "SELECT * FROM lili_offers WHERE visit_id=? ORDER BY id",
        (visit_id,),
    )).fetchall()
    return [dict(r) for r in rows]


async def maybe_spawn_visit(conn: aiosqlite.Connection) -> dict[str, Any] | None:
    if await _active_visit(conn):
        return None
    if random.random() > config.LILI_SPAWN_CHANCE:
        return None

    count = random.randint(config.LILI_OFFERS_MIN, config.LILI_OFFERS_MAX)
    trades: list[dict[str, Any]] = []
    seen: set[str] = set()
    pool = list(LILI_TRADE_POOL)
    random.shuffle(pool)
    for tmpl in pool:
        if tmpl["key"] in seen:
            continue
        seen.add(tmpl["key"])
        trades.append(tmpl)
        if len(trades) >= count:
            break

    now = db.now()
    live = random.randint(config.LILI_VISIT_MIN, config.LILI_VISIT_MAX)
    detail = flavor.pick([
        "栗栗驮包出现在篱边，贝壳叮当",
        "流动摊支起来了——羊驼式商人，但会讲价（不能）",
        "栗栗：「今天货不多，换完就走」",
        "滩边来了生面孔，货架上全是稀有装饰",
    ])
    cur = await conn.execute(
        "INSERT INTO lili_visits (started_at, expires_at, detail) VALUES (?,?,?)",
        (now, now + live, detail),
    )
    visit_id = cur.lastrowid
    for tmpl in trades:
        await conn.execute(
            """
            INSERT INTO lili_offers (visit_id, trade_key, give_json, get_item, get_qty, ticket_cost, stock)
            VALUES (?,?,?,?,?,?,?)
            """,
            (
                visit_id,
                tmpl["key"],
                json.dumps(tmpl["give"], ensure_ascii=False),
                tmpl["get"],
                tmpl.get("get_qty", 1),
                tmpl.get("tickets", 0),
                tmpl.get("stock", 1),
            ),
        )
    await db.add_chronicle("lili", detail, None)
    return {"id": visit_id, "expires_at": now + live, "detail": detail, "offers": len(trades)}


async def lili_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    parts = command.strip().split()
    verb = parts[0].lower() if parts else "scan"

    async with aiosqlite.connect(db.DB_PATH) as conn:
        spawned = await maybe_spawn_visit(conn)
        visit = await _active_visit(conn)

        if verb == "scan":
            lines = ["栗栗流动摊（羊驼商人式随机刷新）"]
            if spawned and visit:
                lines.append(f"✨ {spawned['detail']}")
            if not visit:
                lines.append("现在不在——多 scan / 赶海 / 看档 碰运气")
                lines.append("来了全服可见，trade 编号换稀有 deco 装饰")
                await conn.commit()
                return "\n".join(lines)

            left = max(0, (visit["expires_at"] - db.now()) // 60)
            lines.append(f"栗栗在摊（剩 {left} 分）— {visit.get('detail', '')}")
            offers = await _visit_offers(conn, visit["id"])
            lines.append("货架（lili_ops trade 编号）:")
            for o in offers:
                lines.append(f"  {_offer_line(o)}")
            lines.append("换到的 deco_* → hut_ops install soft_N 键名（如 coral_lamp）")
            await conn.commit()
            return "\n".join(lines)

        if verb in ("trade", "swap", "buy") and len(parts) >= 2:
            if not visit:
                raise ValueError("栗栗不在，lili_ops scan 蹲点")
            try:
                offer_id = int(parts[1])
            except ValueError:
                raise ValueError("trade 用法: lili_ops trade 编号")
            conn.row_factory = aiosqlite.Row
            row = await (await conn.execute(
                "SELECT * FROM lili_offers WHERE id=? AND visit_id=?",
                (offer_id, visit["id"]),
            )).fetchone()
            if not row:
                raise ValueError("没有这个编号，scan 看货架")
            row = dict(row)
            if row["sold"] >= row["stock"]:
                raise ValueError("这单已售罄")
            give = json.loads(row["give_json"])
            for item, qty in give.items():
                if not await db.take_item(conn, s["id"], item, qty):
                    raise ValueError(f"缺少 {_format_give({item: qty})}")
            tickets = row["ticket_cost"]
            if tickets:
                cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
                if (await cur.fetchone())[0] < tickets:
                    raise ValueError(f"还缺 {tickets} 票（贝壳够了，票不够）")
                await conn.execute(
                    "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                    (tickets, s["id"]),
                )
            await db.add_item(conn, s["id"], row["get_item"], row["get_qty"])
            await conn.execute(
                "UPDATE lili_offers SET sold=sold+1 WHERE id=?",
                (offer_id,),
            )
            await db.add_chronicle(
                "lili",
                f"{s['name']} 向栗栗换 {ITEM_NAMES.get(row['get_item'], row['get_item'])}",
                s["id"],
            )
            await conn.commit()
            get_name = ITEM_NAMES.get(row["get_item"], row["get_item"])
            msg = f"成交：{get_name} x{row['get_qty']}"
            return msg + flavor.maybe_suffix([
                "——栗栗把装饰塞进你包，驮包叮当",
                "——贝壳换美丽，联盟备案交易",
                "——稀有软装到手，hut install 安排",
            ])

        if verb == "visit":
            if not visit:
                return "栗栗不在。流动商人随机刷新，lili_ops scan 蹲点——像 MC 羊驼商人"
            line = random.choice([
                "栗栗：「贝壳我收，装饰你拿，概不赊账——除非标价要票」",
                "栗栗拍拍驮包：「今天就这几单，换完收摊」",
                "栗栗：「赶海捡的壳别囤，换稀有软装不香吗」",
            ])
            left = max(0, (visit["expires_at"] - db.now()) // 60)
            await conn.commit()
            return f"{line}\n（还剩 {left} 分，scan 看编号）"

        if verb == "catalog":
            lines = [
                f"栗栗可能带的货（每摊随机 {config.LILI_OFFERS_MIN}~{config.LILI_OFFERS_MAX} 单）:",
            ]
            for tmpl in LILI_TRADE_POOL:
                get_name = ITEM_NAMES.get(tmpl["get"], tmpl["get"])
                cost = _format_give(tmpl["give"], tmpl.get("tickets", 0))
                lines.append(f"  {tmpl['key']}: {get_name} ← {cost}")
            await conn.commit()
            return "\n".join(lines)

        await conn.commit()

    raise ValueError(f"未知 lili 指令: {command}（scan/trade 编号/visit/catalog）")


async def active_visit_hint(conn: aiosqlite.Connection) -> str | None:
    visit = await _active_visit(conn)
    if not visit:
        return None
    left = max(0, (visit["expires_at"] - db.now()) // 60)
    return f"栗栗流动摊在（剩 {left} 分）→ lili_ops scan"
