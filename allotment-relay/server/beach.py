"""赶海 — 退潮 + 铲子，猫眼螺/贝壳/竹蛏/蚯蚓饵。"""

from __future__ import annotations

import random

import aiosqlite

from . import config, db, energy, flavor, world
from .catalog import BEACH_LOOT, ITEM_NAMES
from .game import require_steward


async def beach_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    parts = command.strip().split()
    verb = parts[0].lower() if parts else "status"

    if verb == "status":
        tide = world.current_tide()
        w = world.current_weather()
        stock = await db.get_satchel(s["id"])
        has_shovel = stock.get("tool_shovel", 0) > 0
        lines = [
            f"潮汐 {world.tide_label(tide)} · {world.weather_label(w)}",
            f"铲子: {'有' if has_shovel else '无 — tool_ops buy shovel'}",
            f"赶海消耗 {config.BEACH_ENERGY} 精力",
        ]
        if tide != "ebb":
            lines.append("提示：退潮时收获更好")
        return "\n".join(lines)

    if verb == "dig":
        tide = world.current_tide()
        if tide not in ("ebb", "slack"):
            raise ValueError("涨潮没过脚面，等退潮再赶海")
        stock = await db.get_satchel(s["id"])
        if not stock.get("tool_shovel"):
            raise ValueError("需要铲子 tool_ops buy shovel")

        now = db.now()
        day = now // config.FORAGE_COOLDOWN_DAY
        async with aiosqlite.connect(db.DB_PATH) as conn:
            cur = await conn.execute(
                "SELECT last_at, count FROM beach_rolls WHERE steward_id=? AND day=?",
                (s["id"], day),
            )
            row = await cur.fetchone()
            if row and now - row[0] < config.BEACH_COOLDOWN:
                left = config.BEACH_COOLDOWN - (now - row[0])
                raise ValueError(f"这片滩刚翻过，{left // 60} 分后再来")
            await energy.spend(conn, s["id"], config.BEACH_ENERGY, action="赶海")

            weights = [x[3] for x in BEACH_LOOT]
            if tide == "ebb":
                weights = [w + 8 if x[0].startswith("shell") else w for w, x in zip(weights, BEACH_LOOT)]
            roll = random.choices(BEACH_LOOT, weights=weights)[0]
            item, label, qty, _, _ = roll
            await db.add_item(conn, s["id"], item, qty)
            await conn.execute(
                """
                INSERT INTO beach_rolls (steward_id, day, last_at, count)
                VALUES (?,?,?,1)
                ON CONFLICT(steward_id, day) DO UPDATE SET
                    last_at=excluded.last_at, count=count+1
                """,
                (s["id"], day, now),
            )
            await conn.commit()

        msg = f"赶海：{label} x{qty}"
        msg += flavor.maybe_suffix([
            "沙里藏货，铲子诚不欺我",
            "猫眼螺在看你，你也看它",
            "退潮捡漏，联盟传统艺能",
        ])
        await db.add_chronicle("beach", f"{s['name']} 赶海得 {label}", s["id"])
        return msg

    raise ValueError(f"未知 beach 指令: {command}（status/dig）")
