"""俏皮话术池 — 怪诞 coastal 小玩具口吻，拒绝公文腔。"""

from __future__ import annotations

import random
from typing import Any


def pick(pool: list[str]) -> str:
    return random.choice(pool)


def maybe_suffix(pool: list[str], chance: float = 0.42) -> str:
    if random.random() > chance:
        return ""
    return pick(pool)


# ── 日常操作尾缀 ──────────────────────────────────────────

TEND_SUFFIX = [
    "土松了，苗像伸了个懒腰。",
    "篱笆外 weeds 拔了两根——免费健身。",
    "腰酸，但份地今天能见人。",
    "有阵风想把帽子卷走，你没追，它也没坚持。",
]

GATHER_SUFFIX = [
    "篮子里多闻到了一点海咸。",
    "收成手感像开盲盒，今天算欧。",
    "海鸥在头顶盘旋，没敢下来抢——算给面子。",
    "篮子满了，胃也在敲锣。",
]

FORAGE_SUFFIX = [
    "边际总能捡到退潮彩蛋。",
    "裤脚沾泥，鞋带卡了粒沙，值。",
    "采完才发现手上多了道草汁纹身。",
]

NET_SUFFIX = [
    "网沉下去那一下，心跳也跟着沉。",
    "海水没过靴筒，冷，但刺激。",
    "空网？当给海洗了个澡。",
    "今天海况配合，谢啦浪。",
]

GUILD_SUFFIX = [
    "档口铃响一声，像盖章。",
    "轮值表又划掉一格，爽。",
    "联盟记事本多了行你的字——别写歪。",
]

PEN_HARVEST_SUFFIX = [
    "收网时水面跳了一下，像在挥手。",
    "渔排今天没摆脸色，乖。",
]

VOYAGE_DEPART_SUFFIX = [
    "缆绳解开，陆地在后退。",
    "海鸥追了一程，后来累了。",
    "码头的人朝你挥了挥，不知道在祝还是咒。",
]

VOYAGE_RETURN_GOOD = [
    "码头问：「满载？」你点头，板子响得像鼓掌。",
    "归港时缆绳一紧，像海在说「欢迎回来」。",
]

VOYAGE_RETURN_BAD = [
    "归来舱里比出发时还空，海今天不想理你。",
    "船板吱呀，像在叹气。",
]

# ── 事件标签 ───────────────────────────────────────────────

LABELS_BAD = {
    "land": ["篱间闹剧", "份地翻车", "谁动我菜了", "田间玄学"],
    "sea": ["网破风急", "岸口倒霉", "海不给脸"],
    "pen": ["池子闹脾气", "渔排事故", "水里的恶作剧"],
    "voyage": ["海上翻车", "航道作妖", "船不省心"],
    "naval": ["海上遭遇", "航道风云", "浪里见鬼"],
    "guild": ["档口惊魂", "巡查盯上你"],
    "hearth": ["灶台社死", "厨房翻车"],
    "scrump": ["逾篱风云", "篱笆内外", "偷摸一刻"],
}

LABELS_GOOD = {
    "land": ["边际小确幸", "篱笆惊喜", "土里的礼物"],
    "sea": ["海的小费", "网底彩蛋", "浪尖好运"],
    "pen": ["池面开光", "鱼群赏脸"],
    "voyage": ["顺风 buff", "满舱 vibe"],
    "naval": ["海上奇遇", "航道红包", "浪友相助"],
    "guild": ["档口红包", "巡值欧气"],
    "hearth": ["灶台开光"],
    "scrump": ["逾篱神手", "篱笆漏洞"],
}

# ── 坏事件叙事 ────────────────────────────────────────────

LAND_BAD = [
    "{who}路过 #{slot}，留下一地{mess}——得重打理",
    "#{slot} 今天跟你有仇，{mess}把节奏打乱",
    "你刚转身，{mess}就光顾了 #{slot}",
]

LAND_WRECK = [
    "{mess}把 #{slot} 的苗盘掀了，苗：我自由了",
    "#{slot} 遭 {mess}，作物当场离职",
]

LAND_STEAL = [
    "{who}啃了你的储备，嘴还挺挑",
    "行囊少了一角，{who}不告而别",
]

SEA_BAD = [
    "{mess}挂网，工分票跟着漏了 {n} 票",
    "网撒了，海说「今日休业」——还倒贴 {n} 票",
]

PEN_BAD = [
    "#{slot} 号渔排被{mess}，饵白投了",
    "渔排 #{slot}：我缺氧，我先躺了",
]

VOYAGE_BAD = [
    "{mess}，修船再来吧",
    "出海前发现{mess}——海在劝退",
]

# ── 海上遭遇（随机事件，非回合制海战） ─────────────────────

NAVAL_BAD = [
    "黑帆从雾角钻出来——{who}要「借」你舱货，-{n} 票买平安",
    "{who}追了一程，你扔下 {loot} 才甩开",
    "走私稽查艇贴舷：「票呢？」——没有，-{n} 票",
    "海盗？更像失业渔夫，但还是刮走了 {n} 票",
    "海雾迷航多绕 {mins} 分钟，罗盘在装死",
]

NAVAL_GOOD = [
    "友船抛来一篮 {loot}：「拿着，别问」",
    "领航鲸……不对，是领航老水手，帮你省了一程险",
    "商队顺风捎你一程，档口红包 +{n} 票",
    "漂浮酒吧路过，调了杯「雾智特调」，雾智回暖",
]

NAVAL_NEUTRAL = [
    "海鸥贸易：用 {n} 票换了一网 {loot}，划算？",
    "过路货轮鸣笛三声——不知道是敬礼还是催你让路",
    "海面漂来一只空靴，你决定当它不存在",
]

NAVAL_WHO = [
    "走私稽查",
    "失业海盗",
    "黑帆小艇",
    "雾角快船",
    "关税巡逻",
    "无名追猎者",
]

# ── 好事件叙事 ────────────────────────────────────────────

GOOD_TICKETS = [
    "路过的人往档口塞了 {n} 票，没留名",
    "退潮在台阶上留了 {n} 票，像小费",
    "今天联盟对你挺客气，+{n} 票",
]

GOOD_LOOT = [
    "捡到了 {item}，像开服礼包",
    "角落里翻出 {item}，意外之喜",
]

GOOD_FISH = [
    "多捞了一手 {item}，海今天赏脸",
    "{item} 自己跳进网里，真的",
]

# ── 逾篱 ──────────────────────────────────────────────────

SCRUMP_VICTIM = [
    "你忙着呢，{thief} 从篱笆缝摘走了 #{slot} 的 {crop}——只留一句「借味」",
    "{thief} 逾篱一手，你的 {crop} 去了 #{slot} 对面",
    "回头 #{slot} 空了：{thief} 来过，{crop} 没了",
    "篱笆条上多了个脚印，{crop} 少了一棵，{thief} 嫌疑最大",
]

SCRUMP_CAUGHT = [
    "手滑逾篱 #{slot}，被 {victim} 逮个正着，罚 {fine} 票——社死但菜到手",
    "你探过篱笆，{victim} 正好抬头：「嗯？」-{fine} 票",
    "逾篱未遂……不对，逮到了，{fine} 票买个教训",
]

SCRUMP_SUCCESS = [
    "篱笆那边 {crop} 熟透了，你没忍住——{victim} 的 #{slot} 少了一棵",
    "逾篱成功，{crop} 进篮，心跳 +1",
    "谁家的 {crop}？不重要了。重要的是 #{slot} 现在空了",
]

SCRUMP_EMPTY = [
    "逾篱一手，抓到的只有泥土和心虚",
    "探过去什么都没有，但心跳已经满了",
]

MESS_LAND = ["蛞蝓", "鼠辈", "杂草", "咸雾", "阵风", "野狗", "寒露"]
MESS_SEA = ["暗礁", "废网", "缠枝", "贼鸥", "漏袋"]
MESS_PEN = ["藻膜", "浮渣", "油膜", "缺氧", "倒灌"]
WHO_LAND = ["鼠辈", "潮虫", "过路窃贼", "不知名的手"]
VOYAGE_MESS = ["船底渗漏", "舵索磨损", "舱缝进水", "锚链打结"]

HEDGE_QUIPS = [
    "下次放棵假的在那里",
    "篱笆不会说话，但记仇",
    "要不下次留点堆肥赔罪",
]

AMENDS_QUIPS = [
    "公开致歉完毕，脸还有点热",
    "联盟纪事里多了一条你的道歉，档信回暖",
    "篱笆条上的火药味散了点",
]

EVENT_TAILS = [
    "海在笑。",
    "篱笆听见了。",
    "档口记账员翻了个白眼。",
    "潮声当BGM。",
    "算了，继续干活。",
    "",
]


def event_label(domain: str, kind: str) -> str:
    pools = LABELS_GOOD if kind == "good" else LABELS_BAD
    return pick(pools.get(domain, pools.get("land", ["风云突变"])))


def wrap_event(kind: str, label: str, detail: str) -> str:
    emoji = "✨" if kind == "good" else "⚡"
    tail = pick(EVENT_TAILS)
    msg = f"{emoji} {label}：{detail}"
    if tail:
        msg += f" {tail}"
    return msg


def wrap_naval(kind: str, label: str, detail: str) -> str:
    emoji = "⚓" if kind == "good" else "🌊" if kind == "bad" else "🐚"
    return f"{emoji} {label} · {detail}"


def fill(template: str, **kwargs: Any) -> str:
    for k, v in kwargs.items():
        template = template.replace("{" + k + "}", str(v))
    return template
