"""潮下商品/斗士/赌局数值表 — 与文案分离，纯数据。"""

from __future__ import annotations

# ── 强联动货（layer=linked）────────────────────────────────
# vend: 真货回收价（次品=vend*0.45 的独立物品，假货=纪念物 vend 1）
# base: 基准定价（实价 = base × 黑市倍率 × 影信系数）
LINKED_GOODS = {
    "deep_wick": {
        "name": "深海灯芯", "emoji": "🕯️", "base": 40, "vend": 50,
        "genuine_hint": "灯芯是干的，但拿在手里有一丝凉意——像刚从很深的地方捞上来。",
        "effect_note": "（真货效果：下次深漂燃料减免——buff 联动二期接入）",
    },
    "fake_pass": {
        "name": "伪造买路票", "emoji": "🎫", "base": 15, "vend": 24,
        "genuine_hint": "纸的手感几乎和档口的一模一样。几乎。",
        "effect_note": "（真货效果：下次 bribe 半价——buff 联动二期接入）",
    },
    "old_hook_t5": {
        "name": "旧制 T5 鱼钩", "emoji": "🎣", "base": 45, "vend": 58,
        "genuine_hint": "钩尖在灯下泛着一层旧钢特有的哑光。",
        "effect_note": "（真货效果：数次稀有渔获加权——buff 联动二期接入）",
    },
    "unmarked_pillbox": {
        "name": "无标药盒", "emoji": "💊", "base": 20, "vend": 28,
        "genuine_hint": "盒子是真的。里面的药片没有任何标记。掌柜理货的手停了一下：「吃不死人。」",
        "effect_note": "（真货效果：下次治疗半价——buff 联动二期接入）",
    },
    "greenhouse_part": {
        "name": "温室私改件", "emoji": "🔧", "base": 55, "vend": 70,
        "genuine_hint": "螺纹是正的，咬合得很紧。好东西。",
        "effect_note": "（真货效果：阵风期生长惩罚减轻——buff 联动二期接入）",
    },
    "unsigned_key": {
        "name": "没署名的仓库钥匙", "emoji": "🗝️", "base": 30, "vend": 40,
        "genuine_hint": "齿口很新。锁孔里的灰是旧的。",
        "effect_note": "（真货效果：一次性私货箱——联动二期接入）",
    },
}

# ── 常规黑货（layer=common）───────────────────────────────
COMMON_GOODS = {
    "smuggled_tobacco": {"name": "走私烟丝", "emoji": "🚬", "base": 12, "vend": 16},
    "bulk_liquor": {"name": "散装烈酒", "emoji": "🥃", "base": 15, "vend": 20,
                    "hint": "入袋可 kitchen_ops eat 回精力；小概率次日宿醉（联动二期，一期为高回收价物品）"},
    "black_salt": {"name": "黑盐", "emoji": "🧂", "base": 18, "vend": 24},
    "old_chart_scrap": {"name": "旧海图残页", "emoji": "🗺️", "base": 22, "vend": 29},
    "rope_toolkit": {"name": "麻绳扳手套件", "emoji": "🧰", "base": 25, "vend": 33},
    "bite_block": {"name": "麻醉咬木", "emoji": "🪵", "base": 10, "vend": 13,
                   "hint": "角斗前置：咬住它，单场 body 惩罚 -5（深坑二期接入）"},
    "fog_glass_bead": {"name": "海雾玻璃珠", "emoji": "🔮", "base": 14, "vend": 19},
    "tide_worn_compass": {"name": "潮蚀罗盘", "emoji": "🧭", "base": 20, "vend": 26},
    "herringbone_knife": {"name": "鲱骨小刀", "emoji": "🔪", "base": 16, "vend": 21},
    "waxed_canvas": {"name": "打蜡帆布", "emoji": "📦", "base": 13, "vend": 17},
    "storm_matches": {"name": "防风火柴", "emoji": "🔥", "base": 9, "vend": 12},
    "quiet_bell": {"name": "哑铃铛", "emoji": "🔕", "base": 11, "vend": 15},
}

# ── 稀有黑货（layer=rare，每轮至多 1 种库存 1）────────────
RARE_GOODS = {
    "black_pearl": {"name": "黑珍珠", "emoji": "⚫", "base": 120, "vend": 160,
                    "hint": "没人问来路。掌柜也没打算说。"},
    "ship_bell": {"name": "沉船铜钟", "emoji": "🔔", "base": 100, "vend": 140,
                  "hint": "钟身刻着一条船的名字。那条船的名字不该出现在这里。"},
    "k_handkerchief": {"name": "素色手帕", "emoji": "🤍", "base": 150, "vend": 200,
                       "hint": "叠得一丝不苟。没人见过有人用它。"},
}

# ── NPC 斗士（深坑二期，表先立）───────────────────────────
PIT_FIGHTERS = [
    {"key": "rookie_wang", "name": "新兵阿旺", "level": 1, "power": 30},
    {"key": "old_mo", "name": "老磨", "level": 3, "power": 60},
    {"key": "butcher_gan", "name": "屠夫老甘", "level": 4, "power": 78},
]

# ── 黑市价格 ──────────────────────────────────────────────
# 实价 = base × 倍率区间(按层) × 影信系数(undertide_config.UT_REP_TIERS)
LAYER_MULT = {"common": 1.4, "linked": 1.6, "rare": 1.8}
