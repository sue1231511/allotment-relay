"""周潮不再和岸税叠加：上线告示，一次性，world_flags 防重复。

写法同 energy_notice：init_db 里跟别的一次性迁移一起跑（保存点 + 标记原子）。
岛上已经有人时，写一条潮生会厅示 + 一条全岛纪事；全新的岛（还没有人）不写，标记照写，以后不会再补。
重复启动不会重复写。
"""
from __future__ import annotations

from . import config, db

TIDE_TAX_CAP_FLAG = "tide_tax_cap_notice_v1"
TIDE_TAX_CAP_ACTION = "tide_tax_cap_notice"


def _cap_pct() -> int:
    return int(round(config.WEEKLY_TAKE_CAP_RATE * 100))


def notice_text() -> str:
    pct = _cap_pct()
    return (
        "【潮生会告示 · 周潮与岸税新规】\n"
        "即日起，每周周潮和岸税不再叠着收：\n"
        "1. 周潮冲走的票，抵本周岸税。本周周潮实际冲走你多少票，你本周岸税应交额就先减掉多少，最低减到 0。"
        "税单和纪事里会写明「黑潮已冲 X，抵税 X」这样的话。\n"
        f"2. 一周总拿走封顶：周潮实际冲走加本周岸税实收，合计不超过周一结算前口袋的 {pct}%。"
        "先压岸税；如果光周潮就超过这条线，周潮本身也只冲到这条线。\n"
        "3. 其余照旧：周潮只冲 3 万以上的超额，风暴窗板照样少冲；本周新号免征；岸税档表、潮差、潮锈和岸维都没变。\n"
        "有疑问来潮生会留言。"
    )


async def _announce_work(conn, stats: dict[str, int]) -> int:
    row = await (await conn.execute("SELECT COUNT(*) FROM stewards")).fetchone()
    if int((row[0] if row else 0) or 0) <= 0:
        return 0
    text = notice_text()
    await db.add_chronicle(TIDE_TAX_CAP_ACTION, text, None, conn=conn)
    await conn.execute(
        "INSERT INTO hui_notices (tag, body, created_at, retracted) VALUES ('厅示', ?, ?, 0)",
        (text, db.now()),
    )
    stats["processed"] += 2
    return 2


async def announce_tide_tax_cap(conn) -> int:
    """上线告示。返回写了几条（0 = 已发过，或岛上还没有人）。"""
    return await db.run_flagged_migration(
        conn, TIDE_TAX_CAP_FLAG, "周潮岸税封顶告示", _announce_work
    )
