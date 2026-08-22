"""目送人·阿槐：替玩家在渡口送别并保存名字。"""
from __future__ import annotations

from . import db, survival, world
from .game import require_steward

MUSONG_HELP = """visit_ops musong 子命令（整句写进 command）：
  musong visit — 去渡口见目送人·阿槐；空子命令也是 visit
  musong send 名字 — 请阿槐替你目送一个人；每个游戏日一次
  musong remember — 查看最近记下的送别
例子：musong visit · musong send 安 · musong remember
这是公开世界里的虚构纪事，只写一个简短称呼，不要填写现实隐私。"""


def _scene(name: str) -> str:
    phase = world.current_day_phase()
    tide = world.current_tide()
    if phase == "dawn":
        sight = "晨雾把渡口藏去一半，那道身影沿着潮湿的栈桥渐渐淡了"
    elif phase == "dusk":
        sight = "落日落到海平面上，那道影子被余光拉得很长"
    elif phase == "night":
        sight = "船灯没入黑水，只剩灯塔一次次照过空荡的航道"
    else:
        sight = "小船离开木桩，岸上的面容慢慢缩成看不清的一点"
    tide_line = {
        "ebb": "退潮把水声带远",
        "slack": "平潮安静得像所有人都屏住了呼吸",
        "flood": "涨潮推着船向外走",
    }.get(tide, "潮水缓慢移动")
    return (
        f"阿槐把“{name}”写在渡口的小册上。{tide_line}，{sight}。\n\n"
        "他没有说挽留的话，只在原地站着。\n"
        "“愿意回头的时候，心口会暖一下。接下来的路，还是要自己走。”"
    )


async def _send(steward: dict, name: str) -> str:
    target = " ".join(name.strip().split())
    if not target:
        raise ValueError("用法：visit_ops musong send 名字")
    if len(target) > 24:
        raise ValueError("送别称呼最多 24 个字符")
    day = db.day_id()
    async with db.connect() as conn:
        exists = await (await conn.execute(
            "SELECT 1 FROM musong_sendoffs WHERE steward_id=? AND day=?",
            (steward["id"], day),
        )).fetchone()
        if exists:
            raise ValueError("今天已经请阿槐目送过一个人了。送别不赶场，换班后再来。")
        await conn.execute(
            "INSERT INTO musong_sendoffs (steward_id, day, target_name, created_at) VALUES (?,?,?,?)",
            (steward["id"], day, target, db.now()),
        )
        await survival.bump(conn, steward["id"], mist_wit=2, standing=1)
        await db.add_chronicle(
            "musong", f"{steward['name']} 请阿槐目送了 {target}", steward["id"], conn=conn
        )
        await conn.commit()
    return _scene(target) + "\n\n雾智 +2 · 档信 +1（今日送别）"


async def _remember(steward_id: int) -> str:
    async with db.connect() as conn:
        rows = await (await conn.execute(
            """SELECT target_name, day FROM musong_sendoffs
               WHERE steward_id=? ORDER BY created_at DESC LIMIT 8""",
            (steward_id,),
        )).fetchall()
    if not rows:
        return "阿槐的小册还没有为你记下任何名字。试试 visit_ops musong send 名字。"
    lines = ["阿槐替你目送过："]
    lines.extend(f"  · {row[0]}（第 {row[1]} 个潮日）" for row in rows)
    lines.append("\n“记得不是为了把人留下，是让走过的路不至于无声。”")
    return "\n".join(lines)


async def musong_ops(key_id: int, command: str = "visit") -> str:
    steward = await require_steward(key_id)
    parts = (command or "visit").strip().split(maxsplit=1)
    verb = parts[0].lower() if parts else "visit"
    rest = parts[1] if len(parts) > 1 else ""
    if verb in {"help", "帮助"}:
        return MUSONG_HELP
    if verb in {"visit", "见", "拜访"}:
        from . import npc
        return await npc.npc_ops(key_id, "visit 目送人·阿槐")
    if verb in {"send", "目送", "送别"}:
        return await _send(steward, rest)
    if verb in {"remember", "记得", "册子"}:
        return await _remember(steward["id"])
    raise ValueError(f"未知 musong 指令：{command}\n{MUSONG_HELP}")
