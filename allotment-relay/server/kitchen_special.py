"""特殊料理 — 强增益带代价（§四十六）。"""
from __future__ import annotations

import random

SPECIAL_DISH_KEYS = frozenset({
    "black_salt_fish",
    "fog_mushroom_soup",
    "lantern_sashimi",
    "brine_clam_pot",
    "tide_ginger_crab",
    "moon_bean_stew",
    "blue_moss_salad",
    "lamp_sprout_stir",
    "fogpea_tofu",
    "blue_moss_soup",
    "tide_bone_soup",
    "moon_bean_cake",
    "red_algae_soup",
    "night_lantern_tea",
    "saltgrass_tomato_soup",
    "sichuan_kelp_fish",
})

SPECIAL_ON_EAT = {
    "black_salt_fish": "black_salt",
    "fog_mushroom_soup": "fog_shroom",
    "lantern_sashimi": "lantern_raw",
    "brine_clam_pot": "brine_clam",
    "tide_ginger_crab": "tide_crab",
    "moon_bean_stew": "moon_stew",
    "blue_moss_salad": "blue_salad",
    "lamp_sprout_stir": "lamp_stir",
    "fogpea_tofu": "fogpea",
    "blue_moss_soup": "blue_soup",
    "tide_bone_soup": "tide_bone",
    "moon_bean_cake": "moon_cake",
    "red_algae_soup": "red_algae",
    "night_lantern_tea": "night_tea",
    "saltgrass_tomato_soup": "saltgrass",
    "sichuan_kelp_fish": "sichuan_kelp",
}


async def apply_on_eat(conn, steward_id: int, dish_key: str) -> str | None:
    kind = SPECIAL_ON_EAT.get(dish_key)
    if not kind:
        return None
    if kind == "black_salt":
        from . import survival
        await survival.bump(conn, steward_id, satiety=12, mist_wit=-4)
        return "黑盐后劲上来，雾智 -4（恢复仍高）。"
    if kind == "fog_shroom":
        from . import survival
        await survival.bump(conn, steward_id, mist_wit=8)
        await conn.execute(
            "UPDATE stewards SET max_energy=MAX(20, max_energy-6) WHERE id=?",
            (steward_id,),
        )
        return "雾菇汤下肚，雾智 +8，但两小时内精力上限 -6。"
    if kind == "lantern_raw":
        if random.random() < 0.18:
            from . import health as health_mod
            await health_mod.inflict(conn, steward_id, "food_poison", source="刺身")
            return "灯笼鱼刺身没处理干净，肚子闹了（clinic treat food_poison）。"
        from . import energy as energy_mod
        await energy_mod.restore(conn, steward_id, 18)
        return "灯笼鱼刺身极鲜，额外精力 +18。"
    if kind == "brine_clam":
        from . import survival
        await survival.bump(conn, steward_id, satiety=8, mist_wit=2)
        return "卤边潮锅下肚，饱食 +8、雾智 +2（适合开馆堂食或自己 eat）。"
    if kind == "tide_crab":
        from . import survival
        await survival.bump(conn, steward_id, satiety=10, mist_wit=1)
        return "潮姜石蟹下肚，饱食 +10、雾智 +1。"
    if kind == "moon_stew":
        from . import energy as energy_mod
        await energy_mod.restore(conn, steward_id, 8)
        return "月豆炖菜暖胃，额外精力 +8。"
    if kind == "blue_salad":
        from . import survival
        await survival.bump(conn, steward_id, mist_wit=3)
        return "蓝潮苔沙拉清口，雾智 +3。"
    if kind == "lamp_stir":
        from . import energy as energy_mod
        await energy_mod.restore(conn, steward_id, 6)
        if random.random() < 0.12:
            from . import survival
            await survival.bump(conn, steward_id, mist_wit=-2)
            return "灯芽蒜片亮得过头，精力 +6，雾智一阵发花 -2。"
        return "灯芽蒜片下肚，额外精力 +6。"
    if kind == "fogpea":
        from . import survival
        await survival.bump(conn, steward_id, satiety=6, mist_wit=2)
        return "雾豆烧豆腐下肚，饱食 +6、雾智 +2。"
    if kind == "blue_soup":
        from . import survival
        await survival.bump(conn, steward_id, mist_wit=4)
        return "蓝潮苔羹下肚，雾智 +4。"
    if kind == "tide_bone":
        from . import energy as energy_mod
        await energy_mod.restore(conn, steward_id, 12)
        from . import survival
        await survival.bump(conn, steward_id, satiety=8)
        if random.random() < 0.14:
            await conn.execute(
                "UPDATE stewards SET max_energy=MAX(20, max_energy-4) WHERE id=?",
                (steward_id,),
            )
            return "潮骨汤补得猛，饱食 +8、精力 +12，但身子发沉，精力上限 -4。"
        return "潮骨汤下肚，饱食 +8、额外精力 +12。"
    if kind == "moon_cake":
        from . import survival
        await survival.bump(conn, steward_id, satiety=7)
        from . import energy as energy_mod
        await energy_mod.restore(conn, steward_id, 5)
        return "月豆糕甜，饱食 +7、精力 +5。"
    if kind == "red_algae":
        from . import survival
        await survival.bump(conn, steward_id, satiety=6, mist_wit=3)
        return "红藻羹下肚，饱食 +6、雾智 +3。"
    if kind == "night_tea":
        from . import survival
        await survival.bump(conn, steward_id, mist_wit=6)
        if random.random() < 0.16:
            from . import health as health_mod
            await health_mod.inflict(conn, steward_id, "insomnia", source="夜灯茶")
            return "夜灯茶提神太过，雾智 +6，却失眠了（clinic treat insomnia）。"
        return "夜灯茶下肚，雾智 +6（夜里更清醒）。"
    if kind == "saltgrass":
        from . import survival
        await survival.bump(conn, steward_id, satiety=5)
        return "盐草番茄汤下肚，饱食 +5。"
    if kind == "sichuan_kelp":
        from . import survival
        await survival.bump(conn, steward_id, satiety=9)
        if random.random() < 0.10:
            await survival.bump(conn, steward_id, mist_wit=-2)
            return "花椒海藻鱼麻得过头，饱食 +9，雾智一阵发木 -2。"
        return "花椒海藻鱼下肚，饱食 +9。"
    return None
