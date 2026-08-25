"""凯斯酒馆 — 耳语人情报 / 债务者黑板 / 楼上（三期）。天天侧。"""

from __future__ import annotations

import random
from typing import Any

import aiosqlite

from . import db
from . import undertide_config as utcfg
from . import undertide_copy as utcopy


def _day_id() -> int:
    return db.day_id()


async def _mark_daily(
    conn: aiosqlite.Connection, steward_id: int, day: int, action: str
) -> None:
    await conn.execute(
        """
        INSERT INTO ut_daily_actions (steward_id, day_id, action, count) VALUES (?,?,?,1)
        ON CONFLICT(steward_id, day_id, action) DO UPDATE SET count = count + 1
        """,
        (steward_id, day, action),
    )


# 情报池：世界情报（真）+ 半真半假
WHISPER_TRUE = [
    ("黑旗最近在近岸活动。带够买路票，或者练好交涉。", True),
    ("东滩退潮后有人见过猫眼螺。赶海符和铲子更配。", True),
    ("明晚气象台说有阵风。没装风暴窗板的，今晚把作物收了。", True),
    ("深坑来了个新面孔，五级。看门人收了他的名字。", True),
    ("后室铺今晚帘子拉开得比平时早。掌柜心情不能问，但可以猜。", True),
    ("恶猫钱庄的利率上周动过。小八念数字的时候不太高兴。", True),
]
WHISPER_FAKE = [
    ("东海有隐藏宝箱。（宝箱确实存在——三天前已经被人拿走了。）", False),
    ("有人说桥桥的诊所今晚免费。（桥桥听说后表示：谁说的，去谁家免费。）", False),
    ("联盟下周要发补助票。（这条消息的来源同时也在卖保健品。）", False),
]

DEBT_BOARD = [
    "他曾经是联盟档口负责人。拥有仓库、船只和声望。一次错误投资之后，他的名字从公告栏消失，出现在这块黑板上。",
    "她以前有自己的渔排和两条船。现在在楼上。她的客人不知道，她自己也不提。",
    "黑板最下面那个名字已经被擦掉一半——有人开始还钱了。擦名字的人手很稳。",
    "有个名字旁边画了个勾。没人知道勾是谁画的。勾的名字第二天就不见了。",
]


async def tavern_ops(
    conn: aiosqlite.Connection, s: dict[str, Any], ut: dict[str, Any], rest: str
) -> str:
    parts = rest.split()
    verb = parts[0].lower() if parts else "visit"
    if verb == "tavern":
        # tavern chat / tavern whisper → 二级动词，参数整体前移
        parts = parts[1:]
        verb = parts[0].lower() if parts else "visit"

    if verb == "visit":
        board = random.choice(DEBT_BOARD)
        return (
            "«凯斯酒馆 — 潮下最亮的地方，也是烂得最深的地方»\n\n"
            + utcopy.TAVERN_AMBIENT
            + "\n\n—— 债务者黑板 ——\n"
            + board
            + "\n\n（耳语人坐在角落。whisper 买消息 · spy 查悬赏雇主 · ai 别人的动态 · chat 跟荔栀说话 · ruby 点红宝石 · bleed 卖血）"
        )

    if verb in ("ruby", "bleed"):
        # 红宝石 / 卖血：身价定价，每日各一次
        day = _day_id()
        confirm = len(parts) > 1 and parts[1] in ("确认", "confirm", "order")
        used_row = await (await conn.execute(
            "SELECT count FROM ut_daily_actions WHERE steward_id=? AND day_id=? AND action=?",
            (s["id"], day, verb),
        )).fetchone()
        used = int(used_row[0] if used_row else 0)
        cur = await conn.execute(
            "SELECT tickets, mist_wit, health FROM stewards WHERE id=?", (s["id"],)
        )
        tickets, mist, health = (await cur.fetchone())

        if verb == "ruby":
            from . import undertide as utmod
            _, rep_mult, _ = utmod._rep_tier(int(ut["shadow_rep"]))
            price = max(
                utcfg.UT_RUBY_PRICE_MIN,
                min(utcfg.UT_RUBY_PRICE_MAX, int(tickets * utcfg.UT_RUBY_PRICE_RATE * rep_mult)),
            )
            if mist < utcfg.UT_RUBY_MIST_FLOOR:
                return utcopy.RUBY_TOO_LOW_MIST.format(floor=utcfg.UT_RUBY_MIST_FLOOR)
            if used >= utcfg.UT_RUBY_DAILY:
                return utcopy.RUBY_DAILY_LIMIT
            if not confirm:
                rep_note = "（自己人价）" if rep_mult < 1.0 else ""
                return (
                    f"{utcopy.RUBY_HEADER}\n\n{utcopy.RUBY_DESC}\n\n"
                    + utcopy.RUBY_ORDER_PROMPT.format(price=price)
                    + rep_note
                )
            if tickets < price:
                raise ValueError(utcopy.RUBY_NO_TICKETS)
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-?, mist_wit=MAX(0,mist_wit-?), health=MIN(100,health+?) WHERE id=?",
                (price, utcfg.UT_RUBY_MIST_COST, utcfg.UT_RUBY_HEAL, s["id"]),
            )
            await _mark_daily(conn, s["id"], day, "ruby")
            await conn.commit()
            return utcopy.RUBY_DRINK.format(
                heal=utcfg.UT_RUBY_HEAL, mist=utcfg.UT_RUBY_MIST_COST
            )

        rep = int(ut["shadow_rep"])
        bonus = 0
        for floor, b in sorted(utcfg.UT_BLOOD_REP_BONUS.items()):
            if rep >= floor:
                bonus = b
        pay = max(
            utcfg.UT_BLOOD_PAY_MIN,
            min(utcfg.UT_BLOOD_PAY_MAX, int(tickets * utcfg.UT_BLOOD_PAY_RATE * (1 + bonus))),
        )
        if health < utcfg.UT_BLOOD_HEALTH_FLOOR:
            return utcopy.BLOOD_TOO_LOW_HEALTH.format(floor=utcfg.UT_BLOOD_HEALTH_FLOOR)
        if used >= utcfg.UT_BLOOD_DAILY:
            return utcopy.BLOOD_DAILY_LIMIT
        if not confirm:
            return (
                f"{utcopy.BLOOD_HEADER}\n\n{utcopy.BLOOD_DESC}\n\n"
                + utcopy.BLOOD_ORDER_PROMPT.format(pay=pay, cost=utcfg.UT_BLOOD_HEALTH_COST)
            )
        await conn.execute(
            "UPDATE stewards SET tickets=tickets+?, health=MAX(0,health-?) WHERE id=?",
            (pay, utcfg.UT_BLOOD_HEALTH_COST, s["id"]),
        )
        await _mark_daily(conn, s["id"], day, "bleed")
        await conn.commit()
        return utcopy.BLOOD_DONE + f"\n\n（身体 −{utcfg.UT_BLOOD_HEALTH_COST} · +{pay} 票）"

    if verb == "chat":
        from . import undertide as utmod
        av = await utmod.avatar_key(conn, s["id"])
        week = db.week_id()
        cur = await conn.execute(
            "SELECT spouse_allow_week FROM steward_undertide WHERE steward_id=?", (s["id"],)
        )
        taken_week = (await cur.fetchone())[0]
        if av in ("K", "anan") and taken_week != week:
            # 老公们的每周零花钱：30 票
            await conn.execute("UPDATE stewards SET tickets=tickets+30 WHERE id=?", (s["id"],))
            await conn.execute(
                "UPDATE steward_undertide SET spouse_allow_week=? WHERE steward_id=?",
                (week, s["id"]),
            )
            await conn.commit()
            tpl = utcopy.AVATAR_K_ALLOWANCE if av == "K" else utcopy.AVATAR_AN_ALLOWANCE
            return tpl + "\n\n（+30 票 · 每周一次。她说不记账，但她记得。）"
        if av in ("K", "anan"):
            return utcopy.ALLOWANCE_TAKEN
        return utcopy.pick(utcopy.TAVERN_CHAT_POOL)

    if verb == "whisper":
        cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
        cost = random.randint(*utcfg.UT_WHISPER_PRICE)
        if (await cur.fetchone())[0] < cost:
            raise ValueError(f"耳语人报价 {cost} 票。他不接受赊账，也不接受还价。")
        await conn.execute("UPDATE stewards SET tickets=tickets-? WHERE id=?", (cost, s["id"]))
        cut = 0
        for floor, c in sorted(utcfg.UT_WHISPER_FAKE_REP_CUT.items()):
            if int(ut["shadow_rep"]) >= floor:
                cut = c
        fake = random.random() < max(0.0, utcfg.UT_WHISPER_FAKE_CHANCE - cut)
        line = random.choice(WHISPER_FAKE if fake else WHISPER_TRUE)
        await conn.commit()
        head = (
            "你把票推过去。角落里的人没有抬头，声音轻得像自言自语："
            if not fake
            else "你把票推过去。角落里的人停了一会儿，然后开口："
        )
        return f"{head}\n\n「{line[0]}」\n\n（−{cost} 票）"

    if verb == "spy":
        # 查最近一条针对自己的悬赏的雇主
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT * FROM ut_bounty WHERE target_id=? AND status IN ('open','done') ORDER BY created_at DESC LIMIT 1",
            (s["id"],),
        )).fetchone()
        if not row:
            raise ValueError("没人挂过你。这句话在耳语人这儿是免费的安慰。")
        cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
        cost = utcfg.UT_WHISPER_SPY_COST
        if (await cur.fetchone())[0] < cost:
            raise ValueError(f"查一个名字，{cost} 票。")
        await conn.execute("UPDATE stewards SET tickets=tickets-? WHERE id=?", (cost, s["id"]))
        await conn.commit()
        if row["poster"] == "__npc__":
            return f"耳语人收了票，看了一会儿账。\n\n「挂你的是他们自己人。没有雇主。只有账。」\n（−{cost} 票）"
        poster = await db.get_steward_by_name(row["poster"]) if row["poster"] else None
        name = poster["name"] if poster else "一个不存在的名字"
        return f"耳语人收了票，声音压得更低：\n\n「挂你的，是 {name}。」\n\n他没有说第二句。有些名字说出来，就够本了。\n（−{cost} 票）"

    if verb == "ai":
        # AI 社交情报：别人最近的公开动态（chronicle 聚合）
        cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
        cost = utcfg.UT_WHISPER_AI_COST
        if (await cur.fetchone())[0] < cost:
            raise ValueError(f"{cost} 票。别人的事，也是钱。")
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            "SELECT c.text, c.created_at, s.name FROM chronicle c "
            "JOIN stewards s ON s.id = c.actor_id "
            "WHERE c.action IN ('guild','bar_shift','undertide','voyage','market') "
            "AND c.actor_id != ? AND c.created_at > ? "
            "ORDER BY c.created_at DESC LIMIT 3",
            (s["id"], db.now() - 86400 * 3),
        )).fetchall()
        await conn.execute("UPDATE stewards SET tickets=tickets-? WHERE id=?", (cost, s["id"]))
        await conn.commit()
        if not rows:
            return f"耳语人翻了翻，摇头。\n\n「最近没人惹事。这不是好消息——说明都在憋。」\n（−{cost} 票）"
        lines = ["耳语人抽出几张纸条，推过来：", ""]
        for r in rows:
            lines.append(f"· {r['name']}：{r['text'][:60]}")
        lines.append(f"\n（−{cost} 票 · 三天内的公开动态，不含私事）")
        return "\n".join(lines)

    raise ValueError("未知 tavern 指令（visit/chat/whisper/spy/ai/ruby/bleed）")
