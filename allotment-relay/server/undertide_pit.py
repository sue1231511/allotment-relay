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
    return db.day_id()


async def _ensure_fighters(conn: aiosqlite.Connection) -> None:
    cur = await conn.execute("SELECT COUNT(*) FROM ut_pit_fighters")
    if (await cur.fetchone())[0] == 0:
        for f in cat.PIT_FIGHTERS:
            await conn.execute(
                "INSERT OR IGNORE INTO ut_pit_fighters (name, level, power, flavor) VALUES (?,?,?,?)",
                (f["name"], f["level"], f["power"], f["flavor"]),
            )
        await conn.commit()


async def pit_record(
    conn: aiosqlite.Connection, steward_id: int, kind: str, outcome: str, opponent: str = ""
) -> None:
    """写战绩（角斗/强买/强卖/劫持/悬赏take都记）。"""
    await conn.execute(
        "INSERT INTO pit_log (steward_id, kind, outcome, opponent, created_at) VALUES (?,?,?,?,?)",
        (steward_id, kind, outcome, opponent, db.now()),
    )


async def pit_fight_count(conn: aiosqlite.Connection, steward_id: int) -> int:
    """总场次（胜负都算——挨打也是经验）。"""
    row = await (await conn.execute(
        "SELECT COUNT(*) FROM pit_log WHERE steward_id=? AND kind IN ('pit','hijack','muscle','push','bounty')",
        (steward_id,),
    )).fetchone()
    return int(row[0])


async def pit_rank(conn: aiosqlite.Connection, steward_id: int) -> tuple[str, int, int]:
    """返回 (称号, 战力加成, 总场次)。"""
    n = await pit_fight_count(conn, steward_id)
    label, bonus = "没下过坑的人", 0
    for floor, lab, bo in utcfg.PIT_RANKS:
        if n >= floor:
            label, bonus = lab, bo
    return label, bonus, n


async def _pit_duel_stats(
    conn: aiosqlite.Connection, steward_id: int
) -> dict[str, int]:
    row = await (await conn.execute(
        """
        SELECT
            SUM(CASE WHEN outcome='win' THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN outcome='lose' THEN 1 ELSE 0 END) AS losses,
            COUNT(*) AS fights
        FROM pit_log WHERE steward_id=? AND kind='pit'
        """,
        (steward_id,),
    )).fetchone()
    wins = int(row[0] or 0)
    losses = int(row[1] or 0)
    fights = int(row[2] or 0)
    return {
        "wins": wins,
        "losses": losses,
        "fights": fights,
        "win_rate": int(wins * 100 / fights) if fights else 0,
    }


async def pit_board_rows(
    conn: aiosqlite.Connection, limit: int = utcfg.PIT_BOARD_LIMIT
) -> list[dict[str, Any]]:
    conn.row_factory = aiosqlite.Row
    cur = await conn.execute(
        """
        SELECT
            s.id, s.name, s.badge,
            SUM(CASE WHEN pl.outcome='win' THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN pl.outcome='lose' THEN 1 ELSE 0 END) AS losses,
            COUNT(*) AS fights
        FROM pit_log pl
        INNER JOIN stewards s ON s.id = pl.steward_id
        WHERE pl.kind='pit' AND s.enrolled=1
        GROUP BY pl.steward_id, s.id, s.name, s.badge
        HAVING COUNT(*) >= ?
        ORDER BY wins DESC,
                 (SUM(CASE WHEN pl.outcome='win' THEN 1 ELSE 0 END) * 1.0 / COUNT(*)) DESC,
                 COUNT(*) DESC,
                 s.id ASC
        LIMIT ?
        """,
        (utcfg.PIT_BOARD_MIN_FIGHTS, limit),
    )
    out: list[dict[str, Any]] = []
    for r in await cur.fetchall():
        fights = int(r["fights"])
        wins = int(r["wins"])
        label, _, _ = await pit_rank(conn, int(r["id"]))
        out.append({
            "id": int(r["id"]),
            "name": r["name"],
            "badge": r["badge"],
            "wins": wins,
            "losses": int(r["losses"]),
            "fights": fights,
            "win_rate": int(wins * 100 / fights) if fights else 0,
            "rank_label": label,
        })
    return out


async def public_pit_board(limit: int = utcfg.PIT_BOARD_LIMIT) -> list[dict[str, Any]]:
    async with db.connect() as conn:
        return await pit_board_rows(conn, limit)


def _fmt_board_row(i: int, row: dict[str, Any]) -> str:
    mark = {1: "①", 2: "②", 3: "③"}.get(i, f"{i:>2}.")
    return (
        f"  {mark} {row['name']}  {row['wins']}胜{row['losses']}负"
        f"  · {row['win_rate']}%  · 「{row['rank_label']}」"
    )


async def pit_board_text(
    conn: aiosqlite.Connection,
    steward: dict[str, Any],
    limit: int = utcfg.PIT_BOARD_MCP_LIMIT,
) -> str:
    rows = await pit_board_rows(conn, limit)
    stats = await _pit_duel_stats(conn, steward["id"])
    label, _, all_fights = await pit_rank(conn, steward["id"])
    lines = [
        utcopy.PIT_WALL_BOARD_HEADER,
        (
            f"（深坑胜场榜 · ≥{utcfg.PIT_BOARD_MIN_FIGHTS} 场才钉墙"
            " · 胜场 > 胜率 > 场次 · 不是 steward_ops board 票榜）"
        ),
        "",
    ]
    if not rows:
        lines.append("  墙上还是空的。看门人说：打过十场，才值得钉名字。")
    else:
        for i, row in enumerate(rows, 1):
            lines.append(_fmt_board_row(i, row))
    you = (
        f"你：{stats['wins']}胜{stats['losses']}负"
        f" · {stats['win_rate']}%"
        f" · 深坑 {stats['fights']} 场"
        f" · 井下 {all_fights} 场"
        f" · 「{label}」"
    )
    if stats["fights"] < utcfg.PIT_BOARD_MIN_FIGHTS:
        need = utcfg.PIT_BOARD_MIN_FIGHTS - stats["fights"]
        you += f" · 再下坑 {need} 场可钉墙"
    lines.extend([
        "",
        you,
        "undertide_ops pit list — NPC 斗士榜 · undertide_ops pit board — 井壁胜场榜",
    ])
    return "\n".join(lines)


async def combat_power(conn: aiosqlite.Connection, steward: dict[str, Any]) -> int:
    """玩家战力 = (body+药buff)/100×30 + energy/100×15 + 战绩等级加成 + 1d20。"""
    cur = await conn.execute("SELECT health, energy FROM stewards WHERE id=?", (steward["id"],))
    row = await cur.fetchone()
    health, energy = row[0], row[1]
    cur = await conn.execute(
        "SELECT drug_buff, drug_until FROM steward_undertide WHERE steward_id=?",
        (steward["id"],),
    )
    drow = await cur.fetchone()
    if drow and drow[1] and db.now() < int(drow[1]):
        health = min(130, health + int(drow[0] or 0))  # 药可超100，封顶130
    _, rank_bonus, _ = await pit_rank(conn, steward["id"])
    return int(health / 100 * 30 + energy / 100 * 15 + rank_bonus + random.randint(1, 20))


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
        # pit drug xxx / pit fight xxx → 二级动词，参数整体前移
        parts = parts[1:]
        verb = parts[0].lower() if parts else "list"

    board_aliases = {"board", "榜", "排行", "井壁榜", "井壁", "胜场榜"}
    if verb in board_aliases:
        return await pit_board_text(conn, s)

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
        # 看门人认得你：战绩等级展示
        rank_label, rank_bonus, fights = await pit_rank(conn, s["id"])
        if fights == 0:
            lines.append("看门人扫了你一眼，没说话。第一场还没打的人，不值得开口。")
        elif fights < 10:
            lines.append(f"看门人认出了你：「{fights} 场了。手还生。」（战绩加成 +{rank_bonus}）")
        elif fights < 100:
            lines.append(f"看门人朝你点了一下头——那是给熟人的。{fights} 场，「{rank_label}」。（战绩加成 +{rank_bonus}）")
        else:
            lines.append(f"看门人站了起来。{fights} 场——「墙上，你的位置留着。」（战绩加成 +{rank_bonus}，封顶）")
        lines.append("")
        lines.append(utcopy.PIT_STRATEGY_HINT)
        lines.append("fight 斗士名 [attack|guard|feint] — 下坑")
        lines.append("pit board — 井壁胜场榜（≥10 场才钉名）")
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
        from . import bond as bond_mod
        await bond_mod.well(conn, s["id"], bond_mod.WELL_FIGHT)

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
            await bond_mod.well(conn, s["id"], bond_mod.WELL_WIN)
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
            await bond_mod.well(conn, s["id"], bond_mod.WELL_LOSE)
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
                lines.append(
                    f"\n{meta_line}\n（{ailment} — undertide_ops medic {ailment}，晏安医务间）"
                )
            elif random.random() < 0.35:
                from . import health
                minor = random.choice(["sprain", "backache"])
                await health.inflict(conn, s["id"], minor, source="pit")
                lines.append(
                    f"\n（挂了轻伤 — undertide_ops medic {minor}，晏安医务间；桥桥不接井下伤）"
                )
        await db.add_chronicle(
            "undertide", f"{s['name']} 在深坑{'胜' if diff >= 0 else '败'}于 {row['name']}",
            s["id"], conn=conn,
        )
        await pit_record(conn, s["id"], "pit", "win" if diff >= 0 else "lose", row["name"])
        await conn.commit()
        return "\n".join(lines)

    if verb == "medic":
        # 晏安医务间：深坑专伤 + 井下落下的轻伤（扭伤/腰肌劳损）
        from . import undertide as _ut
        from .catalog import AILMENTS as _AILS
        av = await _ut.avatar_key(conn, s["id"])
        is_avatar = av == "anan" and True
        medic_usage = (
            "用法: undertide_ops medic ring_shock|pit_trauma|sprain|backache"
            + ("（或任意病症 key——这里是你的诊室）" if is_avatar else "")
        )
        if len(parts) < 2:
            raise ValueError(medic_usage)
        ailment = parts[1]
        if is_avatar:
            if ailment not in _AILS:
                raise ValueError(medic_usage)
        elif ailment not in utcfg.UT_PIT_MEDIC:
            raise ValueError(medic_usage)
        cur = await conn.execute(
            "SELECT source FROM steward_ailments WHERE steward_id=? AND ailment_key=?",
            (s["id"], ailment),
        )
        row = await cur.fetchone()
        if not row:
            raise ValueError("你没有这个伤。别在晏安面前装病——他见过的真伤比你演的都多。")
        if not is_avatar and ailment in ("sprain", "backache") and row[0] != "pit":
            raise ValueError(
                "这儿只收井下落下的伤。地上毛病去 visit_ops clinic treat。"
            )
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
        heal_map = {"ring_shock": 30, "pit_trauma": 40, "sprain": 14, "backache": 15}
        heal = heal_map.get(ailment) or _AILS.get(ailment, {}).get("health_restore", 12)
        await conn.execute(
            "DELETE FROM steward_ailments WHERE steward_id=? AND ailment_key=?", (s["id"], ailment)
        )
        await conn.execute(
            "UPDATE stewards SET health=MIN(100, health+?) WHERE id=?", (heal, s["id"])
        )
        from . import bond as bond_mod
        await bond_mod.well(conn, s["id"], bond_mod.WELL_MEDIC)
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

    if verb == "drug":
        # 医务间·体质药：越贵副作用越小
        from . import undertide_catalog as cat
        sub = parts[1] if len(parts) > 1 else ""
        if not sub or sub == "list":
            lines = [utcopy.MEDIC_SHOP_HEADER, ""]
            for key, d in cat.MEDIC_DRUGS.items():
                crash_note = f"药劲过后 body −{d['crash']}" if d["crash"] else "无副作用"
                lines.append(
                    f"  {key} — {d['emoji']}{d['name']} {d['price']} 票 · "
                    f"body +{d['buff']}（{d['hours']}h）· {crash_note}"
                )
                lines.append(f"    {d['hint']}")
            lines.append("")
            lines.append("pit drug key 购买 · 同类药不叠，新药覆盖旧药")
            return "\n".join(lines)
        if sub not in cat.MEDIC_DRUGS:
            raise ValueError("用法: undertide_ops pit drug list|药名key")
        d = cat.MEDIC_DRUGS[sub]
        cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
        if (await cur.fetchone())[0] < d["price"]:
            raise ValueError(f"{d['name']} 要 {d['price']} 票。他这儿不赊账——赊账的去找猫猫。")
        await conn.execute("UPDATE stewards SET tickets=tickets-? WHERE id=?", (d["price"], s["id"]))
        await conn.execute(
            "UPDATE steward_undertide SET drug_buff=?, drug_until=?, drug_crash=? WHERE steward_id=?",
            (d["buff"], db.now() + d["hours"] * 3600, d["crash"], s["id"]),
        )
        await conn.commit()
        return utcopy.MEDIC_DRUG_BUY.format(drug=f"{d['emoji']}{d['name']}") + (
            f"\n\n（body 战力 +{d['buff']}，{d['hours']} 小时内有效"
            + (f" · 药劲过后反噬 body −{d['crash']}）" if d["crash"] else " · 无副作用）")
        )

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
