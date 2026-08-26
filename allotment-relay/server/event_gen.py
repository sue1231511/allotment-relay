"""Procedural random events — composed at runtime with flavor.py voice."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

from . import world
from .catalog import FORAGE_LOOT, ITEM_NAMES, RANDOM_LOOT, fish_keys_for_tide, fish_keys_for_zones
from . import config, flavor
from .config import NAVAL_ENCOUNTER_CHANCE


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

SCRUMP_TRIGGERS = {"tend", "gather", "forage", "guild"}

DOMAIN_AILMENTS = {
    "land": ["sprain", "cut", "backache", "allergy", "blister"],
    "sea": ["cold", "jelly_sting", "shell_scratch"],
    "pen": ["cut", "crab_pinch", "blister"],
    "voyage": ["cold", "food_poison", "backache"],
    "guild": ["blister", "sprain"],
    "hearth": ["food_poison"],
}


def _pick_ailment(domain: str, trigger: str, weather: str) -> str | None:
    from .health import TRIGGER_AILMENTS

    pool = list(DOMAIN_AILMENTS.get(domain, []))
    extra = TRIGGER_AILMENTS.get(trigger, [])
    for k in extra:
        if k not in pool:
            pool.append(k)
    if weather == "misty" and "cold" not in pool:
        pool.append("cold")
    if weather == "gale" and "sprain" not in pool:
        pool.append("sprain")
    if not pool:
        return None
    return random.choice(pool)


@dataclass
class GeneratedEvent:
    kind: str
    label: str
    detail: str
    repair_tickets: int = 0
    repair_item: str | None = None
    repair_qty: int = 0
    effects: list[str] = field(default_factory=list)


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
        "scrump": (4, 10),
    }
    return ranges.get(domain, (4, 10))


def generate_event(
    trigger: str,
    steward: dict[str, Any],
    *,
    good: bool,
    pen: dict[str, Any] | None = None,
    voyage: bool = False,
    allow_scrump: bool = False,
) -> GeneratedEvent | None:
    domain = TRIGGER_DOMAIN.get(trigger)
    if not domain:
        return None

    # 逾篱摘取 — 纯随机事件，不再靠手动指令
    if allow_scrump and trigger in SCRUMP_TRIGGERS and not good and random.random() < config.SCRUMP_EVENT_CHANCE:
        sub = "scrump_victim" if random.random() < 0.55 else "scrump_attempt"
        return GeneratedEvent(
            kind="bad",
            label=flavor.event_label("scrump", "bad"),
            detail="……",  # filled by apply
            repair_tickets=random.randint(4, 8) if sub == "scrump_attempt" else 0,
            effects=[sub],
        )

    kind = "good" if good else "bad"
    label = flavor.event_label(domain, kind)
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
        if domain == "land" and roll < 0.32:
            effects.append("plot_untend")
            detail_parts.append(flavor.fill(
                flavor.pick(flavor.LAND_BAD),
                who=flavor.pick(flavor.WHO_LAND),
                slot=slot,
                mess=flavor.pick(flavor.MESS_LAND),
            ))
        elif domain == "land" and roll < 0.48:
            effects.append("plot_wreck")
            detail_parts.append(flavor.fill(
                flavor.pick(flavor.LAND_WRECK),
                slot=slot,
                mess=flavor.pick(flavor.MESS_LAND),
            ))
        elif domain == "land" and roll < 0.62:
            effects.append("plot_delay")
            detail_parts.append(flavor.fill(
                flavor.pick(flavor.LAND_DELAY_DETAIL),
                slot=slot,
                reason=flavor.pick(flavor.LAND_DELAY),
            ))
        elif domain == "land" and roll < 0.70:
            effects.append("plot_delay")
            detail_parts.append(flavor.fill(
                flavor.pick(flavor.LAND_SCARECROW_FALL),
                slot=slot,
            ))
        elif domain == "land":
            effects.append("steal_item")
            detail_parts.append(flavor.fill(
                flavor.pick(flavor.LAND_STEAL),
                who=flavor.pick(flavor.WHO_LAND),
            ))

        elif domain == "sea" and roll < 0.5:
            effects.append("net_cost")
            extra = random.randint(4, 10)
            effects.append(f"ticket_fine:{extra}")
            detail_parts.append(flavor.fill(
                flavor.pick(flavor.SEA_BAD),
                mess=flavor.pick(flavor.MESS_SEA),
                n=extra,
            ))
        elif domain == "sea":
            effects.append("steal_item")
            detail_parts.append(flavor.fill(
                flavor.pick(flavor.SEA_STEAL),
                mess=flavor.pick(flavor.MESS_SEA),
            ))

        elif domain == "pen" and pen and roll < 0.5:
            effects.append("pen_unfeed")
            detail_parts.append(flavor.fill(
                flavor.pick(flavor.PEN_BAD),
                slot=slot,
                mess=flavor.pick(flavor.MESS_PEN),
            ))
        elif domain == "pen" and pen:
            effects.append("pen_wreck")
            detail_parts.append(flavor.fill(
                flavor.pick(flavor.PEN_WRECK_DETAIL),
                slot=slot,
                reason=flavor.pick(flavor.PEN_WRECK),
            ))

        elif domain == "voyage" and roll < 0.4:
            effects.append("boat_damage")
            detail_parts.append(flavor.fill(
                flavor.pick(flavor.VOYAGE_BAD),
                mess=flavor.pick(flavor.VOYAGE_MESS),
            ))
        elif domain == "voyage" and voyage and roll < 0.65:
            delay = random.randint(300, 900)
            effects.append(f"voyage_delay:{delay}")
            detail_parts.append(flavor.fill(
                flavor.pick(flavor.VOYAGE_DELAY_DETAIL),
                reason=flavor.pick(flavor.VOYAGE_DELAY),
                mins=delay // 60,
            ))
        elif domain == "voyage":
            effects.append("boat_damage")
            detail_parts.append(flavor.fill(
                flavor.pick(flavor.VOYAGE_HARD_NO),
                mess=flavor.pick(flavor.VOYAGE_MESS),
            ))

        elif domain == "guild":
            fine = random.randint(5, 12)
            effects.append(f"ticket_fine:{fine}")
            detail_parts.append(flavor.fill(
                flavor.pick(flavor.GUILD_FINE_DETAIL),
                reason=flavor.pick(flavor.GUILD_FINE_REASON),
                fine=fine,
            ))

        elif domain == "hearth" and steward.get("mascot_name") and roll < 0.5:
            delta = -random.randint(12, 22)
            effects.append(f"mascot_spirit:{delta}")
            detail_parts.append(flavor.fill(
                flavor.pick(flavor.HEARTH_MASCOT_DETAIL),
                mess=flavor.pick(flavor.HEARTH_MASCOT_BAD),
                name=steward["mascot_name"],
                delta=delta,
            ))
        elif domain == "hearth":
            fine = random.randint(3, 7)
            effects.append(f"ticket_fine:{fine}")
            detail_parts.append(flavor.fill(
                flavor.pick(flavor.HEARTH_BAD_DETAIL),
                mess=flavor.pick(flavor.HEARTH_BAD),
                fine=fine,
            ))

        else:
            fine = random.randint(*_ticket_range(domain, kind))
            effects.append(f"ticket_fine:{fine}")
            detail_parts.append(flavor.fill(
                flavor.pick(flavor.GENERIC_FINE),
                fine=fine,
            ))

        lo, hi = _ticket_range(domain, kind)
        repair_tickets = random.randint(lo, hi)
        if domain == "land" and random.random() < 0.35:
            repair_item, repair_qty = "compost", 1
        if domain == "pen" and random.random() < 0.4:
            repair_item, repair_qty = "compost", random.randint(1, 2)

    else:
        roll = random.random()
        if roll < 0.26:
            bonus = random.randint(*_ticket_range(domain, "good"))
            effects.append(f"ticket_bonus:{bonus}")
            detail_parts.append(flavor.fill(flavor.pick(flavor.GOOD_TICKETS), n=bonus))
        elif roll < 0.48 and domain in {"sea", "voyage", "pen"}:
            zones = {"near", "shore"} if domain == "pen" else {"near", "far", "deep", "shore"}
            if domain == "voyage":
                zones = {"far", "deep"}
            fk = random.choice(fish_keys_for_zones(zones) or ["herring"])
            qty = random.randint(1, 2)
            item = ITEM_NAMES.get(f"fish_{fk}", fk)
            effects.append(f"loot:fish_{fk}:{qty}")
            detail_parts.append(flavor.fill(flavor.pick(flavor.GOOD_FISH), item=f"{item} x{qty}"))
        elif roll < 0.62:
            item, qty = random.choice(RANDOM_LOOT)
            iname = ITEM_NAMES.get(item, item)
            effects.append(f"loot:{item}:{qty}")
            detail_parts.append(flavor.fill(flavor.pick(flavor.GOOD_LOOT), item=f"{iname} x{qty}"))
        elif roll < 0.74 and domain in {"land", "guild", "hearth"}:
            wit = random.randint(4, 10)
            effects.append(f"mist_wit:{wit}")
            detail_parts.append(flavor.fill(flavor.pick(flavor.GOOD_MIST_WIT), n=wit))
        elif roll < 0.82 and domain in {"land", "guild"}:
            stand = random.randint(3, 8)
            effects.append(f"standing:{stand}")
            detail_parts.append(flavor.fill(flavor.pick(flavor.GOOD_STANDING), n=stand))
        elif roll < 0.93 and int(steward.get("health") or 100) < 100:
            # 各域好事件都可能回身体（份地/出海/畜栏/小屋……）
            heal = random.randint(5, 14)
            effects.append(f"health:{heal}")
            detail_parts.append(flavor.fill(flavor.pick(flavor.GOOD_HEALTH), n=heal))
        else:
            bonus = random.randint(6, 14)
            effects.append(f"ticket_bonus:{bonus}")
            detail_parts.append(flavor.fill(
                flavor.pick(flavor.GOOD_WEATHER_DETAIL),
                who=flavor.pick(flavor.GOOD_WEATHER_GIFT),
                n=bonus,
            ))

        if weather == "clear" and random.random() < 0.2:
            item = flavor.pick([x[0] for x in FORAGE_LOOT[:3]])
            effects.append(f"loot:{item}:1")
            detail_parts.append(flavor.fill(
                flavor.pick(flavor.FORAGE_BONUS),
                item=ITEM_NAMES.get(item, item),
            ))
        # 好事件附加：身体未满时偶尔再回一点（各种域都有）
        if (
            int(steward.get("health") or 100) < 100
            and not any(e.startswith("health:") for e in effects)
            and random.random() < 0.16
        ):
            heal = random.randint(3, 8)
            effects.append(f"health:{heal}")
            detail_parts.append(flavor.fill(flavor.pick(flavor.GOOD_HEALTH), n=heal))

    if not detail_parts:
        return None

    if kind == "bad" and random.random() < config.AILMENT_BAD_EVENT_CHANCE:
        picked = _pick_ailment(domain, trigger, weather)
        if picked:
            effects.append(f"ailment:{picked}")

    if weather == "gale" and kind == "bad" and random.random() < 0.3:
        detail_parts.append(flavor.pick(flavor.WEATHER_TAIL_BAD))
    if tide == "flood" and domain == "sea" and kind == "bad" and random.random() < 0.25:
        detail_parts.append(flavor.pick(flavor.TIDE_TAIL_BAD))

    return GeneratedEvent(
        kind=kind,
        label=label,
        detail="，".join(detail_parts),
        repair_tickets=repair_tickets if kind == "bad" else 0,
        repair_item=repair_item,
        repair_qty=repair_qty,
        effects=effects,
    )


@dataclass
class NavalEncounter:
    kind: str
    label: str
    detail: str
    effects: list[str] = field(default_factory=list)


def generate_naval_encounter(
    route: str,
    steward: dict[str, Any],
    *,
    bad_bias: float = 0.0,
) -> NavalEncounter | None:
    chance = NAVAL_ENCOUNTER_CHANCE.get(route, 0.25)
    if random.random() > chance:
        return None

    from . import survival

    bad_weight = 0.42 + bad_bias + survival.naval_bad_bias(steward)
    if world.current_weather() == "gale":
        bad_weight += 0.12
    if world.current_day_phase() == "night":
        bad_weight += 0.08
    if world.current_weather() == "clear":
        bad_weight -= 0.06

    roll = random.random()
    effects: list[str] = []
    label = flavor.event_label("naval", "bad")

    if roll < bad_weight:
        kind = "bad"
        sub = random.random()
        if sub < 0.35:
            fine = random.randint(6, 16)
            effects.append(f"ticket_fine:{fine}")
            detail = flavor.fill(
                flavor.pick(flavor.NAVAL_BAD),
                who=flavor.pick(flavor.NAVAL_WHO),
                n=fine,
                loot="一点舱货",
                mins=random.randint(8, 22),
            )
        elif sub < 0.6:
            effects.append("boat_damage")
            fine = random.randint(4, 10)
            effects.append(f"ticket_fine:{fine}")
            detail = flavor.fill(
                flavor.pick(flavor.NAVAL_BAD_EXTRA),
                who=flavor.pick(flavor.NAVAL_WHO),
            )
        elif sub < 0.82:
            fine = random.randint(5, 12)
            effects.append(f"ticket_fine:{fine}")
            effects.append(f"standing:{-random.randint(3, 7)}")
            detail = flavor.fill(
                flavor.pick(flavor.NAVAL_BAD),
                who="海雾",
                n=fine,
                loot="方向感",
                mins=random.randint(8, 18),
            )
        else:
            effects.append("cargo_loss:1")
            standing = -random.randint(4, 9)
            effects.append(f"standing:{standing}")
            detail = flavor.fill(
                flavor.pick(flavor.NAVAL_BAD_EXTRA),
                who=flavor.pick(flavor.NAVAL_WHO),
                n=abs(standing),
            )
    elif roll < bad_weight + 0.38:
        kind = "good"
        label = flavor.event_label("naval", "good")
        sub = random.random()
        if sub < 0.34:
            bonus = random.randint(8, 18)
            effects.append(f"ticket_bonus:{bonus}")
            detail = flavor.fill(flavor.pick(flavor.NAVAL_GOOD), n=bonus, loot="红包")
        elif sub < 0.60:
            zones = {"near", "far", "deep"} if route != "near" else {"near", "shore"}
            fk = random.choice(fish_keys_for_zones(zones) or ["herring"])
            qty = random.randint(1, 2)
            effects.append(f"loot:fish_{fk}:{qty}")
            iname = ITEM_NAMES.get(f"fish_{fk}", fk)
            detail = flavor.fill(flavor.pick(flavor.NAVAL_GOOD), loot=f"{iname} x{qty}", n=0)
        elif sub < 0.82:
            wit = random.randint(6, 14)
            effects.append(f"mist_wit:{wit}")
            effects.append(f"satiety:{random.randint(3, 8)}")
            detail = flavor.fill(
                flavor.pick(flavor.NAVAL_GOOD),
                loot="热汤",
                n=wit,
            )
        else:
            heal = random.randint(6, 14)
            effects.append(f"health:{heal}")
            detail = flavor.fill(flavor.pick(flavor.GOOD_HEALTH), n=heal)
        # 出海好运偶尔再附带一点气色
        if (
            int(steward.get("health") or 100) < 100
            and not any(e.startswith("health:") for e in effects)
            and random.random() < 0.22
        ):
            extra_heal = random.randint(3, 8)
            effects.append(f"health:{extra_heal}")
            detail = detail + "，" + flavor.fill(flavor.pick(flavor.GOOD_HEALTH), n=extra_heal)
    else:
        kind = "neutral"
        label = flavor.pick(flavor.NAVAL_NEUTRAL_LABEL)
        if random.random() < 0.55:
            fine = random.randint(3, 8)
            fk = random.choice(fish_keys_for_zones({route, "shore"}) or ["herring"])
            effects.append(f"ticket_fine:{fine}")
            effects.append(f"loot:fish_{fk}:1")
            iname = ITEM_NAMES.get(f"fish_{fk}", fk)
            detail = flavor.fill(
                flavor.pick(flavor.NAVAL_NEUTRAL),
                n=fine,
                loot=iname,
            )
        else:
            detail = flavor.pick(flavor.NAVAL_NEUTRAL)

    return NavalEncounter(kind=kind, label=label, detail=detail, effects=effects)


def generate_world_pulse() -> dict[str, Any]:
    effect_types = [
        ("storm_front", "bad", "户外份地得重打理，苗盘：这班我不上了"),
        ("fish_run", "good", "撒网手气上调，渔获更愿意上钩——海偶尔做个人"),
        ("blight_whisper", "bad", "收成偶尔会「蒸发」一点点，别问去哪了"),
        ("loot_surge", "good", "交换台台阶像退潮礼包区，捡到的算你眼神好"),
        ("red_tide", "bad", "渔排和网都不太给面子，今天宜躺"),
        ("calm_sea", "good", "出海报废略降，胆小船长也能装勇敢"),
        ("warm_breeze", "good", "暖风吹过份地，打理时偶尔多捡到一点"),
        ("fog_bank", "bad", "浓雾缠岸，赶海和撒网都容易空欢喜"),
        ("merchant_caravan", "good", "流动商贩路过档口，票子像被风捎来"),
        ("gnat_swarm", "bad", "小虫成团，露天作物得再 tend 一遍"),
    ]
    effect, kind, hint = random.choice(effect_types)

    subjects = {
        "storm_front": ["风暴前沿", "低压槽", "雷暴脊", "黑云压境", "乌云快递"],
        "fish_run": ["渔汛", "银鳞翻浪", "潮线沸腾", "鱼群开派对"],
        "blight_whisper": ["枯病低语", "霉丝蔓延", "叶脉发黄", "蔫菜预警"],
        "loot_surge": ["玻璃潮", "漂物汛", "宝箱潮", "退潮大清仓"],
        "red_tide": ["赤潮", "藻华", "紫水带", "海的颜色不对"],
        "calm_sea": ["平流", "镜海", "无风带", "海面躺平"],
        "warm_breeze": ["暖风带", "阳面回温", "软风过境", "晒被天"],
        "fog_bank": ["雾墙", "贴岸浓雾", "能见度告急", "海雾结账"],
        "merchant_caravan": ["流动商贩", "驮货驴队", "档口巡游", "票子顺风车"],
        "gnat_swarm": ["小虫汛", "蚜虫云", "飞虫编队", "嗡嗡编队"],
        "weekly_tide": ["周潮", "浅潮", "灌仓潮", "黑潮"],
    }
    verbs = ["掠过", "笼罩", "扫过", "渗入", "降临在", "打卡"]
    label = flavor.pick(subjects.get(effect, ["异象"]))
    text = f"{label}{flavor.pick(verbs)}联盟——{hint}"
    fish_focus = None
    if effect == "fish_run":
        fish_focus = random.choice(fish_keys_for_tide(world.current_tide()) or ["herring"])
        text += f"（{ITEM_NAMES.get(f'fish_{fish_focus}', fish_focus)} 特别多）"

    from . import lore as lore_mod
    detail = lore_mod.pulse_season_detail(effect) or hint

    return {
        "effect": effect,
        "kind": kind,
        "label": label,
        "text": text,
        "detail": detail,
        "fish_focus": fish_focus,
    }
