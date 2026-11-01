"""旧送礼纪事补收礼人：一次性，world_flags 防重复。

以前每次打开「收到的礼物」都会对整张纪事表跑一条 UPDATE 补 target_id（全表扫描，每次请求两遍）。
现在唯一的送礼写入点（game/tote.py）两条纪事都带收礼人，所以只有早期历史数据漏写；
改成启动时在保存点里补一遍，补完写标记，以后不再扫。
匹配规则和原来一致：正文里含「送礼给 名字：」，名字相同的取编号最小的岛民。
"""
from __future__ import annotations

import re

from . import db

_NAME_RE = re.compile(r"送礼给 ([^：]+)：")

GIFT_TARGET_FLAG = "gift_target_backfill_v1"


async def _backfill_work(conn, stats: dict[str, int]) -> int:
    rows = await (await conn.execute(
        "SELECT id, text FROM chronicle WHERE action IN ('gift', 'gift_inbox') AND target_id IS NULL"
    )).fetchall()
    if not rows:
        return 0
    names = await (await conn.execute(
        "SELECT id, name FROM stewards WHERE name != '' ORDER BY id ASC"
    )).fetchall()
    by_name = {str(name).lower(): int(sid) for sid, name in names}  # 岛民名唯一（不分大小写）
    needles = [(int(sid), f"送礼给 {name}：".lower()) for sid, name in names]
    updates: list[tuple[int, int]] = []
    for chronicle_id, text in rows:
        low = str(text or "").lower()
        target = 0
        for m in _NAME_RE.finditer(low):  # 快路径：抽出「送礼给 X：」里的 X 直接查表
            target = by_name.get(m.group(1), 0)
            if target:
                break
        if not target:  # 名字里带全角冒号之类的，退回逐个比对
            for sid, needle in needles:
                if needle in low:
                    target = sid
                    break
        if target:
            updates.append((target, int(chronicle_id)))
    if updates:
        await conn.executemany("UPDATE chronicle SET target_id=? WHERE id=?", updates)
    fixed = len(updates)
    stats["processed"] += fixed
    return fixed


async def backfill_gift_targets(conn) -> int:
    """返回补了几条（0 = 已补过或没有要补的）。"""
    return await db.run_flagged_migration(conn, GIFT_TARGET_FLAG, "旧送礼补收礼人", _backfill_work)
