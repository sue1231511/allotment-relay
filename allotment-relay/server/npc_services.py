"""NPC 收费服务全表（方案 §五十五）。

已有入口的只指路；缺的在这里落地：磨刀、鱼处理、动物清洁、家具翻新、家具搬运。
"""
from __future__ import annotations

from typing import Any

SERVICES: dict[str, dict[str, Any]] = {
    "boat_repair": {
        "name": "修船",
        "cost": 0,
        "via": "港口看出海栏点修船，或 voyage_ops repair",
        "aliases": ("修船", "船修"),
    },
    "hut_repair": {
        "name": "修屋",
        "cost": 0,
        "via": "小屋杂务点请匠，或 hut_ops 杂务 请匠",
        "aliases": ("修屋", "请匠"),
    },
    "pick_repair": {
        "name": "修镐",
        "cost": 0,
        "via": "盐风崖升镐，或 quarry_ops 升镐",
        "aliases": ("修镐", "镐"),
    },
    "rod_repair": {
        "name": "修钓竿",
        "cost": 0,
        "via": "渔具栏修竿，或 tide_ops gear repair rod",
        "aliases": ("修钓竿", "修竿", "钓竿"),
    },
    "whet": {
        "name": "磨刀",
        "cost": 8,
        "aliases": ("磨刀", "whet", "sharpen"),
        "do": "whet",
    },
    "furnish": {
        "name": "家具翻新",
        "cost": 14,
        "aliases": ("家具翻新", "翻新", "refurbish"),
        "do": "furnish",
    },
    "vet": {
        "name": "兽医",
        "cost": 0,
        "via": "上手页小屋点找兽医，或 visit_ops 霍衡",
        "aliases": ("兽医", "霍衡"),
    },
    "soil_test": {
        "name": "土壤检测",
        "cost": 6,
        "aliases": ("土壤检测", "测土", "soil"),
        "do": "soil",
    },
    "fish_process": {
        "name": "鱼处理",
        "cost": 10,
        "aliases": ("鱼处理", "处理鱼", "process"),
        "do": "fish",
    },
    "boat_name": {
        "name": "船命名",
        "cost": 0,
        "via": "voyage_ops 履历；改名走船主自己记，不另开收费窗",
        "aliases": ("船命名", "船名"),
    },
    "gyotaku": {
        "name": "鱼拓制作",
        "cost": 0,
        "via": "岸工坊打鱼拓，或 craft_ops 打 鱼拓",
        "aliases": ("鱼拓", "鱼拓制作"),
    },
    "bouquet": {
        "name": "花束包装",
        "cost": 0,
        "via": "集市花店点默默买花，或 visit_ops 默默 买花",
        "aliases": ("花束", "花束包装"),
    },
    "wedding": {
        "name": "婚礼布置",
        "cost": 0,
        "via": "总览点连理所办宴留影，或 visit_ops 连理所",
        "aliases": ("婚礼布置", "布置"),
    },
    "animal_wash": {
        "name": "动物清洁",
        "cost": 12,
        "aliases": ("动物清洁", "洗畜", "wash"),
        "do": "wash",
    },
    "move_furn": {
        "name": "家具搬运",
        "cost": 9,
        "aliases": ("家具搬运", "搬运", "move"),
        "do": "move",
    },
}

ALIASES: dict[str, str] = {}
for _key, _meta in SERVICES.items():
    ALIASES[_key] = _key
    ALIASES[_meta["name"]] = _key
    for _a in _meta.get("aliases") or ():
        ALIASES[_a] = _key


def resolve(token: str) -> str | None:
    raw = (token or "").strip()
    if not raw:
        return None
    return ALIASES.get(raw) or ALIASES.get(raw.lower())


def catalog_text() -> str:
    lines = ["收费服务（方案点名齐全；已有入口只指路，新开的当场办）："]
    for key, meta in SERVICES.items():
        if meta.get("via"):
            lines.append(f"  {meta['name']} — {meta['via']}")
        else:
            lines.append(
                f"  {meta['name']} {meta['cost']} 票 — visit_ops 服务 {meta['name']}"
            )
    lines.append("例子：visit_ops 服务 · 服务 磨刀 · 服务 鱼处理 鲭鱼 · 服务 动物清洁 1")
    return "\n".join(lines)


async def handle(conn, steward: dict[str, Any], raw: str) -> str:
    parts = (raw or "").strip().split()
    if not parts or parts[0] in ("list", "目录", "catalog", "价目"):
        return catalog_text()
    key = resolve(parts[0])
    if not key:
        return catalog_text()
    meta = SERVICES[key]
    if meta.get("via"):
        return f"{meta['name']}不在这扇窗。{meta['via']}"
    do = meta.get("do")
    sid = steward["id"]
    cost = int(meta["cost"])
    cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (sid,))
    have = int((await cur.fetchone())[0])
    if have < cost:
        raise ValueError(f"{meta['name']}要 {cost} 票，你只有 {have}")

    if do == "whet":
        await conn.execute(
            "UPDATE stewards SET tickets=tickets-? WHERE id=?", (cost, sid)
        )
        from . import light_bad_events as light_mod

        await light_mod.take_flag(conn, sid, "shovel_dull")
        return f"磨刀了（-{cost} 票）。铲刃发钝那次消了；下次赶海不另耗。"

    if do == "furnish":
        await conn.execute(
            "UPDATE stewards SET tickets=tickets-? WHERE id=?", (cost, sid)
        )
        from . import hut_appliances as appl_mod

        note = ""
        if await appl_mod.has_appliance(conn, sid, "fridge"):
            note = await appl_mod.repair(conn, sid, "fridge", tickets=0)
        return f"家具翻新了（-{cost} 票）。{note or '软装擦过了，没有厨电可补。'}"

    if do == "soil":
        await conn.execute(
            "UPDATE stewards SET tickets=tickets-? WHERE id=?", (cost, sid)
        )
        from . import soil as soil_mod

        report = await soil_mod.status_report(conn, sid)
        return f"土壤检测（-{cost} 票）\n{report}"

    if do == "fish":
        from . import db
        from .catalog import SEA_CATCH, item_label, resolve_item_key

        token = parts[1] if len(parts) > 1 else ""
        item = resolve_item_key(token) if token else ""
        if not item or not item.startswith("fish_"):
            raise ValueError("鱼处理要写鱼名。例：服务 鱼处理 鲭鱼")
        species = item[5:]
        if species not in SEA_CATCH:
            raise ValueError("这种鱼处理不了")
        if not await db.take_item(conn, sid, item, 1):
            raise ValueError(f"行囊没有{item_label(item)}")
        await conn.execute(
            "UPDATE stewards SET tickets=tickets-? WHERE id=?", (cost, sid)
        )
        out = "proc_pickled_fish"
        await db.add_item(conn, sid, out, 1)
        return (
            f"把{item_label(item)}腌成了腌鱼（-{cost} 票）。"
            "耐放，可灶上再做，也可卖。"
        )

    if do == "wash":
        slot = 1
        if len(parts) > 1 and parts[1].isdigit():
            slot = int(parts[1])
        cur = await conn.execute(
            "SELECT id, species, ailment FROM barn_animals "
            "WHERE steward_id=? AND slot=? AND species IS NOT NULL",
            (sid, slot),
        )
        row = await cur.fetchone()
        if not row:
            raise ValueError(f"{slot}号栏是空的")
        await conn.execute(
            "UPDATE stewards SET tickets=tickets-? WHERE id=?", (cost, sid)
        )
        if row[2] in ("heat_thirst", "mange"):
            await conn.execute(
                "UPDATE barn_animals SET ailment='', ailment_at=0 WHERE id=?",
                (row[0],),
            )
            return f"{slot}号栏洗过了（-{cost} 票）。暑渴/癞癣退了。"
        return f"{slot}号栏洗过了（-{cost} 票）。身上干净，病还在的仍要找兽医。"

    if do == "move":
        await conn.execute(
            "UPDATE stewards SET tickets=tickets-? WHERE id=?", (cost, sid)
        )
        return f"家具搬过了（-{cost} 票）。槽位没变，只是换了墙边。"

    return catalog_text()
