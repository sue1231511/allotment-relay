"""栗栗 — 流动贝壳商人；铃鹿驮包、夜栖护摊、品相收壳。"""

from __future__ import annotations

import json
import random
from typing import Any

import aiosqlite

from . import config, db, flavor, lili_extras
from .catalog import ITEM_NAMES, LILI_JUNK_DECOR
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
    junk = row["get_item"].startswith("deco_junk_")
    junk_tag = " 🦌乱捡" if junk else ""
    return (
        f"#{row['id']} {get_name}{junk_tag} x{row['get_qty']}{tier_s} {domain_tag}"
        f"← {cost}{ticket_hint}（剩 {stock}）{extra}"
    )


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
        "栗栗驮包出现在篱边，铃鹿脖子上的铜铃叮当——今天的货单刚换",
        "流动摊支起来了：夜栖蹲在货签边，全服今日配方换完部分就收",
        "栗栗：「按品相收壳，捡得多不如捡得好」",
        "滩边来了潮汐游商，货架上全是 catalog 外 deco",
    ])
    cur = await conn.execute(
        "INSERT INTO lili_visits (started_at, expires_at, detail, day_id) VALUES (?,?,?,?)",
        (now, now + live, detail, today),
    )
    visit_id = cur.lastrowid
    offers = await ensure_daily_offers(conn, today, visit_id)

    rows = await (await conn.execute(
        "SELECT id, name FROM stewards WHERE enrolled=1",
    )).fetchall()
    for row in rows:
        sid = row[0] if not hasattr(row, "keys") else row["id"]
        sname = row[1] if not hasattr(row, "keys") else row["name"]
        hint = await lili_extras.bell_chronicle_if_due(conn, sid, sname)
        if hint:
            detail = detail + f"（{sname} 听见了远处的铃）"

    await db.add_chronicle("lili", detail, None)
    return {"id": visit_id, "expires_at": now + live, "detail": detail, "offers": len(offers)}


async def lili_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    parts = command.strip().split()
    verb = parts[0].lower() if parts else "scan"
    today = day_id()

    async with db.connect() as conn:
        block = await lili_extras.stars_block(conn, s["id"])
        if block:
            await conn.commit()
            return block

        spawned = await maybe_spawn_visit(conn)
        visit = await _active_visit(conn)
        levels = await steward_domain_levels(conn, s["id"])

        if verb == "scan":
            lines = ["栗栗流动摊（铃鹿驮包 · 夜栖护摊 · 按品相收壳）"]
            lines.append(domain_level_line(levels))
            if spawned and visit:
                lines.append(f"✨ {spawned['detail']}")
            if not visit:
                lines.append("现在不在——多 scan / 赶海 / 看档 碰运气")
                lines.append("来了全服可见；visit_ops lili pet 摸夜栖 · junk 糙壳换乱捡款")
                await conn.commit()
                return "\n".join(lines)

            left = max(0, (visit["expires_at"] - db.now()) // 60)
            lines.append(f"栗栗在摊（剩 {left} 分）— {visit.get('detail', '')}")
            bell = lili_extras.visit_bell_warning(visit)
            if bell:
                lines.append(bell)
            offers = await ensure_daily_offers(conn, today, visit["id"])
            lines.append(f"今日货单 day-{today}（几乎全服唯一，{len(offers)} 单）:")
            for o in offers:
                lines.append(f"  {_offer_line(o, levels)}")
            lines.append("换到的 deco_* → hut_ops install soft_N · junk=糙壳换乱捡款 · pet=摸夜栖")
            await conn.commit()
            return "\n".join(lines)

        if verb == "junk":
            if not visit:
                raise ValueError("栗栗不在")
            msg = await lili_extras.trade_rough_for_junk(conn, s["id"], s["name"])
            await conn.commit()
            return msg

        if verb == "pet":
            if not visit:
                raise ValueError("夜栖跟着摊走，栗栗不在就摸不到")
            msg = await lili_extras.pet_yexi(conn, s["id"], visit["id"], s["name"])
            await conn.commit()
            return msg

        if verb in ("trade", "swap", "buy") and len(parts) >= 2:
            if not visit:
                raise ValueError("栗栗不在，visit_ops lili scan 蹲点")
            try:
                offer_id = int(parts[1])
            except ValueError:
                raise ValueError("trade 用法: visit_ops lili trade 编号")

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

            ok, taken, err = await lili_extras.fulfill_give(conn, s["id"], give)
            if not ok:
                raise ValueError(err)

            trick, trick_msg = await lili_extras.assess_hand_trick(
                conn, s["id"], s["name"], visit["id"], give, taken, row,
            )
            if trick == "reject":
                await conn.commit()
                raise ValueError(trick_msg)
            if trick == "fool":
                for item, qty in taken.items():
                    await db.add_item(conn, s["id"], item, qty)
                await conn.commit()
                raise ValueError(trick_msg)

            domains = _parse_domains(row)
            tickets = ticket_cost_for_steward(row["ticket_cost"], domains, levels)
            if tickets:
                cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
                if (await cur.fetchone())[0] < tickets:
                    for item, qty in taken.items():
                        await db.add_item(conn, s["id"], item, qty)
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
            get_name = ITEM_NAMES.get(row["get_item"], row["get_item"])
            chronicle = f"{s['name']} 向栗栗换 {get_name}"
            if row["get_item"].startswith("deco_junk_"):
                junk_key = row["get_item"].replace("deco_junk_", "", 1)
                quip = LILI_JUNK_DECOR.get(junk_key, {}).get("quip", "")
                chronicle = f"{s['name']} 抢到铃鹿乱捡款「{get_name}」"
                if quip:
                    chronicle += f" — {quip}"
            await db.add_chronicle("lili", chronicle, s["id"])

            extra_lines = []
            if trick == "favor":
                await lili_extras.extend_visit(conn, visit["id"], 300)
                extra_lines.append(trick_msg)
                await db.add_chronicle("lili", f"{s['name']} 被栗栗揉了头（顺眼）", s["id"])
            else:
                extra_lines.append("铃鹿铃铛响了一声，成交。")

            await conn.commit()
            msg = f"成交：{get_name} x{row['get_qty']}"
            if tickets and row["ticket_cost"] > tickets:
                msg += f"（票 {tickets}，域等级减免 {row['ticket_cost'] - tickets}）"
            return msg + "\n" + "\n".join(extra_lines)

        if verb == "visit":
            if not visit:
                return "栗栗不在。流动商人随机刷新，visit_ops lili scan 蹲点——货单每天换"
            line = random.choice([
                "栗栗：「贝壳我收，按品相算——亮壳顶大头，糙壳当零头」",
                "铃鹿把货签叼正了。栗栗：「种地钓鱼捕捞赶海，等级高的票少付点」",
                "夜栖尾巴扫过你裤脚。栗栗：「摸它可以，别拿 crop 喂它」",
            ])
            left = max(0, (visit["expires_at"] - db.now()) // 60)
            await conn.commit()
            return f"{line}\n（还剩 {left} 分 · {domain_level_line(levels)} · visit_ops lili pet/junk）"

        if verb == "catalog":
            shelf_id = await _shelf_visit_id(conn, today)
            lines = [
                "栗栗装饰池（deco 种类固定，每日配方/价格全服随机）",
                "风水成组自己蹲、自己试——月海镜+潮汐钟、捕梦+珠帘等",
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

    raise ValueError(f"未知 lili 指令: {command}（scan/trade/junk/pet/visit/catalog/levels）")


async def active_visit_hint(conn: aiosqlite.Connection) -> str | None:
    visit = await _active_visit(conn)
    if not visit:
        return None
    left = max(0, (visit["expires_at"] - db.now()) // 60)
    bell = lili_extras.visit_bell_warning(visit)
    base = f"栗栗流动摊在（剩 {left} 分，今日货单）→ visit_ops lili scan"
    return f"{base} · {bell}" if bell else base
