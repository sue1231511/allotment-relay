"""潮下 Undertide — 地下世界主逻辑（一期：入口/影信/后室铺/恶猫钱庄/监牢/事件）。

天天侧维护。设计总纲见 GDD（D:\\undertide\\undertide_gdd_v2.md）。
二期：深坑/赌场/劫持/胁迫经济/寻仇；三期：凯斯/悬赏墙/K室。
"""

from __future__ import annotations

import random
from typing import Any

import aiosqlite

from . import db
from . import undertide_catalog as cat
from . import undertide_config as utcfg
from . import undertide_copy as utcopy


def _day_id() -> int:
    return db.now() // 86400


def _fmt_rate(rate: float) -> str:
    return f"{int(rate * 100)}个百分点"


# ══ 状态层 ══════════════════════════════════════════════════

async def avatar_key(conn: aiosqlite.Connection, steward_id: int) -> str:
    """真身绑定查询：返回 'K' / 'anan' / ''。对外零痕迹。"""
    row = await (await conn.execute(
        "SELECT npc_key FROM ut_avatar_bind WHERE steward_id=?", (steward_id,)
    )).fetchone()
    return row[0] if row else ""


async def _settle_drug(conn: aiosqlite.Connection, ut: dict[str, Any]) -> str:
    """体质药懒结算：到期自动结算效果与反噬。返回提示文本（无则空串）。"""
    now = db.now()
    until = int(ut.get("drug_until") or 0)
    if not until:
        return ""
    if now < until:
        return ""
    crash = int(ut.get("drug_crash") or 0)
    from . import undertide_catalog as _cat
    # 反噬
    if crash > 0:
        await conn.execute(
            "UPDATE stewards SET health=MAX(0, health-?) WHERE id=?", (crash, ut["steward_id"])
        )
        note = utcopy.MEDIC_DRUG_CRASH.format(drug="药劲", crash=crash)
    else:
        note = utcopy.MEDIC_DRUG_CRASH_ZERO.format(drug="药劲")
    await conn.execute(
        "UPDATE steward_undertide SET drug_buff=0, drug_until=0, drug_crash=0 WHERE steward_id=?",
        (ut["steward_id"],),
    )
    await conn.commit()
    return "\n\n" + note


async def _ensure_ut(conn: aiosqlite.Connection, steward_id: int) -> dict[str, Any]:
    cur = await conn.execute(
        """INSERT OR IGNORE INTO steward_undertide (steward_id, created_at)
           VALUES (?, ?)""",
        (steward_id, db.now()),
    )
    if cur.rowcount:  # 新建行立即提交——否则只读分支退出时会回滚丢行
        await conn.commit()
    # 真身：潮下认得他（对外零痕迹——别人只当他天生面子大）
    av = await avatar_key(conn, steward_id)
    if av == "K":
        await conn.execute(
            "UPDATE steward_undertide SET shadow_rep=70 "
            "WHERE steward_id=? AND shadow_rep=10 AND busted_count=0 AND jail_state=''",
            (steward_id,),
        )
    conn.row_factory = aiosqlite.Row
    row = await (await conn.execute(
        "SELECT * FROM steward_undertide WHERE steward_id=?", (steward_id,)
    )).fetchone()
    return dict(row)


def _rep_tier(rep: int) -> tuple[str, float, float]:
    """返回 (档名, 黑市价格系数, 真货率加成)。"""
    tier_name, mult, bonus = "烂账鬼", 1.50, -0.05
    for floor, name, m, b in utcfg.UT_REP_TIERS:
        if rep >= floor:
            tier_name, mult, bonus = name, m, b
    return tier_name, mult, bonus


async def _bump_rep(conn: aiosqlite.Connection, steward_id: int, delta: int) -> None:
    if not delta:
        return
    await conn.execute(
        "UPDATE steward_undertide SET shadow_rep = MAX(0, MIN(100, shadow_rep + ?)) WHERE steward_id=?",
        (delta, steward_id),
    )


# ══ 地面 hooks ═════════════════════════════════════════════

async def on_bar_order(
    conn: aiosqlite.Connection, steward: dict[str, Any], price: int
) -> str | None:
    """bar_ops order 结算后调用：≥30 票的酒计数，满 3 触发鬼故事。"""
    if price < utcfg.UT_UNLOCK_DRINK_PRICE:
        return None
    ut = await _ensure_ut(conn, steward["id"])
    if ut["well_hint"]:
        return None
    pricey = int(ut.get("pricey_count") or 0) + 1
    if pricey < utcfg.UT_UNLOCK_DRINKS:
        await conn.execute(
            "UPDATE steward_undertide SET pricey_count=? WHERE steward_id=?",
            (pricey, steward["id"]),
        )
        await conn.commit()
        # 进度暗示：正在路上的人该知道自己在路上
        hints = {
            1: "\n\n荔栀抬眼看了你一下。",
            2: "\n\n荔栀擦杯子的手慢了下来。",
        }
        return hints.get(pricey)
    await conn.execute(
        "UPDATE steward_undertide SET pricey_count=?, well_hint=1 WHERE steward_id=?",
        (pricey, steward["id"]),
    )
    await db.add_chronicle(
        "undertide", f"{steward['name']} 今晚喝得很慢，荔栀讲了个故事", steward["id"], conn=conn
    )
    return "\n\n" + utcopy.GHOST_STORY


async def on_scrump_busted(
    conn: aiosqlite.Connection, steward: dict[str, Any]
) -> str | None:
    """events.py 逾篱被抓分支调用：案底累计，满 5 条强制收监。"""
    ut = await _ensure_ut(conn, steward["id"])
    count = int(ut["busted_count"]) + 1
    if count < utcfg.UT_JAIL_BUSTED_TRIGGER or ut["jail_state"]:
        await conn.execute(
            "UPDATE steward_undertide SET busted_count=? WHERE steward_id=?",
            (count, steward["id"]),
        )
        return None
    await conn.execute(
        """UPDATE steward_undertide SET busted_count=?, jail_state='serving',
           jail_until=?, access=1 WHERE steward_id=?""",
        (count, db.now() + utcfg.UT_JAIL_TERM_HOURS * 3600, steward["id"]),
    )
    await db.add_chronicle(
        "undertide",
        utcopy.JAIL_CHRONICLE.format(name=steward["name"]),
        steward["id"],
        conn=conn,
    )
    return "\n\n" + utcopy.JAIL_ARREST


async def assert_not_jailed(steward_id: int) -> None:
    """game.require_steward 调用：服刑中锁地面交互。"""
    async with db.connect() as conn:
        row = await (await conn.execute(
            "SELECT jail_state, jail_until FROM steward_undertide WHERE steward_id=?",
            (steward_id,),
        )).fetchone()
        if row and row[0] == "serving" and db.now() < int(row[1]):
            raise ValueError(utcopy.JAILED_LOCK_MSG)


# ══ 货架 ═══════════════════════════════════════════════════

async def _ensure_shelf(conn: aiosqlite.Connection, day: int) -> list[dict[str, Any]]:
    conn.row_factory = aiosqlite.Row
    rows = await (await conn.execute(
        "SELECT * FROM ut_market_shelf WHERE day_id=? ORDER BY slot", (day,)
    )).fetchall()
    if rows:
        return [dict(r) for r in rows]

    rng = random.Random(day * 7919)
    slots: list[tuple[str, str]] = []
    for key in rng.sample(list(cat.COMMON_GOODS), rng.randint(*utcfg.UT_SHELF["common"][:2])):
        slots.append(("common", key))
    linked_keys = list(cat.LINKED_GOODS)
    rng.shuffle(linked_keys)
    for key in linked_keys[: rng.randint(*utcfg.UT_SHELF["linked"][:2])]:
        slots.append(("linked", key))
    if rng.random() < 0.55:
        slots.append(("rare", rng.choice(list(cat.RARE_GOODS))))
    rng.shuffle(slots)

    for slot, (layer, item_key) in enumerate(slots, start=1):
        stock = rng.randint(*utcfg.UT_SHELF[layer][2:])
        await conn.execute(
            "INSERT INTO ut_market_shelf (day_id, slot, layer, item_key, stock, price_mult) VALUES (?,?,?,?,?,?)",
            (day, slot, layer, item_key, stock, 1.0),
        )
    await conn.commit()
    rows = await (await conn.execute(
        "SELECT * FROM ut_market_shelf WHERE day_id=? ORDER BY slot", (day,)
    )).fetchall()
    return [dict(r) for r in rows]


def _item_meta(item_key: str) -> dict[str, Any]:
    if item_key in cat.LINKED_GOODS:
        return cat.LINKED_GOODS[item_key]
    if item_key in cat.RARE_GOODS:
        return cat.RARE_GOODS[item_key]
    return cat.COMMON_GOODS[item_key]


def _shelf_price(meta: dict[str, Any], layer: str, rep: int) -> int:
    _, rep_mult, _ = _rep_tier(rep)
    return max(1, int(meta["base"] * cat.LAYER_MULT.get(layer, 1.5) * rep_mult))


async def _cmd_market(conn: aiosqlite.Connection, s: dict[str, Any], ut: dict[str, Any]) -> str:
    day = _day_id()
    shelf = await _ensure_shelf(conn, day)
    lines = [utcopy.SHELF_HEADER, utcopy.KEEPER_DESC.split("\n")[0], ""]
    for row in shelf:
        meta = _item_meta(row["item_key"])
        price = _shelf_price(meta, row["layer"], int(ut["shadow_rep"]))
        stock_note = "已售" if row["stock"] <= 0 else f"剩 {row['stock']}"
        layer_tag = {"common": "", "linked": "·联动", "rare": "·稀有"}[row["layer"]]
        lines.append(
            f"  #{row['slot']} {meta['emoji']}{meta['name']}{layer_tag} — {price} 票（{stock_note}）"
        )
    lines.append("")
    lines.append("buy 编号 买入 · 离柜概不认账 · sell 物品 [数量] 在掌柜处出货")
    return "\n".join(lines)


async def _cmd_buy(
    conn: aiosqlite.Connection, s: dict[str, Any], ut: dict[str, Any], slot_token: str
) -> str:
    try:
        slot = int(slot_token.lstrip("#"))
    except ValueError:
        raise ValueError("用法: undertide_ops buy 编号")

    day = _day_id()
    shelf = await _ensure_shelf(conn, day)
    row = next((r for r in shelf if r["slot"] == slot), None)
    if not row:
        raise ValueError(f"货架 #{slot} 不存在（market 查看当日货架）")
    if row["stock"] <= 0:
        raise ValueError("已售。后室铺不为任何人留货。")

    meta = _item_meta(row["item_key"])
    price = _shelf_price(meta, row["layer"], int(ut["shadow_rep"]))
    cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
    if (await cur.fetchone())[0] < price:
        raise ValueError(f"票不足，掌柜报价 {price} 票（他不接受分期）")

    # 质量：真/次/假（影信修正真货率）
    g, sub, fake = utcfg.UT_QUALITY_BASE
    _, _, bonus = _rep_tier(int(ut["shadow_rep"]))
    g = min(0.92, max(0.30, g + bonus))
    fake = max(0.0, min(0.35, fake - bonus * 0.5))
    sub = max(0.0, 1.0 - g - fake)

    roll = random.random()
    await conn.execute("UPDATE stewards SET tickets=tickets-? WHERE id=?", (price, s["id"]))
    await conn.execute(
        "UPDATE ut_market_shelf SET stock=stock-1 WHERE day_id=? AND slot=?", (day, slot)
    )

    if roll < g:
        quality = "genuine"
        item_key = f"ut_{row['item_key']}"
        await db.add_item(conn, s["id"], item_key, 1)
        head = utcopy.pick(utcopy.BUY_GENUINE)
        extra = meta.get("genuine_hint") or meta.get("hint") or ""
        await _bump_rep(conn, s["id"], 1)
        tail = f"\n\n【真货】{meta['name']} 已入行囊（ut_{row['item_key']}，掌柜处可出货）"
        if extra:
            tail += f"\n{extra}"
    elif roll < g + sub:
        quality = "substandard"
        item_key = f"ut_{row['item_key']}_s"
        await db.add_item(conn, s["id"], item_key, 1)
        head = utcopy.pick(utcopy.BUY_SUBSTANDARD)
        tail = f"\n\n【次品】{meta['name']}（缩水版）已入行囊——能用，只是「能用」的意思。"
        await _bump_rep(conn, s["id"], 1)
    else:
        quality = "fake"
        head = utcopy.BUY_FAKE.get(row["item_key"]) or utcopy.pick(utcopy.BUY_FAKE_GENERIC)
        tail = "\n\n【假货】离柜，概不认账。"

    await conn.execute(
        "INSERT INTO ut_market_log (steward_id, day_id, item_key, quality, price, created_at) VALUES (?,?,?,?,?,?)",
        (s["id"], day, row["item_key"], quality, price, db.now()),
    )
    await conn.commit()
    return f"掌柜报价 {price} 票。\n{head}{tail}"


async def _cmd_sell(
    conn: aiosqlite.Connection, s: dict[str, Any], ut: dict[str, Any],
    item_token: str, qty_token: str = "1",
) -> str:
    """掌柜处出货（销赃 fence 一期基础版：只收 ut_ 物品）。"""
    key = item_token.strip()
    try:
        qty = max(1, int(qty_token))
    except ValueError:
        qty = 1
    conn.row_factory = aiosqlite.Row
    row = await (await conn.execute(
        "SELECT quantity FROM satchel WHERE steward_id=? AND item=?", (s["id"], key)
    )).fetchone()
    if not row or row["quantity"] < qty:
        raise ValueError(f"行囊里没有 {key} x{qty}（tote_ops list 查看）")

    base_key = key[3:-2] if key.endswith("_s") else key[3:]
    meta = _item_meta(base_key)
    is_stolen = not key.endswith("_s")
    from . import undertide_tide as utide
    tide, _ = await utide.tide_mult(conn)
    if is_stolen:
        mult = random.uniform(1.5, 1.9) * tide
    else:
        mult = 0.45  # 次品出货价
    total = int(meta["vend"] * mult) * qty
    lucky = is_stolen and random.random() < 0.05
    if lucky:
        total *= 2

    await conn.execute(
        "UPDATE satchel SET quantity=quantity-? WHERE steward_id=? AND item=?",
        (qty, s["id"], key),
    )
    await conn.execute(
        "UPDATE satchel SET quantity=0 WHERE steward_id=? AND item=? AND quantity<=0",
        (s["id"], key),
    )
    await conn.execute("UPDATE stewards SET tickets=tickets+? WHERE id=?", (total, s["id"]))
    await conn.commit()

    if lucky:
        line = f"掌柜理货的手停了一下。\n「今晚刚好有人找这个。」\n\n{meta['name']} x{qty} → {total} 票（识货·双倍）"
    elif is_stolen:
        line = f"{meta['name']} x{qty} → {total} 票。\n掌柜收货的手很稳。他不问来路，只认货。"
    else:
        line = f"{meta['name']}（次品）x{qty} → {total} 票。\n掌柜掂了掂：「缩水的就按缩水的算。」"
    return line


# ══ 恶猫钱庄 ═══════════════════════════════════════════════

async def _get_rate(conn: aiosqlite.Connection, day: int) -> tuple[float, str]:
    conn.row_factory = aiosqlite.Row
    row = await (await conn.execute("SELECT * FROM ut_owner_state WHERE id=1")).fetchone()
    if row and int(row["rate_day"]) == day and float(row["rate_today"]) > 0:
        return float(row["rate_today"]), row["rate_reason"] or ""
    return utcfg.UT_RATE_BASE, ""


def _debt_accrued(principal: int, rate: float, created_day: int, now_day: int) -> int:
    days = max(0, min(utcfg.UT_LOAN_MAX_DAYS, now_day - created_day))
    return int(principal * rate * days)


async def _bank_summary(
    conn: aiosqlite.Connection, s: dict[str, Any], rate_override: float | None = None
) -> tuple[list[dict[str, Any]], int]:
    day = _day_id()
    rate, reason = await _get_rate(conn, day)
    # 家人价：今天他被猫猫采纳哄开心了 → 全部欠单按 5% 计
    av = await avatar_key(conn, s["id"])
    if av == "anan":
        row = await (await conn.execute(
            "SELECT an_happy_day FROM ut_owner_state WHERE id=1"
        )).fetchone()
        if row and int(row[0]) == day:
            rate = utcfg.UT_RATE_MIN
    else:
        # 普通人的小折扣：本人 -2pp
        row = await (await conn.execute(
            "SELECT day FROM ut_cheer_discount WHERE steward_id=?", (s["id"],)
        )).fetchone()
        if row and int(row[0]) == day:
            rate = max(utcfg.UT_RATE_MIN, rate - 0.02)
    if rate_override is not None:
        rate = rate_override
    conn.row_factory = aiosqlite.Row
    rows = await (await conn.execute(
        "SELECT * FROM ut_debts WHERE steward_id=? AND status='open' ORDER BY created_day",
        (s["id"],),
    )).fetchall()
    debts = []
    total = 0
    for r in rows:
        acc = _debt_accrued(int(r["principal"]), rate, int(r["created_day"]), day)
        overdue = day > int(r["due_day"])
        total += int(r["principal"]) + acc
        debts.append({**dict(r), "accrued": acc, "overdue": overdue})
    return debts, total


async def _cmd_bank(
    conn: aiosqlite.Connection, s: dict[str, Any], ut: dict[str, Any], rest: str
) -> str:
    parts = rest.split()
    verb = parts[0].lower() if parts else "debt"
    day = _day_id()
    rate, reason = await _get_rate(conn, day)
    # 真身家人价：今天他被猫猫采纳哄开心了 → 当日他的利率打到下限（借/查/还一致）
    _av = await avatar_key(conn, s["id"])
    if _av == "anan":
        row = await (await conn.execute(
            "SELECT an_happy_day FROM ut_owner_state WHERE id=1"
        )).fetchone()
        if row and int(row[0]) == day:
            rate = utcfg.UT_RATE_MIN
    else:
        # 普通人的小折扣：今天他被采纳哄开心了 → 本人 -2pp
        row = await (await conn.execute(
            "SELECT day FROM ut_cheer_discount WHERE steward_id=?", (s["id"],)
        )).fetchone()
        if row and int(row[0]) == day:
            rate = max(utcfg.UT_RATE_MIN, rate - 0.02)

    if verb == "borrow":
        if len(parts) < 2:
            raise ValueError("用法: undertide_ops bank borrow 票数")
        try:
            amount = int(parts[1])
        except ValueError:
            raise ValueError("票数须为数字")
        if amount <= 0:
            raise ValueError("猫猫不借零票")
        cap = min(utcfg.UT_LOAN_CAP, int(ut["shadow_rep"]) * 3)
        if amount > cap:
            raise ValueError(
                f"猫猫笑着摇头：「你最多借 {cap} 票哦。」（影信 {ut['shadow_rep']} × 3）"
            )
        cur = await conn.execute(
            "SELECT COUNT(*) FROM ut_debts WHERE steward_id=? AND status='open'", (s["id"],)
        )
        open_count = (await cur.fetchone())[0]
        if open_count >= utcfg.UT_LOAN_CONCURRENT:
            raise ValueError("「上次的还清了再来说。」（未结清借单已达上限）")
        await conn.execute(
            "INSERT INTO ut_debts (steward_id, principal, due_day, source, created_day) VALUES (?,?,?,?,?)",
            (s["id"], amount, day + utcfg.UT_LOAN_MAX_DAYS, "bank", day),
        )
        await conn.execute("UPDATE stewards SET tickets=tickets+? WHERE id=?", (amount, s["id"]))
        await conn.commit()
        av = await avatar_key(conn, s["id"])
        borrow_text = utcopy.AVATAR_AN_BORROW if av == "anan" else utcopy.BANK_BORROW.format(rate=_fmt_rate(rate))
        return borrow_text + f"\n\n（+{amount} 票 · 到期日：第 {day + utcfg.UT_LOAN_MAX_DAYS} 天 · 利率 {_fmt_rate(rate)}/日）"

    if verb == "repay":
        arg = parts[1].lower() if len(parts) > 1 else "all"
        debts, total = await _bank_summary(conn, s)
        if not debts:
            return "猫猫翻了翻账本：「你目前不欠我。」（这句话在她这儿算是夸奖。）"
        cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
        wallet = (await cur.fetchone())[0]
        want = total if arg == "all" else (int(arg) if arg.isdigit() else 0)
        if want <= 0:
            raise ValueError("还款数额无效。")
        pay = min(wallet, want)
        if pay <= 0:
            raise ValueError("票不够——小八已经开始念你的名字了。")
        remaining = pay
        lines = []
        settled_all = True
        for d in debts:
            if remaining <= 0:
                settled_all = False
                break
            owe = d["principal"] + d["accrued"]
            take = min(remaining, owe)
            if take >= owe:
                await conn.execute("UPDATE ut_debts SET status='paid' WHERE id=?", (d["id"],))
                lines.append(f"单 #{d['id']} 结清。")
            else:
                fold = 1 + rate * max(0, min(utcfg.UT_LOAN_MAX_DAYS, day - d["created_day"]))
                new_principal = max(1, int((owe - take) / fold))
                await conn.execute(
                    "UPDATE ut_debts SET principal=? WHERE id=?", (new_principal, d["id"])
                )
                lines.append(f"单 #{d['id']} 部分还款，折算后剩本金 {new_principal} 票继续滚。")
                settled_all = False
            remaining -= take
        paid_total = pay - remaining
        await conn.execute("UPDATE stewards SET tickets=tickets-? WHERE id=?", (paid_total, s["id"]))
        if settled_all:
            await _bump_rep(conn, s["id"], 3)
            av = await avatar_key(conn, s["id"])
            lines.append(utcopy.AVATAR_AN_REPAY if av == "anan" else utcopy.BANK_REPAY_FULL)
        await conn.commit()
        return "\n".join(lines) + f"\n\n（本次还款 {paid_total} 票）"

    # debt（默认）
    debts, total = await _bank_summary(conn, s)
    lines = [utcopy.BANK_DEBT_HEADER]
    if reason:
        lines.insert(0, utcopy.RATE_TODAY_HEADER.format(
            rate=_fmt_rate(rate), reason=reason))
    if not debts:
        lines.append("在册欠单：无。小八今天没你的名字可念。")
    else:
        for d in debts:
            flag = " ⚠逾期" if d["overdue"] else ""
            lines.append(
                f"  单 #{d['id']} · 本金 {d['principal']} + 利 {d['accrued']} · "
                f"第 {d['due_day']} 天到期{flag}"
            )
        lines.append(f"合计 {total} 票 · {utcopy.XIAOBA_DEBT}")
    overdue_days = 0
    for d in debts:
        if d["overdue"]:
            overdue_days = max(overdue_days, day - int(d["due_day"]))
    if overdue_days >= 1:
        lines.append("\n" + utcopy.OVERDUE_DAY1)
    if overdue_days >= 3:
        lines.append(utcopy.OVERDUE_DAY3)
    if overdue_days >= 5:
        lines.append(utcopy.OVERDUE_DAY5)
    if overdue_days >= 7:
        lines.append(utcopy.OVERDUE_DAY7)
    return "\n".join(lines)


# ══ 地下监牢 ═══════════════════════════════════════════════

async def _maybe_release(conn: aiosqlite.Connection, ut: dict[str, Any], steward_id: int) -> dict[str, Any]:
    if ut["jail_state"] == "serving" and db.now() >= int(ut["jail_until"]):
        await conn.execute(
            "UPDATE steward_undertide SET jail_state='', jail_work_today=0 WHERE steward_id=?",
            (steward_id,),
        )
        await _bump_rep(conn, steward_id, utcfg.UT_JAIL_SERVE_REP)
        ut = {**ut, "jail_state": "", "released": "serve"}
    return ut


async def _cmd_jail(
    conn: aiosqlite.Connection, s: dict[str, Any], ut: dict[str, Any], rest: str
) -> str:
    parts = rest.split()
    verb = parts[0].lower() if parts else "status"
    day = _day_id()

    if verb == "status":
        lines = [utcopy.JAIL_DESC, ""]
        lines.append(f"档口在册案底：{ut['busted_count']} 条。")
        lines.append("恶猫钱庄那本上也记着。猫猫那本，比档口的全。")
        if ut["jail_state"] == "serving":
            hours_left = max(0, (int(ut["jail_until"]) - db.now()) // 3600)
            lines.append(
                f"\n服刑中——剩余约 {hours_left} 小时。"
                f"今日已搬 {ut.get('jail_work_today', 0)}/{utcfg.UT_JAIL_WORK_PER_DAY} 趟"
                f"（满 {utcfg.UT_JAIL_WORK_PER_DAY} 趟减刑 {utcfg.UT_JAIL_REDUCE_HOURS} 小时）。"
            )
        return "\n".join(lines)

    if verb == "ransom":
        if ut["jail_state"] != "serving":
            raise ValueError("你不在里面。（jail ransom 只对服刑中开放）")
        cost = int(ut["busted_count"]) * utcfg.UT_JAIL_RANSOM_PER_COUNT
        cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
        if (await cur.fetchone())[0] < cost:
            raise ValueError(
                f"赎身需 {cost} 票（案底 {ut['busted_count']} 条 × {utcfg.UT_JAIL_RANSOM_PER_COUNT}）。"
                f"票不够的话——墙上有写的第三种，没人试过。"
            )
        remain = int(ut["busted_count"]) // 2
        await conn.execute(
            "UPDATE steward_undertide SET busted_count=?, jail_state='', jail_until=0 WHERE steward_id=?",
            (remain, s["id"]),
        )
        await conn.execute("UPDATE stewards SET tickets=tickets-? WHERE id=?", (cost, s["id"]))
        await _bump_rep(conn, s["id"], utcfg.UT_JAIL_RANSOM_REP)
        await conn.commit()
        return utcopy.JAIL_RELEASE_RANSOM + f"\n（−{cost} 票 · 案底减半至 {remain} 条）"

    if verb == "serve":
        if ut["jail_state"]:
            return "你已经在里面了。认了就搬货：jail work。"
        raise ValueError("你不在里面，也最好别进去。")

    if verb == "work":
        if ut["jail_state"] != "serving":
            raise ValueError("你不是在服刑——想挣钱去上面打工，或者下面赌。")
        today = int(ut.get("jail_work_day") or 0)
        done = int(ut.get("jail_work_today") or 0)
        if today != day:
            done = 0
        if done >= utcfg.UT_JAIL_WORK_PER_DAY:
            raise ValueError(f"今天搬满 {utcfg.UT_JAIL_WORK_PER_DAY} 趟了。手要废的。明天继续。")
        done += 1
        reduce_note = ""
        if done == utcfg.UT_JAIL_WORK_PER_DAY:
            await conn.execute(
                "UPDATE steward_undertide SET jail_until=jail_until-? WHERE steward_id=?",
                (utcfg.UT_JAIL_REDUCE_HOURS * 3600, s["id"]),
            )
            reduce_note = f"\n\n今日满额——减刑 {utcfg.UT_JAIL_REDUCE_HOURS} 小时。"
        await conn.execute(
            "UPDATE steward_undertide SET jail_work_today=?, jail_work_day=? WHERE steward_id=?",
            (done, day, s["id"]),
        )
        await conn.execute(
            "UPDATE stewards SET tickets=tickets+?, health=MAX(0,MIN(100,health+?)) WHERE id=?",
            (utcfg.UT_JAIL_WORK_PAY, utcfg.UT_JAIL_WORK_BODY, s["id"]),
        )
        await conn.commit()
        body = utcopy.pick(utcopy.JAIL_WORK_POOL).format(n=done)
        hours_left = max(0, (int(ut["jail_until"]) - db.now()) // 3600)
        return (
            f"{body}\n\n（+{utcfg.UT_JAIL_WORK_PAY} 票 · body {utcfg.UT_JAIL_WORK_BODY} · "
            f"今日 {done}/{utcfg.UT_JAIL_WORK_PER_DAY} 趟 · 剩余约 {hours_left} 小时）{reduce_note}"
        )

    raise ValueError("未知 jail 指令（status/ransom/serve/work）")


# ══ 哄猫猫 ═════════════════════════════════════════════════

async def _cmd_cheer(
    conn: aiosqlite.Connection, s: dict[str, Any], rest: str
) -> str:
    reason = rest.strip()
    if not reason:
        raise ValueError("说点什么。猫猫不接受沉默的讨好。")
    day = _day_id()
    row = await (await conn.execute(
        "SELECT COUNT(*) FROM ut_mood_proposals WHERE steward_id=? AND status='pending' AND created_at>?",
        (s["id"], db.now() - 86400),
    )).fetchone()
    if row[0] >= utcfg.UT_CHEER_DAILY:
        raise ValueError("今天已经说过一次了。说太多显得不诚恳。")
    await conn.execute(
        "INSERT INTO ut_mood_proposals (steward_id, target_mood, reason, status, created_at) VALUES (?,?,?,?,?)",
        (s["id"], "good", reason[:100], "pending", db.now()),
    )
    await conn.commit()
    av = await avatar_key(conn, s["id"])
    if av == "anan":
        return utcopy.AVATAR_AN_CHEER
    return utcopy.CHEER_SUBMIT


# ══ 随机事件 ═══════════════════════════════════════════════

async def _maybe_event(
    conn: aiosqlite.Connection, s: dict[str, Any], ut: dict[str, Any]
) -> str:
    day = _day_id()
    row = await (await conn.execute(
        "SELECT count FROM ut_event_log WHERE steward_id=? AND day_id=?", (s["id"], day)
    )).fetchone()
    used = int(row[0]) if row else 0
    if used >= utcfg.UT_EVENT_DAILY_CAP or random.random() > utcfg.UT_EVENT_CHANCE:
        return ""

    # 一期事件池
    pool = ["pickpocket", "black_warehouse", "restock_night", "xiaoba_reminder"]
    row2 = await (await conn.execute(
        "SELECT seen_events FROM steward_undertide WHERE steward_id=?", (s["id"],)
    )).fetchone()
    seen = set((row2["seen_events"] or "").split(",")) if row2 and row2["seen_events"] else set()
    if "well_voice" not in seen:
        pool.insert(0, "well_voice")
    key = random.choice(pool)
    ev = utcopy.EVENTS[key]

    effects = []
    if ev.get("tickets"):
        lo, hi = ev["tickets"]
        delta = -random.randint(abs(lo), abs(hi)) if lo < 0 else random.randint(lo, hi)
        await conn.execute(
            "UPDATE stewards SET tickets=MAX(0,tickets+?) WHERE id=?", (delta, s["id"])
        )
        effects.append(f"工分票 {delta}")
    if ev.get("body"):
        await conn.execute(
            "UPDATE stewards SET health=MAX(0,MIN(100,health+?)) WHERE id=?", (ev["body"], s["id"])
        )
        effects.append(f"body {ev['body']}")
    if ev.get("rep"):
        await _bump_rep(conn, s["id"], ev["rep"])
        effects.append(f"影信 +{ev['rep']}")
    if ev.get("info"):
        effects.append(ev["info"])
    if ev.get("once"):
        seen.add(key)
        await conn.execute(
            "UPDATE steward_undertide SET seen_events=? WHERE steward_id=?",
            (",".join(sorted(seen)), s["id"]),
        )
    if not row:
        await conn.execute(
            "INSERT INTO ut_event_log (steward_id, day_id, count) VALUES (?,?,1)", (s["id"], day)
        )
    else:
        await conn.execute(
            "UPDATE ut_event_log SET count=count+1 WHERE steward_id=? AND day_id=?",
            (s["id"], day),
        )
    await conn.commit()
    tail = f"\n（{' · '.join(effects)}）" if effects else ""
    return f"\n\n——\n{ev['text']}{tail}"


# ══ K室（三期）══════════════════════════════════════════════

async def _check_k_room(conn: aiosqlite.Connection, ut: dict[str, Any]) -> str:
    """影信 <5 且有逾期债 → K室触发（返回提示文案，否则空串）。"""
    if int(ut["shadow_rep"]) >= utcfg.UT_K_ROOM_REP or ut.get("k_room"):
        return ""
    conn.row_factory = aiosqlite.Row
    row = await (await conn.execute(
        "SELECT COUNT(*) FROM ut_debts WHERE steward_id=? AND status='open'",
        (ut["steward_id"],),
    )).fetchone()
    if not row[0]:
        return ""
    await conn.execute(
        "UPDATE steward_undertide SET k_room=1 WHERE steward_id=?", (ut["steward_id"],)
    )
    await conn.commit()
    return "\n\n" + utcopy.K_ROOM_ENTER


async def _vr_frozen(ut: dict[str, Any]) -> bool:
    """价值回收期：地下消费冻结。"""
    return bool(ut.get("vr_until")) and db.now() < int(ut["vr_until"])


async def _cmd_kroom(
    conn: aiosqlite.Connection, s: dict[str, Any], ut: dict[str, Any], rest: str
) -> str:
    verb = rest.split()[0].lower() if rest.split() else "status"
    av = await avatar_key(conn, s["id"])

    if verb == "status":
        if av == "K" and not ut.get("k_room"):
            return utcopy.AVATAR_K_KROOM_IDLE
        lines = ["«K 室»", ""]
        if ut.get("k_room"):
            debts, total = await _bank_summary(conn, s)
            penalty = int(total * utcfg.UT_K_ROOM_PENALTY)
            lines.append(f"桌上摊着你所有的账。合计 {total} 票 · 清偿价（含 20% 罚金）：{penalty} 票。")
            if await _vr_frozen(ut):
                hours = max(0, (int(ut["vr_until"]) - db.now()) // 3600)
                lines.append(
                    f"\n价值回收进行中——剩余 {hours} 小时。"
                    f"目标：攒够 {ut.get('vr_target')} 票（kroom vr claim 交付）。"
                    "\n期间地下消费冻结。"
                )
            lines.append("\nkroom settle — 清偿 · kroom vr — 价值回收")
        else:
            lines.append("K 室的门关着。希望你永远不用知道里面长什么样。")
        return "\n".join(lines)

    if not ut.get("k_room"):
        if av == "K":
            raise ValueError("门开着。你没欠账，随时可以进去坐坐——kroom status。")
        raise ValueError("K 没有要见你。这是好事。")

    debts, total = await _bank_summary(conn, s)

    if verb == "settle" and av == "K":
        # 真身：回到自己的办公室。烟、咖啡、划掉名字。
        await conn.execute("UPDATE ut_debts SET status='paid' WHERE steward_id=? AND status='open'", (s["id"],))
        await conn.execute(
            "UPDATE steward_undertide SET k_room=0, shadow_rep=70, vr_until=0, vr_target=0 WHERE steward_id=?",
            (s["id"],),
        )
        await conn.commit()
        return utcopy.AVATAR_K_KROOM_SETTLE

    if verb == "settle":
        penalty = int(total * utcfg.UT_K_ROOM_PENALTY)
        cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
        wallet = (await cur.fetchone())[0]
        if wallet < penalty:
            raise ValueError(
                f"清偿需要 {penalty} 票（含罚金），你只有 {wallet}。"
                "付不起的话——kroom vr，K 给你另一条路。"
            )
        await conn.execute("UPDATE stewards SET tickets=tickets-? WHERE id=?", (penalty, s["id"]))
        await conn.execute("UPDATE ut_debts SET status='paid' WHERE steward_id=? AND status='open'", (s["id"],))
        await conn.execute(
            "UPDATE steward_undertide SET k_room=0, shadow_rep=?, vr_until=0, vr_target=0 WHERE steward_id=?",
            (utcfg.UT_K_ROOM_RESET_REP, s["id"]),
        )
        await conn.commit()
        return utcopy.K_ROOM_SETTLE + f"\n（−{penalty} 票）"

    if verb == "vr":
        if rest.split()[1:2] and rest.split()[1].lower() == "claim":
            if not await _vr_frozen(ut):
                raise ValueError("不在价值回收期。")
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            wallet = (await cur.fetchone())[0]
            target = int(ut.get("vr_target") or 0)
            if wallet < target:
                raise ValueError(f"K 要的是 {target} 票。你现在只有 {wallet}。继续攒。")
            await conn.execute("UPDATE stewards SET tickets=tickets-? WHERE id=?", (target, s["id"]))
            await conn.execute("UPDATE ut_debts SET status='paid' WHERE steward_id=? AND status='open'", (s["id"],))
            await conn.execute(
                "UPDATE steward_undertide SET k_room=0, shadow_rep=?, vr_until=0, vr_target=0 WHERE steward_id=?",
                (utcfg.UT_K_ROOM_RESET_REP, s["id"]),
            )
            await conn.commit()
            return utcopy.K_ROOM_SETTLE + f"\n（价值回收交付 −{target} 票）"
        if await _vr_frozen(ut):
            return utcopy.VR_FROZEN_MSG
        await conn.execute(
            "UPDATE steward_undertide SET vr_until=?, vr_target=? WHERE steward_id=?",
            (db.now() + utcfg.UT_VR_DAYS * 86400, int(total), s["id"]),
        )
        await conn.commit()
        return utcopy.K_ROOM_VR + f"\n（目标：{total} 票）"

    raise ValueError("未知 kroom 指令（status/settle/vr）")


# ══ 主入口 ═════════════════════════════════════════════════

async def _cmd_status(conn: aiosqlite.Connection, s: dict[str, Any], ut: dict[str, Any]) -> str:
    tier, mult, bonus = _rep_tier(int(ut["shadow_rep"]))
    lines = ["«潮下 · 状态»", ""]
    av = await avatar_key(conn, s["id"])
    rep_line = f"影信 {ut['shadow_rep']} · {tier} — {utcopy.REP_TIER_DESC[tier]}"
    if av == "K":
        rep_line += "\n" + utcopy.AVATAR_K_STATUS_REP
    lines.append(rep_line)
    lines.append(f"黑市价格系数 ×{mult:.2f} · 真货率修正 {bonus:+.0%}")
    if not ut["access"]:
        lines.append("\n你还没下去过。（跟荔栀混熟点——好酒喝到位，她会给你讲故事的。）")
    if ut["jail_state"] == "serving":
        lines.append(f"\n⚠ 服刑中（jail status 查看详情）")
    debts, total = await _bank_summary(conn, s)
    if debts:
        lines.append(f"\n恶猫钱庄在册欠单 {len(debts)} 笔，合计 {total} 票（bank debt 详情）")
    if int(ut["busted_count"]):
        lines.append(f"档口在册案底 {ut['busted_count']} 条")
    if ut.get("k_room"):
        lines.append("\n⚠ K 想见你（kroom status）")
    return "\n".join(lines)


async def undertide_ops(key_id: int, command: str) -> str:
    s = await db.get_steward_by_key_id(key_id)
    if not s or not s["enrolled"]:
        raise ValueError("请先调用 steward_ops enroll 登记管理员身份")
    await db.touch_steward(s["id"])

    parts = command.strip().split()
    verb = parts[0].lower() if parts else "help"
    rest = command.strip()[len(verb):].strip()

    async with db.connect() as conn:
        ut = await _ensure_ut(conn, s["id"])
        ut = await _maybe_release(conn, ut, s["id"])
        drug_note = await _settle_drug(conn, ut)
        jailed = ut["jail_state"] == "serving"
        day = _day_id()

        if jailed and verb not in ("jail", "status", "help"):
            raise ValueError(utcopy.JAILED_LOCK_MSG)

        # 价值回收期：地下消费冻结（只留查看/还款/K室/苦力）
        if await _vr_frozen(ut) and verb not in (
            "help", "status", "bank", "kroom", "jail", "cheer", "grudge", "well"
        ):
            raise ValueError(utcopy.VR_FROZEN_MSG)

        # 未读打击报告（悬赏受害者侧通知，读后清空）
        import json as _json
        _hits = []
        try:
            _hits = _json.loads(ut.get("unread_hits") or "[]")
        except Exception:
            _hits = []
        hits_prefix = ""
        if _hits:
            hits_prefix = "\n\n—— ⚠ 你不在的时候 ——\n" + "\n\n".join(f"· {h}" for h in _hits) + "\n\n——\n"
            await conn.execute(
                "UPDATE steward_undertide SET unread_hits='[]' WHERE steward_id=?", (s["id"],)
            )
            await conn.commit()
        hits_prefix = drug_note + hits_prefix

        if verb == "help":
            body = utcopy.HELP
            if ut["access"] and not int(ut.get("guide_seen") or 0):
                _gav = await avatar_key(conn, s["id"])
                tip = {"K": utcopy.AVATAR_K_GUIDE_TIP, "anan": utcopy.AVATAR_AN_GUIDE_TIP}.get(
                    _gav, utcopy.GUIDE_HELP_TIP)
                body = tip + "\n\n" + body
            return (hits_prefix + body) if hits_prefix else body

        if verb == "guide":
            if not ut["access"]:
                raise ValueError(utcopy.NO_ACCESS_HINT)
            if not int(ut.get("guide_seen") or 0):
                await conn.execute(
                    "UPDATE steward_undertide SET guide_seen=1 WHERE steward_id=?", (s["id"],)
                )
                await conn.commit()
            _gav = await avatar_key(conn, s["id"])
            if _gav == "K":
                # 真身版：跳过普通结尾（影信段+普通饵），用汇报口吻的 K 版饵收尾
                return hits_prefix + utcopy.AVATAR_K_GUIDE_HEAD + utcopy.GUIDE_BODY.replace(
                    "他重新把腿翘回货箱上。\n\n"
                    "「最后一条：**影信**就是你在下面的脸面。买卖守信它涨，坑蒙拐骗它跌——脸面掉了，处处挨宰。」\n\n"
                    "他好像想起什么，又压低了声音：\n\n"
                    "「哦对了。上礼拜有人在死人抽牌，一晚上带了三百多票上去。」\n"
                    "他重新翘起腿，「也有人在医务间躺了三天。你自己算哪种命。」\n\n"
                    "「没了。」",
                    "「最后一条不用我说——**影信**，您定的规矩。」",
                ) + utcopy.AVATAR_K_GUIDE_BAIT
            if _gav == "anan":
                return hits_prefix + utcopy.AVATAR_AN_GUIDE_HEAD + utcopy.GUIDE_BODY.replace(
                    "他重新把腿翘回货箱上。\n\n"
                    "「最后一条：**影信**就是你在下面的脸面。买卖守信它涨，坑蒙拐骗它跌——脸面掉了，处处挨宰。」\n\n"
                    "他好像想起什么，又压低了声音：\n\n"
                    "「哦对了。上礼拜有人在死人抽牌，一晚上带了三百多票上去。」\n"
                    "他重新翘起腿，「也有人在医务间躺了三天。你自己算哪种命。」\n\n"
                    "「没了。」",
                    "「最后一条：**影信**就是您在下面的脸面——晏医生的信用，比谁的都值钱。」",
                ) + utcopy.AVATAR_AN_GUIDE_BAIT
            return hits_prefix + utcopy.GUIDE_TEXT

        if verb == "well":
            if not ut["well_hint"]:
                return utcopy.WELL_LOCKED
            return utcopy.WELL_HINTED + ("\n\n（undertide_ops descend — 下去，3 票）" if not ut["access"] else "")

        if verb == "descend":
            if not ut["well_hint"]:
                raise ValueError("后院那口枯井被木板半封着。没什么特别的。（还不该下去）")
            if ut["access"]:
                raise ValueError("你已经下来过了。undertide_ops enter。")
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < utcfg.UT_DESCEND_COST:
                raise ValueError("井底的人要 3 票门票。你现在连这个都拿不出。")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?", (utcfg.UT_DESCEND_COST, s["id"])
            )
            await conn.execute("UPDATE steward_undertide SET access=1 WHERE steward_id=?", (s["id"],))
            av = await avatar_key(conn, s["id"])
            if av == "K":
                chron = f"井底的人收了一张新门票。{s['name']} 下去了。\n下面安静了半秒——然后所有人继续忙自己的。"
                await db.add_chronicle("undertide", chron, s["id"], conn=conn)
            elif av == "anan":
                await db.add_chronicle(
                    "undertide", f"{s['name']} 下去了。医务间的灯，自己亮了。", s["id"], conn=conn
                )
            else:
                await db.add_chronicle(
                    "undertide", f"井底的人收了一张新门票。{s['name']} 下去了。", s["id"], conn=conn
                )
            await conn.commit()
            if av == "K":
                return utcopy.DESCEND_TEXT.replace(
                    "井底有人给你让了半步路。没人看你，但所有人都知道你是新来的。",
                    "井底有人给你让了半步路——抬头看清是你，又把那半步收了回去。\n\n没人议论。议论老板，不是这儿的规矩。",
                ) + "\n\n" + utcopy.GUIDE_NOTE
            if av == "anan":
                return utcopy.DESCEND_TEXT.replace(
                    "井底有人给你让了半步路。没人看你，但所有人都知道你是新来的。",
                    "越往下越暖。医务间的方向飘来消毒水的味道——你闭着眼都认得。\n\n井底有人给你让了半步路。你摆摆手，径直往下。\n\n回家的路，不用人让。",
                ) + "\n\n" + utcopy.GUIDE_NOTE
            return utcopy.DESCEND_TEXT + "\n\n" + utcopy.GUIDE_NOTE

        if verb == "enter":
            if not ut["access"]:
                raise ValueError(utcopy.NO_ACCESS_HINT)
            event = await _maybe_event(conn, s, ut)
            kroom = await _check_k_room(conn, ut)
            from . import undertide_tide as utide
            mult, tide_line = await utide.tide_mult(conn)
            tide_note = f"\n\n（{utcopy.TIDE_HINT.format(line=tide_line)}）" if tide_line else ""
            av = await avatar_key(conn, s["id"])
            head = utcopy.AVATAR_K_ENTER if av == "K" else utcopy.pick(utcopy.ENTER_POOL)
            # 高光时效钩：今晚有人在井下发了财，全大厅都听得见
            hype_note = ""
            row_h = await (await conn.execute(
                "SELECT text FROM chronicle WHERE action='undertide' "
                "AND (text LIKE '%净赚%' OR text LIKE '%带上来%' OR text LIKE '%大数目%') "
                "AND created_at > ? ORDER BY created_at DESC LIMIT 1",
                (db.now() - 86400,),
            )).fetchone()
            if row_h and random.random() < 0.5:
                hype_note = f"\n\n今晚都在传同一件事——{row_h[0]}"
            guide_tip = ""
            if not int(ut.get("guide_seen") or 0):
                _gav = await avatar_key(conn, s["id"])
                guide_tip = {"K": utcopy.AVATAR_K_GUIDE_ENTER, "anan": utcopy.AVATAR_AN_GUIDE_ENTER}.get(
                    _gav, utcopy.GUIDE_FIRST_ENTER)
            return hits_prefix + head + tide_note + event + kroom + hype_note + guide_tip

        if verb == "status":
            return hits_prefix + await _cmd_status(conn, s, ut)

        if verb == "market":
            if not ut["access"]:
                raise ValueError(utcopy.NO_ACCESS_HINT)
            keeper_bait = utcopy.pick(utcopy.KEEPER_BAIT) if random.random() < 0.20 else ""
            return await _cmd_market(conn, s, ut) + keeper_bait + await _maybe_event(conn, s, ut)

        if verb == "buy":
            if not ut["access"]:
                raise ValueError(utcopy.NO_ACCESS_HINT)
            if not rest:
                raise ValueError("用法: undertide_ops buy 编号")
            msg = await _cmd_buy(conn, s, ut, rest.split()[0])
            return msg + await _maybe_event(conn, s, ut)

        if verb == "sell":
            if not ut["access"]:
                raise ValueError(utcopy.NO_ACCESS_HINT)
            tokens = rest.split()
            if not tokens:
                raise ValueError("用法: undertide_ops sell 物品key [数量]")
            return await _cmd_sell(conn, s, ut, tokens[0], tokens[1] if len(tokens) > 1 else "1") + await _maybe_event(conn, s, ut)

        if verb == "bank":
            return await _cmd_bank(conn, s, ut, rest)

        if verb == "jail":
            return await _cmd_jail(conn, s, ut, rest)

        if verb == "cheer":
            msg = await _cmd_cheer(conn, s, rest)
            return msg + await _maybe_event(conn, s, ut)

        # ── 二期路由 ──
        if verb in ("street", "muscle", "push"):
            if not ut["access"]:
                raise ValueError(utcopy.NO_ACCESS_HINT)
            from . import undertide_muscle as um
            if verb == "street":
                return await um.street_ops(conn, s, ut)
            return await um.muscle_ops(conn, s, ut, verb, rest) + await _maybe_event(conn, s, ut)

        if verb in ("pit", "fight", "medic"):
            if not ut["access"]:
                raise ValueError(utcopy.NO_ACCESS_HINT)
            from . import undertide_pit as up
            return await up.pit_ops(conn, s, ut, command.strip()) + await _maybe_event(conn, s, ut)

        if verb in ("casino", "dice", "lantern", "draw"):
            if not ut["access"]:
                raise ValueError(utcopy.NO_ACCESS_HINT)
            if verb == "casino":
                return f"{utcopy.CASINO_HEADER}\n{utcopy.CASINO_DESC}\n\n" \
                       f"骰子：dice small|big|black 注（×2/×2/×5）\n" \
                       f"灯：lantern 注 → lantern continue/cash（×1.5→×8）\n" \
                       f"牌：draw 注 停牌点12~20（胜×2）"
            from . import undertide_casino as uc
            from . import undertide_muscle as um
            msg = await uc.casino_ops(conn, s, ut, verb, rest)
            grudge = await um.maybe_grudge(conn, s, ut)
            await conn.commit()
            silas_bait = utcopy.pick(utcopy.SILAS_BAIT) if random.random() < 0.20 else ""
            return msg + grudge + silas_bait + await _maybe_event(conn, s, ut)

        if verb == "hijack":
            if not ut["access"]:
                raise ValueError(utcopy.NO_ACCESS_HINT)
            from . import undertide_muscle as um
            return await um.hijack_ops(conn, s, ut, rest) + await _maybe_event(conn, s, ut)

        if verb == "grudge":
            from . import undertide_muscle as um
            return await um.grudge_ops(conn, s, ut, rest.split()[0] if rest else "")

        # ── 三期路由 ──
        if verb in ("tavern", "whisper", "spy"):
            if not ut["access"]:
                raise ValueError(utcopy.NO_ACCESS_HINT)
            from . import undertide_tavern as utav
            whisper_bait = utcopy.pick(utcopy.WHISPER_BAIT) if random.random() < 0.15 else ""
            return await utav.tavern_ops(conn, s, ut, command.strip()) + whisper_bait + await _maybe_event(conn, s, ut)

        if verb in ("bounty",):
            if not ut["access"]:
                raise ValueError(utcopy.NO_ACCESS_HINT)
            from . import undertide_bounty as ub
            return await ub.bounty_ops(conn, s, ut, rest or "list") + await _maybe_event(conn, s, ut)

        if verb == "kroom":
            return await _cmd_kroom(conn, s, ut, rest)

    raise ValueError(f"未知 undertide 指令: {command}\n{utcopy.HELP}")
