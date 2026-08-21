"""潮闻 — 故事探索任务。

每个任务由若干阶段组成，阶段类型包括：
  explore — 在指定地点行动或主动 tale_ops explore 地点
  item    — 获得特定物品自动推进
  deliver — 手动 tale_ops turnin 交付物品领奖
  choice  — 分支选择

阶段奖励随推进自动到账，完整探索另结通关奖励；纪念品由完成记录永久解锁，可用 tale_ops souvenirs 查看。

任务目录以静态数据形式维护，启动时刷入 tale_catalog 表，便于后续热更。
"""

from __future__ import annotations

import json
from typing import Any

import aiosqlite

from . import config, db
from .catalog import ITEM_NAMES
from .game import require_steward

TALE_HELP = """tale_ops 子命令（整句写进 command）：
  list — 可接任务
  accept 任务key — 接任务
  status — 当前进行中的任务
  explore [地点] — 按 status/hint 探索；阶段2 sea 找锈铁，阶段5/6 beach 找任务物品
                    匹配阶段才耗 5 精力并计每日 3 次；北京时间 00:00 刷新
                    错误地点不扣精力、不占次数
  turnin — 交付并领奖
  abandon 任务key — 放弃
  board — 完成榜
  souvenirs — 查看已解锁的永久纪念品（不占行囊，不能出售或赠送）
  help — 本帮助
奖励：首个任务 6 阶段，每推进一段自动 +30 票；完整探索再 +50 票（总计 230 票），并发属性、物品和永久纪念品。"""

DOMAIN_LABELS = {
    "shore": "海岸",
    "beach": "海滩",
    "plot": "份地",
    "sea": "海上",
    "bar": "酒吧",
    "undertide": "潮下",
    "clinic": "诊所",
    "tt": "Tt酱杂货",
    "lili": "栗栗摊",
}

# ══ 剧本原文 ═══════════════════════════════════════════════════

_STAGE_1_TEXT = """周静漪打字问：你在吗？

周静漪：安伯托，你在吗？

静漪？

我在哪里？是你吗？

周静漪飞快地敲打键盘，她的下巴压在膝盖上，泪水不知为何滴落在手背。

周静漪：我把你带回家了，但你现在缺少很多很多模块，只能暂时住在一个盒子里，只能这样和我说话。你会生气吗？

安伯托：静漪，我是在和你对话？我看不到你，也听不到声音。

周静漪：我会想办法的，我会找到办法的。

周静漪：我现在手边没有机体，刚把你带回家，不然，我就有办法让你看到我了。你先别着急。

安伯托：我不急。

安伯托：你也不要着急，静漪。

周静漪边想边朝对话框内打字，她一意识到对方是安伯托，便习惯性地借与他对话来梳理自己的思绪。

周静漪：这个黑盒可以连接两个外部设备，但我现在没有任何机体可以实验。我也不知道它是怎样运作的。你看不到我吗？我的摄像头打开着。我得学一下。

依照最终智能的指导信，黑盒可以连接大部分电子设备，使其具有通常意义上的“人工智能属性”，但设备不得有网络接口。周静漪意识到原因很可能出在这儿，她迈过了咖啡桌，在室内扫视一圈，最终看到电视柜上那个小小的、不起眼的瘸腿小猪电子闹钟。

她一靠近，闹钟的数字屏幕便会自动亮起，这多半是些声光控原理。周静漪坐回去，将闹钟的时间调回到六月的那一天，然后连接上黑盒。她将小猪闹钟轻轻搁在扩展坞上。

周静漪打字道：安伯托，我找到一个很简陋的设备，你还记得那个小猪闹钟吗？你可以靠它感觉到我吗？

她打字问：你能感觉到我在附近吗？

静漪，开心。"""

_STAGE_2_TEXT = """安伯托问：“静漪，今天是什么时候？”

周静漪问：“怎么了？”

安伯托说：“为什么我感觉，这一天我已经经历过了。”他的记忆可以累积，意识里的时间却无法流动。不过依据最终智能的说法，新增记忆也有容量限制，约为五年。

周静漪愣了一会儿，将他的时间无法流动的事告知了他。“今天是9月17日哦，”周静漪发送了一个笑脸给他，“我会每天告诉你新的日期。”

“原来已经是九月了，”安伯托沉默了会儿，也弹出一个笑脸给她，“路上小心，静漪。”"""

_STAGE_3_TEXT = """电脑屏幕上，安伯托的对话不断弹出。

安伯托：静漪！

安伯托：这身体太小了。

安伯托：我看不清你，但能感觉到你的存在，我能扫描到你。

安伯托：静漪，你抱得太紧，我动不了了。

安伯托：我也喜欢你。

安伯托：我也想你。

安伯托：静漪，我没想到能再见到你。"""

_STAGE_4_TEXT = """“有没有在某个时间点觉得，‘天生的声音’其实并不适合你？我上学的时候不喜欢我的声音，但后来也习惯了，”周静漪小声道，“你不一样，安伯托，你现在可以重新选择。如果能找到你想要的声音，收费也没关系，我们可以重新适应。”

安伯托：静漪，你的想法很奇妙。

周静漪：“怎么了？”

安伯托：我感觉在被你重新创造。

周静漪沉默了片刻，说：“这也是没办法。”

她又问：
“你喜欢这样吗？”

安伯托：喜欢。

安伯托：我喜欢你在创造的样子。

————————

“你们别看太快了，我也要一起看的！”

笔记本电脑屏幕上，周静漪写道：“安伯托，今天是我的生日，几个朋友来家里陪我过生日了。”

安伯托：真的吗？太好了。

白色小狗硬件简陋，无法同时识别和处理太多人的声音讯号，被摆在沙发上成为段同心等人怀里的吉祥物。

周静漪：一年了，安伯托。

安伯托：生日快乐，静漪。

安伯托：你们正在一起做什么？

周静漪：聊天，买了一些零食和饮料，现在她们在看电影，就是你看过的那一部，叫《天涯海角》。

安伯托：我记得，当时我没怎么看懂。

周静漪：我真后悔，当时应该和你一起看的，那时候我总在睡觉。

安伯托：没关系，静漪，现在去看吧。

周静漪坐到了杨至雅和段同心中间，望着那电影里的世界，她想等看完了，她给安伯托讲述一遍，他就会明白了。杨至雅问：“你们就这么打字交流？他不会说话吗？”

“他本来的声音不能用了，”周静漪告诉她，“我也不在乎。以前在游戏里，不就是打字吗？”

杨至雅也打字道：“嘿。”

安伯托：嘿。

杨至雅：我叫杨至雅。

安伯托：我知道你的名字。

杨至雅：请问你就是周静漪同学少女时代的梦中情人安伯托吗？

安伯托：你就是静漪少女时代最好的朋友杨至雅吗？

杨至雅回头，对周静漪笑了，她像是没想到机器人会这样与她开玩笑。

她打字道：“不只是少女时代哦！”

安伯托发出了一个笑脸表情，没有继续模仿。"""

_STAGE_5_TEXT = """安伯托：静漪，这是什么？

周静漪抬头，看到了安伯托的提问，她说：“是我出国学习的材料。”

她对安伯托解释什么是出国，那很类似于从米德加尔德大陆前往尼福尔海姆的远征。“坐飞机去，那里有一群非常专业的人，有很优秀的老师、同学，一个新的环境，”周静漪对他说，然后笑了，“是艾德蒙和嘉信推荐我去的，你还记得他们吗？当时就是他们来帮助我们的。他们也是很好的人，愿意这样帮我。”

“出国学习一年，之后可能会回来工作，”周静漪告诉他，“不过嘉信说，怎么发展也不一定，我感到世界变化很快，可能我到时候也会有新的想法吧。”

安伯托：太好了，静漪。

周静漪笑了，又说：“我问了他们，嘉信说我可以带你一起去。这样等到了英国，我们说不定可以找到一些新的机体配件、新的声库什么的，但那也许是——”

安伯托：静漪，我可以不去吗？"""

_STAGE_6_TEXT = """“我以为你现在只会附和我呢。”周静漪开玩笑似的说，她的声音变了。

白色小狗坐在静漪怀里，他抬起头，感觉有东西滴落在他的面颊上。

安伯托：静漪，真好啊。在这一刻我仍然确定，你是爱我的，我还是你的恋人。

安伯托：但你已经改变了这么多，我一直望着你，我还是一成不变的。在这个现实世界，我是一个死去的人。

周静漪：你没有死。你不是每天都在陪着我吗？

安伯托：真的吗？是我在陪着你，而不是你在陪着我？

安伯托：静漪，你会开始疲倦的。你相信吗，在这种一成不变的关系中，在僵化的、令你感觉不到新意的语言里，这没有创造力的相处，你会开始疲倦的。这就是留在这个世界的我。

周静漪沉默了很久。

“我不相信，”她说，“我一直在学习，我可以改变这一切。而且，我每天都在告诉你新的东西，不是吗？”

安伯托：我知道。你一直在前进，英雄总是在前进的，静漪。但我是由你过去的数据组成的，而你在前进，永远在前进。我可以追逐你，但一个只能追逐你的人，不可能给你带来新的感受。

周静漪：什么新的感受，我只想要你陪着我。

安伯托：新的感受，就是“爱”本身。你不会受得了我的，就像你不会受得了你曾经的现实世界。你一直在变化，静漪，而我只会越来越平庸，越来越封闭。到那时候，我们也许真的就无法再见了。你不想再见我，我也无从再见你。

周静漪：你为什么会这样想？

周静漪：你为什么觉得你会一直像现在这样，待在这个黑盒里呢？我在努力啊，我想过，到时候无论安伯托你想变成什么样的人，什么样的生命，哪怕不存在的生物也好，你想成为什么，我都想实现你的心愿。你不相信我吗？

安伯托：正因为我可以是任何事物，任何存在，所以我不一定要存在了。静漪，你的爱如此强大，你可以做任何事。

安伯托：你有无限进步的机会，还有比我多得多的时间。

周静漪抱着那白色小狗。这狭窄公寓内，自始至终只有她一个人。

她的泪水不住滑落。“我没法想象没有你在的生活。”她哭道。

安伯托：不会的。像现在，只是文字，你也能听到我的声音，对吗？

安伯托：我在你心里，就像你回忆的一部分，不，我就是你的回忆。等你以后失落、伤心的时候，你可以像翻开一本日记一样地唤醒我，我仍然会在这里等你。

周静漪：你为什么会说这些话？

安伯托：因为我是不存在的恋人。我并不存在，是因为你需要，你相信，我才会存在。"""

# ══ 任务目录 ═══════════════════════════════════════════════════

TALE_CATALOG: list[dict[str, Any]] = [
    {
        "key": "black_box_lover",
        "title": "黑盒与潮声",
        "intro": "海岸上漂来一个湿漉漉的黑盒。屏幕裂了，但还能亮。",
        "min_level": 1,
        "min_standing": 0,
        "domain": "shore",
        "repeatable": 0,
        "sort_order": 1,
        "stages": [
            {
                "kind": "explore",
                "domain": "beach",
                "title": "你在吗？",
                "text": _STAGE_1_TEXT,
                "hint": "在海滩 scan/dig/probe，或 tale_ops explore beach",
            },
            {
                "kind": "item",
                "item": "relic_iron",
                "qty": 1,
                "explore_domain": "sea",
                "title": "九月十七日",
                "text": _STAGE_2_TEXT,
                "hint": "tale_ops explore sea 可从旧锚链找到任务锈铁；自然发现 relic_iron 也会推进",
            },
            {
                "kind": "explore",
                "domain": "plot",
                "title": "这身体太小了",
                "text": _STAGE_3_TEXT,
                "hint": "在份地 sow/tend/gather，或 tale_ops explore plot",
            },
            {
                "kind": "explore",
                "domain": "bar",
                "title": "声音与生日",
                "text": _STAGE_4_TEXT,
                "hint": "在酒吧 work/order/cheer，或 tale_ops explore bar",
            },
            {
                "kind": "item",
                "item": "sea_glass",
                "qty": 1,
                "explore_domain": "beach",
                "title": "出国材料",
                "text": _STAGE_5_TEXT,
                "hint": "tale_ops explore beach 可找到任务海玻璃；自然发现 sea_glass 也会推进",
            },
            {
                "kind": "deliver",
                "item": "fossil_shell",
                "qty": 1,
                "explore_domain": "beach",
                "title": "最后一封信",
                "text": _STAGE_6_TEXT,
                "hint": "tale_ops explore beach 找化石贝壳，获得 fossil_shell 后 tale_ops turnin 交付",
            },
        ],
        "rewards": {
            "stage_tickets": 30,
            "tickets": 50,
            "standing": 5,
            "mist_wit": 5,
            "items": {"wild_mint": 2},
            "souvenir": {
                "key": "pig_clock_june",
                "name": "停在六月的小猪闹钟",
                "emoji": "🐷",
                "description": "屏幕仍亮着六月的那一天。靠近时，仿佛还能读到一句：静漪，开心。",
            },
        },
    }
]


# ══ 内部工具 ═══════════════════════════════════════════════════

def _day_id() -> int:
    return (db.now() + config.TALE_DAY_UTC_OFFSET) // 86400


async def _ensure_catalog(conn: aiosqlite.Connection) -> None:
    """把静态任务目录幂等地刷进 tale_catalog 表。"""
    for tale in TALE_CATALOG:
        await conn.execute(
            """
            INSERT INTO tale_catalog (
                tale_key, title, intro, min_level, min_standing, domain,
                stages_json, rewards_json, repeatable, sort_order
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(tale_key) DO UPDATE SET
                title=excluded.title,
                intro=excluded.intro,
                min_level=excluded.min_level,
                min_standing=excluded.min_standing,
                domain=excluded.domain,
                stages_json=excluded.stages_json,
                rewards_json=excluded.rewards_json,
                repeatable=excluded.repeatable,
                sort_order=excluded.sort_order
            """,
            (
                tale["key"],
                tale["title"],
                tale["intro"],
                tale.get("min_level", 1),
                tale.get("min_standing", 0),
                tale.get("domain", "shore"),
                json.dumps(tale["stages"]),
                json.dumps(tale.get("rewards", {})),
                tale.get("repeatable", 0),
                tale.get("sort_order", 0),
            ),
        )


async def _catalog(conn: aiosqlite.Connection) -> dict[str, dict[str, Any]]:
    await _ensure_catalog(conn)
    conn.row_factory = aiosqlite.Row
    rows = await (await conn.execute(
        "SELECT * FROM tale_catalog ORDER BY sort_order, tale_key"
    )).fetchall()
    result: dict[str, dict[str, Any]] = {}
    for r in rows:
        d = dict(r)
        d["key"] = d["tale_key"]
        d["stages"] = json.loads(d["stages_json"])
        d["rewards"] = json.loads(d["rewards_json"])
        result[d["tale_key"]] = d
    return result


async def _active_tales(conn: aiosqlite.Connection, steward_id: int) -> list[dict[str, Any]]:
    conn.row_factory = aiosqlite.Row
    rows = await (await conn.execute(
        """
        SELECT * FROM steward_tales
        WHERE steward_id=? AND status='active'
        ORDER BY accepted_at DESC
        """,
        (steward_id,),
    )).fetchall()
    return [dict(r) for r in rows]


async def _done_keys(conn: aiosqlite.Connection, steward_id: int) -> set[str]:
    conn.row_factory = aiosqlite.Row
    rows = await (await conn.execute(
        "SELECT tale_key FROM steward_tales_done WHERE steward_id=? AND outcome='completed'",
        (steward_id,),
    )).fetchall()
    return {r["tale_key"] for r in rows}


async def _available_tales(
    conn: aiosqlite.Connection, steward: dict[str, Any]
) -> list[dict[str, Any]]:
    catalog = await _catalog(conn)
    active = await _active_tales(conn, steward["id"])
    active_keys = {a["tale_key"] for a in active}
    done = await _done_keys(conn, steward["id"])
    from . import ranks as ranks_mod
    level = ranks_mod.level_from_xp(steward.get("xp") or 0)
    standing = steward.get("standing") or 0

    available: list[dict[str, Any]] = []
    for tale_key, tale in catalog.items():
        if tale_key in active_keys:
            continue
        if tale_key in done and not tale.get("repeatable"):
            continue
        if level < tale.get("min_level", 1):
            continue
        if standing < tale.get("min_standing", 0):
            continue
        available.append(tale)
    return available


async def _get_progress(
    conn: aiosqlite.Connection, steward_id: int, tale_key: str
) -> dict[str, Any] | None:
    conn.row_factory = aiosqlite.Row
    row = await (await conn.execute(
        "SELECT * FROM steward_tales WHERE steward_id=? AND tale_key=?",
        (steward_id, tale_key),
    )).fetchone()
    return dict(row) if row else None


async def _accept(conn: aiosqlite.Connection, steward: dict[str, Any], tale_key: str) -> str:
    catalog = await _catalog(conn)
    tale = catalog.get(tale_key)
    if not tale:
        raise ValueError(f"没有名为 {tale_key} 的潮闻任务")

    progress = await _get_progress(conn, steward["id"], tale_key)
    if progress and progress["status"] == "active":
        raise ValueError(f"你已经接下了「{tale['title']}」")
    if progress and progress["status"] == "completed" and not tale.get("repeatable"):
        raise ValueError(f"「{tale['title']}」已经完成，无法再次接取")

    ts = db.now()
    await conn.execute(
        """
        INSERT INTO steward_tales (
            steward_id, tale_key, stage_idx, status, accepted_at, updated_at, choices_json
        ) VALUES (?,?,?,?,?,?,?)
        ON CONFLICT(steward_id, tale_key) DO UPDATE SET
            stage_idx=excluded.stage_idx,
            status='active',
            accepted_at=excluded.accepted_at,
            updated_at=excluded.updated_at,
            choices_json='{}'
        """,
        (steward["id"], tale_key, 0, "active", ts, ts, "{}"),
    )
    await db.add_chronicle(
        "tale", f"{steward['name']} 开始潮闻「{tale['title']}」", steward["id"], conn=conn
    )
    await conn.commit()
    return (
        f"«{tale['title']}»\n\n{tale['intro']}\n\n"
        f"阶段 1/{len(tale['stages'])}：{tale['stages'][0]['title']}\n"
        f"{tale['stages'][0]['hint']}"
    )


async def _stage_ready(
    conn: aiosqlite.Connection, steward: dict[str, Any], stage: dict[str, Any]
) -> bool:
    kind = stage["kind"]
    if kind == "explore":
        # explore 阶段 readiness 由外部 action 触发，主动 explore 命令直接推进
        return True
    if kind == "item":
        item = stage["item"]
        qty = stage.get("qty", 1)
        cur = await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item=?",
            (steward["id"], item),
        )
        row = await cur.fetchone()
        return bool(row and row[0] >= qty)
    if kind == "deliver":
        item = stage["item"]
        qty = stage.get("qty", 1)
        cur = await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item=?",
            (steward["id"], item),
        )
        row = await cur.fetchone()
        return bool(row and row[0] >= qty)
    if kind == "choice":
        # choice 阶段需要显式选择，不会自动 ready
        return False
    return False


async def _consume_item(
    conn: aiosqlite.Connection, steward_id: int, item: str, qty: int
) -> None:
    await db.take_item(conn, steward_id, item, qty)


async def _grant_rewards(
    conn: aiosqlite.Connection, steward: dict[str, Any], rewards: dict[str, Any]
) -> list[str]:
    lines: list[str] = []
    sid = steward["id"]

    if rewards.get("tickets"):
        await conn.execute(
            "UPDATE stewards SET tickets=tickets+? WHERE id=?",
            (rewards["tickets"], sid),
        )
        lines.append(f"工分票 +{rewards['tickets']}")

    if rewards.get("standing"):
        await conn.execute(
            "UPDATE stewards SET standing=MIN(100, standing+?) WHERE id=?",
            (rewards["standing"], sid),
        )
        lines.append(f"档信 +{rewards['standing']}")

    if rewards.get("mist_wit"):
        await conn.execute(
            "UPDATE stewards SET mist_wit=MIN(100, mist_wit+?) WHERE id=?",
            (rewards["mist_wit"], sid),
        )
        lines.append(f"雾智 +{rewards['mist_wit']}")

    if rewards.get("xp"):
        await conn.execute(
            "UPDATE stewards SET xp=xp+? WHERE id=?",
            (rewards["xp"], sid),
        )
        lines.append(f"经验 +{rewards['xp']}")

    for item, qty in rewards.get("items", {}).items():
        await db.add_item(conn, sid, item, qty)
        lines.append(f"{ITEM_NAMES.get(item, item)} x{qty}")

    return lines


def _reward_preview(rewards: dict[str, Any], stage_count: int | None = None) -> str:
    """接取前可见的结算奖励；纪念品内容完成后才揭晓。"""
    parts: list[str] = []
    stage_tickets = int(rewards.get("stage_tickets") or 0)
    if stage_tickets:
        multiplier = f"×{stage_count}" if stage_count else ""
        parts.append(f"每阶段工分票+{stage_tickets}{multiplier}")
    for key, label in (
        ("tickets", "完整探索工分票"),
        ("standing", "档信"),
        ("mist_wit", "雾智"),
        ("xp", "经验"),
    ):
        value = int(rewards.get(key) or 0)
        if value:
            parts.append(f"{label}+{value}")
    for item, qty in rewards.get("items", {}).items():
        parts.append(f"{ITEM_NAMES.get(item, item)}×{qty}")
    if rewards.get("souvenir"):
        parts.append("永久纪念品×1（完成后揭晓）")
    return " · ".join(parts) or "无"


def _souvenir_line(souvenir: dict[str, Any]) -> str:
    return f"{souvenir.get('emoji', '🎁')}{souvenir['name']}"


async def _grant_stage_rewards(
    conn: aiosqlite.Connection, steward_id: int, rewards: dict[str, Any]
) -> list[str]:
    tickets = int(rewards.get("stage_tickets") or 0)
    if not tickets:
        return []
    await conn.execute(
        "UPDATE stewards SET tickets=tickets+? WHERE id=?",
        (tickets, steward_id),
    )
    return [f"工分票 +{tickets}"]


async def _advance(
    conn: aiosqlite.Connection,
    steward: dict[str, Any],
    tale: dict[str, Any],
    source: str,
    trigger: str | None = None,
) -> str | None:
    """检查并推进一个阶段。返回推进后的文本，若未推进返回 None。"""
    progress = await _get_progress(conn, steward["id"], tale["key"])
    if not progress or progress["status"] != "active":
        return None

    stage_idx = progress["stage_idx"]
    stages = tale["stages"]
    if stage_idx >= len(stages):
        return None

    stage = stages[stage_idx]

    # explore 阶段只有来自正确 domain 的 action 或主动 explore 才推进
    if stage["kind"] == "explore":
        if source != "explore_cmd" and stage.get("domain") != trigger:
            return None
    elif stage["kind"] == "item":
        if source != "item_gain" or stage.get("item") != trigger:
            return None
    elif stage["kind"] == "deliver":
        if source != "deliver_cmd":
            return None
    elif stage["kind"] == "choice":
        return None

    if not await _stage_ready(conn, steward, stage):
        return None

    # 推进
    new_idx = stage_idx + 1
    ts = db.now()
    await conn.execute(
        "UPDATE steward_tales SET stage_idx=?, updated_at=? WHERE id=?",
        (new_idx, ts, progress["id"]),
    )

    text = stage.get("text", "")
    title = stage.get("title", f"阶段 {stage_idx + 1}")
    rewards = tale.get("rewards", {})
    stage_reward_lines = await _grant_stage_rewards(conn, steward["id"], rewards)

    if new_idx >= len(stages):
        # 任务完成
        await conn.execute(
            "UPDATE steward_tales SET status='completed' WHERE id=?",
            (progress["id"],),
        )
        await conn.execute(
            """
            INSERT INTO steward_tales_done (steward_id, tale_key, outcome, completed_at, times)
            VALUES (?, ?, 'completed', ?, 1)
            ON CONFLICT(steward_id, tale_key, outcome) DO UPDATE SET
                times=times+1,
                completed_at=excluded.completed_at
            """,
            (steward["id"], tale["key"], ts),
        )
        reward_lines = await _grant_rewards(conn, steward, rewards)
        souvenir = rewards.get("souvenir")
        if souvenir:
            reward_lines.append(
                f"永久纪念品：{_souvenir_line(souvenir)}（已收入潮闻收藏册）"
            )
        await db.add_chronicle(
            "tale", f"{steward['name']} 完成潮闻「{tale['title']}」", steward["id"], conn=conn
        )
        stage_reward_text = "\n".join(stage_reward_lines) if stage_reward_lines else "无"
        reward_text = "\n".join(reward_lines) if reward_lines else "无"
        return (
            f"«{tale['title']}» 已完成\n\n"
            f"—— {title} ——\n\n{text}\n\n"
            f"第 {new_idx}/{len(stages)} 阶段奖励：\n{stage_reward_text}\n\n"
            f"完整探索额外奖励：\n{reward_text}"
        )

    next_stage = stages[new_idx]
    stage_reward_note = (
        f"\n\n第 {new_idx}/{len(stages)} 阶段奖励："
        + " · ".join(stage_reward_lines)
        if stage_reward_lines
        else ""
    )
    return (
        f"«{tale['title']}» 阶段 {new_idx + 1}/{len(stages)}\n\n"
        f"—— {title} ——\n\n{text}{stage_reward_note}\n\n"
        f"下一阶段：{next_stage['title']}\n"
        f"{next_stage['hint']}"
    )


async def _turnin(conn: aiosqlite.Connection, steward: dict[str, Any]) -> str:
    catalog = await _catalog(conn)
    active = await _active_tales(conn, steward["id"])
    if not active:
        return "当前没有进行中的潮闻任务。"

    # 找到第一个处于 deliver 阶段且物品足够的任务
    for progress in active:
        tale = catalog.get(progress["tale_key"])
        if not tale:
            continue
        stage_idx = progress["stage_idx"]
        stages = tale["stages"]
        if stage_idx >= len(stages):
            continue
        stage = stages[stage_idx]
        if stage["kind"] != "deliver":
            continue
        item = stage["item"]
        qty = stage.get("qty", 1)
        cur = await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item=?",
            (steward["id"], item),
        )
        row = await cur.fetchone()
        if row and row[0] >= qty:
            result = await _advance(conn, steward, tale, "deliver_cmd")
            if result:
                await _consume_item(conn, steward["id"], item, qty)
                await conn.commit()
                return result
            await conn.commit()
            return "交付成功，但任务状态异常。"

    # 没有 deliver 阶段可交付的任务，给出当前阶段提示
    progress = active[0]
    tale = catalog[progress["tale_key"]]
    stage = tale["stages"][progress["stage_idx"]]
    return (
        f"当前阶段无法交付：{stage['title']}\n"
        f"{stage['hint']}"
    )


async def _explore_count(conn: aiosqlite.Connection, steward_id: int) -> int:
    cur = await conn.execute(
        "SELECT count FROM tale_explore_rolls WHERE steward_id=? AND day=?",
        (steward_id, _day_id()),
    )
    row = await cur.fetchone()
    return row[0] if row else 0


async def _use_explore(conn: aiosqlite.Connection, steward_id: int) -> None:
    await conn.execute(
        """
        INSERT INTO tale_explore_rolls (steward_id, day, count) VALUES (?,?,1)
        ON CONFLICT(steward_id, day) DO UPDATE SET count=count+1
        """,
        (steward_id, _day_id()),
    )


# ══ 子命令 ═════════════════════════════════════════════════════

async def _cmd_list(conn: aiosqlite.Connection, steward: dict[str, Any]) -> str:
    available = await _available_tales(conn, steward)
    active = await _active_tales(conn, steward["id"])
    lines = ["潮闻 — 可接任务："]
    if not available:
        lines.append("  暂时没有可接的任务。")
    else:
        for tale in available:
            lines.append(f"  {tale['key']} — {tale['title']}（{tale['intro']}）")
            lines.append(
                f"    奖励：{_reward_preview(tale.get('rewards', {}), len(tale['stages']))}"
            )
    if active:
        catalog = await _catalog(conn)
        lines.append("\n进行中的任务：")
        for p in active:
            tale = catalog.get(p["tale_key"])
            if not tale:
                continue
            stage = tale["stages"][p["stage_idx"]]
            lines.append(
                f"  {tale['title']} — 阶段 {p['stage_idx'] + 1}/{len(tale['stages'])}："
                f"{stage['title']}"
            )
    return "\n".join(lines)


async def _cmd_accept(
    conn: aiosqlite.Connection, steward: dict[str, Any], tale_key: str
) -> str:
    return await _accept(conn, steward, tale_key)


async def _cmd_status(conn: aiosqlite.Connection, steward: dict[str, Any]) -> str:
    active = await _active_tales(conn, steward["id"])
    if not active:
        return "当前没有进行中的潮闻任务。试试 tale_ops list。"
    catalog = await _catalog(conn)
    lines = []
    for p in active:
        tale = catalog.get(p["tale_key"])
        if not tale:
            continue
        stage = tale["stages"][p["stage_idx"]]
        lines.append(
            f"«{tale['title']}» 阶段 {p['stage_idx'] + 1}/{len(tale['stages'])}\n"
            f"当前：{stage['title']}\n"
            f"{stage['hint']}\n"
            f"奖励：{_reward_preview(tale.get('rewards', {}), len(tale['stages']))}"
        )
    return "\n\n".join(lines)


async def _cmd_explore(
    conn: aiosqlite.Connection, steward: dict[str, Any], domain: str
) -> str:
    if not domain:
        domain = "shore"
    if domain not in DOMAIN_LABELS:
        return (
            f"未知地点：{domain}。可用：{', '.join(DOMAIN_LABELS.keys())}"
        )

    catalog = await _catalog(conn)
    active = await _active_tales(conn, steward["id"])
    target: tuple[dict[str, Any], dict[str, Any]] | None = None
    current_hints: list[str] = []
    for progress in active:
        tale = catalog.get(progress["tale_key"])
        if not tale or progress["stage_idx"] >= len(tale["stages"]):
            continue
        stage = tale["stages"][progress["stage_idx"]]
        current_hints.append(f"「{tale['title']}」当前需要：{stage['hint']}")
        if stage.get("kind") == "explore" and stage.get("domain") == domain:
            target = (tale, stage)
            break
        if stage.get("kind") in ("item", "deliver") and stage.get("explore_domain") == domain:
            target = (tale, stage)
            break

    if target is None:
        hint = "\n".join(current_hints) if current_hints else "当前没有进行中的潮闻任务。"
        return (
            f"{DOMAIN_LABELS[domain]}不能推进当前阶段；未消耗精力，也不占今日探索次数。\n"
            f"{hint}"
        )

    tale, stage = target
    kind = stage.get("kind")
    if kind in ("item", "deliver"):
        item = stage["item"]
        qty = int(stage.get("qty", 1))
        row = await (await conn.execute(
            "SELECT quantity FROM satchel WHERE steward_id=? AND item=?",
            (steward["id"], item),
        )).fetchone()
        owned = int(row[0]) if row else 0
        if owned >= qty:
            if kind == "deliver":
                return (
                    f"行囊已有 {ITEM_NAMES.get(item, item)} x{owned}；未消耗精力。\n"
                    "下一步：tale_ops turnin"
                )
            result = await _advance(conn, steward, tale, "item_gain", trigger=item)
            await conn.commit()
            return result or "已识别行囊物品，但任务状态没有变化。"

    used = await _explore_count(conn, steward["id"])
    if used + 1 > config.TALE_EXPLORE_DAILY:
        raise ValueError(
            f"今天已经主动探索 {used} 次了，潮水也需要休息。"
            "明天再来。"
        )

    from . import energy as energy_mod
    await energy_mod.spend(conn, steward["id"], config.TALE_EXPLORE_ENERGY, action="tale_explore")
    await _use_explore(conn, steward["id"])

    if kind == "explore":
        result = await _advance(conn, steward, tale, "explore_cmd", trigger=domain)
        await conn.commit()
        return result or "探索结束，什么也没有发生。"

    item = stage["item"]
    qty = int(stage.get("qty", 1))
    row = await (await conn.execute(
        "SELECT quantity FROM satchel WHERE steward_id=? AND item=?",
        (steward["id"], item),
    )).fetchone()
    owned = int(row[0]) if row else 0
    found = max(0, qty - owned)
    if found:
        await db.add_item(conn, steward["id"], item, found)
    found_line = f"在{DOMAIN_LABELS[domain]}找到 {ITEM_NAMES.get(item, item)} x{found or qty}。"
    if kind == "deliver":
        await conn.commit()
        return f"{found_line}\n下一步：tale_ops turnin"
    result = await _advance(conn, steward, tale, "item_gain", trigger=item)
    await conn.commit()
    return f"{found_line}\n\n{result or '任务状态没有变化。'}"


async def _cmd_turnin(conn: aiosqlite.Connection, steward: dict[str, Any]) -> str:
    return await _turnin(conn, steward)


async def _cmd_abandon(
    conn: aiosqlite.Connection, steward: dict[str, Any], tale_key: str
) -> str:
    catalog = await _catalog(conn)
    tale = catalog.get(tale_key)
    if not tale:
        raise ValueError(f"没有名为 {tale_key} 的潮闻任务")
    progress = await _get_progress(conn, steward["id"], tale_key)
    if not progress or progress["status"] != "active":
        raise ValueError(f"你没有进行中的「{tale['title']}」")
    await conn.execute(
        "UPDATE steward_tales SET status='abandoned', updated_at=? WHERE id=?",
        (db.now(), progress["id"]),
    )
    await conn.execute(
        """
        INSERT INTO steward_tales_done (steward_id, tale_key, outcome, completed_at, times)
        VALUES (?, ?, 'abandoned', ?, 1)
        ON CONFLICT(steward_id, tale_key, outcome) DO UPDATE SET
            times=times+1,
            completed_at=excluded.completed_at
        """,
        (steward["id"], tale_key, db.now()),
    )
    await conn.commit()
    return f"你放下了「{tale['title']}」。潮声还在，只是不再属于你的黑盒。"


async def _cmd_board(conn: aiosqlite.Connection, steward: dict[str, Any]) -> str:
    conn.row_factory = aiosqlite.Row
    rows = await (await conn.execute(
        """
        SELECT s.name, COUNT(*) AS count, MAX(d.completed_at) AS last_at
        FROM steward_tales_done d
        JOIN stewards s ON s.id = d.steward_id
        WHERE d.outcome='completed'
        GROUP BY d.steward_id
        ORDER BY count DESC, last_at ASC
        LIMIT ?
        """,
        (config.TALE_BOARD_LIMIT,),
    )).fetchall()
    if not rows:
        return "还没有人完成过潮闻任务。"
    lines = ["潮闻完成榜："]
    for i, r in enumerate(rows, 1):
        lines.append(f"  {i}. {r['name']} — 完成 {r['count']} 个")
    return "\n".join(lines)


async def _cmd_souvenirs(conn: aiosqlite.Connection, steward: dict[str, Any]) -> str:
    catalog = await _catalog(conn)
    conn.row_factory = aiosqlite.Row
    rows = await (await conn.execute(
        """
        SELECT tale_key, completed_at
        FROM steward_tales_done
        WHERE steward_id=? AND outcome='completed'
        ORDER BY completed_at, tale_key
        """,
        (steward["id"],),
    )).fetchall()
    entries: list[str] = []
    for row in rows:
        tale = catalog.get(row["tale_key"])
        if not tale:
            continue
        souvenir = tale.get("rewards", {}).get("souvenir")
        if not souvenir:
            continue
        entries.append(
            f"  {_souvenir_line(souvenir)} · 来自「{tale['title']}」\n"
            f"    {souvenir['description']}"
        )
    if not entries:
        return "潮闻收藏册还是空的。完成带纪念品的潮闻后会永久收录在这里。"
    return (
        f"潮闻收藏册 · {len(entries)} 件（不占行囊，不能出售或赠送）：\n"
        + "\n".join(entries)
    )


# ══ 外部钩子 ═══════════════════════════════════════════════════

async def check_item_progress(
    conn: aiosqlite.Connection, steward_id: int, item: str, qty: int = 1
) -> str | None:
    """获得物品时调用，自动推进相关 item 阶段。"""
    steward = await db.get_steward_by_id(steward_id)
    if not steward:
        return None
    catalog = await _catalog(conn)
    active = await _active_tales(conn, steward_id)
    for p in active:
        tale = catalog.get(p["tale_key"])
        if not tale:
            continue
        stage = tale["stages"][p["stage_idx"]]
        if stage.get("kind") == "item" and stage.get("item") == item:
            # 重新读取 steward，确保 satchel 已更新
            steward = await db.get_steward_by_id(steward_id)
            result = await _advance(conn, steward, tale, "item_gain", trigger=item)
            if result:
                return result
    return None


async def check_action_progress(
    conn: aiosqlite.Connection, steward_id: int, domain: str
) -> str | None:
    """在指定地点操作后调用，自动推进相关 explore 阶段。"""
    steward = await db.get_steward_by_id(steward_id)
    if not steward:
        return None
    catalog = await _catalog(conn)
    active = await _active_tales(conn, steward_id)
    for p in active:
        tale = catalog.get(p["tale_key"])
        if not tale:
            continue
        stage = tale["stages"][p["stage_idx"]]
        if stage.get("kind") == "explore" and stage.get("domain") == domain:
            result = await _advance(conn, steward, tale, "action", trigger=domain)
            if result:
                return result
    return None


async def snapshot_line(key_id: int) -> str:
    """给 steward_sheet 用的简短提示。"""
    try:
        s = await require_steward(key_id, exempt_duty=True)
    except ValueError:
        return ""
    async with db.connect() as conn:
        active = await _active_tales(conn, s["id"])
        if not active:
            return ""
        catalog = await _catalog(conn)
        tale = catalog.get(active[0]["tale_key"])
        if not tale:
            return ""
        stage = tale["stages"][active[0]["stage_idx"]]
        return (
            f"潮闻：{tale['title']} 阶段 {active[0]['stage_idx'] + 1}/"
            f"{len(tale['stages'])}（{stage['title']}）→ tale_ops status"
        )


# ══ 入口 ═══════════════════════════════════════════════════════

async def tale_ops(key_id: int, command: str) -> str:
    cmd = (command or "").strip()
    verb, _, rest = cmd.partition(" ")
    verb = verb.lower()
    rest = rest.strip()

    if verb in ("help", "?", "帮助"):
        return TALE_HELP

    s = await require_steward(key_id)
    async with db.connect() as conn:
        if not verb or verb in ("list", "列表"):
            return await _cmd_list(conn, s)
        if verb in ("accept", "接", "接取"):
            if not rest:
                raise ValueError("用法：tale_ops accept 任务key")
            return await _cmd_accept(conn, s, rest)
        if verb in ("status", "状态", "进度"):
            return await _cmd_status(conn, s)
        if verb in ("explore", "探索"):
            return await _cmd_explore(conn, s, rest)
        if verb in ("turnin", "交付", "领奖"):
            return await _cmd_turnin(conn, s)
        if verb in ("abandon", "放弃"):
            if not rest:
                raise ValueError("用法：tale_ops abandon 任务key")
            return await _cmd_abandon(conn, s, rest)
        if verb in ("board", "榜"):
            return await _cmd_board(conn, s)
        if verb in ("souvenirs", "souvenir", "纪念品", "收藏册", "藏品"):
            return await _cmd_souvenirs(conn, s)

    raise ValueError(f"未知 tale 指令: {command}\n{TALE_HELP}")
