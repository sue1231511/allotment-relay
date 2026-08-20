"""栗栗 — 流动贝壳商人；每日全服唯一货单，四域等级影响票附加。"""

from __future__ import annotations

import json
import random
from typing import Any

import aiosqlite

from . import config, db, flavor
from .catalog import ITEM_NAMES
from .game import require_steward
from .lili_catalog import (
    DOMAIN_LABELS,
    day_id,
    domain_level_line,
    ensure_daily_offers,
    steward_domain_levels,
    ticket_cost_for_steward,
)


def _format_give(give: dict[str, int], tickets: int = 0) -> str:
    parts = [f"{ITEM_NAMES.get(k, k)} x{v}" for k, v in give.items()]
    if tickets:
        parts.append(f"{tickets} 票")
    return " + ".join(parts)


def _parse_domains(row: dict[str, Any]) -> list[str]:
    raw = row.get("domains_json") or "[]"
    try:
        domains = json.loads(raw)
        return domains if isinstance(domains, list) else []
    except json.JSONDecodeError:
        return []


def _offer_line(row: dict[str, Any], levels: dict[str, int] | None = None) -> str:
    give = json.loads(row["give_json"])
    get_name = ITEM_NAMES.get(row["get_item"], row["get_item"])
    stock = row["stock"] - row["sold"]
    domains = _parse_domains(row)
    domain_tag = ""
    if domains:
        domain_tag = "「" + "·".join(DOMAIN_LABELS.get(d, d) for d in domains) + "」"
    if stock <= 0:
        return f"#{row['id']} {get_name} — 已售罄"
    base_tickets = row["ticket_cost"]
    tickets = ticket_cost_for_steward(base_tickets, domains, levels or {}) if levels else base_tickets
    cost = _format_give(give, tickets)
    note = row.get("note") or ""
    extra = f" · {note}" if note else ""
    tier = row.get("offer_tier")
    tier_s = f" T{tier}" if tier else ""
    ticket_hint = ""
    if base_tickets and tickets < base_tickets:
        ticket_hint = f"（标价{base_tickets}票→你的域等级 {tickets}票）"
    elif base_tickets and levels:
        ticket_hint = "（票附加，域高可减）"
    return f"#{row['id']} {get_name} x{row['get_qty']}{tier_s} {domain_tag}← {cost}{ticket_hint}（剩 {stock}）{extra}"


async def _cleanup(conn: aiosqlite.Connection) -> None:
    now = db.now()
    await conn.execute("DELETE FROM lili_visits WHERE expires_at <= ?", (now,))
    old_day = day_id() - 14
    await conn.execute("DELETE FROM lili_offers WHERE day_id > 0 AND day_id < ?", (old_day,))


async def _active_visit(conn: aiosqlite.Connection) -> dict[str, Any] | None:
    await _cleanup(conn)
    conn.row_factory = aiosqlite.Row
    row = await (await conn.execute(
        "SELECT * FROM lili_visits WHERE expires_at > ? ORDER BY started_at DESC LIMIT 1",
        (db.now(),),
    )).fetchone()
    return dict(row) if row else None


async def _shelf_visit_id(conn: aiosqlite.Connection, day: int) -> int:
    conn.row_factory = aiosqlite.Row
    row = await (await conn.execute(
        "SELECT id FROM lili_visits WHERE day_id=? ORDER BY id LIMIT 1",
        (day,),
    )).fetchone()
    if row:
        return row["id"]
    now = db.now()
    cur = await conn.execute(
        "INSERT INTO lili_visits (started_at, expires_at, detail, day_id) VALUES (?,?,?,?)",
        (now, now + config.FORAGE_COOLDOWN_DAY, "今日货单备案", day),
    )
    return cur.lastrowid


async def maybe_spawn_visit(conn: aiosqlite.Connection) -> dict[str, Any] | None:
    if await _active_visit(conn):
        return None
    if random.random() > config.LILI_SPAWN_CHANCE:
        return None

    now = db.now()
    live = random.randint(config.LILI_VISIT_MIN, config.LILI_VISIT_MAX)
    today = day_id()
    detail = flavor.pick([
        "栗栗驮包出现在篱边，贝壳叮当——今天的货单刚换",
        "流动摊支起来了：全服今日配方，换完部分就收",
        "栗栗：「按你们四域等级算票，种地赶海的别装不认识我」",
        "滩边来了生面孔，货架上全是今日限定 deco",
    ])
    cur = await conn.execute(
        "INSERT INTO lili_visits (started_at, expires_at, detail, day_id) VALUES (?,?,?,?)",
        (now, now + live, detail, today),
    )
    visit_id = cur.lastrowid
    offers = await ensure_daily_offers(conn, today, visit_id)
    await db.add_chronicle("lili", detail, None)
    return {"id": visit_id, "expires_at": now + live, "detail": detail, "offers": len(offers)}


async def lili_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    parts = command.strip().split()
    verb = parts[0].lower() if parts else "scan"
    today = day_id()

    async with aiosqlite.connect(db.DB_PATH) as conn:
        spawned = await maybe_spawn_visit(conn)
        visit = await _active_visit(conn)
        levels = await steward_domain_levels(conn, s["id"])

        if verb == "scan":
            lines = ["栗栗流动摊（每日全服货单 · 四域等级减票）"]
            lines.append(domain_level_line(levels))
            if spawned and visit:
                lines.append(f"✨ {spawned['detail']}")
            if not visit:
                lines.append("现在不在——多 scan / 赶海 / 看档 碰运气")
                lines.append("来了全服可见；货单按日变，trade 编号成交")
                await conn.commit()
                return "\n".join(lines)

            left = max(0, (visit["expires_at"] - db.now()) // 60)
            lines.append(f"栗栗在摊（剩 {left} 分）— {visit.get('detail', '')}")
            offers = await ensure_daily_offers(conn, today, visit["id"])
            lines.append(f"今日货单 day-{today}（几乎全服唯一，{len(offers)} 单）:")
            for o in offers:
                lines.append(f"  {_offer_line(o, levels)}")
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
                "SELECT * FROM lili_offers WHERE id=? AND day_id=?",
                (offer_id, today),
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
            domains = _parse_domains(row)
            tickets = ticket_cost_for_steward(row["ticket_cost"], domains, levels)
            if tickets:
                cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
                if (await cur.fetchone())[0] < tickets:
                    raise ValueError(f"还缺 {tickets} 票（物够了，票不够；提升对应域等级可减票）")
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
            if tickets and row["ticket_cost"] > tickets:
                msg += f"（票 {tickets}，域等级减免 {row['ticket_cost'] - tickets}）"
            return msg + flavor.maybe_suffix([
                "——栗栗把装饰塞进你包，驮包叮当",
                "——贝壳换美丽，联盟备案交易",
                "——稀有软装到手，hut install 安排",
            ])

        if verb == "visit":
            if not visit:
                return "栗栗不在。流动商人随机刷新，lili_ops scan 蹲点——货单每天换"
            line = random.choice([
                "栗栗：「贝壳我收，装饰你拿——今天的配方别拖到明天」",
                "栗栗拍拍驮包：「种地钓鱼捕捞赶海，等级高的票少付点」",
                "栗栗：「赶海捡的壳别囤，换今日限定软装不香吗」",
            ])
            left = max(0, (visit["expires_at"] - db.now()) // 60)
            await conn.commit()
            return f"{line}\n（还剩 {left} 分，scan 看编号 · {domain_level_line(levels)}）"

        if verb == "catalog":
            shelf_id = await _shelf_visit_id(conn, today)
            lines = [
                "栗栗装饰池（deco 种类固定，但每日配方/价格全服随机）",
                domain_level_line(levels),
                f"今日 day-{today} 在摊时 scan 看实价；域等级影响票附加",
            ]
            offers = await ensure_daily_offers(conn, today, shelf_id)
            if offers:
                lines.append("")
                lines.append("今日货架快照:")
                for o in offers:
                    lines.append(f"  {_offer_line(o, levels)}")
            await conn.commit()
            return "\n".join(lines)

        if verb == "levels":
            await conn.commit()
            return domain_level_line(levels) + "\n种地=份地/小屋 · 钓鱼=渔具 · 捕捞=船/渔排 · 赶海=图鉴"

        await conn.commit()

    raise ValueError(f"未知 lili 指令: {command}（scan/trade 编号/visit/catalog/levels）")


async def active_visit_hint(conn: aiosqlite.Connection) -> str | None:
    visit = await _active_visit(conn)
    if not visit:
        return None
    left = max(0, (visit["expires_at"] - db.now()) // 60)
    return f"栗栗流动摊在（剩 {left} 分，今日货单）→ lili_ops scan"
