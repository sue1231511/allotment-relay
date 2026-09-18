"""特殊料理 — 强增益带代价（§四十六）。"""
from __future__ import annotations

import random
from typing import Any

SPECIAL_DISH_KEYS = frozenset({
    "black_salt_fish",
    "fog_mushroom_soup",
    "lantern_sashimi",
})

SPECIAL_ON_EAT = {
    "black_salt_fish": "black_salt",
    "fog_mushroom_soup": "fog_shroom",
    "lantern_sashimi": "lantern_raw",
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
    return None
