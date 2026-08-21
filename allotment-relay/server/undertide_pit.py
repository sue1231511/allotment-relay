"""深坑 — 角斗与晏安医务间（二期）。天天侧。"""

from __future__ import annotations

import random
from typing import Any

import aiosqlite

from . import db
from . import undertide_catalog as cat
from . import undertide_config as utcfg
from . import undertide_copy as utcopy


def _day_id() -> int:
    return db.now() // 86400


async def _ensure_fighters(conn: aiosqlite.Connection) -> None:
    cur = await conn.execute("SELECT COUNT(*) FROM ut_pit_fighters")
    if (await cur.fetchone())[0] == 0:
        for f in cat.PIT_FIGHTERS:
            await conn.execute(
                "INSERT OR IGNORE INTO ut_pit_fighters (name, level, power, flavor) VALUES (?,?,?,?)",
                (f["name"], f["level"], f["power"], f["flavor"]),
            )
        await conn.commit()


async def combat_power(conn: aiosqlite.Connection, steward: dict[str, Any]) -> int:
    """玩家战力 = body/100×30 + energy/100×15 + 1d20。"""
    cur = await conn.execute("SELECT health, energy FROM stewards WHERE id=?", (steward["id"],))
    row = await cur.fetchone()
    health, energy = row[0], row[1]
    return int(health / 100 * 30 + energy / 100 * 15 + random.randint(1, 20))


STRATEGY_BEATS = {"attack": "feint", "guard": "attack", "feint": "guard"}


def strategy_mod(mine: str, theirs: str) -> float:
    if STRATEGY_BEATS.get(mine) == theirs:
        return 1.10
    if STRATEGY_BEATS.get(theirs) == mine:
        return 0.90
    return 1.0


async def pit_ops(
    conn: aiosqlite.Connection, s: dict[str, Any], ut: dict[str, Any], rest: str
) -> str:
    await _ensure_fighters(conn)
    parts = rest.split()
    verb = parts[0].lower() if parts else "list"
    if verb == "pit":
        verb = "list"

    if verb == "list":
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            "SELECT * FROM ut_pit_fighters WHERE alive=1 ORDER BY level, name"
        )).fetchall()
        lines = [utcopy.PIT_FIGHT_HEADER, ""]
        for r in rows:
            entry, prize, _, _ = _ladder(r["level"])
            lines.append(
                f"  Lv{r['level']} {r['name']} — 入场 {entry} · 胜奖 {prize} · "
                f"战绩 {r['wins']}胜{r['losses']}负\n    {r['flavor']}"
            )
        lines.append("")
        lines.append(utcopy.PIT_STRATEGY_HINT)
        lines.append("fight 斗士名 [attack|guard|feint] — 下坑")
        return "\n".join(lines)

    if verb == "fight":
        if len(parts) < 2:
            raise ValueError("用法: undertide_ops fight 斗士名 [attack|guard|feint]")
        name = parts[1]
        my_strat = parts[2].lower() if len(parts) > 2 and parts[2].lower() in STRATEGY_BEATS else random.choice(list(STRATEGY_BEATS))
        cur = await conn.execute("SELECT health, energy FROM stewards WHERE id=?", (s["id"],))
        health, energy = (await cur.fetchone())
        if health < utcfg.UT_PIT_MIN_BODY:
            return utcopy.PIT_GATEMAN_REJECT
        if ut.get("pit_banned"):
            return utcopy.HIJACK_BAN_MSG

        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT * FROM ut_pit_fighters WHERE name=? AND alive=1", (name,)
        )).fetchone()
        if not row:
            raise ValueError(f"「{name}」不在今晚的名单上（pit 查看）")
        level = row["level"]
        entry, prize, base, crit_rate = _ladder(level)

        cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
        if (await cur.fetchone())[0] < entry:
            raise ValueError(f"入场费 {entry} 票。看门人不赊账，也不负责你的尊严。")

        their_strat = random.choice(list(STRATEGY_BEATS))
        my_power = int(await combat_power(conn, s) * strategy_mod(my_strat, their_strat))
        their_power = int(row["power"] * strategy_mod(their_strat, my_strat)) + random.randint(1, 20)
        diff = my_power - their_power

        await conn.execute(
            "UPDATE stewards SET tickets=tickets-?, energy=MAX(0,energy-15) WHERE id=?",
            (entry, s["id"]),
        )

        lines = [f"«深坑 · {s['name']} vs {row['name']}»",
                 f"你的策略：{my_strat} / 对方：{their_strat}",
                 f"战力 {my_power} vs {their_power}（{'你占优' if diff > 0 else '你落下风'}）", ""]

        from . import undertide as utmod
        if diff >= 0:
            win_msg = utcopy.pick(utcopy.PIT_WIN_LINES)
            await conn.execute(
                "UPDATE stewards SET tickets=tickets+? WHERE id=?", (entry + prize, s["id"])
            )
            await conn.execute(
                "UPDATE ut_pit_fighters SET losses=losses+1 WHERE id=?", (row["id"],)
            )
            await utmod._bump_rep(conn, s["id"], utcfg.UT_PIT_WIN_REP)
            lines.append(win_msg)
            lines.append(f"\n（入场 −{entry} · 胜奖 +{prize} · 影信 +{utcfg.UT_PIT_WIN_REP}）")
            # 胜者也可能挂彩
            if random.random() < 0.30:
                loss = random.randint(5, 10)
                await conn.execute(
                    "UPDATE stewards SET health=MAX(0,health-?) WHERE id=?", (loss, s["id"])
                )
                lines.append(f"（代价是一块迅速变紫的淤青。body −{loss}）")
            # NPC 惨败死亡
            if diff >= 15 and random.random() < utcfg.UT_PIT_DEATH_CHANCE:
                await conn.execute("UPDATE ut_pit_fighters SET alive=0 WHERE id=?", (row["id"],))
                await _spawn_replacement(conn, level)
                lines.append("\n" + utcopy.PIT_NPC_DEATH)
        else:
            lose_msg = utcopy.pick(utcopy.PIT_LOSE_LINES)
            await conn.execute(
                "UPDATE ut_pit_fighters SET wins=wins+1 WHERE id=?", (row["id"],)
            )
            lines.append(lose_msg)
            loss = random.randint(10, 15)
            await conn.execute(
                "UPDATE stewards SET health=MAX(0,health-?) WHERE id=?", (loss, s["id"])
            )
            lines.append(f"\n（入场 −{entry} · body −{loss}）")
            # 重伤判定
            if random.random() < crit_rate:
                ailment = random.choices(
                    ["ring_shock", "pit_trauma"], weights=[0.6, 0.4]
                )[0]
                from . import health
                await health.inflict(conn, s["id"], ailment, source="pit")
                meta_line = (
                    "你走得出去，但走得不太像样。"
                    if ailment == "pit_trauma"
                    else "人还能站，只是整个世界像慢了半拍。"
                )
                lines.append(f"\n{meta_line}\n（{ailment} — undertide_ops medic {ailment}）")
            elif random.random() < 0.35:
                from . import health
                await health.inflict(conn, s["id"], random.choice(["sprain", "backache"]), source="pit")
                lines.append("\n（挂了普通伤 — 桥桥那儿能治：visit_ops clinic treat）")
        await db.add_chronicle(
            "undertide", f"{s['name']} 在深坑{'胜' if diff >= 0 else '败'}于 {row['name']}",
            s["id"], conn=conn,
        )
        await conn.commit()
        return "\n".join(lines)

    if verb == "medic":
        # 真身：自己的诊室——全病谱开放（地面 12 种 + 深坑 2 种），材料费 ≈ 原价 1/4
        from . import undertide as _ut
        from .catalog import AILMENTS as _AILS
        av = await _ut.avatar_key(conn, s["id"])
        is_avatar = av == "anan" and True
        valid_keys = set(_AILS) if is_avatar else set(utcfg.UT_PIT_MEDIC)
        if len(parts) < 2 or parts[1] not in valid_keys:
            raise ValueError(
                "用法: undertide_ops medic ring_shock|pit_trauma"
                + ("（或任意病症 key——这里是你的诊室）" if is_avatar else "")
            )
        ailment = parts[1]
        cur = await conn.execute(
            "SELECT 1 FROM steward_ailments WHERE steward_id=? AND ailment_key=?",
            (s["id"], ailment),
        )
        if not await cur.fetchone():
            raise ValueError("你没有这个伤。别在晏安面前装病——他见过的真伤比你演的都多。")
        if is_avatar:
            import math
            base = _AILS[ailment]["cost"] if ailment in _AILS else utcfg.UT_PIT_MEDIC.get(
                ailment, (60, 90))[0]
            cost = max(2, math.ceil(base * 0.25))
        else:
            cost = random.randint(*utcfg.UT_PIT_MEDIC[ailment])
        cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
        wallet = (await cur.fetchone())[0]
        paid_note = ""
        if wallet >= cost:
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?", (cost, s["id"])
            )
            paid_note = f"（手术费 −{cost} 票）"
        else:
            # 付不起 → 划账恶猫钱庄（按当日利率起息）
            await conn.execute(
                "INSERT INTO ut_debts (steward_id, principal, due_day, source, created_day) VALUES (?,?,?,?,?)",
                (s["id"], cost, _day_id() + 7, "surgery", _day_id()),
            )
            paid_note = f"（手术费 {cost} 票，账已划转恶猫钱庄，按当日利率起息）"
        heal_map = {"ring_shock": 30, "pit_trauma": 40}
        heal = heal_map.get(ailment) or _AILS.get(ailment, {}).get("health_restore", 12)
        await conn.execute(
            "DELETE FROM steward_ailments WHERE steward_id=? AND ailment_key=?", (s["id"], ailment)
        )
        await conn.execute(
            "UPDATE stewards SET health=MIN(100, health+?) WHERE id=?", (heal, s["id"])
        )
        await conn.commit()
        if is_avatar:
            ail_name = _AILS.get(ailment, {}).get("name", ailment)
            return utcopy.AVATAR_AN_MEDIC.format(ail=ail_name, cost=cost, heal=heal)
        if wallet < cost:
            body = utcopy.PIT_MEDIC_BROKE
        else:
            tpl = utcopy.PIT_MEDIC_RING if ailment == "ring_shock" else utcopy.PIT_MEDIC_TRAUMA
            body = tpl.format(cost=cost)
        return body + f"\n\n{paid_note}\n（body +{heal} · {ailment} 已处理）"

    raise ValueError("未知 pit 指令（list/fight/medic）")


def _ladder(level: int) -> tuple[int, int, int, float]:
    entry, prize, base, crit = utcfg.UT_PIT_LADDER[min(level, 5) - 1][1:]
    return entry, prize, base, crit


async def _spawn_replacement(conn: aiosqlite.Connection, level: int) -> None:
    name = random.choice(cat.PIT_REPLACEMENTS)
    await conn.execute(
        "INSERT OR IGNORE INTO ut_pit_fighters (name, level, power, flavor) VALUES (?,?,?,?)",
        (name, level, _ladder(level)[2] + random.randint(-3, 3), "顶上那个位置的新人。"),
    )
