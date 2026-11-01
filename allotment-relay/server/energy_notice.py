"""精力梯子与渔网新规上线告示：一次性，world_flags 防重复。

init_db 里跟别的一次性迁移一起跑（保存点 + 标记原子）：岛上已经有人时，写一条潮生会告示 + 一条全岛纪事；
全新的岛（还没有管理员）不写，标记照写，以后不会再补。重复启动不会重复写。
"""
from __future__ import annotations

from . import db

ENERGY_LADDER_FLAG = "energy_ladder_notice_v1"
ENERGY_LADDER_ACTION = "energy_ladder_notice"

ENERGY_LADDER_NOTICE = (
    "【潮生会告示 · 灶台与渔网新规】\n"
    "即日起岛上几处规矩调整：\n"
    "1. 熟菜精力重新排过：照谱做的菜按用料贵贱排，最便宜的也有 22 点，越费料越顶饱。\n"
    "2. 随手乱炖照样能吃，但不会比照谱做的菜更顶饱。\n"
    "3. 特色菜加成减半：灯笼鱼刺身 +9、潮骨汤 +6。\n"
    "4. 花店菊花香茅茶 8 → 10 点。\n"
    "5. 雾菇汤、卤浸海藻锅、卤边潮锅、海鲜炒饭四道菜卖给系统的回收价回调，想多赚请去小馆或集市。\n"
    "6. 渔网只看量不看鱼价，按档位给固定奖励；钓贵鱼请用竿子。\n"
    "有疑问来潮生会留言。"
)


async def _announce_work(conn, stats: dict[str, int]) -> int:
    row = await (await conn.execute("SELECT COUNT(*) FROM stewards")).fetchone()
    if int((row[0] if row else 0) or 0) <= 0:
        return 0
    await db.add_chronicle(ENERGY_LADDER_ACTION, ENERGY_LADDER_NOTICE, None, conn=conn)
    await conn.execute(
        "INSERT INTO hui_notices (tag, body, created_at, retracted) VALUES ('厅示', ?, ?, 0)",
        (ENERGY_LADDER_NOTICE, db.now()),
    )
    stats["processed"] += 2
    return 2


async def announce_energy_ladder(conn) -> int:
    """上线告示。返回写了几条（0 = 已发过，或岛上还没有人）。"""
    return await db.run_flagged_migration(conn, ENERGY_LADDER_FLAG, "精力梯子告示", _announce_work)
