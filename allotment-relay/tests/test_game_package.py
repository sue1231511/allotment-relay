#!/usr/bin/env python3
"""game 包门面契约：原 server/game.py 的全部顶层名字必须继续可从 game 拿到。

2026-09-27 game.py 拆成 game/ 包（纯搬家）。外部几十处 `from .game import ...`
和 `game.xxx` 依赖这批名字；谁改 __init__.py 漏导出，这里第一时间红。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# 拆分当天的全部顶层函数（含被外部引用的私有名 _plot_one/_load_named_plot 等）
NAMES = {
    "base": ["_parse_int", "_parcel_line", "_load_named_plot", "require_steward"],
    "manual": ["relay_manual"],
    "steward": ["steward_sheet", "steward_revise", "peer_sheet", "guild_shift"],
    "plot": ["plot_ops", "_plot_one"],
    "tide": ["tide_ops", "_collect_bottle_replies", "_collect_handoffs"],
    "shed": ["shed_ops", "_shed_one", "mascot_ops", "beacon_ops", "swap_ops", "hearth_ops"],
    "tote": ["_satchel_stack_expand", "_tote_one", "tote_ops"],
}


def test_game_package_facade() -> None:
    import asyncio
    import os
    import tempfile

    os.environ.setdefault("DATA_DIR", tempfile.mkdtemp())
    from server import game

    for mod, names in NAMES.items():
        for name in names:
            assert hasattr(game, name), f"game.{name} 不在门面上（子模块 {mod}）"
            attr = getattr(game, name)
            assert callable(attr), f"game.{name} 不是可调用对象"
            assert attr.__module__ == f"server.game.{mod}", (
                f"game.{name} 应住在 server.game.{mod}，实际 {attr.__module__}"
            )

    # 手册能跑、体量正常（拆分当天 45427 字符；大幅缩水=手册被误删）
    manual = asyncio.run(game.relay_manual())
    assert "潮汐岛手册" in manual and len(manual) > 40000, len(manual)

    # 拆分时的行数锚点：plot 是最大块；谁把 _plot_one 细拆了请更新这里的下限
    import inspect

    plot_src = inspect.getsource(game._plot_one)
    assert len(plot_src.splitlines()) > 900, len(plot_src.splitlines())


if __name__ == "__main__":
    test_game_package_facade()
    print("game package facade ok")
