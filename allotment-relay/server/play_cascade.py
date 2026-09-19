"""方案末「钓条鱼串起修冰箱腌鱼修帆」级联提示。

不另开玩法，只读现有库存/耐久，告诉下一步。
"""
from __future__ import annotations

from typing import Any


async def hint(conn, steward: dict[str, Any]) -> str | None:
    from . import loop_couple as loop_mod

    return await loop_mod.hint(conn, steward)
