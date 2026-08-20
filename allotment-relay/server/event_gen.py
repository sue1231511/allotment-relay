"""Procedural random events — composed at runtime, not hardcoded incident tables."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from . import config, world
from .catalog import FORAGE_LOOT, ITEM_NAMES, RANDOM_LOOT, fish_keys_for_tide, fish_keys_for_zones


TRIGGER_DOMAIN = {
    "tend": "land",
    "gather": "land",
    "sow": "land",
    "forage": "land",
    "net": "sea",
    "pen_feed": "pen",
    "pen_harvest": "pen",
    "pen_stock": "pen",
    "voyage_depart": "voyage",
    "voyage_return": "voyage",
    "guild": "guild",
    "brew": "hearth",
}

ALL_TRIGGERS = set(TRIGGER_DOMAIN)


@dataclass
class GeneratedEvent:
    kind: str
    label: str
    detail: str
    repair_tickets: int = 0
    repair_item: str | None = None
    repair_qty: int = 0
    effects: list[str] = field(default_factory=list)


def _pick(pool: list[str]) -> str:
    return random.choice(pool)


def _compose_label(domain: str, kind: str) -> str:
    if kind == "good":
        pools = {
            "land": ["边际馈赠", "访客留礼", "意外丰收", "篱笆好运"],
            "sea": ["满网惊喜", "退潮遗宝", "渔汛余泽", "浪尖礼物"],
            "pen": ["池面吉兆", "放养顺遂", "水纹赐福"],
            "voyage": ["顺风归港", "舱满星照", "航道眷顾"],
            "guild": ["档口红包", "巡值嘉奖"],
            "hearth": ["灶台灵光", "香气招财"],
        }
    else:
        pools = {
            "land": ["份地波折", "篱间祸事", "作物劫难", "田间意外"],
            "sea": ["渔网波折", "岸口祸事", "潮汐反噬"],
            "pen": ["渔排险情", "池面祸端", "放养波折"],
            "voyage": ["海上险情", "航道波折", "舱底祸事"],
            "guild": ["巡查风波", "档口罚单"],
            "hearth": ["灶台失手", "烟火意外"],
        }
    return _pick(pools.get(domain, ["风云突变"]))


def _ticket_range(domain: str, kind: str) -> tuple[int, int]:
    if kind == "good":
        return (8, 18)
    ranges = {
        "land": (3, 9),
        "sea": (4, 12),
        "pen": (4, 11),
        "voyage": (5, 14),
        "guild": (6, 12),
        "hearth": (3, 8),
    }
    return ranges.get(domain, (4, 10))


def generate_event(
    trigger: str,
    steward: dict[str, Any],
    *,
    good: bool,
    pen: dict[str, Any] | None = None,
    voyage: bool = False,
) -> GeneratedEvent | None:
    domain = TRIGGER_DOMAIN.get(trigger)
    if not domain:
        return None

    kind = "good" if good else "bad"
    label = _compose_label(domain, kind)
    effects: list[str] = []
    detail_parts: list[str] = []
    repair_tickets = 0
    repair_item: str | None = None
    repair_qty = 0
    slot = str(pen["slot"]) if pen else str(random.randint(1, 3))

    weather = world.current_weather()
    tide = world.current_tide()

    if kind == "bad":
        roll = random.random()
        if domain == "land" and roll < 0.34:
            effects.append("plot_untend")
            detail_parts.append(
                f"{_pick(['蛞蝓', '鼠窜', '寒露', '杂草'])}掠过 #{slot}，得重新打理"
            )
        elif domain == "land" and roll < 0.52:
            effects.append("plot_wreck")
            detail_parts.append(f"{_pick(['阵风', '冰雹', '野狗'])}掀翻了 #{slot} 的育苗盘")
        elif domain == "land" and roll < 0.68:
            effects.append("plot_delay")
            detail_parts.append(f"{_pick(['咸雾', '阴潮', '霜冻'])}打乱 #{slot} 的生长节奏")
        elif domain == "land":
            effects.append("steal_item")
            detail_parts.append(f"{_pick(['鼠患', '潮虫', '窃贼'])}动了你的储备")

        elif domain == "sea" and roll < 0.45:
            effects.append("net_cost")
            extra = random.randint(4, 10)
            effects.append(f"ticket_fine:{extra}")
            detail_parts.append(f"{_pick(['暗礁', '废网', '缠枝'])}挂住了渔网（-{extra} 票）")
        elif domain == "sea":
            effects.append("steal_item")
            detail_parts.append(f"{_pick(['浪头', '贼鸥', '漏袋'])}卷走了些物资")

        elif domain == "pen" and pen and roll < 0.5:
            effects.append("pen_unfeed")
            detail_parts.append(f"{_pick(['藻膜', '浮渣', '油膜'])}封住 #{slot} 号渔排，需再投饵")
        elif domain == "pen" and pen:
            effects.append("pen_wreck")
            detail_parts.append(f"#{slot} 号渔排{_pick(['缺氧', '倒灌', '寒流'])}，鱼苗尽失")

        elif domain == "voyage" and roll < 0.38:
            effects.append("boat_damage")
            detail_parts.append(f"{_pick(['船底渗漏', '舵索断裂', '舱缝进水'])}，须修船再出海")
        elif domain == "voyage" and voyage and roll < 0.62:
            delay = random.randint(300, 900)
            effects.append(f"voyage_delay:{delay}")
            detail_parts.append(f"{_pick(['无风停滞', '迷雾迷航', '逆流顶浪'])}，归港延误 {delay // 60} 分钟")
        elif domain == "voyage":
            effects.append("boat_damage")
            detail_parts.append(f"出航前发现{_pick(['缆绳磨损', '帆眼松动', '舱底暗裂'])}")

        elif domain == "guild":
            fine = random.randint(5, 12)
            effects.append(f"ticket_fine:{fine}")
            detail_parts.append(f"联盟巡查：{_pick(['篱笆松脱', '档口杂乱', '消防桶空'])}，罚 {fine} 票")

        elif domain == "hearth" and steward.get("mascot_name") and roll < 0.5:
            delta = -random.randint(12, 22)
            effects.append(f"mascot_spirit:{delta}")
            detail_parts.append(f"{_pick(['闷雷', '锅崩', '烟呛'])}把吉祥物吓退了士气")
        elif domain == "hearth":
            fine = random.randint(3, 7)
            effects.append(f"ticket_fine:{fine}")
            detail_parts.append(f"灶台{_pick(['糊锅', '溢汤', '熄火'])}，浪费 {fine} 票")

        else:
            fine = random.randint(*_ticket_range(domain, kind))
            effects.append(f"ticket_fine:{fine}")
            detail_parts.append(f"一波{_pick(['小劫', '波折', '意外'])}，损失 {fine} 票")

        lo, hi = _ticket_range(domain, kind)
        repair_tickets = random.randint(lo, hi)
        if domain == "land" and random.random() < 0.35:
            repair_item, repair_qty = "compost", 1
        if domain == "pen" and random.random() < 0.4:
            repair_item, repair_qty = "compost", random.randint(1, 2)

    else:
        roll = random.random()
        if roll < 0.28:
            bonus = random.randint(*_ticket_range(domain, "good"))
            effects.append(f"ticket_bonus:{bonus}")
            detail_parts.append(f"{_pick(['路人', '邻居', '过客', '巡潮员'])}留下 {bonus} 票")
        elif roll < 0.55 and domain in {"sea", "voyage", "pen"}:
            zones = {"near", "shore"} if domain == "pen" else {"near", "far", "deep", "shore"}
            if domain == "voyage":
                zones = {"far", "deep"}
            fk = random.choice(fish_keys_for_zones(zones) or ["herring"])
            qty = random.randint(1, 2)
            effects.append(f"loot:fish_{fk}:{qty}")
            detail_parts.append(f"意外收获 {ITEM_NAMES.get(f'fish_{fk}', fk)} x{qty}")
        elif roll < 0.72:
            item, qty = random.choice(RANDOM_LOOT)
            effects.append(f"loot:{item}:{qty}")
            detail_parts.append(f"捡到 {ITEM_NAMES.get(item, item)} x{qty}")
        else:
            bonus = random.randint(6, 14)
            effects.append(f"ticket_bonus:{bonus}")
            detail_parts.append(f"{_pick(['退潮', '晨雾', '顺风'])}带来 {bonus} 票小确幸")

        if weather == "clear" and random.random() < 0.2:
            item, qty = random.choice(FORAGE_LOOT[:3])[0], 1
            effects.append(f"loot:{item}:{qty}")
            detail_parts.append(f"顺道得 {ITEM_NAMES.get(item, item)}")

    if not detail_parts:
        return None

    if weather == "gale" and kind == "bad" and random.random() < 0.3:
        detail_parts.append("（阵风加剧）")
    if tide == "flood" and domain == "sea" and kind == "bad" and random.random() < 0.25:
        detail_parts.append("（涨潮作祟）")

    return GeneratedEvent(
        kind=kind,
        label=label,
        detail="，".join(detail_parts),
        repair_tickets=repair_tickets if kind == "bad" else 0,
        repair_item=repair_item,
        repair_qty=repair_qty,
        effects=effects,
    )


def generate_world_pulse() -> dict[str, Any]:
    """Random server-wide pulse with procedural label + effect type."""
    effect_types = [
        ("storm_front", "bad", "户外份地需重新打理"),
        ("fish_run", "good", "渔网更容易有收获"),
        ("blight_whisper", "bad", "收成时有小概率折损"),
        ("loot_surge", "good", "交换台台阶上多了漂流物资"),
        ("red_tide", "bad", "渔排与撒网更易出问题"),
        ("calm_sea", "good", "出海报废略降"),
    ]
    effect, kind, hint = random.choice(effect_types)

    subjects = {
        "storm_front": ["风暴前沿", "低压槽", "雷暴脊", "黑云压境"],
        "fish_run": ["渔汛", "鱼群过境", "银鳞翻浪", "潮线沸腾"],
        "blight_whisper": ["枯病低语", "霉丝蔓延", "叶脉发黄"],
        "loot_surge": ["玻璃潮", "漂物汛", "宝箱潮"],
        "red_tide": ["赤潮", "藻华", "紫水带"],
        "calm_sea": ["平流", "镜海", "无风带"],
    }
    verbs = ["掠过", "笼罩", "扫过", "渗入", "降临在"]
    label = _pick(subjects.get(effect, ["异象"]))
    text = f"{label}{_pick(verbs)}联盟，{hint}"
    fish_focus = None
    if effect == "fish_run":
        fish_focus = random.choice(fish_keys_for_tide(world.current_tide()) or list(["herring"]))
        text += f"（{ITEM_NAMES.get(f'fish_{fish_focus}', fish_focus)} 尤多）"

    return {
        "effect": effect,
        "kind": kind,
        "label": label,
        "text": text,
        "fish_focus": fish_focus,
    }
