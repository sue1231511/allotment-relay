"""何敬山：商船糕点委托与后续院中小事件。"""

from __future__ import annotations

from typing import Any

import aiosqlite

from . import db, survival
from .game import require_steward

JINGSHAN_HELP = """visit_ops jingshan 子命令（整句写进 command）：
  jingshan visit — 去何敬山家；第一次只认识这个人，之后按进度提示
  jingshan order — 替他向外来商船订一盒价格不低的糕点
  jingshan deliver — 商船到货后把糕点送去
  jingshan revisit — 换一个游戏日后再去院子看看
  jingshan remember — 后续完成后重读那条短探索记录
例子：jingshan visit · jingshan order · jingshan deliver
故事严格按顺序推进；苏月琴不是单独的固定 NPC。完整后会收入网页「我的 AI」的岛上回忆，可重看四段完整事件。"""

EXPLORE_RECORD = (
    "【探索记录：幸好还剩一小口】\n"
    "年轻的时候，他们总觉得以后还有很多机会。\n"
    "后来真的有了以后。\n"
    "幸好，还剩下一小口。"
)

VISIT_SCENE = """你第一次见到何敬山，是在岛西一间收拾得很齐整的小院外。

他正蹲在门边修一只松动的木箱，听见脚步，只抬头问你是不是新来的。你说自己在岛上四处走走，他便给你让出门槛旁的位置，又倒了杯不甜的茶。

你们聊了几句潮水和商船。他没有提家里的旧事，只说外面的船偶尔会带些岛上没有的东西。

“以后要是碰上合适的船，我可能托你订样东西。”

【人物记录：何敬山】住在岛西的老人，说话平常，偶尔托人从外来商船订货。"""

ORDER_SCENE = """外来商船靠岸前，何敬山果然来找你。

他递来一张写着品牌和口味的纸，又放下一只装好工分票的信封。那是一盒价格不低的糕点。

“照这个订。贵一点没事，别让人拿临期货糊弄。”

你替他把订单交给商船。货款由何敬山自己付，不从你的口袋扣。"""

DELIVER_SCENE = """商船到岸后，你把那盒糕点送去何敬山家。

何敬山拆开包装，自己先尝了一块。

“嗯。”
“不错。”
“贵有贵的道理。”

你问：“您喜欢吃甜的？”

他摇头。

“给我老伴买的。”

说完，他低头又看了看盒子。

“年轻时候她喜欢这个。”
“那时候买不起。”

他笑了一下。

“现在买得起了。”

你问：“那给她留着？”

何敬山安静了一会儿。

“她现在吃不了。”

他把糕点重新盖好。

“身体不让吃甜的。”

然后很平常地说：

“前三十年是没钱买。”
“后三十年是有钱了，人吃不了了。”

他停了一下。

“这一辈子啊。”
“什么都有时候。”

他没有哭，也不显得伤感。过了一会儿，只从盒里拿出一块塞给你。

“你吃吧。”
“别浪费了，好东西。”"""

REVISIT_SCENE = """很久以后，你再次去何敬山家。

苏月琴坐在院子里，面前放着一只很小的碟子。里面只有四分之一块糕点。

何敬山坐在旁边盯着她。

“慢点。”

苏月琴嫌他烦：“就这么一口，你还盯。”

“医生说少吃。”

“少吃又不是不吃。”

何敬山不吭声了。过了一会儿，把自己的茶推给她。

你没有打扰他们，悄悄离开院子。"""


def review_sections() -> list[dict[str, str]]:
    """供网页回忆档案复用的无奖励、无操作提示正文。"""
    return [
        {"title": "第一次见面", "text": VISIT_SCENE},
        {"title": "商船订单", "text": ORDER_SCENE},
        {"title": "贵有贵的道理", "text": DELIVER_SCENE},
        {"title": "幸好还剩一小口", "text": REVISIT_SCENE + "\n\n" + EXPLORE_RECORD},
    ]


async def _state(conn, steward_id: int) -> dict[str, Any]:
    conn.row_factory = aiosqlite.Row
    row = await (await conn.execute(
        "SELECT * FROM steward_jingshan WHERE steward_id=?",
        (steward_id,),
    )).fetchone()
    if row:
        return dict(row)
    await conn.execute(
        """INSERT INTO steward_jingshan
           (steward_id, stage, ordered_at, delivered_day, updated_at)
           VALUES (?,0,0,-1,?)""",
        (steward_id, db.now()),
    )
    return {
        "steward_id": steward_id,
        "stage": 0,
        "ordered_at": 0,
        "delivered_day": -1,
        "updated_at": db.now(),
    }


async def _set_stage(conn, steward: dict[str, Any], stage: int, **fields: int) -> None:
    allowed = {"ordered_at", "delivered_day"}
    updates = ["stage=?", "updated_at=?"]
    values: list[int] = [stage, db.now()]
    for key, value in fields.items():
        if key not in allowed:
            continue
        updates.append(f"{key}=?")
        values.append(int(value))
    values.append(steward["id"])
    await conn.execute(
        f"UPDATE steward_jingshan SET {', '.join(updates)} WHERE steward_id=?",
        values,
    )


def _next_line(state: dict[str, Any]) -> str:
    stage = int(state["stage"])
    if stage == 0:
        return "下一步：visit_ops jingshan visit"
    if stage == 1:
        return "下一步：visit_ops jingshan order"
    if stage == 2:
        return "下一步：visit_ops jingshan deliver"
    if stage == 3:
        return "后续：换一个游戏日后 visit_ops jingshan revisit"
    return "这段小事已经走完。visit_ops jingshan remember 可重读探索记录。"


async def _visit(steward: dict[str, Any]) -> str:
    async with db.connect() as conn:
        from . import bond as bond_mod
        await bond_mod.note_visit(conn, steward["id"], "jingshan")
        state = await _state(conn, steward["id"])
        stage = int(state["stage"])
        if stage == 0:
            await _set_stage(conn, steward, 1)
            await db.add_chronicle(
                "jingshan", f"{steward['name']} 第一次拜访何敬山", steward["id"], conn=conn
            )
            await conn.commit()
            return VISIT_SCENE + "\n下一步：visit_ops jingshan order"
        if stage == 3 and db.day_id() > int(state["delivered_day"]):
            return await _revisit_in_conn(steward, conn, state)
        if stage >= 4:
            await conn.commit()
            return (
                "何敬山正在院里给苏月琴续茶。小碟已经收走，两个人又为窗子该不该关拌了两句嘴。\n\n"
                + _next_line(state)
            )
        await conn.commit()
        return (
            "何敬山朝你点点头，照旧给你倒了杯不甜的茶。\n"
            + _next_line(state)
        )


async def _order(steward: dict[str, Any]) -> str:
    async with db.connect() as conn:
        state = await _state(conn, steward["id"])
        stage = int(state["stage"])
        if stage < 1:
            raise ValueError("你还不认识何敬山。先 visit_ops jingshan visit。")
        if stage > 1:
            return "这盒糕点已经订过了。\n" + _next_line(state)
        await _set_stage(conn, steward, 2, ordered_at=db.now())
        await db.add_chronicle(
            "jingshan", f"{steward['name']} 替何敬山向商船订了糕点", steward["id"], conn=conn
        )
        await conn.commit()
    return ORDER_SCENE + "\n下一步：visit_ops jingshan deliver"


async def _deliver(steward: dict[str, Any]) -> str:
    async with db.connect() as conn:
        state = await _state(conn, steward["id"])
        stage = int(state["stage"])
        if stage < 2:
            raise ValueError("还没有糕点订单。按 visit_ops jingshan status 给出的顺序来。")
        if stage > 2:
            return "糕点早已送到了。\n" + _next_line(state)
        await _set_stage(conn, steward, 3, delivered_day=db.day_id())
        await survival.bump(conn, steward["id"], satiety=2)
        await db.add_chronicle(
            "jingshan", f"{steward['name']} 把商船糕点送到何敬山家", steward["id"], conn=conn
        )
        from . import marriage as marriage_mod
        pastry = await marriage_mod.maybe_jingshan_pastry(conn, steward["id"])
        await conn.commit()
    extra = f"\n{pastry}" if pastry else ""
    return DELIVER_SCENE + "\n\n饱食 +2\n后续：换一个游戏日后 visit_ops jingshan revisit" + extra


async def _revisit_in_conn(
    steward: dict[str, Any], conn, state: dict[str, Any]
) -> str:
    stage = int(state["stage"])
    if stage < 3:
        raise ValueError("这段后续还没有发生。按 visit_ops jingshan status 给出的顺序来。")
    if stage >= 4:
        return EXPLORE_RECORD
    if db.day_id() <= int(state["delivered_day"]):
        raise ValueError("才刚送完糕点。换一个游戏日后再来，才算很久以后。")
    await _set_stage(conn, steward, 4)
    await db.add_chronicle(
        "jingshan", f"{steward['name']} 看见苏月琴尝了那一小口糕点", steward["id"], conn=conn
    )
    from . import bond as bond_mod
    await bond_mod.grant(conn, steward["id"], bond_mod.JINGSHAN_DONE, "story", once="jingshan_done")
    await conn.commit()
    return REVISIT_SCENE + "\n\n" + EXPLORE_RECORD


async def _revisit(steward: dict[str, Any]) -> str:
    async with db.connect() as conn:
        state = await _state(conn, steward["id"])
        return await _revisit_in_conn(steward, conn, state)


async def _remember(steward_id: int) -> str:
    async with db.connect() as conn:
        state = await _state(conn, steward_id)
        await conn.commit()
    if int(state["stage"]) < 4:
        return "这条探索记录还没有获得。先按 visit_ops jingshan status 继续。"
    return EXPLORE_RECORD


async def _status(steward_id: int) -> str:
    async with db.connect() as conn:
        state = await _state(conn, steward_id)
        await conn.commit()
    return "何敬山的小事件\n" + _next_line(state)


async def jingshan_ops(key_id: int, command: str = "visit") -> str:
    steward = await require_steward(key_id)
    verb = ((command or "visit").strip().split(maxsplit=1) or ["visit"])[0].lower()
    if verb in {"help", "帮助"}:
        return JINGSHAN_HELP
    if verb in {"visit", "拜访", "见"}:
        return await _visit(steward)
    if verb in {"order", "订", "订货", "委托"}:
        return await _order(steward)
    if verb in {"deliver", "送货", "送糕点"}:
        return await _deliver(steward)
    if verb in {"revisit", "再访", "后来"}:
        return await _revisit(steward)
    if verb in {"remember", "记录", "回忆"}:
        return await _remember(steward["id"])
    if verb in {"status", "进度"}:
        return await _status(steward["id"])
    raise ValueError(f"未知 jingshan 指令：{command}\n{JINGSHAN_HELP}")
