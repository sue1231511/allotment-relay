"""韶年望潮人 — 卦象、占卜符、价目与文案。"""

from __future__ import annotations

from typing import Any

FORTUNE_COST = 10
TRANSFER_COST = 30
TRANSFER_SUCCESS_RATE = 0.60
TRANSFER_FAIL_BAD_MULT = 0.10

FORTUNES: dict[str, dict[str, Any]] = {
    "fish_catch": {
        "name": "渔获卦",
        "omen": "吉",
        "line": "卦里鱼影翻涌，今日下竿，肥鱼自己往你钩上撞。",
        "hint": "钓鱼稀有概率翻倍",
    },
    "harvest": {
        "name": "丰收卦",
        "omen": "吉",
        "line": "田垄饱满，今日收成会多出一截。",
        "hint": "收成 +20%",
    },
    "peach": {
        "name": "桃花卦",
        "omen": "吉",
        "line": "人缘卦象软和，今日联盟里对你顺眼的人更多。",
        "hint": "社交回暖翻倍",
    },
    "broke": {
        "name": "破财卦",
        "omen": "凶",
        "line": "卦象漏财，巷口那拾叶怕是要多看你两眼。",
        "hint": "易被拾叶盯上、偷包",
    },
    "rough_sea": {
        "name": "破浪卦",
        "omen": "凶",
        "line": "海面下暗流涌动，今日出海凶多吉少，听我一句，别去。",
        "hint": "出海易遇坏海遇",
    },
    "flat": {
        "name": "平卦",
        "omen": "平",
        "line": "卦象平平，今日无大起大落，自己踏实干活。",
        "hint": "无特殊",
    },
}

GOOD_FORTUNES = ("fish_catch", "harvest", "peach")
BAD_FORTUNES = ("broke", "rough_sea")
ALL_FORTUNE_KEYS = tuple(FORTUNES.keys())

CHARMS: dict[str, dict[str, Any]] = {
    "fish_charm": {
        "name": "钓鱼符",
        "aliases": ("钓鱼符", "fish"),
        "price": 20,
        "line": "符纸带着潮腥，今日竿下必有回响。",
        "hint": "今日钓鱼必不空竿",
    },
    "field_charm": {
        "name": "护田符",
        "aliases": ("护田符", "field"),
        "price": 25,
        "line": "符角压在篱笆上，斑鸠今日绕着你田走。",
        "hint": "今日斑鸠偷不到你的菜",
    },
    "beach_charm": {
        "name": "赶海符",
        "aliases": ("赶海符", "beach"),
        "price": 30,
        "line": "符随潮动，今日翻沙比旁人多出一倍。",
        "hint": "今日赶海收获翻倍",
    },
    "calm_sea": {
        "name": "定风波",
        "aliases": ("定风波", "calm", "sea"),
        "price": 40,
        "line": "这张最金贵，海神见了都给你让路。",
        "hint": "今日出海不遇坏海遇",
    },
}

VISIT_LINE = "坐，我替你卜一卦，看今日这光景，宜不宜下海。"
TRANSFER_OK = "成了，今日逆风转顺，放心去。"
TRANSFER_FAIL = "海神没应，今日这霉运怕是要黏你一天，我劝你早点回屋躺着。"

CHRONICLE_TAGS = ("韶年", "望潮人", "滩头韶年")
