#!/usr/bin/env python3
"""从现有目录数据生成 server/price_book.py（价格簿）。

只用于首次生成与人工对照：生成物提交进仓库，之后价格簿手工维护。
tests/test_price_book.py 会校验价格簿与 catalog / tt / 花房 / 后室铺里的字面价一致，
任何一边改了没同步都会红。

用法：python scripts/gen_price_book.py [输出路径]   （默认写 server/price_book.py）
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_log = logging.getLogger("gen_price_book")


def _made_b(sell: int) -> int:
    """B = ceil(sell / 0.70)，使 floor(0.70B) == sell。整数运算。"""
    if sell <= 0:
        return 0
    b = (sell * 100 + 69) // 70
    assert b * 70 // 100 == sell, (sell, b)
    return b


def build() -> dict[str, dict]:
    from server import catalog as c
    from server import tt
    from server.florist_catalog import FLOWERS, TEAS
    from server.pricing import LOOT_EXCLUDE, TOKEN_ITEMS
    from server.undertide_catalog import COMMON_GOODS, LINKED_GOODS, RARE_GOODS

    legacy = getattr(c, "LEGACY_ITEM_PRICES", c.ITEM_PRICES)
    book: dict[str, dict] = {}

    # 1. 可买品：Tt 货架（含种子、饲料、渔需、工具、嫁妆）
    for item, base, kind in tt.shop_skus():
        if item in TOKEN_ITEMS:
            continue
        ch = ["tt_flat" if kind == "dowry" else "tt"]
        if item.startswith("seed_"):
            ch.append("plot")
        book[item] = {"B": int(base), "cls": "buy", "ch": tuple(ch)}
    for k, meta in c.TOOLS.items():
        item = f"tool_{k}"
        e = book.get(item)
        if e is None:
            book[item] = {"B": int(meta["cost"]), "cls": "buy", "ch": ("tool_ops",)}
        else:
            e["ch"] = tuple(e["ch"]) + ("tool_ops",)
            e["B"] = max(e["B"], int(meta["cost"]))

    # 2. 小屋家具（hut_ops buy）：回收走折旧，ITEM_PRICES 只作展示（cost//2）
    for cat in (c.HUT_HARD, c.HUT_SOFT):
        for k, meta in cat.items():
            item = f"fit_{k}"
            cost = int(meta.get("cost") or 0)
            if meta.get("craft_only") or cost <= 0:
                continue
            book[item] = {"B": cost, "cls": "buy", "ch": ("hut",), "sell": cost // 2}

    # 3. 畜栏
    for k, meta in c.LIVESTOCK.items():
        book[f"live_{k}"] = {"B": int(meta["buy"]), "cls": "buy", "ch": ("barn",)}

    # 4. 默语花房：鲜花、茶包（回收保持 8 / 4）
    for k, meta in FLOWERS.items():
        book[f"flower_{k}"] = {"B": int(meta["price"]), "cls": "buy", "ch": ("florist",),
                               "sell": int(legacy.get(f"flower_{k}", 8))}
    for k, meta in TEAS.items():
        book[f"flower_tea_{k}"] = {"B": int(meta["price"]) - 8, "cls": "buy", "ch": ("florist",),
                                   "sell": int(legacy.get(f"flower_tea_{k}", 4))}

    # 5. 后室铺：店货（货架买、强卖买；出货价另算，不走 tote vend）
    for layer, goods in (("common", COMMON_GOODS), ("linked", LINKED_GOODS), ("rare", RARE_GOODS)):
        for k, meta in goods.items():
            book[f"ut_{k}"] = {"B": int(meta["base"]), "cls": "buy", "ch": ("ut_shelf",),
                               "layer": layer, "notote": True}
            # 6. 赃物：强买抢来的，任何商店都买不到。B 由旧 vend 字段反推
            if k not in LOOT_EXCLUDE and layer in ("common", "rare"):
                book[f"utl_{k}"] = {"B": _made_b(int(meta["vend"])), "cls": "made", "loot": True,
                                    "notote": True}

    # 5b. 诊所药品（clinic buy；最低买入 = 九折）
    from server.clinic_copy import CLINIC_MEDICINES
    for key, meta in CLINIC_MEDICINES.items():
        book[key] = {"B": int(meta["price"]), "cls": "buy", "ch": ("clinic",)}

    # 7. 其余全部是产出品（含熟菜基础价、手工品、作物、鱼、矿、畜产……）
    import re
    star_dish = re.compile(r"^dish_.+_s[1-5]$")
    for item, sell in sorted(legacy.items()):
        if item in book or item in TOKEN_ITEMS:
            continue
        if star_dish.match(item) or item.startswith("mix_"):
            continue   # 熟菜星级价、混搭菜价由配方公式推出，不进簿
        book[item] = {"B": _made_b(int(sell)), "cls": "made"}
    return dict(sorted(book.items()))


def render(book: dict[str, dict]) -> str:
    lines = [
        '"""价格簿：每个物品唯一的基础价 B（单一来源）。',
        "",
        "cls   buy  = 系统有买入渠道（B = 0 折扣时的标价）",
        "      made = 没有任何系统买入渠道（B = ceil(改版前回收价 / 0.70)，floor(0.70B) 恰好等于旧回收价）",
        "ch    买入渠道标签：tt（吃好感折扣）tt_flat（嫁妆柜不打折）plot tool_ops hut barn florist clinic ut_shelf",
        "sell  固定回收价（只能往下调，不能高于公式；花、茶包、家具展示价）",
        "notote 不走 tote_ops vend（后室铺货走销赃，家具走小屋折旧）",
        "loot  赃物（强买抢来的 utl_ 货，任何商店买不到，走高价销赃通道）",
        "",
        "手作信物（订婚戒、潮誓戒等，见 pricing.TOKEN_ITEMS）不在簿里：不可回收。",
        "",
        "改价：直接改这个文件，tests/test_price_book.py 会逼你同步 catalog / tt 等处的字面值。",
        "初始内容由 scripts/gen_price_book.py 从改版前的目录数据生成。",
        '"""',
        "from __future__ import annotations",
        "",
        "BOOK: dict[str, dict] = {",
    ]
    for k, v in book.items():
        parts = []
        for fk in ("B", "cls", "ch", "layer", "sell", "notote", "loot"):
            if fk in v:
                parts.append(f'"{fk}": {v[fk]!r}')
        lines.append(f'    "{k}": {{{", ".join(parts)}}},')
    lines.append("}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    argv = sys.argv[1:] if argv is None else argv
    out = Path(argv[0]) if argv else ROOT / "server" / "price_book.py"
    try:
        book = build()
        out.write_text(render(book), encoding="utf-8")
    except Exception:
        _log.exception("生成价格簿失败 out=%s", out)
        return 1
    _log.info("写入 %s，共 %d 项", out, len(book))
    return 0


if __name__ == "__main__":
    sys.exit(main())
