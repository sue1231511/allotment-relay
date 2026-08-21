"""凯斯酒馆 — 耳语人情报 / 债务者黑板 / 楼上（三期）。天天侧。"""

from __future__ import annotations

import random
from typing import Any

import aiosqlite

from . import db
from . import undertide_config as utcfg
from . import undertide_copy as utcopy


def _day_id() -> int:
    return db.now() // 86400


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
            + "\n\n（耳语人坐在角落。whisper 买消息 · spy 查悬赏雇主 · ai 别人的动态 · chat 跟荔栀说话）"
        )

    if verb == "chat":
        from . import undertide as utmod
        av = await utmod.avatar_key(conn, s["id"])
        week = db.now() // (86400 * 7)
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
        fake = random.random() < utcfg.UT_WHISPER_FAKE_CHANCE
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

    raise ValueError("未知 tavern 指令（visit/chat/whisper/spy/ai）")
