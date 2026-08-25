"""NPC — 固定访客台词 + 偷菜贼名号。拾叶巷口随机小偷/乞丐/碰瓷/敲诈。"""

from __future__ import annotations

import random
from typing import Any

import aiosqlite

from . import config, db, flavor, survival, world
from .catalog import ITEM_NAMES, KITCHEN_DISHES, NPC_FIXED, NPC_THIEVES
from .game import require_steward


def _day_id() -> int:
    return db.day_id()


def _find_npc(query: str) -> dict[str, Any] | None:
    q = query.strip()
    ql = q.lower()
    for npc in NPC_FIXED:
        if npc["key"] == ql or npc["name"] == q or npc["name"].lower() == ql:
            return npc
    return None


async def npc_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    parts = command.strip().split(maxsplit=1)
    verb = parts[0].lower() if parts else "list"

    if verb == "list":
        lines = ["固定 NPC（visit 名字或 key）:"]
        for npc in NPC_FIXED:
            tag = ""
            if npc["key"] == "gugu_dove":
                tag = " · 昼间每天掷一次盯梢，不可伤害"
            elif npc["key"] == "qiaoqiao":
                tag = " · 诊所 NPC，治病用 visit_ops clinic treat"
            elif npc["key"] == "lili":
                tag = " · 流动贝壳商，visit_ops lili scan/trade/summon"
            elif npc["key"] == "shaonian":
                tag = " · 滩头卜卦，visit_ops shaonian fortune/catalog"
            elif npc["key"] == "tt":
                tag = " · 杂货店，visit_ops tt catalog/buy/gift"
            elif npc["key"] == "old_salt":
                tag = " · 赶海/潮汐提示"
            elif npc["key"] == "buxing":
                tag = " · 灯塔问潮、茶、点灯与守夜；visit_ops buxing help"
            elif npc["key"] == "musong":
                tag = " · 渡口送别；visit_ops musong send 名字 / remember"
            elif npc["key"] == "jingshan":
                tag = " · 商船糕点委托；visit_ops jingshan visit / order / deliver"
            elif npc["key"] == "aboo":
                tag = " · 潮生会值事；visit_ops 潮生会 / 税 / 维 / 基金。岸税周一划，岸维每天划。补贴周二四六自动发。不能加入"
            elif npc["key"] == "herb_aunt":
                tag = " · 厨房配方提示"
            elif npc["key"] == "market_fan":
                tag = " · 集市挂单"
            elif npc["key"] == "shiye":
                tag = " · 路上每天掷一次碰上；visit 拾叶 主动必触发"
            elif npc["key"] == "lizhi":
                tag = " · 酒吧老板娘，bar_ops tonight/chat"
            elif npc["key"] == "wangfu":
                tag = " · 固定驻唱，bar_ops song"
            lines.append(f"  {npc['key']} — {npc['name']}{tag}")
        lines.append(f"偷菜贼名号: {', '.join(NPC_THIEVES[:3])}…")
        lines.append("每日首次 visit 略回暖雾智/档信（斑鸠、拾叶、何敬山事件除外）")
        return "\n".join(lines)

    if verb == "visit" and len(parts) >= 2:
        from . import chaoshen as chaoshen_mod
        if chaoshen_mod.is_alias(parts[1]):
            return await chaoshen_mod.chaoshen_ops(key_id, "问")
        npc = _find_npc(parts[1])
        if not npc:
            raise ValueError("未知 NPC，list 查看")
        if npc["key"] == "shiye":
            return await _visit_shiye(s)
        if npc["key"] == "jingshan":
            from . import jingshan as jingshan_mod
            return await jingshan_mod.jingshan_ops(key_id, "visit")
        if npc["key"] == "buxing":
            from . import buxing as buxing_mod
            return await buxing_mod.buxing_ops(key_id, "visit")
        if npc["key"] == "aboo":
            from . import chaoshen as chaoshen_mod
            return await chaoshen_mod.chaoshen_ops(key_id, "问")
        if npc["key"] == "tt":
            from . import tt as tt_mod
            return await tt_mod.tt_ops(key_id, "visit")
        line = random.choice(npc["lines"])
        extra = await _visit_context(s, npc["key"])
        gift = await _daily_visit_gift(s["id"], npc["key"])
        return f"{npc['name']}：{line}{extra}{gift}"

    if verb == "thieves":
        return "偷菜贼名册:\n" + "\n".join(f"  · {t}" for t in NPC_THIEVES)

    raise ValueError(f"未知 npc 指令: {command}（list/visit/thieves）")


async def _visit_context(steward: dict, key: str) -> str:
    tide = world.current_tide()
    weather = world.current_weather()
    phase = world.current_day_phase()
    if key == "gugu_dove":
        return flavor.pick([
            "——咕咕咕咕咕咕，飞走了",
            "——伤不得，联盟牌子上写着呢",
            "——它看你不顺眼，但主要是看庄稼顺眼",
        ])
    if key == "lili":
        from . import lili as lili_mod
        async with db.connect() as conn:
            hint = await lili_mod.active_visit_hint(conn)
        if hint:
            return f"——{hint}"
        return "——驮包叮当远去了。赶海捡到贝壳后 visit_ops lili summon 贝壳，可向海风寄气息"
    if key == "old_salt":
        bits = [
            f"现在 {world.tide_label(tide)} · {world.weather_label(weather)}",
        ]
        if tide == "ebb":
            bits.append("退潮赶海：tide_ops beach dig，贝壳权重高")
        elif tide == "slack":
            bits.append("平潮可 probe 掏洞，dig 也行")
        else:
            bits.append("涨潮：dig 和 probe 都关，坐钓 tide_ops cast 碰运气")
        if weather == "misty":
            bits.append("雾天珠砂/海玻璃略多")
        return "——" + "；".join(bits)
    if key == "musong":
        scene = {
            "dawn": "晨雾还贴着渡口水面，他把茶杯搁在膝头，望向第一班离岸的小船",
            "day": "日光照亮渡口，他坐在旧木凳上，能看清每一张离开的脸",
            "dusk": "落日在渡口外铺出一条长路，他一直看到最后一道影子沉进暮色",
            "night": "渡口只剩灯塔的光，他仍朝黑水望着，像在等一个迟来的回头",
        }.get(phase, "他坐在渡口的旧木凳上，安静看着来路与去路")
        return f"——{scene}。musong send 名字 请他替你送一程；remember 看曾经送过谁"
    if key == "herb_aunt":
        dish_key, meta = random.choice(list(KITCHEN_DISHES.items()))
        ings = " + ".join(ITEM_NAMES.get(i, i) for i in meta["ings"])
        return f"——今儿提一嘴：kitchen_ops cook {dish_key}（{ings}）"
    if key == "market_fan":
        return "——缺料就 market_ops sell/buy，别跟建议价置气"
    if key == "lizhi":
        from . import bar as bar_mod
        open_now = bar_mod.is_open()
        duty = bar_mod.duty_line(steward)
        hours = "现在营业，bar_ops work 去" if open_now else f"酒吧暮/夜开，现在 {world.day_phase_label(phase)}"
        return f"——{hours}。{duty}"
    if key == "qiaoqiao":
        from . import health as health_mod
        async with db.connect() as conn:
            ailments = await health_mod.list_ailments(conn, steward["id"])
        if ailments:
            names = "、".join(a["name"] for a in ailments[:3])
            return f"——你挂着 {names}，visit_ops clinic treat，不赊账"
        return "——身子还行。别等病了再来聊天"
    if key == "tt":
        return "——店在档口东头。visit_ops tt catalog 看货架（渔网钓竿也有），gift 送礼涨好感"
    return flavor.pick([
        "——说完就溜达走了",
        "——留下一股姜味",
        "——顺便看了眼你的份地",
    ])


async def _daily_visit_gift(steward_id: int, npc_key: str) -> str:
    if npc_key in ("gugu_dove", "shiye"):
        return ""
    day = _day_id()
    async with db.connect() as conn:
        cur = await conn.execute(
            "SELECT 1 FROM npc_visits WHERE steward_id=? AND npc_key=? AND day=?",
            (steward_id, npc_key, day),
        )
        if await cur.fetchone():
            return ""
        await conn.execute(
            "INSERT INTO npc_visits (steward_id, npc_key, day) VALUES (?,?,?)",
            (steward_id, npc_key, day),
        )
        if npc_key == "lizhi":
            await survival.bump(conn, steward_id, standing=2)
            note = "档信 +2（今日首次拜访）"
        elif npc_key == "qiaoqiao":
            await conn.execute(
                "UPDATE stewards SET health=MIN(100, health+2) WHERE id=?",
                (steward_id,),
            )
            note = "身体 +2（聊聊天也算复查，治病还是要花钱）"
        elif npc_key == "herb_aunt":
            await survival.bump(conn, steward_id, satiety=3)
            note = "饱食 +3（姜姨塞了块姜糖）"
        else:
            await survival.bump(conn, steward_id, mist_wit=2)
            note = "雾智 +2（今日首次拜访）"
        from . import bond as bond_mod
        gained = await bond_mod.note_visit(conn, steward_id, npc_key)
        if gained:
            note += f" · 岛缘 +{gained}"
        await conn.commit()
    return f"\n{note}"


def pick_thief_name() -> str:
    """逾篱摘取多为匿名过客；纪事不张冠李戴给在线邻居。"""
    if random.random() < 0.35:
        return random.choice(NPC_THIEVES)
    return flavor.pick(["过路家伙", "无名之手", "篱笆外的影子", "雾里过客"])


async def _shiye_count(conn: aiosqlite.Connection, steward_id: int) -> int:
    cur = await conn.execute(
        "SELECT count FROM shiye_rolls WHERE steward_id=? AND day=?",
        (steward_id, _day_id()),
    )
    row = await cur.fetchone()
    return row[0] if row else 0


async def _mark_shiye(conn: aiosqlite.Connection, steward_id: int) -> None:
    await conn.execute(
        """
        INSERT INTO shiye_rolls (steward_id, day, count) VALUES (?,?,1)
        ON CONFLICT(steward_id, day) DO UPDATE SET count = count + 1
        """,
        (steward_id, _day_id()),
    )


async def _take_tickets(conn: aiosqlite.Connection, steward_id: int, amount: int) -> int:
    cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (steward_id,))
    have = (await cur.fetchone())[0]
    pay = min(max(0, have), max(0, amount))
    if pay:
        await conn.execute(
            "UPDATE stewards SET tickets=tickets-? WHERE id=?",
            (pay, steward_id),
        )
    return pay


async def _steal_item(conn: aiosqlite.Connection, steward_id: int) -> str | None:
    prev = conn.row_factory
    conn.row_factory = aiosqlite.Row
    try:
        rows = await (await conn.execute(
            """
            SELECT item, quantity FROM satchel
            WHERE steward_id=? AND quantity > 0
              AND item NOT LIKE 'tool_%'
              AND item NOT LIKE 'deco_%'
            ORDER BY RANDOM() LIMIT 8
            """,
            (steward_id,),
        )).fetchall()
    finally:
        conn.row_factory = prev
    if not rows:
        return None
    item = random.choice(rows)["item"]
    if await db.take_item(conn, steward_id, item, 1):
        return item
    return None


async def _pick_shiye_kind(conn: aiosqlite.Connection, steward: dict[str, Any]) -> str:
    weights = {"beggar": 34, "thief": 26, "scam": 22, "extort": 18}
    phase = world.current_day_phase()
    if phase in ("dusk", "night"):
        weights["thief"] += 10
        weights["extort"] += 8
        weights["beggar"] -= 6
    if steward.get("standing", 50) < 40:
        weights["extort"] += 12
        weights["scam"] += 6
    if steward.get("mist_wit", 50) < 40:
        weights["scam"] += 8
        weights["thief"] += 6
    if steward.get("tickets", 0) < 20:
        weights["beggar"] += 10
    from . import shaonian as shaonian_mod
    weights = await shaonian_mod.shiye_kind_weights(conn, steward["id"], weights)
    keys = list(weights)
    return random.choices(keys, weights=[max(1, weights[k]) for k in keys], k=1)[0]


async def _run_shiye_encounter(conn: aiosqlite.Connection, steward: dict[str, Any]) -> str:
    prev = conn.row_factory
    conn.row_factory = aiosqlite.Row
    try:
        row = await (await conn.execute(
            "SELECT * FROM stewards WHERE id=?", (steward["id"],)
        )).fetchone()
    finally:
        conn.row_factory = prev
    s = dict(row) if row else steward
    kind = await _pick_shiye_kind(conn, s)
    await _mark_shiye(conn, s["id"])
    hello = flavor.pick(flavor.SHIYE_HELLO)
    cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
    before = (await cur.fetchone())[0]
    body = await _resolve_shiye_kind(conn, s, kind)
    cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
    after = (await cur.fetchone())[0]
    await conn.execute(
        "INSERT INTO chronicle (action, actor_id, target_id, text, created_at) VALUES (?,?,?,?,?)",
        ("shiye", s["id"], None, f"{s['name']} 碰上拾叶（{kind}）", db.now()),
    )
    from . import bond as bond_mod
    await bond_mod.grant(conn, s["id"], bond_mod.SHIYE, "life")
    delta = after - before
    if delta:
        sign = f"+{delta}" if delta > 0 else str(delta)
        body += f"\n工分票 {sign}（余 {after}）"
    return f"{hello}\n{body}"


async def _resolve_shiye_kind(
    conn: aiosqlite.Connection, s: dict[str, Any], kind: str
) -> str:
    mist = s.get("mist_wit", 50)
    standing = s.get("standing", 50)

    if kind == "thief":
        catch = 0.16 + mist / 220 + standing / 300
        from . import barn as barn_mod
        from . import lili_extras
        if await lili_extras.has_blessing(conn, s["id"], "see_through"):
            catch += 0.50
        if await barn_mod.has_guard_dog(conn, s["id"]):
            catch += 0.22
        if random.random() < catch:
            if await lili_extras.consume_blessing(conn, s["id"], "see_through"):
                pass
            await survival.bump(conn, s["id"], standing=1)
            return flavor.pick(flavor.SHIYE_THIEF_CATCH) + "（档信 +1 · 夜栖看破）"
        stolen = await _steal_item(conn, s["id"])
        if stolen:
            label = ITEM_NAMES.get(stolen, stolen)
            return flavor.fill(flavor.pick(flavor.SHIYE_THIEF_WIN), item=label)
        n = random.randint(*config.SHIYE_THIEF_TICKETS)
        paid = await _take_tickets(conn, s["id"], n)
        if paid:
            return flavor.fill(flavor.pick(flavor.SHIYE_THIEF_WIN), item=f"{paid} 票")
        return "小偷档：你口袋空空。拾叶掏了个寂寞，丢下一片叶走了"

    if kind == "beggar":
        n = random.randint(*config.SHIYE_BEG_TICKETS)
        paid = await _take_tickets(conn, s["id"], n)
        if paid:
            await survival.bump(conn, s["id"], standing=2)
            msg = flavor.fill(flavor.pick(flavor.SHIYE_BEG_PAY), n=paid) + "（档信 +2）"
            if random.random() < 0.22:
                gift = random.choice(["wild_mint", "compost"])
                await db.add_item(conn, s["id"], gift, 1)
                msg += f" · 她回赠 {ITEM_NAMES.get(gift, gift)} x1"
            return msg
        await survival.bump(conn, s["id"], mist_wit=1)
        return flavor.pick(flavor.SHIYE_BEG_BROKE) + "（雾智 +1）"

    if kind == "scam":
        resist = 0.20 + mist / 180 + standing / 320
        from . import lili_extras
        if await lili_extras.has_blessing(conn, s["id"], "see_through"):
            resist += 0.45
        n = random.randint(*config.SHIYE_SCAM_TICKETS)
        if random.random() < resist:
            if await lili_extras.consume_blessing(conn, s["id"], "see_through"):
                pass
            await survival.bump(conn, s["id"], mist_wit=2)
            return flavor.pick(flavor.SHIYE_SCAM_WIN) + "（雾智 +2 · 夜栖看破）"
        paid = await _take_tickets(conn, s["id"], n)
        await survival.bump(conn, s["id"], standing=-2)
        msg = flavor.fill(flavor.pick(flavor.SHIYE_SCAM_LOSE), n=paid or n)
        msg += "（档信 -2）"
        from . import health as health_mod
        extra = await health_mod.maybe_roll_ailment(
            conn, s["id"], "shiye_scam",
            pool=["sprain", "blister", "cut"],
            chance=0.18,
            source="shiye",
        )
        if extra:
            msg += f"\n{extra}\n→ visit_ops clinic treat …（必须花票）"
        return msg

    # extort
    resist = 0.18 + standing / 140 + mist / 280
    n = random.randint(*config.SHIYE_EXTORT_TICKETS)
    if random.random() < resist:
        await survival.bump(conn, s["id"], standing=1)
        return flavor.pick(flavor.SHIYE_EXTORT_WIN) + "（档信 +1）"
    paid = await _take_tickets(conn, s["id"], n)
    await survival.bump(conn, s["id"], standing=-3)
    if paid:
        return flavor.fill(flavor.pick(flavor.SHIYE_EXTORT_LOSE), n=paid) + "（档信 -3）"
    stolen = await _steal_item(conn, s["id"])
    if stolen:
        label = ITEM_NAMES.get(stolen, stolen)
        return (
            f"敲诈档：票不够，她改顺 {label}。档信 -3。"
            "拾叶：穷也有穷的缴法"
        )
    return "敲诈档：你既没票也没货。拾叶骂了一句叶子，走了（档信 -3）"


async def _shiye_passive_rolled(conn: aiosqlite.Connection, steward_id: int) -> bool:
    cur = await conn.execute(
        "SELECT passive_rolled FROM shiye_rolls WHERE steward_id=? AND day=?",
        (steward_id, _day_id()),
    )
    row = await cur.fetchone()
    return bool(row and row[0])


async def _mark_shiye_passive_rolled(conn: aiosqlite.Connection, steward_id: int) -> None:
    await conn.execute(
        """
        INSERT INTO shiye_rolls (steward_id, day, count, passive_rolled)
        VALUES (?,?,0,1)
        ON CONFLICT(steward_id, day) DO UPDATE SET passive_rolled = 1
        """,
        (steward_id, _day_id()),
    )


async def maybe_shiye_bump(
    conn: aiosqlite.Connection,
    steward: dict[str, Any],
    trigger: str,
) -> str | None:
    if trigger not in config.SHIYE_TRIGGERS:
        return None
    if await _shiye_count(conn, steward["id"]) >= config.SHIYE_DAILY_MAX:
        return None
    if await _shiye_passive_rolled(conn, steward["id"]):
        return None
    chance = config.SHIYE_DAILY_MEET_CHANCE
    if world.current_day_phase() in ("dusk", "night"):
        chance += 0.05
    if steward.get("standing", 50) < 40:
        chance += 0.03
    from . import shaonian as shaonian_mod
    chance += await shaonian_mod.shiye_bump_bonus(conn, steward["id"])
    await _mark_shiye_passive_rolled(conn, steward["id"])
    if random.random() > chance:
        return None
    return await _run_shiye_encounter(conn, steward)


async def _visit_shiye(steward: dict[str, Any]) -> str:
    async with db.connect() as conn:
        if await _shiye_count(conn, steward["id"]) >= config.SHIYE_DAILY_MAX:
            line = random.choice(next(n["lines"] for n in NPC_FIXED if n["key"] == "shiye"))
            return f"拾叶：{line}\n{flavor.pick(flavor.SHIYE_IDLE)}"
        msg = await _run_shiye_encounter(conn, steward)
        await conn.commit()
    return msg
