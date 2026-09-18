"""牲畜性格 — 第一批余量：入栏赋性，影响产出与惊逃。"""
from __future__ import annotations

import random
from typing import Any

from . import db
from .catalog import LIVESTOCK

TEMPERS: dict[str, dict[str, Any]] = {
    "calm": {"name": "温驯", "yield_mult": 1.0, "collect_skip": 0.0, "escape": 0.02},
    "skittish": {"name": "惊躁", "yield_mult": 0.92, "collect_skip": 0.10, "escape": 0.14},
    "greedy": {"name": "贪吃", "yield_mult": 1.15, "collect_skip": 0.0, "escape": 0.04},
    "proud": {"name": "傲气", "yield_mult": 1.05, "collect_skip": 0.06, "escape": 0.05},
    "playful": {"name": "欢腾", "yield_mult": 0.98, "collect_skip": 0.04, "escape": 0.08},
    "guard": {"name": "警觉", "yield_mult": 1.0, "collect_skip": 0.0, "escape": 0.03},
}

SPECIES_POOL: dict[str, tuple[str, ...]] = {
    "rabbit": ("skittish", "playful", "calm"),
    "chicken": ("skittish", "greedy", "calm"),
    "duck": ("skittish", "playful", "calm"),
    "sheep": ("calm", "proud", "skittish"),
    "pig": ("greedy", "playful", "calm"),
    "goat": ("proud", "skittish", "calm"),
    "cow": ("calm", "proud", "greedy"),
    "bee": ("calm",),
    "dog": ("guard", "playful"),
    "turkey": ("proud", "skittish"),
    "goose": ("guard", "proud"),
    "quail": ("skittish", "calm"),
    "alpaca": ("calm", "proud"),
}


def roll_for_species(species: str) -> str:
    meta = LIVESTOCK.get(species) or {}
    fixed = meta.get("temper")
    if fixed and fixed in TEMPERS:
        return str(fixed)
    pool = SPECIES_POOL.get(species) or ("calm", "skittish", "greedy")
    return random.choice(pool)


async def ensure_temper(conn, animal: dict[str, Any]) -> dict[str, Any]:
    t = (animal.get("temper") or "").strip()
    if t and t in TEMPERS:
        return animal
    if not animal.get("species"):
        return animal
    t = roll_for_species(animal["species"])
    await conn.execute(
        "UPDATE barn_animals SET temper=? WHERE id=?",
        (t, animal["id"]),
    )
    animal["temper"] = t
    return animal


def label(animal: dict[str, Any]) -> str:
    key = (animal.get("temper") or "calm").strip()
    return TEMPERS.get(key, TEMPERS["calm"])["name"]


def adjust_yield(animal: dict[str, Any], qty: int) -> int:
    key = (animal.get("temper") or "calm").strip()
    mult = float(TEMPERS.get(key, TEMPERS["calm"]).get("yield_mult") or 1)
    return max(0, int(round(qty * mult)))


def collect_skip_chance(animal: dict[str, Any]) -> float:
    key = (animal.get("temper") or "calm").strip()
    return float(TEMPERS.get(key, TEMPERS["calm"]).get("collect_skip") or 0)


def escape_chance(animal: dict[str, Any]) -> float:
    key = (animal.get("temper") or "calm").strip()
    base = float(TEMPERS.get(key, TEMPERS["calm"]).get("escape") or 0)
    if animal.get("guard"):
        return base * 0.3
    return base


async def backfill_empty(conn, steward_id: int) -> None:
    cur = await conn.execute(
        "SELECT id, species, temper FROM barn_animals WHERE steward_id=? AND species IS NOT NULL",
        (steward_id,),
    )
    for row in await cur.fetchall():
        if (row[2] or "").strip():
            continue
        t = roll_for_species(row[1])
        await conn.execute("UPDATE barn_animals SET temper=? WHERE id=?", (t, row[0]))
