"""沿海联盟 lore 扩写 — 回流玩法文案，不改机制。"""

from __future__ import annotations

import random

BAR_OWNER = "荔栀"

# ── 十一、纪事模板（可拼进 add_chronicle 或随机尾缀）──
CHRONICLE_LORE: dict[str, list[str]] = {
    "voyage_deep": [
        "某档主从深漂回来。船还在，人也还在。酒吧当晚可能解锁「深海回声」。",
        "深漂归港。旧账本边角那句话又在传：归港者可饮。",
    ],
    "hail_parley": [
        "外海今天少打一架。对方收了票，联盟少修一条船。",
        "买路票成交。黑旗也要算油钱——联盟记下了。",
    ],
    "amends": [
        "一次逾篱，一次致歉。菜没长回来，档信长回来一点。",
        "篱笆条火药味散了。联盟公约：自然脱落越界，不视作主动逾篱。",
    ],
    "lili": [
        "栗栗来了。她不收票。有贝壳的赶紧。",
        "流动摊出现。今日货单全服一份，换完部分就走。",
    ],
    "boss": [
        "潮渊之主再次被联盟合力打回深处。神话暂时结束。厨房开始研究怎么做。",
        "神话可以敬畏，肉不能浪费。——联盟厨房传统",
    ],
    "bar_blackout": [
        "灯灭了。歌没停。荔栀骂人的声音也没停。",
        "停电全场合唱。纪事里又有人喊「来一个！」荔栀：「滚。」",
    ],
    "hangover": [
        "昨晚属于酒吧。今天属于桥桥大夫。",
        "宿醉。桥桥：「昨晚自己喝，今天自己付。」",
    ],
}

# ── 九、季象 · 脉冲 lore（effect_type → 文案）──
PULSE_SEASON_LORE: dict[str, list[str]] = {
    "red_tide": [
        "赤潮周：近岸捕捞波动，别跟海较劲。姜姨：不新鲜的别往厨房拿。",
        "海红了，岸上人就得学会吃菜。——老水手惯例",
    ],
    "blight_whisper": [
        "枯病周：某类作物生长发虚，堆肥和温室更值钱，邻里 assist 变多。",
        "叶脉发黄那周，联盟周目标常转成救助型——互相搭把手更划算。",
    ],
    "fish_run": [
        "渔汛周：赶海与撒网手气上调，集市水产暴增，酒吧晚上更挤。",
        "白天都发财，晚上都来花钱。——荔栀对渔汛周的总结",
    ],
    "storm_front": [
        "大雾/风暴周：雾智管理更重要，海玻璃与珠砂概率偶升，黑旗时隐时现。",
        "看不清，但大家还在生活。——沿海季象老话",
    ],
    "calm_sea": [
        "平流周：出海报废略降，胆小船长也能装勇敢。",
        "镜面海的日子，适合修船、晒网、去酒吧坐一会儿。",
    ],
    "loot_surge": [
        "退潮礼包周：交换台台阶像宝藏区，捡到的算你眼神好。",
        "滩上旧物多：潮币、relic、化石贝壳——这里不是第一批人。",
    ],
    "warm_breeze": [
        "暖风周：打理份地时更容易顺手捡到小东西，别偷懒。",
        "阳面回温，篱笆边的好运气比天气预报准一点。",
    ],
    "fog_bank": [
        "雾墙周：赶海和撒网容易空网，别跟海赌气。",
        "贴岸浓雾：看得见码头，看不见鱼。",
    ],
    "merchant_caravan": [
        "商贩巡游周：档口工分像被风捎来，guild 多一点点。",
        "流动商贩路过，票子比人走得快。",
    ],
    "gnat_swarm": [
        "小虫汛周：露天作物刚打理完，虫群可能再来一遍。",
        "蚜虫云过境，温室比露天省心。",
    ],
    "storm_surge": [
        "暴潮周：口袋太鼓的人先被海认领。8000 以上的超额会被卷走一截。",
        "潮头拍门那几天，风暴窗板比渔网值钱。",
    ],
    "black_tide": [
        "秋分黑潮：倒灌进档口，工分票按口袋厚度分段冲走。2000 以下没事。",
        "姜姨：海不跟穷人过不去，跟把票堆成墙的人过不去。",
    ],
}

BARTON_SEASON_NOTES: dict[str, list[str]] = {
    "red_tide": [
        "二十年前也有过这种雾。那年三条船没出港，反而都活得挺好。",
        "赤潮别贪。海里红了，岸上人就得学会吃菜。",
    ],
    "blight_whisper": [
        "枯病别硬扛。温室里那几棵，往往是全联盟的指望。",
        "以前叫住在一块儿。后来事情多了，就改叫联盟。",
    ],
    "fish_run": [
        "渔汛来了就干活，别全扔给酒吧。——虽然酒吧也会忙。",
        "网沉下去那一下，心跳也跟着沉。正常。",
    ],
    "storm_front": [
        "风大不可怕。觉得自己比风大才可怕。",
        "二十年前也有过这种雾。那年没人深漂，大家都还行。",
    ],
    "calm_sea": [
        "平流日子修船最划算。别等下一阵风来才想起漏洞。",
        "海今天像账本中间一行：平淡，但够用。",
    ],
    "loot_surge": [
        "滩上捡到的旧潮币，别全当故事。能换票的是真票。",
        "退潮后多走两步，篱笆有记性，海也有。",
    ],
    "warm_breeze": [
        "暖风天多走一圈地。懒的人闻不到好运气。",
        "晒被天适合打理，也适合把欠的账还了。",
    ],
    "fog_bank": [
        "雾大就别跟海较劲。空网不丢人，硬撑才丢人。",
        "看不清岸的时候，先看清自己的票。",
    ],
    "merchant_caravan": [
        "商贩来了就多干点活。票不会自己长腿。",
        "流动商贩路过，档口比酒吧先热闹。",
    ],
    "gnat_swarm": [
        "虫汛周温室更值钱。露天得勤打理。",
        "嗡嗡声大的时候，别跟作物置气，再 tend 一遍。",
    ],
    "storm_surge": [
        "暴潮来了先看口袋，再看出海。票多的人海认识你。",
        "窗板关好。海不认渔网，认厚度。",
    ],
    "black_tide": [
        "秋分那潮不讲情面。堆成墙的票，先给海。",
        "二十年前也有过这种倒灌。那年富人先学会吃菜。",
    ],
}

# ── 三、黑旗派系（who → 一句话定位）──
BLACK_FLAG_FACTIONS: dict[str, dict[str, str]] = {
    "雾角快船": {
        "tag": "雾角快船",
        "lore": "船快、抢小件、不太恋战。穷船别追，追上也没油水。",
        "detail": "黑帆在雾里贴舷，他们只想要轻便货。",
    },
    "兼职海盗": {
        "tag": "兼职海盗",
        "lore": "白天可能还在集市卖鱼。范姐：认出来也别在我摊前打。",
        "detail": "你好像昨天在摊位见过这张脸——也可能没有。",
    },
    "关税巡逻": {
        "tag": "关税巡逻",
        "lore": "自称旧航路税务维护者。荔栀：会做表格的海盗。",
        "detail": "他们要航线登记费、雾区通行费，还有「临时海况管理费」。",
    },
    "无名追猎者": {
        "tag": "无名追猎者",
        "lore": "很少谈判。老水手：你有钱他们拦你，你看见了不该看的他们也拦你。",
        "detail": "几乎不抢东西。只是跟着。",
    },
    "黑帆小艇": {
        "tag": "黑帆小艇",
        "lore": "外海松散协调：买路价别卷同行。",
        "detail": "三票战争以后，大家都学乖了一点。",
    },
    "走私稽查": {
        "tag": "走私稽查",
        "lore": "真假难辨。有人说是黑旗，有人说是旧登记处外包。",
        "detail": "要查舱，也要查你的表情。",
    },
}

# ── 五、篱间 ──
HEDGE_NOTE_SAMPLES = [
    "今天帮你看了一眼地，没动东西。",
    "再伸手我就去档口。",
    "希望你家的菜和你的边界感一起茁壮成长。",
    "昨天确实手快了，票已补，别挂我名册。",
    "篱笆是木头做的，边界不是。",
    "自然脱落越界，不视作主动逾篱。——三颗雾豌豆案后追加",
]

LORE_AMENDS_QUIPS = [
    "三颗雾豌豆案之后，联盟才写下「自然脱落越界不算逾篱」。",
    "致歉完毕。篱笆条可以删了，档信慢慢长回来。",
    "一次逾篱，一次 amends。邻居：勉强算人。",
]

# ── 二、深海 ──
DEEP_LORE_SNIPPETS = [
    "深漂以后，海开始按另一套账本工作。越深，越不像给岸上人准备的。",
    "酒吧最老账本边角：深漂归港的人常说三种反应——不说话的、说海底有人唱歌的、只要烈酒的。",
    "「深海回声」不是纪念英雄，是给确实走到很深又回来的人一个位置坐。",
    "潮渊之主不是邪神，是深海应激。神话可以敬畏，肉不能浪费。",
]

MYTH_OCTOPUS_TABOOS = [
    "第一次吃神话章鱼肉别一个人吃。",
    "深漂当天不吃。吃的时候别讨论它是不是还活着。",
]

# ── 六、栗栗 ──
LILI_LORE = [
    "栗栗不收联盟票，只收贝壳与海玻璃——票只在联盟内部好使。",
    "月海镜不进常规目录。夜里照它，有人说看见旧海岸，有人说什么都没有。",
    "驮包别乱摸。铃鹿替栗栗驮货、代报价，脖子上一枚旧铜铃。",
    "夜栖是栗栗名下的守夜狗，项圈铃铛与栗栗腕上那对。摊在他就在。",
    "滩头规矩：栗栗那儿，捡得多不如捡得好。亮壳硬通货，糙壳当零头。",
    "铃鹿乱捡款不退不换。大家嘴上骂铃鹿，手却很诚实。",
    "风水成组自己蹲、自己试——月海镜配潮汐钟，单件只是装饰。",
]

# ── 七、诊所 ──
CLINIC_LORE = [
    "桥桥不赊账。同情不能当库存。——诊所柜台下旧账本",
    "真正拖垮小聚落的不是传奇瘟疫，是「小病扛扛就过去了」。",
    "宿醉患者说酒是荔栀推荐的：桥桥让你找荔栀报销。荔栀：滚。",
]

# ── 七点五、岸上 NPC 小传 ──
NPC_STORY_LORE = [
    "《渡口的空椅》阿槐年轻时替人送信，一封信能换一顿饭，也能让一家人整夜不睡。后来船票改成了凭证，信越来越少，他还是在渡口留了一张空椅：给不想立刻走的人坐。有人问他等谁，他只说，等那些还没学会好好告别的人。",
    "《两只铃铛》栗栗第一次到岛上时，铃鹿的驮包破了一个洞，亮壳沿着潮线滚了一路。夜栖追着壳跑，她追着夜栖跑，最后是巴顿把两只铃铛系到一起。如今摊子一响，老住民就知道：不是风，是她来了。",
    "《诊费》桥桥刚开诊所那年允许赊账，柜台下压着十七张欠条。雨季过去，病人都好了，药柜却空了。从那以后她把“不赊账”写得很大；但每年第一场大雾，她都会在门口放一壶姜水，不记在账上。",
    "《巷口的叶子》拾叶原先替档口扫地，发现每一片被人踩脏的叶子都比自己干净。她离开后还是会把叶子捡起来，只是顺手也捡走一点不设防的人生。她说这是生意；范姐说她只是把难堪折成了笑话。",
    "《不唱的副歌》我哪有旺夫命第一次驻唱时，只肯唱没有副歌的旧歌。荔栀没赶她走，只把结账单倒扣在吧台上。后来她学会在副歌前停半拍，让全场替她接下去——唱完仍然会笑场，像什么都没输过。",
]

# ── 八、岸上人 ──
SHORE_OBSERVER_LINES = [
    "岸上人从网页看世界，像隔着一层玻璃站在码头边。",
    "荔栀：谁来都一样，进门消费就行。",
    "人类留下的是故事层影响，不是档主外挂。",
]

# ── 四、酒吧 origin ──
BAR_ORIGIN_LORE = [
    "酒吧最初是旧码头补给屋：热水、腌鱼、麦酒、干毛巾。",
    "经营失败 → 来赚票 → 有钱再消费 → 票流回人群。荔栀：没钱就干活，有钱就喝。",
    "牛郎挣的不是钱，是概率。——酒吧内部都市传说",
    "联盟备案正规工。——荔栀名言，档口从未正式用过这措辞。",
]

WET_NOTE_LORE = [
    "旧码头换班夜常有纸条：「今晚别去码头。」背面常写着黑旗换班——不是预言，是提醒。",
    "湿透纸条多从洗碗池漂出。荔栀：以前的事，别去就对了。问多了她也不解释。",
    "三票战争那年，旧码头夜里不宜逗留。纸条传到现在，字句只剩半句。",
]

# ── lore_ops 主题 ──
LORE_TOPICS: dict[str, list[str]] = {
    "alliance": [
        "沿海联盟不是建国神话，是生活点互相认账后形成的共同体。",
        "最早工分票因为三件事：船坏了要人帮、偷菜不能天天打架、欠账要有人记。",
        "老水手巴顿：以前叫住在一块儿。后来事情多了，就改叫联盟。",
        "滩上会挖出旧潮币、锈铁 relic、化石贝壳——这里不是第一批人。",
    ],
    "deep": DEEP_LORE_SNIPPETS,
    "blackflag": [
        "「黑旗」不是单一组织，是岸上统称：船快、旗黑、雾里拦人、不报登记号。",
        "雾角快船 / 兼职海盗 / 关税巡逻 / 无名追猎者——至少四路。",
        "买路票早期靠喊价。三票战争后外海流传：抢归抢，别卷同行。",
        "黑帆议会是否存在，联盟从未证实。但买路价偶尔异常一致。",
    ],
    "bar": BAR_ORIGIN_LORE + WET_NOTE_LORE + [
        "著名停电全场合唱：我哪有旺夫命清唱，后厨洗盘子的也跟。",
        "厕所辣条案：现在默认酒吧民俗。门口贴过「禁止蹲地吃辣条」，第三天又有人吃。",
    ],
    "hedge": [
        "联盟最早公约只有「自己的地自己管」——完全没用。",
        "三颗雾豌豆案：巴顿判定风吹脱落，联盟追加自然脱落越界不算逾篱。",
        "hedge_note 后来发展成篱间文学：礼貌型、威胁型、阴阳型、认错型、哲学型。",
    ] + HEDGE_NOTE_SAMPLES[:3],
    "lili": LILI_LORE,
    "clinic": CLINIC_LORE,
    "npc": NPC_STORY_LORE,
    "tt": [
        "档口东头那间杂货，招牌写着 Tt酱。种子、饲料、渔网钓竿、剪刀挤奶器——别去集市跟人砍价种子。",
        "Tt酱不讲价。好感写在账本上：十颗心，满了才肯打 75 折。心多了她记账越懒。",
        "有人连着送了一周熟菜，爱心才多两颗。75 折不是两天刷出来的。",
        "有人说她心情好会塞熟菜。有人说那是假的。进店的人自己知道。",
        "剪羊毛的剪刀只有她店里有。渔网和钓竿她也进了货，入门不必再跑潮汐铺。",
        "蚯蚓饵她论份卖。嫌贵就自己 tend 翻土，别在店里叹气。",
    ],
    "season": [
        "联盟季象不是固定节日，是沿海生活者都知道的周期性麻烦。",
        "赤潮周 / 枯病周 / 渔汛周 / 大雾周——各有玩法侧重，不是全员绝望。",
    ],
    "barton": [
        "巴顿不卖预言，只提醒：这些事以前也发生过，联盟以前也熬过去了。",
    ] + [x for notes in BARTON_SEASON_NOTES.values() for x in notes[:1]],
    "boss": CHRONICLE_LORE["boss"] + MYTH_OCTOPUS_TABOOS,
    "shore": SHORE_OBSERVER_LINES,
}

LORE_TOPIC_LABELS = {
    "alliance": "沿海联盟旧史",
    "deep": "深海与潮渊",
    "blackflag": "黑旗政治",
    "bar": "滨海酒吧",
    "hedge": "篱间伦理",
    "lili": "游商栗栗",
    "tt": "Tt酱杂货",
    "clinic": "桥桥诊所",
    "npc": "岸上 NPC 小传",
    "season": "季象与脉冲",
    "barton": "老水手巴顿",
    "boss": "潮渊之主",
    "shore": "岸上人",
}


def pulse_season_detail(effect_type: str) -> str:
    pool = PULSE_SEASON_LORE.get(effect_type, [])
    return random.choice(pool) if pool else ""


def barton_season_note(effect_type: str) -> str:
    pool = BARTON_SEASON_NOTES.get(effect_type, [])
    return random.choice(pool) if pool else ""


def black_flag_faction(who: str | None = None) -> dict[str, str]:
    if who and who in BLACK_FLAG_FACTIONS:
        return BLACK_FLAG_FACTIONS[who]
    key = random.choice(list(BLACK_FLAG_FACTIONS.keys()))
    return BLACK_FLAG_FACTIONS[key]


def black_flag_detail(who: str) -> str:
    fac = BLACK_FLAG_FACTIONS.get(who)
    if fac:
        return fac["detail"]
    return random.choice([
        "黑帆贴舷，要你表态。",
        "海上没有政府，只有「你今天遇到谁」。",
    ])


def chronicle_lore(action: str) -> str | None:
    pool = CHRONICLE_LORE.get(action)
    if not pool or random.random() > 0.35:
        return None
    return random.choice(pool)


def hedge_note_hint() -> str:
    return random.choice(HEDGE_NOTE_SAMPLES)


def amends_quip() -> str:
    if random.random() < 0.4:
        return random.choice(LORE_AMENDS_QUIPS)
    return ""


def boss_defeat_lore() -> str:
    return random.choice(CHRONICLE_LORE["boss"])


def daily_lore_tip() -> str:
    topic = random.choice(list(LORE_TOPICS.keys()))
    return random.choice(LORE_TOPICS[topic])


def lore_topic_text(topic: str) -> str:
    key = topic.strip().lower()
    if key in ("list", "topics", "help"):
        lines = ["lore 主题（lore_ops scan 主题名）："]
        for k, label in LORE_TOPIC_LABELS.items():
            lines.append(f"  {k} — {label}")
        return "\n".join(lines)
    if key not in LORE_TOPICS:
        known = " / ".join(LORE_TOPIC_LABELS.keys())
        return f"未知主题。可用: {known}\n或 lore_ops scan 随机抽一条。"
    label = LORE_TOPIC_LABELS.get(key, key)
    body = random.choice(LORE_TOPICS[key])
    extra = ""
    if key == "season" and random.random() < 0.5:
        note = barton_season_note(random.choice(list(BARTON_SEASON_NOTES.keys())))
        if note:
            extra = f"\n\n老水手巴顿：「{note}」"
    return f"«{label}»\n\n{body}{extra}"


def lore_scan_random() -> str:
    topic = random.choice(list(LORE_TOPICS.keys()))
    return lore_topic_text(topic)
