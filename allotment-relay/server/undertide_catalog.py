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

# ── 黑市装备（rare 层刷新，加战力、有损耗度，找掌柜修）────────
UT_GEAR_GOODS = {
    "rust_knuckles": {"name": "锈铁指虎", "emoji": "👊", "power": 2, "durability": 20, "price": 120,
                      "flavor": "磨得发亮。前主人用它打出过一条活路，也打出过一口牙。"},
    "blackflag_cutlass": {"name": "黑旗弯刀", "emoji": "⚔️", "power": 4, "durability": 30, "price": 200,
                          "flavor": "刀身上有道缺口，像是砍断过什么不该砍的东西。"},
    "sunken_blade": {"name": "沉船军刀", "emoji": "🗡️", "power": 6, "durability": 40, "price": 300,
                     "flavor": "从一艘没人提名字的沉船里捞上来的。刀鞘比刀还新。"},
}

# ── NPC 斗士（深坑）────────────────────────────────────────
# power 为战力底盘（等级梯度 58/64/70/77/85；对标玩家满状态 60/72/78/85）
PIT_FIGHTERS = [
    {"name": "新兵阿旺", "level": 1, "power": 58, "flavor": "第一次下坑，手一直在抖。但没退。"},
    {"name": "赔率小萨", "level": 1, "power": 60, "flavor": "输了七场还在打。所有人都押他输，他无所谓。"},
    {"name": "双港老雕", "level": 2, "power": 64, "flavor": "打完就去酒馆，喝完就来打。没有别的日程。"},
    {"name": "缝过三针的安", "level": 2, "power": 66, "flavor": "肚子上三道疤，缝得很漂亮。没人问是谁缝的。"},
    {"name": "老磨", "level": 3, "power": 70, "flavor": "三十七场。墙上有他的名字。他想凑个整数。"},
    {"name": "雨季来的女人", "level": 3, "power": 72, "flavor": "没人知道她从哪来。她打完就走，从不喝酒。"},
    {"name": "屠夫老甘", "level": 4, "power": 77, "flavor": "以前真的杀猪。手艺没丢。"},
    {"name": "墙上的名字", "level": 5, "power": 88, "flavor": "没人叫他真名。赢到第五级的人，名字就上墙了。"},
]
# 阵亡后自动补充的新人名池
PIT_REPLACEMENTS = [
    "替班的水手", "从外港来的", "第三次下坑的账房", "红头巾",
    "刚戒酒的", "半张脸有疤的", "沉默的大个子", "来还债的",
]

# ── 街头随机 NPC（胁迫经济）────────────────────────────────
STREET_NPC_NAMES = {
    "soft": ["刚输光的赌徒", "数着零钱的手艺人", "抱着空鱼篓的赶海人", "第一次下井的年轻人"],
    "norm": ["落魄水手", "赶夜路的货郎", "代人跑腿的信使", "退休的码头记账员"],
    "hard": ["退役斗士", "独眼船工", "收摊的私盐贩", "说话很轻的大个子"],
    "danger": ["不认识的人", "坐在最暗角落的人", "没有行李的人", "一直看着你的男人"],
}
TIER_LABEL = {"soft": "软柿子", "norm": "普通人", "hard": "硬茬", "danger": "别惹"}
TIER_MOOD = {
    "soft": "你一瞪眼，他就把货递过来了。手在抖。",
    "norm": "「便宜点不行吗。」他讨价还价了一句，声音不大。",
    "hard": "他看了看你的手，笑了。",
    "danger": "那人坐在阴影里。你看不清脸。你唯一确定的是——其他人绕着他走。",
}

# ── 医务间·体质药（越贵副作用越小）─────────────────────────
MEDIC_DRUGS = {
    "rough_stim": {
        "name": "粗制兴奋剂", "emoji": "💉", "price": 15,
        "buff": 10, "hours": 24, "crash": 8,
        "hint": "见效快，来路不明。药劲过去的那一下，会把你打回原形。",
    },
    "standard_boost": {
        "name": "标准强化剂", "emoji": "🧪", "price": 40,
        "buff": 15, "hours": 24, "crash": 4,
        "hint": "正经手艺提的。副作用轻，但别指望白坐车。",
    },
    "refined_extract": {
        "name": "精制提取物", "emoji": "💠", "price": 90,
        "buff": 20, "hours": 24, "crash": 0,
        "hint": "晏安自己那套流程出的。没有副作用——只有价格。",
    },
}

# ── 黑市价格 ──────────────────────────────────────────────
# 实价 = base × 倍率区间(按层) × 影信系数(undertide_config.UT_REP_TIERS)
LAYER_MULT = {"common": 1.4, "linked": 1.6, "rare": 1.8}
