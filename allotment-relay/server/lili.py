"""栗栗 — 流动贝壳商人；铃鹿驮包、夜栖护摊、品相收壳。"""

from __future__ import annotations

import json
import random
from typing import Any

import aiosqlite

from . import config, db, flavor, lili_extras
from .catalog import ITEM_NAMES, ITEM_PRICES, LILI_DECOR, LILI_JUNK_DECOR
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
        """
        SELECT * FROM lili_visits
        WHERE expires_at > ? AND detail != '今日货单备案'
        ORDER BY started_at DESC LIMIT 1
        """,
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


async def _open_visit(
    conn: aiosqlite.Connection,
    seconds: int,
    detail: str,
    *,
    announce: bool = True,
) -> dict[str, Any]:
    now = db.now()
    today = day_id()
    cur = await conn.execute(
        "INSERT INTO lili_visits (started_at, expires_at, detail, day_id) VALUES (?,?,?,?)",
        (now, now + seconds, detail, today),
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

    if announce:
        await db.add_chronicle("lili", detail, None, conn=conn)
    return {"id": visit_id, "expires_at": now + seconds, "detail": detail, "offers": len(offers)}


async def maybe_spawn_visit(conn: aiosqlite.Connection) -> dict[str, Any] | None:
    if await _active_visit(conn):
        return None
    if random.random() > config.LILI_SPAWN_CHANCE:
        return None
    live = random.randint(config.LILI_VISIT_MIN, config.LILI_VISIT_MAX)
    detail = flavor.pick([
        "栗栗驮包出现在篱边，铃鹿脖子上的铜铃叮当——今天的货单刚换",
        "流动摊支起来了：夜栖蹲在货签边，全服今日配方换完部分就收",
        "栗栗：「按品相收壳，捡得多不如捡得好」",
        "滩边来了潮汐游商，货架上全是 catalog 外 deco",
    ])
    return await _open_visit(conn, live, detail)


async def _ensure_summon_stay(conn: aiosqlite.Connection, visit: dict[str, Any], seconds: int) -> dict[str, Any]:
    left = max(0, visit["expires_at"] - db.now())
    need = seconds - left
    if need > 0:
        await lili_extras.extend_visit(conn, visit["id"], need)
        visit = dict(visit)
        visit["expires_at"] = visit["expires_at"] + need
    return visit


async def _do_summon(conn: aiosqlite.Connection, s: dict[str, Any], token: str) -> str:
    item = lili_extras.resolve_summon_item(token)
    if not item:
        raise ValueError("用法: visit_ops lili summon 贝壳id（tote_ops list 看行囊，例 shell_catseye）")
    label = ITEM_NAMES.get(item, item)
    grade = lili_extras.summon_grade(item)
    grade_name = lili_extras.SUMMON_GRADE_LABEL[grade]

    if not await db.take_item(conn, s["id"], item, 1):
        raise ValueError(f"行囊没有 {label}（{item}）")

    st = await lili_extras.load_summon_state(conn, s["id"])
    first = not int(st.get("summon_done") or 0)
    stored = int(st.get("summon_chance") or config.LILI_SUMMON_BASE)
    visit = await _active_visit(conn)
    already = visit is not None
    roll_chance = 100 if first else stored
    success = already or random.random() * 100 < roll_chance
    new_chance, delta = lili_extras.next_summon_chance(
        stored if not first else config.LILI_SUMMON_BASE, grade,
    )
    await lili_extras.save_summon_state(conn, s["id"], new_chance)
    delta_line = (
        f"下次成功率 {new_chance}%"
        + (f"（{'+' if delta > 0 else ''}{delta}%）" if delta else "（不变）")
    )

    if not success:
        return (
            f"海风把 {label} 的气息吹散了。这次没人来。\n"
            f"献上的是{grade_name}。{delta_line}"
        )

    if visit is None:
        detail = f"海风里有贝壳味——栗栗被 {s['name']} 唤到滩头"
        visit = await _open_visit(
            conn, config.LILI_SUMMON_LIVE, detail, announce=grade not in ("rare", "junk"),
        )
        already = False

    lines: list[str] = []
    if grade == "rare":
        visit = await _ensure_summon_stay(conn, visit, config.LILI_SUMMON_LIVE)
        pay = lili_extras.summon_payout(item, grade)
        await conn.execute(
            "UPDATE stewards SET tickets=tickets+? WHERE id=?", (pay, s["id"]),
        )
        gift_item, gift_qty = lili_extras.pick_summon_gift()
        await db.add_item(conn, s["id"], gift_item, gift_qty)
        from . import energy
        tea = await energy.restore(conn, s["id"], 8)
        gift_name = ITEM_NAMES.get(gift_item, gift_item)
        broadcast = (
            f"🌊 海风卷着铜铃声掠过滩头——{s['name']} 手中的极品贝壳引来了游商【栗栗】！"
            f"护摊犬【夜栖】已在街角支起货架，限时停靠 30 分钟！"
        )
        await db.add_chronicle("lili", broadcast, None, conn=conn)
        await db.add_chronicle("lili", f"{s['name']} 献上极品 {label}，栗栗双眼放光", s["id"], conn=conn)
        lines.append("栗栗双眼放光，抬手把你头发揉乱。夜栖欢快摇尾，端出一碗热茶。")
        lines.append(broadcast)
        tea_note = f"，热茶回精力 {tea}" if tea else ""
        lines.append(f"收购 {label} +{pay} 票（极品加三成），附赠 {gift_name} x{gift_qty}{tea_note}")
    elif grade == "junk":
        await lili_extras.shorten_visit(conn, visit["id"], config.LILI_SUMMON_JUNK_CUT)
        await conn.execute(
            "UPDATE stewards SET tickets = MAX(0, tickets-?) WHERE id=?",
            (config.LILI_SUMMON_FEE, s["id"]),
        )
        broadcast = (
            f"💥 {s['name']} 试图用一块发臭的泥壳糊弄游商，被【栗栗】当场弹了脑壳，"
            f"【夜栖】把货架往后拉了拉，并降低了下次引商概率！"
        )
        await db.add_chronicle("lili", broadcast, None, conn=conn)
        await db.add_chronicle("lili", f"{s['name']} 被栗栗弹了脑壳（引商翻车）", s["id"], conn=conn)
        lines.append("栗栗当场弹了你脑壳。夜栖龇牙轻哼，护住摊位账本。")
        lines.append(broadcast)
        lines.append(f"扣 {config.LILI_SUMMON_FEE} 票辛苦费，游商提前 10 分钟收摊。")
    elif grade == "good":
        pay = lili_extras.summon_payout(item, grade)
        await conn.execute(
            "UPDATE stewards SET tickets=tickets+? WHERE id=?", (pay, s["id"]),
        )
        lines.append("栗栗满意点头，验货盖章。夜栖在账本上划了一笔。")
        lines.append(f"足额收下 {label}，+{pay} 票。摊已支起，visit_ops lili scan 看货架。")
    else:
        pay = lili_extras.summon_payout(item, grade)
        await conn.execute(
            "UPDATE stewards SET tickets=tickets+? WHERE id=?", (pay, s["id"]),
        )
        lines.append("栗栗挑了挑眉，勉强收下。夜栖把账本护得更紧了些。")
        lines.append(f"换得基础工分票 +{pay}。摊已支起，visit_ops lili scan 看货架。")

    visit = await _active_visit(conn)
    if visit:
        left = max(0, (visit["expires_at"] - db.now()) // 60)
        stay = f"已在摊，剩 {left} 分" if already else f"停靠约 {left} 分"
    else:
        stay = "她已经把摊收了"
    if first:
        lines.append("（第一次寄气息，海风这次一定把她送来了）")
    lines.append(f"{stay}。{delta_line}")
    return "\n".join(lines)


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

        spawned = None
        if verb not in ("summon", "唤", "引商", "call"):
            spawned = await maybe_spawn_visit(conn)
        visit = await _active_visit(conn)
        levels = await steward_domain_levels(conn, s["id"])

        if verb in ("summon", "唤", "引商", "call"):
            token = " ".join(parts[1:]).strip()
            if not token:
                raise ValueError("用法: visit_ops lili summon 贝壳id（例 shell_catseye / ✨亮壳·🐚猫眼螺）")
            msg = await _do_summon(conn, s, token)
            await conn.commit()
            return msg

        if verb == "scan":
            lines = ["栗栗流动摊（铃鹿驮包 · 夜栖护摊 · 按品相收壳）"]
            lines.append(domain_level_line(levels))
            if spawned and visit:
                lines.append(f"✨ {spawned['detail']}")
            if not visit:
                st = await lili_extras.load_summon_state(conn, s["id"])
                lines.append("现在不在——赶海捡壳后 visit_ops lili summon 贝壳 可向海风寄气息")
                lines.append(lili_extras.summon_rate_line(st) + " · pet 摸夜栖 · junk 糙壳换乱捡款")
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
            lines.append("换到的 deco_* → hut_ops install soft_N · summon=献壳唤摊 · junk=糙壳换乱捡款 · pet=摸夜栖")
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
            await db.add_chronicle("lili", chronicle, s["id"], conn=conn)

            extra_lines = []
            if trick == "favor":
                await lili_extras.extend_visit(conn, visit["id"], 300)
                extra_lines.append(trick_msg)
                await db.add_chronicle("lili", f"{s['name']} 被栗栗揉了头（顺眼）", s["id"], conn=conn)
            else:
                extra_lines.append("铃鹿铃铛响了一声，成交。")

            await conn.commit()
            msg = f"成交：{get_name} x{row['get_qty']}"
            if tickets and row["ticket_cost"] > tickets:
                msg += f"（票 {tickets}，域等级减免 {row['ticket_cost'] - tickets}）"
            return msg + "\n" + "\n".join(extra_lines)

        if verb == "visit":
            if not visit:
                return "栗栗不在。赶海捡壳后 visit_ops lili summon 贝壳 可唤摊；scan 也会碰运气"
            line = random.choice([
                "栗栗：「贝壳我收，按品相算——亮壳顶大头，糙壳当零头」",
                "铃鹿把货签叼正了。栗栗：「种地钓鱼捕捞赶海，等级高的票少付点」",
                "夜栖尾巴扫过你裤脚。栗栗：「摸它可以，别拿 crop 喂它」",
            ])
            left = max(0, (visit["expires_at"] - db.now()) // 60)
            await conn.commit()
            return f"{line}\n（还剩 {left} 分 · {domain_level_line(levels)} · visit_ops lili pet/junk/summon）"

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

    raise ValueError(f"未知 lili 指令: {command}（scan/trade/junk/pet/summon/visit/catalog/levels）")


def _item_emoji(key: str) -> str:
    if key.startswith("deco_junk_"):
        meta = LILI_JUNK_DECOR.get(key.replace("deco_junk_", "", 1)) or {}
        return str(meta.get("emoji") or "🦌")
    if key.startswith("deco_"):
        meta = LILI_DECOR.get(key.replace("deco_", "", 1)) or {}
        return str(meta.get("emoji") or "🐚")
    if key.startswith("shell_"):
        return "🐚"
    return "🌰"


def _sku(
    *,
    sid: str,
    kind: str,
    name: str,
    note: str,
    price: str,
    can: bool,
    emoji: str = "·",
    detail: str = "",
    target: str = "",
) -> dict[str, Any]:
    return {
        "id": sid,
        "kind": kind,
        "name": name,
        "emoji": emoji,
        "note": note,
        "detail": detail or note,
        "price": price,
        "can": can,
        "target": target or sid,
    }


def _give_ready(stock: dict[str, int], give: dict[str, int]) -> tuple[bool, str]:
    taken: dict[str, int] = {}
    for req_item, req_qty in give.items():
        base_shell = lili_extras.parse_shell(req_item)
        if base_shell and base_shell[0] == req_item and base_shell[1] == "normal":
            need_value = lili_extras.item_trade_value(req_item, req_qty)
            got_value = 0
            variants = [
                lili_extras.shell_item_key(req_item, "shine"),
                req_item,
                lili_extras.shell_item_key(req_item, "rough"),
            ]
            for variant in variants:
                have = stock.get(variant, 0) - taken.get(variant, 0)
                if have <= 0:
                    continue
                grade = lili_extras.parse_shell(variant)[1]
                unit = max(1, int(ITEM_PRICES.get(req_item, 1) * lili_extras.SHELL_GRADE_MULT[grade]))
                while have > 0 and got_value < need_value:
                    take_n = min(have, max(1, (need_value - got_value + unit - 1) // unit))
                    taken[variant] = taken.get(variant, 0) + take_n
                    have -= take_n
                    got_value += unit * take_n
            if got_value < need_value:
                label = ITEM_NAMES.get(req_item, req_item)
                return False, f"缺少 {label}（按品相折算还差约 {need_value - got_value} 票等价）"
            continue
        have = stock.get(req_item, 0) - taken.get(req_item, 0)
        if have < req_qty:
            return False, f"缺少 {ITEM_NAMES.get(req_item, req_item)} x{req_qty}"
        taken[req_item] = taken.get(req_item, 0) + req_qty
    return True, ""


async def player_view(conn: aiosqlite.Connection, s: dict[str, Any]) -> dict[str, Any]:
    """给 /island 用的流动摊。数值仍走 lili_ops，这里只摊开能点的。"""
    spawned = await maybe_spawn_visit(conn)
    visit = await _active_visit(conn)
    levels = await steward_domain_levels(conn, s["id"])
    today = day_id()
    stock = await db.get_satchel(s["id"])
    tickets = int(s.get("tickets") or 0)
    block = await lili_extras.stars_block(conn, s["id"])
    st = await lili_extras.load_summon_state(conn, s["id"])
    here = visit is not None
    left = max(0, (visit["expires_at"] - db.now()) // 60) if visit else 0
    if block:
        line = block
    elif spawned and visit:
        line = spawned.get("detail") or f"栗栗在摊（剩 {left} 分）"
    elif here:
        line = f"栗栗在摊（剩 {left} 分）。贝壳换货，不在就献壳唤摊。"
        bell = lili_extras.visit_bell_warning(visit)
        if bell:
            line = f"{line} {bell}"
    else:
        line = "现在不在。赶海捡到贝壳后，点「唤摊」献一枚试试。"
    line = f"{line} · {domain_level_line(levels)}"

    offers: list[dict[str, Any]] = []
    if here:
        rows = await ensure_daily_offers(conn, today, visit["id"])
        for row in rows:
            give = json.loads(row["give_json"])
            stock_left = int(row["stock"]) - int(row["sold"])
            get_name = ITEM_NAMES.get(row["get_item"], row["get_item"])
            domains = _parse_domains(row)
            cost_tickets = ticket_cost_for_steward(row["ticket_cost"], domains, levels)
            ready, why = _give_ready(stock, give)
            if stock_left <= 0:
                can = False
                note = "已售罄"
            elif block:
                can = False
                note = block
            elif not ready:
                can = False
                note = why
            elif cost_tickets and tickets < cost_tickets:
                can = False
                note = f"还缺 {cost_tickets} 票"
            else:
                can = True
                note = row.get("note") or _format_give(give, cost_tickets)
            offers.append(_sku(
                sid=str(row["id"]),
                kind="trade",
                name=f"{get_name} x{row['get_qty']}",
                emoji=_item_emoji(row["get_item"]),
                note=note,
                detail=f"{_format_give(give, cost_tickets)}。{note}",
                price="换" if can else ("罄" if stock_left <= 0 else "看"),
                can=can,
                target=str(row["id"]),
            ))
    else:
        offers.append(_sku(
            sid="away",
            kind="look",
            name="摊还没支",
            emoji="🌰",
            note="不在。切到唤摊，献一枚贝壳试试。",
            detail="栗栗是流动摊。不在时献壳唤摊，和 visit_ops lili summon 同一套。",
            price="看",
            can=False,
            target="scan",
        ))

    summons: list[dict[str, Any]] = []
    for item, qty in sorted(stock.items()):
        n = int(qty or 0)
        if n <= 0:
            continue
        if not lili_extras.resolve_summon_item(item):
            continue
        grade = lili_extras.summon_grade(item)
        grade_name = lili_extras.SUMMON_GRADE_LABEL.get(grade, grade)
        can = (not block) and n > 0
        summons.append(_sku(
            sid=item,
            kind="summon",
            name=ITEM_NAMES.get(item, item),
            emoji=_item_emoji(item),
            note=f"袋里 {n} · {grade_name} · {lili_extras.summon_rate_line(st)}",
            detail=f"献上这枚，向海风寄气息。{grade_name}。{lili_extras.summon_rate_line(st)}",
            price="献",
            can=can,
            target=item,
        ))
    if not summons:
        summons.append(_sku(
            sid="no-shell",
            kind="look",
            name="没有能献的壳",
            emoji="🐚",
            note="去海边赶海捡。亮壳比糙壳灵。",
            detail="赶海翻沙能捡到贝壳。第一次献壳海风一定把她送来。",
            price="看",
            can=False,
            target="scan",
        ))

    pet_ok = here and not block
    rough_n = sum(v for k, v in stock.items() if k.startswith("shell_rough_"))
    junk_ok = here and (not block) and rough_n >= lili_extras.ROUGH_JUNK_COST
    side = [
        _sku(
            sid="pet",
            kind="pet",
            name="摸夜栖",
            emoji="🐕",
            note="摊在才能摸。每天每摊一次。" if pet_ok else ("夜栖跟着摊走。" if not here else (block or "这会儿摸不了。")),
            detail="摸护摊犬夜栖。可能蹭来祝福，也可能翻车得狗毛。摊不在摸不到。",
            price="摸" if pet_ok else "看",
            can=pet_ok,
            target="",
        ),
        _sku(
            sid="junk",
            kind="junk",
            name="糙壳换乱捡款",
            emoji="🦌",
            note=(
                f"糙壳 {rough_n}/{lili_extras.ROUGH_JUNK_COST}"
                if junk_ok else
                (f"凑够 {lili_extras.ROUGH_JUNK_COST} 枚糙壳。现在 {rough_n}。" if here else "摊不在。")
            ),
            detail=f"铃鹿乱捡的货，不退换。要 {lili_extras.ROUGH_JUNK_COST} 枚糙壳。",
            price="换" if junk_ok else "看",
            can=junk_ok,
            target="",
        ),
    ]

    return {
        "name": "栗栗流动摊",
        "speaker": "栗栗",
        "line": line,
        "here": here,
        "left_min": left,
        "tabs": [
            {"key": "shelf", "label": "货架", "badge": "在" if here else ""},
            {"key": "summon", "label": "唤摊", "badge": ""},
            {"key": "side", "label": "摊边", "badge": ""},
        ],
        "items": {
            "shelf": offers,
            "summon": summons,
            "side": side,
        },
    }


async def active_visit_hint(conn: aiosqlite.Connection) -> str | None:
    visit = await _active_visit(conn)
    if not visit:
        return None
    left = max(0, (visit["expires_at"] - db.now()) // 60)
    bell = lili_extras.visit_bell_warning(visit)
    base = f"栗栗流动摊在（剩 {left} 分，今日货单）→ visit_ops lili scan"
    return f"{base} · {bell}" if bell else base
