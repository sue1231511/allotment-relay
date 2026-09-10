"""畜栏疫病 — 气候加权得病、邻栏传染、病死、接触感染人。"""

from __future__ import annotations

import random
from typing import Any

import aiosqlite

from . import db, world
from .catalog import LIVESTOCK

# 牲口病。霍衡治这些；人沾上的走桥桥。
BARN_AILMENTS: dict[str, dict[str, Any]] = {
    "hoof_rot": {
        "name": "蹄瘟",
        "emoji": "🦶",
        "cost": 18,
        "species": frozenset({"sheep", "goat", "cow", "pig"}),
        "human": "hoof_toxin",
        "yield_mult": 0.5,
        "weight": 18,
    },
    "fowl_pox": {
        "name": "羽疹",
        "emoji": "🪶",
        "cost": 12,
        "species": frozenset({"chicken", "duck"}),
        "human": "barn_fever",
        "yield_mult": 0.5,
        "weight": 16,
    },
    "milk_fever": {
        "name": "奶热",
        "emoji": "🌡️",
        "cost": 22,
        "species": frozenset({"cow", "goat"}),
        "human": "barn_fever",
        "yield_mult": 0.35,
        "weight": 12,
    },
    "swine_cough": {
        "name": "猪咳",
        "emoji": "🐽",
        "cost": 16,
        "species": frozenset({"pig"}),
        "human": "barn_fever",
        "yield_mult": 0.5,
        "weight": 12,
    },
    "bee_mite": {
        "name": "螨箱",
        "emoji": "🐝",
        "cost": 14,
        "species": frozenset({"bee"}),
        "human": None,
        "yield_mult": 0.4,
        "weight": 10,
    },
    "mange": {
        "name": "癞癣",
        "emoji": "🩹",
        "cost": 15,
        "species": frozenset({"dog", "rabbit", "sheep"}),
        "human": "barn_fever",
        "yield_mult": 0.65,
        "weight": 14,
    },
    "heat_thirst": {
        "name": "暑渴",
        "emoji": "🥵",
        "cost": 10,
        "species": frozenset(LIVESTOCK),
        "human": None,
        "yield_mult": 0.7,
        "weight": 10,
    },
    "frost_bite": {
        "name": "冻蹄",
        "emoji": "❄️",
        "cost": 14,
        "species": frozenset({"sheep", "goat", "cow", "pig", "rabbit", "dog"}),
        "human": None,
        "yield_mult": 0.7,
        "weight": 10,
    },
    "murrain": {
        "name": "畜瘟",
        "emoji": "☠️",
        "cost": 36,
        "species": frozenset(k for k in LIVESTOCK if k != "bee"),
        "human": "murrain_touch",
        "yield_mult": 0.2,
        "weight": 6,
        "fatal": True,
        "contagious": True,
        "contact": 0.48,
    },
}

BARN_AILMENT_ALIASES = {
    "蹄瘟": "hoof_rot",
    "羽疹": "fowl_pox",
    "奶热": "milk_fever",
    "猪咳": "swine_cough",
    "螨箱": "bee_mite",
    "癞癣": "mange",
    "暑渴": "heat_thirst",
    "冻蹄": "frost_bite",
    "畜瘟": "murrain",
}


def animal_ailment_key(animal: dict | None) -> str:
    if not animal:
        return ""
    key = str(animal.get("ailment") or "").strip()
    return key if key in BARN_AILMENTS else ""


def animal_ailment_label(animal: dict | None) -> str:
    key = animal_ailment_key(animal)
    if not key:
        return ""
    meta = BARN_AILMENTS[key]
    return f"{meta['emoji']}{meta['name']}"


def yield_qty(animal: dict, qty: int) -> int:
    key = animal_ailment_key(animal)
    if not key:
        return max(0, int(qty))
    mult = float(BARN_AILMENTS[key].get("yield_mult") or 1)
    return max(1, int(qty * mult)) if qty else 0


def resolve_barn_ailment(token: str) -> str | None:
    raw = (token or "").strip()
    if not raw:
        return None
    if raw in BARN_AILMENTS:
        return raw
    if raw.lower() in BARN_AILMENTS:
        return raw.lower()
    return BARN_AILMENT_ALIASES.get(raw)


def _climate_weights(climate: str | None) -> dict[str, int]:
    boost: dict[str, int] = {}
    if climate in ("pest_wave", "blossom_tide"):
        boost["fowl_pox"] = 22
        boost["mange"] = 8
    if climate in ("drought", "heatwave"):
        boost["heat_thirst"] = 28
        boost["murrain"] = 10
        boost["milk_fever"] = 8
    if climate == "gale_crop":
        boost["hoof_rot"] = 16
    if climate in ("frost", "snowbound", "north_wind"):
        boost["frost_bite"] = 26
    if climate == "murrain_week":
        boost["murrain"] = 36
        boost["hoof_rot"] = 10
        boost["swine_cough"] = 8
    if climate == "thunderstorm":
        boost["swine_cough"] = 8
        boost["heat_thirst"] = 6
    if climate == "red_tide":
        boost["mange"] = 4
    return boost


def _pick_for_species(species: str, climate: str | None) -> str | None:
    boost = _climate_weights(climate)
    keys: list[str] = []
    weights: list[int] = []
    for key, meta in BARN_AILMENTS.items():
        allowed = meta.get("species") or frozenset()
        if species not in allowed:
            continue
        w = int(meta.get("weight") or 8) + int(boost.get(key) or 0)
        if w <= 0:
            continue
        keys.append(key)
        weights.append(w)
    if not keys:
        return None
    return random.choices(keys, weights=weights, k=1)[0]


def _infect_chance(climate: str | None) -> float:
    chance = 0.08
    if climate in ("murrain_week",):
        chance = 0.28
    elif climate in ("heatwave", "drought"):
        chance = 0.16
    elif climate in ("pest_wave", "blossom_tide"):
        chance = 0.14
    elif climate in ("frost", "snowbound"):
        chance = 0.12
    elif climate in ("gale_crop", "thunderstorm"):
        chance = 0.11
    return chance


def contact_chance(animal_key: str, *, carcass: bool) -> float:
    meta = BARN_AILMENTS.get(animal_key) or {}
    if not meta.get("human"):
        return 0.04 if carcass else 0.0
    base = float(meta.get("contact") or 0.28)
    if carcass:
        return min(0.72, base + 0.18)
    return base * 0.45


async def contact_human(
    conn: aiosqlite.Connection,
    steward_id: int,
    animal_key: str,
    *,
    source: str = "barn",
    force: bool = False,
) -> str | None:
    """摸病畜 / 清病死栏。人的病归桥桥。"""
    meta = BARN_AILMENTS.get(animal_key) or {}
    human_key = meta.get("human")
    if not human_key:
        return None
    if not force and random.random() > contact_chance(animal_key, carcass=source in ("carcass", "barn_die", "disease_death")):
        return None
    from . import health

    return await health.inflict(conn, steward_id, human_key, source=source)


async def apply_ailment(
    conn: aiosqlite.Connection,
    animal_id: int,
    key: str,
) -> None:
    if key not in BARN_AILMENTS:
        return
    await conn.execute(
        "UPDATE barn_animals SET ailment=?, ailment_at=? WHERE id=?",
        (key, db.now(), animal_id),
    )


async def clear_ailment(
    conn: aiosqlite.Connection,
    steward_id: int,
    slot: int,
) -> None:
    await conn.execute(
        "UPDATE barn_animals SET ailment='', ailment_at=0 WHERE steward_id=? AND slot=?",
        (steward_id, slot),
    )


async def list_sick(
    conn: aiosqlite.Connection,
    steward_id: int,
) -> list[dict[str, Any]]:
    conn.row_factory = aiosqlite.Row
    rows = await (
        await conn.execute(
            "SELECT * FROM barn_animals WHERE steward_id=? AND species IS NOT NULL ORDER BY slot",
            (steward_id,),
        )
    ).fetchall()
    sick: list[dict[str, Any]] = []
    for row in rows:
        animal = dict(row)
        key = animal_ailment_key(animal)
        if not key:
            continue
        spec = LIVESTOCK.get(animal.get("species") or "", {})
        meta = BARN_AILMENTS[key]
        sick.append(
            {
                "slot": int(animal["slot"]),
                "species": animal["species"],
                "name": spec.get("name") or animal["species"],
                "emoji": spec.get("emoji") or "·",
                "ailment": key,
                "ailment_name": meta["name"],
                "ailment_emoji": meta["emoji"],
                "cost": int(meta["cost"]),
                "animal": animal,
            }
        )
    return sick


async def tick_barn_disease(
    conn: aiosqlite.Connection,
    steward_id: int,
) -> list[str]:
    """每个游戏日最多滚一次。病死空栏不给肉。"""
    from .barn import CLEAR_SLOT_SQL

    day = db.day_id()
    cur = await conn.execute(
        "SELECT barn_disease_day FROM stewards WHERE id=?",
        (steward_id,),
    )
    row = await cur.fetchone()
    last = 0
    if row:
        last = int(row[0] if not hasattr(row, "keys") else row["barn_disease_day"] or 0)
    if last == day:
        return []
    await conn.execute(
        "UPDATE stewards SET barn_disease_day=? WHERE id=?",
        (day, steward_id),
    )

    conn.row_factory = aiosqlite.Row
    rows = await (
        await conn.execute(
            "SELECT * FROM barn_animals WHERE steward_id=? AND species IS NOT NULL",
            (steward_id,),
        )
    ).fetchall()
    if not rows:
        return []

    climate = world.field_climate_effect()
    notes: list[str] = []
    animals = [dict(r) for r in rows]
    now = db.now()

    # 病死
    still: list[dict[str, Any]] = []
    for animal in animals:
        key = animal_ailment_key(animal)
        if not key:
            still.append(animal)
            continue
        meta = BARN_AILMENTS[key]
        started = int(animal.get("ailment_at") or 0)
        age = now - started if started else 0
        fatal = bool(meta.get("fatal"))
        die = False
        if fatal and age >= 36 * 3600 and random.random() < 0.38:
            die = True
        elif not fatal and age >= 72 * 3600 and random.random() < 0.12:
            die = True
        if not die:
            still.append(animal)
            continue
        spec = LIVESTOCK.get(animal.get("species") or "", {})
        name = spec.get("name") or animal.get("species")
        slot = int(animal["slot"])
        await conn.execute(CLEAR_SLOT_SQL, (steward_id, slot))
        notes.append(f"#{slot} {name}病死了（{meta['name']}），栏空了，没肉")
        ill = await contact_human(conn, steward_id, key, source="disease_death")
        if ill:
            notes.append(ill)
            notes.append("人的病去桥桥诊所，别来蹄角棚")
        await db.add_chronicle(
            "barn_disease",
            f"畜栏病死：#{slot} {name}·{meta['name']}",
            steward_id,
            conn=conn,
        )

    # 邻栏传染（畜瘟优先）
    by_slot = {int(a["slot"]): a for a in still}
    contagious = [
        a for a in still
        if animal_ailment_key(a) and BARN_AILMENTS[animal_ailment_key(a)].get("contagious")
    ]
    for src in contagious:
        src_key = animal_ailment_key(src)
        for nb in (int(src["slot"]) - 1, int(src["slot"]) + 1):
            other = by_slot.get(nb)
            if not other or animal_ailment_key(other):
                continue
            species = other.get("species") or ""
            allowed = BARN_AILMENTS[src_key].get("species") or frozenset()
            if species not in allowed:
                continue
            if random.random() > 0.42:
                continue
            await apply_ailment(conn, int(other["id"]), src_key)
            other["ailment"] = src_key
            spec = LIVESTOCK.get(species, {})
            notes.append(f"#{nb} {spec.get('name', species)}被邻栏传染了{BARN_AILMENTS[src_key]['name']}")

    # 新发病
    chance = _infect_chance(climate)
    for animal in still:
        if animal_ailment_key(animal):
            continue
        if random.random() > chance:
            continue
        species = animal.get("species") or ""
        picked = _pick_for_species(species, climate)
        if not picked:
            continue
        await apply_ailment(conn, int(animal["id"]), picked)
        animal["ailment"] = picked
        spec = LIVESTOCK.get(species, {})
        meta = BARN_AILMENTS[picked]
        notes.append(f"#{animal['slot']} {spec.get('name', species)}得了{meta['emoji']}{meta['name']} — visit_ops 兽医 treat {animal['slot']}")
        await db.add_chronicle(
            "barn_disease",
            f"畜栏患病：#{animal['slot']} {spec.get('name', species)}·{meta['name']}",
            steward_id,
            conn=conn,
        )
    return notes
