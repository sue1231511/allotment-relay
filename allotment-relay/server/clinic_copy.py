"""桥桥诊所 — 剧情台词、药品货架、窗台斑鸠（设计稿落地）。"""

from __future__ import annotations

import random
from typing import Any

# ── 进门氛围 ──────────────────────────────────────────────

ATMOSPHERE = [
    "诊所里很安静，药柜上的瓶瓶罐罐排得整整齐齐。窗台上斑鸠窝边挂着一串干燥花，不知道是装饰还是药材。",
    "阳光从半开的窗户照进来，斑鸠的影子投在地上圆滚滚的。柜台上放着一杯没喝完的茶。",
    "门上的铃铛响了一下，斑鸠被吓得抖了抖毛。药柜旁贴着手写的价目表，字迹工整。",
]

GREETINGS = [
    "桥桥大夫：「哪儿不舒服？站那儿别动我看看。」",
    "桥桥大夫：「又是你啊。坐。」",
    "桥桥大夫：「来了？自己拿号——开玩笑的，就你一个。说吧。」",
    "桥桥大夫：「别紧张，我又不吃人。……虽然收费是有点贵。」",
    "桥桥大夫：「进来把门带上。风吹进来咕咕斑鸠不高兴。」",
    "桥桥大夫：「你来得正好，咕咕斑鸠刚才对着门口叫了半天，我还以为它在预言什么。原来是你要来。」",
    "桥桥大夫：「看你这个走路姿势……又作了对吧。坐下说。」",
    "桥桥大夫：「欢迎光临——不是，这是诊所，不该说欢迎光临。你怎么了？」",
    "桥桥大夫：「门口那个价目表看过了吗？看过了就别还价。」",
    "桥桥大夫：「今天第几个了……算了不数了。你说你的。」",
]

DISCOUNT_HINTS = [
    "桥桥大夫嘀咕：「今天还行，没什么烦心事。看在这个份上给你便宜点。」",
    "桥桥大夫：「你运气好，我刚吃完东西心情不错。九折，别得寸进尺。」",
    "桥桥大夫：「窗台那只咕咕斑鸠今天没拉屎在我药材上，所以你享福了。打折。」",
    "桥桥大夫：「外头天气不错，咕咕斑鸠也没闹，算你赶上好时候了。」",
    "桥桥大夫：「今天开门到现在没人来添堵。你要是乖乖看完病走人，给你折扣。」",
]

NIGHT_LINES = [
    "桥桥大夫：「……几点了。进来。」",
    "桥桥大夫：「大半夜的不睡觉来看病，怎么，白天不够你作的？」",
    "桥桥大夫：「这个点只有两种人会来——喝多了的和打输了的。你是哪种？」",
    "桥桥大夫：「咕咕斑鸠都睡了，你比鸟还能熬。」",
    "桥桥大夫：「再晚来一步我就锁门了。」",
    "桥桥大夫：「凌晨看诊加收五块。嫌贵回去躺着等天亮。」",
]

CHAT_LINES = [
    "桥桥大夫擦着药柜：「别闲聊，有病治病，没病别占号。」",
    "桥桥大夫：「咕咕斑鸠比你们好伺候。它至少不还价。」",
    "桥桥大夫：「票不到位，药不到位。诊所不搞慈善——这话我说腻了，但还得说。」",
    "桥桥大夫：「你要是闲得慌，去种地去。别在我这儿晃。」",
    "桥桥大夫：「窗台上那窝别碰。碰坏了你赔不起。」",
]

# ── 窗台斑鸠（每日最多 1 次）──────────────────────────────

DOVE_EVENTS: list[dict[str, Any]] = [
    {
        "id": "nap",
        "text": "窗台上的斑鸠把头埋进翅膀里，圆成一团灰扑扑的毛球，呼吸平稳。",
        "mood": 0,
    },
    {
        "id": "hello",
        "text": "你走进诊所的时候，窗台上的斑鸠转过头看了你一眼，咕咕叫了两声，像是在打招呼。",
        "mood": 1,
    },
    {
        "id": "nest",
        "text": "斑鸠嘴里叼着一小截干草飞回窝里，正忙着给自己加被子。你路过的时候它警惕地蹲低了身子，过了一会儿又放松了。",
        "mood": 0,
    },
    {
        "id": "sun",
        "text": "午后阳光正好，斑鸠展开一边翅膀摊在窗台上，整只鸟瘫成一块饼。看到你来了也没动，只翻了翻眼皮。",
        "mood": 1,
    },
    {
        "id": "beg",
        "text": "斑鸠从窝里探出头，对你咕咕咕叫个不停。它盯着你的背包，好像闻到了什么粮食的味道。",
        "mood": 0,
        "feed_item": "crop_fogpea",
        "feed_favor": 2,
    },
]

# ── 药品货架（可 buy / use；价目与 treat 对齐）────────────

CLINIC_MEDICINES: dict[str, dict[str, Any]] = {
    "med_sober": {
        "name": "醒酒药", "emoji": "💊", "price": 28, "ailment": "hangover",
        "aliases": ["醒酒药", "解酒药"],
    },
    "med_sprain": {
        "name": "消炎镇痛膏药", "emoji": "🩹", "price": 28, "ailment": "sprain",
        "aliases": ["膏药", "消炎镇痛膏药", "扭伤膏药"],
    },
    "med_bandage": {
        "name": "创可贴", "emoji": "🩹", "price": 16, "ailment": "infection",
        "aliases": ["创可贴", "bandage"],
        "hint": "生肉感染辅助——仍要走疗程，用贴可少等一半间隔",
        "infection_wait_halve": True,
    },
    "med_bloodclear": {
        "name": "净血针剂", "emoji": "💉", "price": 42, "ailment": "infection",
        "aliases": ["净血针剂", "针剂"],
        "hint": "生肉感染一针压一档（不能跳疗程间隔）",
    },
    "med_rockcough": {
        "name": "咳嗽糖浆", "emoji": "🍯", "price": 28, "ailment": "rock_dust",
        "aliases": ["咳嗽糖浆", "糖浆"],
    },
    "med_saltphlegm": {
        "name": "化痰散", "emoji": "🌿", "price": 24, "ailment": "wreck_cough",
        "aliases": ["化痰散"],
    },
    "med_cold": {
        "name": "感冒药", "emoji": "🤧", "price": 26, "ailment": "cold",
        "aliases": ["感冒药"],
    },
    "med_vitamin": {
        "name": "多维元素片", "emoji": "💊", "price": 16, "ailment": "malnutrition",
        "aliases": ["多维元素片", "维生素片"],
    },
    "med_hexincense": {
        "name": "祛咒香", "emoji": "🪔", "price": 48, "ailment": "legfish_hex",
        "aliases": ["祛咒香", "祛咒"],
    },
    # 无病回身体：贵。不是治病，是刮口袋里的票换气色。
    "med_tonic": {
        "name": "回春汤", "emoji": "🍵", "price": 110, "heal": 18,
        "aliases": ["回春汤", "tonic"],
        "hint": "无病可服，身体 +18；不治病症。贵是故意的",
    },
    "med_tonic_strong": {
        "name": "大补丸", "emoji": "🧧", "price": 280, "heal": 40,
        "aliases": ["大补丸", "大补", "strong_tonic"],
        "hint": "无病可服，身体 +40；不治病症。口袋鼓才配喝",
    },
}

TREAT_LINES: dict[str, list[str]] = {
    "hangover": [
        "醒酒药，一副。下次少喝点——你听得进去的话就不会来找我了。",
        "酒吧开心了？身体替你扛着呢。把药喝了，苦的。",
        "头还疼吗？药效半小时。下回喝之前想想今天这趟跑得值不值。",
    ],
    "sprain": [
        "别乱动。我先按一下看看哪里……这儿？忍着。",
        "膏药贴上去了。明天别再跑去滑那个破礁石，它不会长腿跑掉的。",
        "贴了膏药就安分点，不要贴完出去又折腾。",
    ],
    "infection": [
        "又吃生肉了？你看看你，连兔子都知道找草吃，你连兔子都不如。手伸出来，打针。",
        "生肉生肉生肉，你是没长灶台还是懒得开火？针进去了，别动。",
        "三十多块起。贵吧？下次记得开火。这钱本来能买好几份菜了。",
    ],
    "rock_dust": [
        "矿区待多久了？张嘴，咳两声我听听。……行了，喝糖浆。",
        "挖矿的都这样，觉得自己铁肺。嗓子废了再来找我就不是这个价了。",
        "糖浆给你，甜的，唯一温柔的一次。下回带个口罩行不行？",
    ],
    "wreck_cough": [
        "海边蹲太久了。化痰散拿好，冲水喝，别干吞。",
        "这东西味道不好，但管用。忍两天就通了。",
    ],
    "cold": [
        "风暴天还往外跑，你当自己防水的？药拿着，回去裹被子。",
        "这个要按时吃。别吃了一顿觉得好了就停——停了复发我双倍收费。",
    ],
    "malnutrition": [
        "又光啃水果过日子？你这不叫养生叫糟蹋。维生素片给你。",
        "求你了，去吃顿正经饭。多维元素片只是应急的，你不能靠这个活。",
    ],
    "legfish_hex": [
        "……你碰了那东西？等着。（从柜子深处翻出一捆干草点燃）别问，配合就行。",
        "祛咒香点上了。坐着别说话。我说好了才能动。——好了。以后离那鱼远点。",
        "三十二块？早涨了。你要是再馋嘴碰那东西，下次更贵。",
    ],
    "ring_shock": [
        "又来了。赢了还是输了？——算了别说了，输了的脸就是你这样的。躺好别动。",
        "你们在底下打得挺开心啊？骨头没断算你命硬。下回碎了我可接不回去。",
        "这块淤青挺好看的，要不要留着当纹身？不要？那忍着。",
        "跌打酒上了，烧的那下子你忍。——叫什么叫，这才哪到哪。",
    ],
    "pit_trauma": [
        "我是大夫不是收尸的，麻烦下次抬上来之前先确认人还有气。",
        "重创不便宜，嫌贵？你去问问底下那些打你的人报不报销。",
        "能不能别每次都搞到这个程度。票不要钱的？我的药材不要钱的？你的命不要钱的？——行了趴好。",
        "我建议你换个爱好。种地挺好的，又晒太阳又不挨揍。",
        "你再来一次我就在门口贴你照片，注明'此人请先收全款再治疗'。",
    ],
}

TONIC_LINES = [
    "桥桥大夫：「没病也要调？行啊，票到位就给你吊一瓶。」",
    "桥桥大夫：「气色差就说气色差。别装病——调理价目表在那儿，自己挑。」",
    "桥桥大夫：「有钱人的爱好：花钱买睡得着。躺好，别动针。」",
    "桥桥大夫：「这汤贵是故意的。口袋鼓才配喝。」",
]

TONIC_DONE_LINES = [
    "针推完了。腰背松一点了吧？票我收下了。",
    "调理做完。别指望一次变潮汐本尊——下次还想回气色，再带票来。",
    "好了。身体回了一截。有病还是先 treat，调理不治病。",
]

_MED_BY_ALIAS: dict[str, str] = {}
_TONIC_BY_ALIAS: dict[str, str] = {}


def _build_med_aliases() -> None:
    if _MED_BY_ALIAS:
        return
    for key, meta in CLINIC_MEDICINES.items():
        _MED_BY_ALIAS[key] = key
        _MED_BY_ALIAS[meta["name"]] = key
        for alias in meta.get("aliases", ()):
            _MED_BY_ALIAS[alias] = key


def _build_tonic_aliases() -> None:
    if _TONIC_BY_ALIAS:
        return
    from . import config

    for key, meta in config.CLINIC_TONIC_TIERS.items():
        _TONIC_BY_ALIAS[key] = key
        _TONIC_BY_ALIAS[meta["label"]] = key
        _TONIC_BY_ALIAS[meta["label"].replace("调理", "")] = key
    # 常见英文 / 口语
    _TONIC_BY_ALIAS.update({
        "light": "小", "small": "小", "s": "小",
        "mid": "中", "medium": "中", "m": "中",
        "full": "大", "strong": "大", "l": "大", "大补": "大",
        "rest": "中",  # 裸写 rest 默认中档
    })


def resolve_medicine(token: str) -> str | None:
    _build_med_aliases()
    raw = (token or "").strip()
    if raw in CLINIC_MEDICINES:
        return raw
    return _MED_BY_ALIAS.get(raw) or _MED_BY_ALIAS.get(raw.lower())


def resolve_tonic_tier(token: str) -> str | None:
    """clinic 调理 小|中|大 → tier key；空串返回 None（由调用方展示价目）。"""
    _build_tonic_aliases()
    raw = (token or "").strip()
    if not raw:
        return None
    if raw in _TONIC_BY_ALIAS:
        return _TONIC_BY_ALIAS[raw]
    low = raw.lower()
    return _TONIC_BY_ALIAS.get(low)


def medicine_is_tonic(meta: dict[str, Any]) -> bool:
    """回春汤 / 大补丸：无病可服，只回身体，不治病症。"""
    return int(meta.get("heal") or 0) > 0 and not meta.get("ailment")


def register_medicine_items() -> None:
    from .catalog import ITEM_NAMES, ITEM_PRICES

    for key, meta in CLINIC_MEDICINES.items():
        label = f"{meta['emoji']}{meta['name']}"
        ITEM_NAMES[key] = label
        ITEM_PRICES[key] = int(meta["price"])


def pick_treat_line(ailment_key: str) -> str:
    pool = TREAT_LINES.get(ailment_key)
    if not pool:
        return ""
    return f"桥桥大夫：「{random.choice(pool)}」"


def pick_tonic_line() -> str:
    return random.choice(TONIC_LINES)


def pick_tonic_done() -> str:
    return f"桥桥大夫：「{random.choice(TONIC_DONE_LINES)}」"


def pick_atmosphere() -> str:
    return random.choice(ATMOSPHERE)


def pick_greeting() -> str:
    return random.choice(GREETINGS)


def pick_chat() -> str:
    return random.choice(CHAT_LINES)


def pick_night() -> str:
    return random.choice(NIGHT_LINES)


def pick_discount_hint() -> str:
    return random.choice(DISCOUNT_HINTS)


def pick_dove_event() -> dict[str, Any]:
    return random.choice(DOVE_EVENTS)
