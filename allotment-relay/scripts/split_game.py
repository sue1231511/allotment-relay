# -*- coding: utf-8 -*-
"""把 server/game.py 按领域切成 server/game/ 包。纯搬家：不改任何函数体逻辑。

规则：
- 顶层函数按名字归入 base/manual/steward/plot/tide/shed/tote 七个子模块
- 每个 submodule 头部 = 原 import 头（相对导入升一级 . -> ..）+ from .base import 四件套
- 函数体内的延迟 import（from . import x / from .x import y）同样升一级
- __init__.py re-export 全部顶层名字，外部 from .game import / game.xxx 全兼容
"""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "server"
SRC = ROOT / "game.py"
PKG = ROOT / "game"

# 函数名 -> 子模块
ASSIGN = {
    "_parse_int": "base", "_parcel_line": "base", "_load_named_plot": "base",
    "require_steward": "base",
    "relay_manual": "manual",
    "steward_sheet": "steward", "steward_revise": "steward",
    "peer_sheet": "steward", "guild_shift": "steward",
    "plot_ops": "plot", "_plot_one": "plot",
    "tide_ops": "tide", "_collect_bottle_replies": "tide", "_collect_handoffs": "tide",
    "shed_ops": "shed", "_shed_one": "shed", "mascot_ops": "shed",
    "beacon_ops": "shed", "swap_ops": "shed", "hearth_ops": "shed",
    "tote_ops": "tote", "_tote_one": "tote", "_satchel_stack_expand": "tote",
}

BUMP = [
    (re.compile(r"^(\s*)from \. import "), r"\1from .. import "),
    (re.compile(r"^(\s*)from \.(\w+) import "), r"\1from ..\2 import "),
]


def bump_rel_imports(text: str) -> str:
    out = []
    for line in text.splitlines(keepends=True):
        for pat, rep in BUMP:
            line, n = pat.subn(rep, line, count=1)
            if n:
                break
        out.append(line)
    return "".join(out)


def main() -> None:
    src = SRC.read_text(encoding="utf-8")
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)

    # 模块级非 def/import 语句检查（应只有 docstring）
    stray = [n for n in tree.body if not isinstance(
        n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Import, ast.ImportFrom, ast.Expr))]
    if stray:
        sys.exit(f"发现模块级语句，人工处理: {ast.dump(stray[0])[:200]}")

    # 原文件 import 头 = 到第一个 def 之前的所有行
    first_def = tree.body[0]
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            first_def = node
            break
    header = "".join(lines[: first_def.lineno - 1])
    header = bump_rel_imports(header)

    # 收集函数体
    buckets: dict[str, list[str]] = {m: [] for m in set(ASSIGN.values())}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            mod = ASSIGN.get(node.name)
            if mod is None:
                sys.exit(f"未归类的顶层函数: {node.name}")
            body = "".join(lines[node.lineno - 1: node.end_lineno])
            buckets[mod].append(bump_rel_imports(body))

    order = ["base", "manual", "steward", "plot", "tide", "shed", "tote"]
    PKG.mkdir(exist_ok=True)
    exported: dict[str, list[str]] = {}
    for mod in order:
        parts = buckets[mod]
        names = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and ASSIGN[node.name] == mod:
                names.append(node.name)
        exported[mod] = names
        if mod == "base":
            content = header + "\n\n" + "\n\n\n".join(parts) + "\n"
        else:
            content = (
                header
                + "from .base import _parse_int, _parcel_line, _load_named_plot, require_steward\n"
                + "\n\n" + "\n\n\n".join(parts) + "\n"
            )
        (PKG / f"{mod}.py").write_text(content, encoding="utf-8", newline="")
        print(f"{mod}.py: {len(names)} 函数, {len(names) and sum(p.count(chr(10)) for p in parts)} 行")

    # __init__.py
    init_lines = [
        "# -*- coding: utf-8 -*-",
        '"""game 包：原 server/game.py 按领域拆分的门面。',
        "",
        "对外接口与拆分前完全一致：",
        "  from .game import require_steward   # 或 from ..game import / from server import game",
        "  game.plot_ops / game.tote_ops / game._plot_one ...",
        '"""',
    ]
    for mod in order:
        names = ", ".join(exported[mod])
        init_lines.append(f"from .{mod} import {names}  # noqa: F401")
    (PKG / "__init__.py").write_text("\n".join(init_lines) + "\n", encoding="utf-8", newline="")
    print("__init__.py 写好，导出", sum(len(v) for v in exported.values()), "个名字")


if __name__ == "__main__":
    main()
