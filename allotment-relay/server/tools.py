"""工具 — 锄头/铲子/渔网购买与查询。"""

from __future__ import annotations

import aiosqlite

from . import db, flavor
from .catalog import ITEM_NAMES, TOOLS
from .game import require_steward


async def tool_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    parts = command.strip().split()
    verb = parts[0].lower() if parts else "list"

    if verb == "list":
        stock = await db.get_satchel(s["id"])
        owned = [k for k in stock if k.startswith("tool_")]
        lines = ["工具铺："]
        for key, meta in TOOLS.items():
            item = f"tool_{key}"
            tag = "✓" if item in owned else " "
            lines.append(
                f"  [{tag}] {meta['emoji']}{meta['name']} — {meta['cost']} 票"
                + (f" 渔获+{int(meta['fish_bonus']*100)}%" if meta.get("fish_bonus") else "")
            )
        lines.append("buy hoe|shovel — 锄头 tend 松土+蚯蚓↑；渔具 tier 见 gear_ops")
        return "\n".join(lines)

    if verb == "buy" and len(parts) >= 2:
        key = parts[1].lower().replace("net_", "net_")
        if key == "net":
            key = "net_basic"
        if key not in TOOLS:
            raise ValueError(f"可购: {', '.join(TOOLS.keys())}")
        item = f"tool_{key}"
        cost = TOOLS[key]["cost"]
        async with db.connect() as conn:
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < cost:
                raise ValueError(f"需要 {cost} 票")
            stock = await db.get_satchel(s["id"])
            if stock.get(item, 0) > 0:
                return f"已有 {TOOLS[key]['name']}"
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (cost, s["id"]),
            )
            await db.add_item(conn, s["id"], item, 1)
            if key.startswith("net_"):
                from . import gear
                g = await gear.get_gear(conn, s["id"])
                tier = 2 if key == "net_fine" else 1
                if g["net"] < tier:
                    await conn.execute(
                        "UPDATE steward_gear SET net_tier=? WHERE steward_id=?",
                        (tier, s["id"]),
                    )
            await conn.commit()
        await db.add_chronicle(
            "tool",
            f"{s['name']} 购入 {TOOLS[key]['name']}",
            s["id"],
        )
        msg = f"购入 {ITEM_NAMES.get(item, item)}（-{cost} 票）"
        return msg + flavor.maybe_suffix(["网已备，潮线等你", "铲子到手，退潮见"])

    raise ValueError(f"未知 tool 指令: {command}（list/buy）")
