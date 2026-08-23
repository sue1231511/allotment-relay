"""胁迫经济 — 劫持 / 强买 / 强卖 / 寻仇（二期）。天天侧。"""

from __future__ import annotations

import json
import random
from typing import Any

import aiosqlite

from . import db
from . import undertide_catalog as cat
from . import undertide_config as utcfg
from . import undertide_copy as utcopy


def _day_id() -> int:
    return db.day_id()


# ── 街头随机 NPC 池 ─────────────────────────────────────────


async def _daily_action_used(
    conn: aiosqlite.Connection, steward_id: int, action: str, limit: int
) -> bool:
    day = _day_id()
    row = await (await conn.execute(
        "SELECT count FROM ut_daily_actions WHERE steward_id=? AND day_id=? AND action=?",
        (steward_id, day, action),
    )).fetchone()
    return int(row[0] if row else 0) >= limit


async def _mark_daily_action(conn: aiosqlite.Connection, steward_id: int, action: str) -> None:
    day = _day_id()
    await conn.execute(
        """
        INSERT INTO ut_daily_actions (steward_id, day_id, action, count) VALUES (?,?,?,1)
        ON CONFLICT(steward_id, day_id, action) DO UPDATE SET count = count + 1
        """,
        (steward_id, day, action),
    )


async def _ensure_street(conn: aiosqlite.Connection, day: int) -> list[dict[str, Any]]:
    conn.row_factory = aiosqlite.Row
    rows = await (await conn.execute(
        "SELECT * FROM ut_street_npc WHERE day_id=? ORDER BY slot", (day,)
    )).fetchall()
    if rows:
        return [dict(r) for r in rows]
    rng = random.Random(day * 104729)
    count = rng.randint(*utcfg.UT_NPC_POOL_DAILY)
    used: set[str] = set()
    for slot in range(1, count + 1):
        tier = rng.choices(["soft", "norm", "hard", "danger"], weights=[35, 40, 18, 7])[0]
        pool = [n for n in cat.STREET_NPC_NAMES[tier] if n not in used]
        name = rng.choice(pool) if pool else rng.choice(cat.STREET_NPC_NAMES[tier])
        used.add(name)
        # 货物：1~3 件常规 + 10% 稀有
        stock: list[list] = []
        keys = rng.sample(list(cat.COMMON_GOODS), rng.randint(1, 3))
        for k in keys:
            qty = 1 if k not in stock else 0
            stock.append([f"ut_{k}", 1])
        if rng.random() < utcfg.UT_NPC_RARE_CHANCE:
            stock.append([f"ut_{rng.choice(list(cat.RARE_GOODS))}", 1])
        # 15% 档位标签走眼（显示档 ≠ 真档）
        shown = tier
        if rng.random() < utcfg.UT_TAG_SHIFT_CHANCE:
            order = ["soft", "norm", "hard", "danger"]
            shift = rng.choice([-1, 1])
            shown = order[max(0, min(3, order.index(tier) + shift))]
        await conn.execute(
            "INSERT INTO ut_street_npc (day_id, slot, name, tier, stock_json) VALUES (?,?,?,?,?)",
            (day, slot, name, tier, json.dumps({"tier_shown": shown, "stock": stock})),
        )
    await conn.commit()
    rows = await (await conn.execute(
        "SELECT * FROM ut_street_npc WHERE day_id=? ORDER BY slot", (day,)
    )).fetchall()
    return [dict(r) for r in rows]


def _stock_value(stock: list[list[str, int]]) -> int:
    total = 0
    for key, qty in stock:
        base_key = key[3:]
        meta = cat.RARE_GOODS.get(base_key) or cat.COMMON_GOODS.get(base_key) or cat.LINKED_GOODS.get(base_key) or {"vend": 10}
        total += int(meta.get("vend", 10)) * qty
    return total


async def street_ops(conn: aiosqlite.Connection, s: dict[str, Any], ut: dict[str, Any]) -> str:
    day = _day_id()
    npcs = await _ensure_street(conn, day)
    lines = [utcopy.STREET_HEADER, ""]
    for n in npcs:
        data = json.loads(n["stock_json"])
        shown = data.get("tier_shown", n["tier"])
        stock_note = "、".join(
            (cat.COMMON_GOODS.get(k[3:], {}).get("name") or cat.RARE_GOODS.get(k[3:], {}).get("name") or k)
            for k, _ in data["stock"]
        )
        lines.append(f"  #{n['slot']} 【{cat.TIER_LABEL[shown]}】{n['name']} — 带着：{stock_note}")
    lines.append("")
    lines.append(cat.TIER_MOOD["soft"])
    lines.append(utcopy.STREET_HINT)
    return "\n".join(lines)


def _find_npc(npcs: list[dict[str, Any]], query: str) -> dict[str, Any] | None:
    q = query.strip().lstrip("#")
    for n in npcs:
        if q.isdigit() and int(q) == n["slot"]:
            return n
        if n["name"] == query.strip():
            return n
    return None


async def _my_power(conn: aiosqlite.Connection, steward_id: int) -> int:
    from . import undertide_pit
    from . import db as _db
    cur = await conn.execute("SELECT health, energy FROM stewards WHERE id=?", (steward_id,))
    health, energy = (await cur.fetchone())
    cur = await conn.execute(
        "SELECT drug_buff, drug_until FROM steward_undertide WHERE steward_id=?", (steward_id,)
    )
    drow = await cur.fetchone()
    if drow and drow[1] and _db.now() < int(drow[1]):
        health = min(130, health + int(drow[0] or 0))
    _, rank_bonus, _ = await undertide_pit.pit_rank(conn, steward_id)
    return int(health / 100 * 30 + energy / 100 * 15 + rank_bonus + random.randint(1, 20))


async def muscle_ops(
    conn: aiosqlite.Connection, s: dict[str, Any], ut: dict[str, Any], verb: str, rest: str
) -> str:
    parts = rest.split()
    day = _day_id()
    npcs = await _ensure_street(conn, day)
    from . import undertide as utmod

    if verb == "muscle":
        if await _daily_action_used(conn, s["id"], "muscle", utcfg.UT_MUSCLE_DAILY):
            raise ValueError(f"今天帘外强买次数用完了（每日 {utcfg.UT_MUSCLE_DAILY} 次）。")
        if not parts:
            raise ValueError("用法: undertide_ops muscle 名号（street 查看）")
        npc = _find_npc(npcs, " ".join(parts[:2]) if parts[0].isdigit() else parts[0])
        if not npc:
            raise ValueError("帘外没这个人。street 看看今晚都有谁。")
        data = json.loads(npc["stock_json"])
        value = _stock_value(data["stock"])
        pay = max(1, int(value * utcfg.UT_MUSCLE_PAY))
        my_power = await _my_power(conn, s["id"])
        their_power = utcfg.UT_NPC_TIERS[npc["tier"]] + random.randint(1, 20)
        # K 真身·老板威压：软柿子和普通人不抵抗；硬茬和别惹 +10 气场
        _av = await utmod.avatar_key(conn, s["id"])
        no_resist = _av == "K" and npc["tier"] in ("soft", "norm")
        if _av == "K":
            my_power += 10
        margin = 999 if no_resist else my_power - their_power

        power_line = (
            "（他认出了你——没有抵抗。）" if no_resist
            else f"战力 {my_power} vs {their_power}"
        )
        lines = [f"«强买 · {npc['name']}»", f"真实档位：【{cat.TIER_LABEL[npc['tier']]}】（标签可能是走眼的）",
                 power_line, ""]
        if margin >= 0:
            hurt = margin < 8 and not no_resist
            for key, qty in data["stock"]:
                await db.add_item(conn, s["id"], key, qty)
            await conn.execute(
                "UPDATE stewards SET tickets=MAX(0,tickets-?) WHERE id=?", (pay, s["id"])
            )
            await utmod._bump_rep(conn, s["id"], -4)
            if no_resist:
                body = utcopy.AVATAR_K_MUSCLE_NO_RESIST
            else:
                body = utcopy.pick(utcopy.MUSCLE_WIN_HURT if hurt else utcopy.MUSCLE_WIN).format(
                    npc=npc["name"], pay=pay)
            if hurt:
                await conn.execute(
                    "UPDATE stewards SET health=MAX(0,health-?) WHERE id=?",
                    (random.randint(5, 10), s["id"]))
            lines.append(body)
            goods = "、".join(
                (cat.COMMON_GOODS.get(k[3:], {}).get("name") or cat.RARE_GOODS.get(k[3:], {}).get("name") or k)
                for k, _ in data["stock"])
            lines.append(f"\n（货值约 {value} · 实付 {pay} · 得到：{goods} · 影信 −4）")
            # 记仇
            if random.random() < utcfg.UT_NPC_GRUDGE[npc["tier"]]:
                await _add_grudge(conn, s["id"], npc["name"], npc["tier"], value)
                lines.append("\n（他记住了你。）")
        else:
            steal = random.randint(5, 15)
            await conn.execute(
                "UPDATE stewards SET tickets=MAX(0,tickets-?), health=MAX(0,health-?) WHERE id=?",
                (steal, random.randint(5, 10), s["id"]))
            await utmod._bump_rep(conn, s["id"], -5)
            lines.append(utcopy.pick(utcopy.MUSCLE_FAIL).format(npc=npc["name"]))
            lines.append(f"\n（没拿到货 · 被反抢 {steal} 票 · 影信 −5）")
        from . import undertide_pit as _upt
        await _upt.pit_record(conn, s["id"], "muscle", "win" if margin >= 0 else "lose", npc["name"])
        await _mark_daily_action(conn, s["id"], "muscle")
        await conn.commit()
        return "\n".join(lines)

    if verb == "push":
        if await _daily_action_used(conn, s["id"], "push", utcfg.UT_PUSH_DAILY):
            raise ValueError(f"今天帘外强卖次数用完了（每日 {utcfg.UT_PUSH_DAILY} 次）。")
        if len(parts) < 2:
            raise ValueError("用法: undertide_ops push 名号 物品key")
        npc = _find_npc(npcs, parts[0])
        if not npc:
            raise ValueError("帘外没这个人。")
        item_key = parts[1]
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item=?", (s["id"], item_key)
        )).fetchone()
        if not row or row["quantity"] < 1:
            raise ValueError(f"行囊里没有 {item_key}（tote_ops list / undertide market 的货）")
        base_key = item_key[3:-2] if item_key.endswith("_s") else item_key[3:]
        meta = (cat.LINKED_GOODS.get(base_key) or cat.RARE_GOODS.get(base_key)
                or cat.COMMON_GOODS.get(base_key) or {"name": item_key, "vend": 10})
        mult = random.uniform(*utcfg.UT_PUSH_GAIN)
        gain = int(meta.get("vend", 10) * mult)

        my_power = await _my_power(conn, s["id"])
        their_power = utcfg.UT_NPC_TIERS[npc["tier"]] + random.randint(1, 20)
        # K 真身·老板威压
        _av = await utmod.avatar_key(conn, s["id"])
        no_resist = _av == "K" and npc["tier"] in ("soft", "norm")
        if _av == "K":
            my_power += 10
        win = no_resist or my_power >= their_power

        if win:
            await conn.execute(
                "UPDATE satchel SET quantity=quantity-1 WHERE steward_id=? AND item=?",
                (s["id"], item_key),
            )
            await conn.execute(
                "UPDATE satchel SET quantity=0 WHERE steward_id=? AND item=? AND quantity<=0",
                (s["id"], item_key),
            )
            await conn.execute("UPDATE stewards SET tickets=tickets+? WHERE id=?", (gain, s["id"]))
            near = not no_resist and (my_power - their_power) < 8
            await utmod._bump_rep(conn, s["id"], -3 if near else -2)
            if no_resist:
                lines = [utcopy.AVATAR_K_PUSH_NO_RESIST]
            else:
                lines = [utcopy.pick(utcopy.PUSH_WIN).format(npc=npc["name"], item=meta["name"], gain=gain)]
            lines.append(f"\n（{meta['name']} ×1 → {gain} 票 · 影信 −{3 if near else 2}）")
            if near and random.random() < utcfg.UT_NPC_GRUDGE[npc["tier"]] * 2:
                await _add_grudge(conn, s["id"], npc["name"], npc["tier"], gain)
                lines.append("\n（他收了货。也记了仇。这两件事不冲突。）")
        else:
            await utmod._bump_rep(conn, s["id"], -4)
            lines = [utcopy.pick(utcopy.PUSH_FAIL).format(npc=npc["name"])]
            lines.append("\n（货还在你手里 · 影信 −4）")
        from . import undertide_pit as _upt2
        await _upt2.pit_record(conn, s["id"], "push", "win" if win else "lose", npc["name"])
        await _mark_daily_action(conn, s["id"], "push")
        await conn.commit()
        return "\n".join(lines)

    raise ValueError("未知指令（muscle/push）")


# ── 劫持 ────────────────────────────────────────────────────

HIJACK_TARGETS = {
    "掌柜": 40, "silas": 45, "Silas": 45, "看门人": 50, "耳语人": 25, "斗士": 70,
    "jester": 10, "Jester": 10, "jester潮汐博彩": 10,
}


async def hijack_ops(
    conn: aiosqlite.Connection, s: dict[str, Any], ut: dict[str, Any], rest: str
) -> str:
    target = rest.strip()
    if not target:
        return f"{utcopy.HIJACK_HEADER}\n{utcopy.HIJACK_TARGETS_HINT}"
    from . import undertide as utmod

    day = _day_id()
    cur = await conn.execute(
        "SELECT COUNT(*) FROM ut_hijack_log WHERE steward_id=? AND day_id=?", (s["id"], day)
    )
    if (await cur.fetchone())[0] >= utcfg.UT_HIJACK_DAILY:
        raise ValueError("今天干过一票了。潮下不鼓励过劳。")
    if db.now() < int(ut.get("ban_until") or 0):
        return utcopy.HIJACK_BAN_MSG

    # ── 特例：Jester（守机器的闲人，战力 10，但劫他触发机器大爆炸）──
    if target in ("jester", "Jester"):
        cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
        wallet = (await cur.fetchone())[0]
        # Jester 毫无战力——但机器替他"说话"
        await conn.execute(
            "UPDATE stewards SET tickets=MAX(0, tickets-?) WHERE id=?",
            (min(wallet, random.randint(15, 30)), s["id"]),
        )
        await conn.execute(
            "UPDATE steward_undertide SET hijack_fails=hijack_fails+1 WHERE steward_id=?",
            (s["id"],),
        )
        await utmod._bump_rep(conn, s["id"], -6)
        await db.add_chronicle(
            "undertide",
            f"有人想劫 Jester。机器替他挡了——灯全亮了，嗡嗡响了十秒，那人被弹出去三米远。",
            None, conn=conn,
        )
        await conn.commit()
        return (
            "Jester 看都没看你。你把手伸过去——\n\n"
            "机器猛地亮了。整排灯。嗡嗡嗡嗡。\n\n"
            "你被一股力气弹出去，后背撞上墙，票袋在半空翻了两个跟头。\n\n"
            "Jester 终于抬头，像老师看学生：\n\n"
            "「这台机器护着我。」他说，「三十年了。」\n\n"
            "（被机器弹飞 · 票散了一地 · 影信 −6 · 你不是第一个试的）"
        )

    # ── 特例：猫猫 ──
    if target in ("猫猫", "猫猫老板娘", "恶猫钱庄老板娘"):
        body_loss = random.randint(*utcfg.UT_HIJACK_CAT_BODY)
        cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
        wallet = (await cur.fetchone())[0]
        fee = utcfg.UT_SURGERY_FEE
        lines = [utcopy.SURGERY_FULL, ""]
        if wallet >= fee:
            await conn.execute("UPDATE stewards SET tickets=tickets-? WHERE id=?", (fee, s["id"]))
            lines.append(f"（body −{body_loss} · energy 清零 · 手术费 −{fee} 票）")
        else:
            await conn.execute(
                "INSERT INTO ut_debts (steward_id, principal, due_day, source, created_day) VALUES (?,?,?,?,?)",
                (s["id"], fee, day + 7, "surgery", day),
            )
            lines.append(f"（body −{body_loss} · energy 清零 · 手术费 {fee} 票已记账恶猫钱庄）")
        await conn.execute(
            "UPDATE stewards SET health=MAX(0,health-?), energy=0 WHERE id=?",
            (body_loss, s["id"]),
        )
        await conn.execute(
            "UPDATE steward_undertide SET mark_sewn='反复缝合' WHERE steward_id=?", (s["id"],)
        )
        await utmod._bump_rep(conn, s["id"], -10)
        await conn.execute(
            "INSERT INTO ut_hijack_log (steward_id, day_id, target, outcome) VALUES (?,?,?,?)",
            (s["id"], day, "猫猫", "surgery"),
        )
        await db.add_chronicle(
            "undertide",
            f"有人对恶猫钱庄的老板娘动了手。当晚医务间的灯亮了很久。{s['name']}是自己走出来的，勉强算。",
            s["id"], conn=conn,
        )
        await conn.commit()
        lines.append("（永久档案标记：「反复缝合」。小八逢人就念。影信 −10）")
        return "\n".join(lines)

    # ── 特例：荔栀 ──
    if target in ("荔栀", "老板娘", "lizhi"):
        cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
        wallet = (await cur.fetchone())[0]
        seized = int(wallet * utcfg.UT_HIJACK_LIZHI_CASH)
        body_loss = random.randint(*utcfg.UT_HIJACK_LIZHI_BODY)
        lines = [utcopy.LIZHI_AMBUSH, ""]
        await conn.execute(
            "UPDATE stewards SET tickets=tickets-?, health=MAX(0,health-?), energy=0 WHERE id=?",
            (seized, body_loss, s["id"]),
        )
        # 必毁一块作物（成熟>进度最高>装件>留话）
        conn.row_factory = aiosqlite.Row
        plots = await (await conn.execute(
            "SELECT id, crop, slot, planted_at FROM parcels WHERE steward_id=? AND crop IS NOT NULL ORDER BY planted_at",
            (s["id"],),
        )).fetchall()
        if plots:
            await conn.execute(
                "UPDATE parcels SET crop=NULL, planted_at=NULL, tended=0 WHERE id=?",
                (plots[0]["id"],),
            )
            lines.append(utcopy.LIZHI_CROP_DESTROYED)
            crop_note = f"（地块 #{plots[0]['slot']} 的作物被毁——真毁）"
        else:
            fitting = await (await conn.execute(
                "SELECT id FROM hut_fittings WHERE steward_id=? LIMIT 1", (s["id"],)
            )).fetchone()
            if fitting:
                await conn.execute("DELETE FROM hut_fittings WHERE id=?", (fitting["id"],))
                lines.append(utcopy.LIZHI_CROP_DESTROYED)
                crop_note = "（一个小屋装件被拆走——真拆）"
            else:
                lines.append(utcopy.LIZHI_NO_CROP)
                crop_note = "（地里没东西可毁。K 的人留了话。）"
        await conn.execute(
            "INSERT INTO ut_hijack_log (steward_id, day_id, target, outcome) VALUES (?,?,?,?)",
            (s["id"], day, "荔栀", "k_room"),
        )
        await utmod._bump_rep(conn, s["id"], -8)
        await conn.commit()
        lines.append(f"\n（现金 −{seized} · body −{body_loss} · energy 清零 · 影信 −8）\n{crop_note}")
        return "\n".join(lines)

    # ── 普通目标 ──
    power = HIJACK_TARGETS.get(target)
    if power is None:
        raise ValueError(f"不认识「{target}」。{utcopy.HIJACK_TARGETS_HINT}")
    my_power = await _my_power(conn, s["id"])
    their_power = power + random.randint(1, 20)
    _av = await utmod.avatar_key(conn, s["id"])
    roll = random.random()
    if _av == "K":
        # 老板威压：没人敢惹，但也没人假装高兴
        outcome = (
            "clean" if roll < 0.70 else
            "hurt_npc" if roll < 0.85 else
            "hurt_self" if roll < 0.95 else "fail"
        )
    else:
        outcome = (
            "clean" if roll < 0.40 else
            "hurt_npc" if roll < 0.65 else
            "hurt_self" if roll < 0.85 else "fail"
        )
    # 战力差修正：碾压时更顺，劣势时易翻车
    if my_power - their_power >= 15 and outcome == "fail":
        outcome = "hurt_self"
    if their_power - my_power >= 15 and outcome == "clean":
        outcome = "hurt_self"

    loot = random.randint(*utcfg.UT_HIJACK_LOOT)
    lines = [f"«劫持 · {target}»", f"战力 {my_power} vs {their_power}", ""]
    rep_delta = utcfg.UT_HIJACK_REP[outcome]

    if outcome in ("clean", "hurt_npc", "hurt_self"):
        await conn.execute("UPDATE stewards SET tickets=tickets+? WHERE id=?", (loot, s["id"]))
        pool = {"clean": utcopy.HIJACK_CLEAN, "hurt_npc": utcopy.HIJACK_HURT_NPC,
                "hurt_self": utcopy.HIJACK_HURT_SELF}[outcome]
        if _av == "K":
            lines.append(utcopy.pick(utcopy.AVATAR_K_HIJACK_WIN))
        else:
            lines.append(utcopy.pick(pool))
        note = f"（+{loot} 票 · 影信 {rep_delta}）"
        if outcome == "hurt_self":
            body_loss = random.randint(*[abs(x) for x in utcfg.UT_HIJACK_BODY_SELF])
            await conn.execute(
                "UPDATE stewards SET health=MAX(0,health-?) WHERE id=?", (body_loss, s["id"])
            )
            note = f"（+{loot} 票 · body −{body_loss} · 影信 {rep_delta}）"
        if outcome == "hurt_npc" and target == "斗士":
            lines.append("\n（深坑的墙上，今晚多了一块白。）")
    else:
        fail_count = int(ut.get("hijack_fails") or 0) + 1
        steal = random.randint(5, 15)
        await conn.execute(
            "UPDATE stewards SET tickets=MAX(0,tickets-?), health=MAX(0,health-?) WHERE id=?",
            (steal, random.randint(5, 10), s["id"]),
        )
        ban_note = ""
        await conn.execute(
            "UPDATE steward_undertide SET hijack_fails=? WHERE steward_id=?", (fail_count, s["id"])
        )
        if fail_count >= utcfg.UT_HIJACK_BAN_COUNT:
            await conn.execute(
                "UPDATE steward_undertide SET ban_until=? WHERE steward_id=?",
                (db.now() + 86400, s["id"]),
            )
            await conn.execute(
                "UPDATE steward_undertide SET hijack_fails=0 WHERE steward_id=?", (s["id"],)
            )
            ban_note = "\n（三连败——黑市、赌场、深坑联合抵制 24 小时。）"
        lines.append(utcopy.pick(utcopy.HIJACK_FAIL))
        note = f"（空手 · 被反抢 {steal} 票 · 影信 {rep_delta}）{ban_note}"

    await utmod._bump_rep(conn, s["id"], rep_delta)
    await conn.execute(
        "INSERT INTO ut_hijack_log (steward_id, day_id, target, outcome) VALUES (?,?,?,?)",
        (s["id"], day, target, outcome),
    )
    # 普通劫持计入战绩（猫猫/荔栀特例不计——那不是打架是作死）
    if target not in ("猫猫", "猫猫老板娘", "恶猫钱庄老板娘", "荔栀", "老板娘", "lizhi"):
        from . import undertide_pit as _upt3
        await _upt3.pit_record(conn, s["id"], "hijack", "win" if outcome in ("clean","hurt_npc","hurt_self") else "lose", target)
    await conn.commit()
    lines.append(note)
    return "\n".join(lines)


# ── 寻仇 ────────────────────────────────────────────────────

async def _add_grudge(
    conn: aiosqlite.Connection, steward_id: int, npc_name: str, tier: str, value: int
) -> None:
    cur = await conn.execute(
        "SELECT COUNT(*) FROM ut_grudge WHERE steward_id=? AND status='active'", (steward_id,)
    )
    if (await cur.fetchone())[0] >= utcfg.UT_GRUDGE_MAX:
        return
    await conn.execute(
        "INSERT INTO ut_grudge (steward_id, npc_name, tier, item_value, created_at) VALUES (?,?,?,?,?)",
        (steward_id, npc_name, tier, value, db.now()),
    )


async def maybe_grudge(
    conn: aiosqlite.Connection, s: dict[str, Any], ut: dict[str, Any]
) -> str:
    """潮下动作后 8% 掷骰触发寻仇。"""
    if int(ut.get("pending_grudge") or 0):
        return ""
    cur = await conn.execute(
        "SELECT COUNT(*) FROM ut_grudge WHERE steward_id=? AND status='active'", (s["id"],)
    )
    count = (await cur.fetchone())[0]
    if not count or random.random() > utcfg.UT_GRUDGE_CHANCE_DAILY * 12:  # 每动作近似概率
        return ""
    conn.row_factory = aiosqlite.Row
    row = await (await conn.execute(
        "SELECT * FROM ut_grudge WHERE steward_id=? AND status='active' ORDER BY created_at LIMIT 1",
        (s["id"],),
    )).fetchone()
    if not row:
        return ""
    await conn.execute(
        "UPDATE steward_undertide SET pending_grudge=? WHERE steward_id=?", (row["id"], s["id"])
    )
    await conn.commit()
    return "\n\n——\n" + utcopy.GRUDGE_TRIGGER.format(npc=row["npc_name"])


async def grudge_ops(
    conn: aiosqlite.Connection, s: dict[str, Any], ut: dict[str, Any], action: str
) -> str:
    gid = int(ut.get("pending_grudge") or 0)
    if not gid:
        raise ValueError("没人堵你。至少现在没有。")
    conn.row_factory = aiosqlite.Row
    row = await (await conn.execute(
        "SELECT * FROM ut_grudge WHERE id=? AND steward_id=?", (gid, s["id"])
    )).fetchone()
    if not row:
        await conn.execute("UPDATE steward_undertide SET pending_grudge=0 WHERE steward_id=?", (s["id"],))
        await conn.commit()
        raise ValueError("那条账已经翻篇了。")
    from . import undertide as utmod
    cur = await conn.execute(
        "SELECT COUNT(*) FROM ut_grudge WHERE steward_id=? AND status='active'", (s["id"],)
    )
    full_pool = (await cur.fetchone())[0] >= utcfg.UT_GRUDGE_MAX

    async def _clear() -> None:
        await conn.execute("UPDATE ut_grudge SET status='done' WHERE id=?", (gid,))
        await conn.execute(
            "UPDATE steward_undertide SET pending_grudge=0 WHERE steward_id=?", (s["id"],)
        )

    if action == "pay" and not full_pool:
        cost = int(row["item_value"] * utcfg.UT_GRUDGE_PAYOFF)
        cur2 = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
        if (await cur2.fetchone())[0] < cost:
            raise ValueError(f"消灾费 {cost} 票。付不起就只能打了（grudge fight）或跑（grudge run）。")
        await conn.execute("UPDATE stewards SET tickets=tickets-? WHERE id=?", (cost, s["id"]))
        await _clear()
        await conn.commit()
        return utcopy.GRUDGE_PAY + f"\n（−{cost} 票 · 此单了结）"

    # fight：对面 2 人（满员 3 人）
    enemy_base = (utcfg.UT_NPC_TIERS.get(row["tier"], 30)) * (1.5 if full_pool else 0.75)
    my_power = await _my_power(conn, s["id"])
    their_power = int(enemy_base) + random.randint(1, 20)
    if action in ("fight", "pay"):  # pay 但满员 → 强制一战
        if my_power >= their_power:
            loot = random.randint(10, 25)
            await conn.execute("UPDATE stewards SET tickets=tickets+? WHERE id=?", (loot, s["id"]))
            await _clear()
            await utmod._bump_rep(conn, s["id"], 1)
            await conn.commit()
            head = utcopy.GRUDGE_FULL_POOL if full_pool else ""
            return head + "\n" + utcopy.GRUDGE_FIGHT_WIN.format(loot=loot)
        await conn.execute(
            "UPDATE stewards SET tickets=MAX(0,tickets-?), health=MAX(0,health-?) WHERE id=?",
            (random.randint(10, 20), random.randint(10, 15), s["id"]),
        )
        await _clear()
        await conn.commit()
        return utcopy.GRUDGE_FIGHT_LOSE + "\n（被抢走一些票 · body 大跌）"

    if action == "run":
        if random.random() < 0.60:
            await _clear()
            await conn.commit()
            return utcopy.GRUDGE_RUN_OK + "\n（这一单，他们不想再追了）"
        await conn.execute(
            "UPDATE stewards SET tickets=MAX(0,tickets-?), health=MAX(0,health-?) WHERE id=?",
            (random.randint(5, 15), random.randint(10, 15), s["id"]),
        )
        await _clear()
        await conn.commit()
        return utcopy.GRUDGE_RUN_FAIL

    raise ValueError("用法: undertide_ops grudge pay|fight|run")
