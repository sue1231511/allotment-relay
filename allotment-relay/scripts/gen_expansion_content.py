#!/usr/bin/env python3
"""One-off generator for server/expansion_content.py"""
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "server" / "expansion_content.py"


def _crop(name, emoji, seed, sell, grow, yield_, tier, tags, seasons=None, **extra):
    d = {
        "name": name, "emoji": emoji, "seed_price": seed, "sell": sell,
        "grow": grow, "yield": yield_, "tier": tier, "spread": 0.24,
        "tags": list(tags),
    }
    if seasons:
        d["seasons"] = seasons
    d.update(extra)
    return d


def main():
    lines = ['from __future__ import annotations\n', '\n']
    lines.append('EXTRA_CROPS = {\n')
    crops = [
        ("spinach", "菠菜", "🥬", 8, 17, 55, 5, 1, ["leaf"], None),
        ("lettuce", "生菜", "🥬", 7, 16, 50, 5, 1, ["leaf"], ("春", "秋")),
        ("celery", "芹菜", "🌿", 9, 18, 70, 4, 2, ["leaf"], None),
        ("chives", "韭菜", "🌿", 8, 17, 65, 5, 1, ["seasoning"], ("春", "夏", "秋")),
        ("scallion", "青葱", "🧅", 7, 15, 55, 5, 1, ["seasoning"], None),
        ("shiso", "紫苏", "🌿", 11, 22, 75, 4, 2, ["herb", "seasoning"], ("夏",)),
        ("rapeseed", "油菜", "🌼", 9, 19, 90, 4, 2, ["leaf"], ("春",)),
        ("carrot", "胡萝卜", "🥕", 8, 18, 85, 4, 2, ["root"], None),
        ("daikon", "白萝卜", "🥕", 7, 16, 80, 4, 2, ["root"], ("秋", "冬")),
        ("potato", "土豆", "🥔", 9, 20, 100, 4, 2, ["root"], None),
        ("taro", "芋头", "🍠", 10, 21, 95, 4, 2, ["root", "tropic"], None),
        ("lotus_root", "莲藕", "🪷", 12, 26, 110, 3, 3, ["root"], ("夏", "秋")),
        ("onion", "洋葱", "🧅", 8, 17, 90, 4, 2, ["seasoning"], None),
        ("yam", "山药", "🍠", 11, 24, 120, 3, 3, ["root"], None),
        ("soybean", "黄豆", "🫘", 10, 20, 100, 4, 2, ["legume"], None),
        ("green_pea", "豌豆", "🫛", 9, 19, 85, 5, 1, ["legume"], ("春",)),
        ("green_bean", "四季豆", "🫛", 9, 18, 80, 4, 2, ["legume"], ("春", "夏")),
        ("peanut", "花生", "🥜", 10, 22, 110, 4, 2, ["legume"], ("夏",)),
        ("adzuki", "红豆", "🫘", 10, 21, 100, 4, 2, ["legume"], None),
        ("tomato", "番茄", "🍅", 11, 24, 90, 4, 2, ["fruit"], ("夏",)),
        ("cucumber", "黄瓜", "🥒", 9, 20, 75, 5, 1, ["fruit"], ("春", "夏")),
        ("eggplant", "茄子", "🍆", 10, 22, 95, 4, 2, ["fruit"], ("夏",)),
        ("pumpkin", "南瓜", "🎃", 12, 28, 150, 6, 3, ["fruit"], ("秋",)),
        ("wax_gourd", "冬瓜", "🍈", 11, 25, 140, 3, 3, ["fruit"], ("夏",)),
        ("corn", "玉米", "🌽", 10, 22, 110, 4, 2, ["grain"], ("夏",)),
        ("bell_pepper", "彩椒", "🫑", 12, 26, 100, 4, 2, ["fruit"], ("夏",)),
        ("sichuan_pepper", "花椒", "🌶️", 14, 30, 130, 3, 3, ["seasoning"], ("秋",)),
        ("coriander", "香菜", "🌿", 8, 18, 60, 5, 1, ["herb", "seasoning"], None),
        ("garden_mint", "薄荷", "🌿", 9, 19, 65, 5, 1, ["herb"], ("春", "夏")),
        ("rosemary", "迷迭香", "🌿", 13, 28, 120, 3, 3, ["herb"], None),
        ("basil", "罗勒", "🌿", 11, 24, 85, 4, 2, ["herb"], ("夏",)),
        ("turmeric", "姜黄", "🫚", 12, 26, 100, 4, 2, ["seasoning", "tropic"], None),
        ("rice", "水稻", "🌾", 10, 22, 130, 4, 2, ["grain"], ("夏",)),
        ("wheat", "小麦", "🌾", 8, 18, 120, 4, 2, ["grain"], ("秋", "冬")),
        ("glutinous_rice", "糯米", "🌾", 11, 24, 125, 3, 3, ["grain"], None),
        ("oat", "燕麦", "🌾", 9, 20, 115, 4, 2, ["grain"], ("秋",)),
        ("sorghum", "高粱", "🌾", 9, 19, 110, 4, 2, ["grain"], ("夏",)),
        ("saltgrass", "海盐草", "🌿", 13, 27, 90, 4, 2, ["sea", "special"], None),
        ("tide_ginger", "潮姜", "🫚", 14, 30, 95, 4, 2, ["seasoning", "special"], None),
        ("fog_mushroom", "雾菇", "🍄", 15, 32, 100, 3, 3, ["special"], ("秋", "冬")),
        ("moon_bean", "月豆", "🫛", 13, 29, 105, 4, 2, ["legume", "special"], None),
        ("red_algae", "红藻", "🌿", 11, 23, 80, 4, 2, ["sea"], None),
        ("blue_tide_moss", "蓝潮苔", "🌿", 12, 25, 85, 4, 2, ["sea", "special"], None),
        ("lamp_sprout", "灯芽菜", "💡", 16, 34, 70, 3, 3, ["leaf", "special"], None),
    ]
    for row in crops:
        key = row[0]
        d = _crop(row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8], row[9])
        lines.append(f'    "{key}": {repr(d)},\n')
    lines.append("}\n\n")
    OUT.write_text("".join(lines), encoding="utf-8")
    print("wrote", OUT, "lines", len(lines))


if __name__ == "__main__":
    main()
