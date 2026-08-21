"""世界 Boss — 潮渊之主（深海应激），合力击杀掉神话章鱼肉。"""

from __future__ import annotations

import random

import aiosqlite

from . import config, db, energy, flavor
from .catalog import WORLD_BOSS
from .game import require_steward


async def _ensure_boss(conn: aiosqlite.Connection) -> dict:
    conn.row_factory = aiosqlite.Row
    key = WORLD_BOSS["key"]
    row = await (await conn.execute(
        "SELECT * FROM world_boss WHERE boss_key=?", (key,)
    )).fetchone()
    now = db.now()
    if not row:
        await conn.execute(
            """
            INSERT INTO world_boss (boss_key, hp, max_hp, respawn_at)
            VALUES (?,?,?,0)
            """,
            (key, WORLD_BOSS["hp"], WORLD_BOSS["hp"]),
        )
        row = await (await conn.execute(
            "SELECT * FROM world_boss WHERE boss_key=?", (key,)
        )).fetchone()
    boss = dict(row)
    if boss["hp"] <= 0 and boss.get("respawn_at") and now >= boss["respawn_at"]:
        await conn.execute(
            "UPDATE world_boss SET hp=?, defeated_at=NULL, respawn_at=0 WHERE boss_key=?",
            (WORLD_BOSS["hp"], key),
        )
        boss["hp"] = WORLD_BOSS["hp"]
    return boss


def _day_id() -> int:
    return db.now() // config.FORAGE_COOLDOWN_DAY


async def boss_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    parts = command.strip().split()
    verb = parts[0].lower() if parts else "status"

    if verb == "status":
        async with db.connect() as conn:
            boss = await _ensure_boss(conn)
            await conn.commit()
        pct = int(boss["hp"] / boss["max_hp"] * 100)
        if boss["hp"] <= 0:
            left = max(0, (boss.get("respawn_at") or 0) - db.now())
            return (
                f"「{WORLD_BOSS['name']}」已沉寂 — {left // 3600}h 后可能再醒\n"
                f"战利品: {WORLD_BOSS['loot']} x{WORLD_BOSS['loot_qty']}"
            )
        return (
            f"「{WORLD_BOSS['name']}」 HP {boss['hp']}/{boss['max_hp']} ({pct}%)\n"
            f"boss_ops attack — 消耗 {config.BOSS_ATTACK_ENERGY} 精力，无船也能打（岸边围攻），不扣船票不掉血\n"
            f"伤害每次随机 {config.BOSS_ATTACK_DAMAGE[0]}~{config.BOSS_ATTACK_DAMAGE[1]}，最后一击者拿击杀纪事\n"
            f"击杀全员掉落 {WORLD_BOSS['loot']}"
        )

    if verb == "log":
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            boss = await _ensure_boss(conn)
            rows = await (await conn.execute(
                """
                SELECT ba.damage, ba.created_at, st.name
                FROM boss_attacks ba
                JOIN stewards st ON st.id=ba.steward_id
                WHERE ba.boss_key=? AND ba.created_at > ?
                ORDER BY ba.damage DESC LIMIT 12
                """,
                (WORLD_BOSS["key"], db.now() - 86400 * 2),
            )).fetchall()
            my = await (await conn.execute(
                "SELECT count FROM boss_rolls WHERE steward_id=? AND day=?",
                (s["id"], _day_id()),
            )).fetchone()
            await conn.commit()
        lines = [f"「{WORLD_BOSS['name']}」近期伤害榜（48h）"]
        if boss["hp"] <= 0:
            lines.append("Boss 已沉寂")
        else:
            lines.append(f"当前 HP {boss['hp']}/{boss['max_hp']}")
        if not rows:
            lines.append("尚无攻击记录 — boss_ops attack")
        else:
            for i, r in enumerate(rows, 1):
                lines.append(f"  {i}. {r['name']} -{r['damage']}")
        used = my[0] if my else 0
        lines.append(f"你今日攻击 {used}/{config.BOSS_DAILY_ATTACKS}")
        return "\n".join(lines)

    if verb == "attack":
        day = _day_id()
        async with db.connect() as conn:
            cur = await conn.execute(
                "SELECT count FROM boss_rolls WHERE steward_id=? AND day=?",
                (s["id"], day),
            )
            row = await cur.fetchone()
            if row and row[0] >= config.BOSS_DAILY_ATTACKS:
                raise ValueError(f"今日攻击上限 {config.BOSS_DAILY_ATTACKS}")
            boss = await _ensure_boss(conn)
            if boss["hp"] <= 0:
                raise ValueError("Boss 已倒下，等刷新")
            await energy.spend(conn, s["id"], config.BOSS_ATTACK_ENERGY, action="讨伐")
            lo, hi = config.BOSS_ATTACK_DAMAGE
            dmg = random.randint(lo, hi)
            if s.get("mascot_trait") == "lucky":
                from . import social as social_mod
                dmg = int(dmg * 1.12 * social_mod.mascot_trait_mult(s.get("mascot_spirit", 70)))
            new_hp = max(0, boss["hp"] - dmg)
            await conn.execute(
                "UPDATE world_boss SET hp=? WHERE boss_key=?",
                (new_hp, WORLD_BOSS["key"]),
            )
            await conn.execute(
                """
                INSERT INTO boss_attacks (boss_key, steward_id, damage, created_at)
                VALUES (?,?,?,?)
                """,
                (WORLD_BOSS["key"], s["id"], dmg, db.now()),
            )
            await conn.execute(
                """
                INSERT INTO boss_rolls (steward_id, day, count) VALUES (?,?,1)
                ON CONFLICT(steward_id, day) DO UPDATE SET count = count + 1
                """,
                (s["id"], day),
            )
            loot_msg = ""
            if new_hp <= 0:
                await conn.execute(
                    """
                    UPDATE world_boss SET defeated_at=?, respawn_at=?
                    WHERE boss_key=?
                    """,
                    (db.now(), db.now() + 86400 * 2, WORLD_BOSS["key"]),
                )
                attackers = await (await conn.execute(
                    """
                    SELECT DISTINCT steward_id FROM boss_attacks
                    WHERE boss_key=? AND created_at > ?
                    """,
                    (WORLD_BOSS["key"], db.now() - 3600),
                )).fetchall()
                loot = WORLD_BOSS["loot"]
                qty = WORLD_BOSS["loot_qty"]
                for (sid,) in attackers:
                    await db.add_item(conn, sid, loot, qty)
                loot_msg = (
                    f"\n击杀！{len(attackers)} 位参与者各得 "
                    f"{loot} x{qty}（神话级食材）"
                )
                await db.add_chronicle(
                    "boss",
                    f"{s['name']} 等合力击倒 {WORLD_BOSS['name']}",
                    s["id"],
                )
                from . import lore as lore_mod
                loot_msg += f"\n{lore_mod.boss_defeat_lore()}"
            await conn.commit()
        detail = flavor.pick([
            "触须抽打海面，你仍砍了一刀",
            "深海应激翻涌，姜姨已经在想菜单",
            "全服出力，潮渊之主暂时退回深处",
        ])
        return f"造成 {dmg} 伤害，剩余 HP {new_hp}{loot_msg}\n{detail}"

    raise ValueError(f"未知 boss 指令: {command}（status/attack）")
