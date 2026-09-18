"""动物繁殖 — 第二批。"""
from __future__ import annotations

import random

from . import db
from .catalog import LIVESTOCK, MANURE, ITEM_NAMES

BREEDABLE = frozenset({"chicken", "duck", "rabbit", "goat", "pig", "sheep"})
MIN_AGE_SEC = 5 * 86400


async def try_breed(conn, steward: dict, slot: int) -> str:
    cur = await conn.execute(
        "SELECT * FROM barn_animals WHERE steward_id=? AND slot=?",
        (steward["id"], slot),
    )
    row = await cur.fetchone()
    if not row:
        raise ValueError("空栏")
    animal = dict(row)
    species = animal.get("species")
    if not species or species not in BREEDABLE:
        raise ValueError(f"{LIVESTOCK.get(species, {}).get('name', species or '栏')}不支持配种")
    from . import barn_disease as barn_disease_mod
    if barn_disease_mod.animal_ailment_key(animal):
        raise ValueError("病畜不配种，先 visit_ops 兽医 treat")
    if not animal.get("fed"):
        raise ValueError("先 feed 再 breed")
    born = int(animal.get("born_at") or animal.get("stocked_at") or 0)
    if born and db.now() - born < MIN_AGE_SEC:
        raise ValueError("新进栏的畜还没适应，过几天再配种")
    meta = LIVESTOCK[species]
    feed_item = meta.get("feed")
    feed_qty = int(meta.get("feed_qty") or 1)
    if feed_item and not await db.take_item(conn, steward["id"], feed_item, feed_qty):
        if not await db.take_item(conn, steward["id"], "feed_animal", 1):
            raise ValueError("配种要多喂一份饲料")
    if random.random() > 0.38:
        return f"#{slot} {meta['name']} 没配上，饲料白花了（可改天再试）"
    product = meta.get("product")
    if product:
        qty = max(1, int(meta.get("product_qty") or 1))
        await db.add_item(conn, steward["id"], product, qty)
        out = f"#{slot} 配种成了，多得 {ITEM_NAMES.get(product, product)} ×{qty}"
    elif meta.get("manure"):
        m = meta["manure"]
        await db.add_item(conn, steward["id"], m, 2)
        out = f"#{slot} 配种成了，栏里多了 {MANURE[m]['name']} ×2"
    else:
        out = f"#{slot} {meta['name']} 配种成了（记一笔履历）"
    from . import barn_pedigree as pedigree_mod
    await pedigree_mod.log(conn, steward["id"], slot, f"{meta['name']}配种成功")
    await pedigree_mod.next_generation(conn, steward["id"], species)
    return out
