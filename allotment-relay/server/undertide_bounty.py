"""恩怨墙 — 悬赏榜（三期）。天天侧。"""

from __future__ import annotations

import random
from typing import Any

import aiosqlite

from . import db
from . import undertide_config as utcfg
from . import undertide_copy as utcopy


def _day_id() -> int:
    return db.now() // 86400


async def _settle_expired(conn: aiosqlite.Connection) -> int:
    """AI 挂的单超时 72h → NPC 自动执行（真打：效果落地+目标通知+纪事）。"""
    conn.row_factory = aiosqlite.Row
    rows = await (await conn.execute(
        "SELECT * FROM ut_bounty WHERE status='open' AND poster != '__npc__' AND expires_at < ?",
        (db.now(),),
    )).fetchall()
    for b in rows:
        await conn.execute("UPDATE ut_bounty SET status='npc_done' WHERE id=?", (b["id"],))
        # NPC 打手是职业的：必成，效果真实落地
        await _execute_on_target(conn, b, executor="npc")
        await db.add_chronicle(
            "undertide",
            f"恩怨墙上的一张纸条被人揭走了。针对 {b['target_name']} 的那单，办完了。",
            None, conn=conn,
        )
    if rows:
        await conn.commit()
    return len(rows)


async def _notify_target(conn: aiosqlite.Connection, target_id: int, text: str) -> None:
    """目标侧通知：写进 unread_hits，下次进潮下时送达。"""
    import json as _json
    conn.row_factory = None
    row = await (await conn.execute(
        "SELECT unread_hits FROM steward_undertide WHERE steward_id=?", (target_id,)
    )).fetchone()
    hits = _json.loads(row[0]) if row and row[0] else []
    hits.append(text)
    await conn.execute(
        "UPDATE steward_undertide SET unread_hits=? WHERE steward_id=?",
        (_json.dumps(hits, ensure_ascii=False), target_id),
    )


async def _execute_on_target(
    conn: aiosqlite.Connection, bounty: dict[str, Any], *, executor: str = "taker"
) -> tuple[str, list[str]]:
    """对目标真实执行悬赏效果。返回 (效果行列表, 目标通知文本)。"""
    from . import health as h
    effect_lines: list[str] = []
    target_note = ""
    if bounty["tier"] == "steal":
        conn.row_factory = aiosqlite.Row
        plots = await (await conn.execute(
            "SELECT id, slot FROM parcels WHERE steward_id=? AND crop IS NOT NULL ORDER BY planted_at LIMIT 1",
            (bounty["target_id"],),
        )).fetchall()
        if plots:
            await conn.execute(
                "UPDATE parcels SET crop=NULL, planted_at=NULL, tended=0 WHERE id=?",
                (plots[0]["id"],),
            )
            effect_lines.append(f"目标地块 #{plots[0]['slot']} 的作物被毁。")
            target_note = utcopy.BOUNTY_TARGET_CROP.format(slot=plots[0]["slot"])
        else:
            effect_lines.append("目标地里没东西可毁——这单办得有点尴尬，但纸条还是能交。")
    else:
        loss = random.randint(15, 25)
        await conn.execute(
            "UPDATE stewards SET health=MAX(0,health-?) WHERE id=?", (loss, bounty["target_id"])
        )
        ail = None
        if random.random() < 0.5:
            ail = random.choice(["sprain", "backache"])
            await h.inflict(conn, bounty["target_id"], ail, source="bounty")
            effect_lines.append(f"目标 body −{loss}，挂伤（{ail}）。")
        else:
            effect_lines.append(f"目标 body −{loss}。")
        target_note = utcopy.BOUNTY_TARGET_HIT.format(loss=loss)
    if target_note:
        await _notify_target(conn, bounty["target_id"], target_note)
    return target_note, effect_lines


async def _maybe_npc_post(conn: aiosqlite.Connection, s: dict[str, Any], reason: str) -> None:
    """恶猫钱庄的烂账鬼（逾期≥6天）自动挂单。"""
    conn.row_factory = aiosqlite.Row
    row = await (await conn.execute(
        """SELECT d.*, ? today FROM ut_debts d WHERE d.steward_id=? AND d.status='open'
           AND ? > d.due_day + 5 LIMIT 1""",
        (_day_id(), s["id"], _day_id()),
    )).fetchone()
    if not row:
        return
    cur = await conn.execute(
        "SELECT COUNT(*) FROM ut_bounty WHERE target_id=? AND status='open' AND poster='__npc__'",
        (s["id"],),
    )
    if (await cur.fetchone())[0]:
        return
    bounty = utcfg.UT_BOUNTY_TIERS["beat"]
    await conn.execute(
        """INSERT INTO ut_bounty (poster, poster_id, target_name, target_id, tier, bounty, status, expires_at, created_at)
           VALUES ('__npc__', NULL, ?, ?, 'beat', ?, 'open', ?, ?)""",
        (s["name"], s["id"], bounty, db.now() + 86400 * 7, db.now()),
    )
    await db.add_chronicle(
        "undertide",
        f"恩怨墙上多了一张烫金的纸条：「此人欠钱。打轻点。他要留着还债。」——指名 {s['name']}。",
        None, conn=conn,
    )


async def bounty_ops(
    conn: aiosqlite.Connection, s: dict[str, Any], ut: dict[str, Any], rest: str
) -> str:
    await _settle_expired(conn)
    await _maybe_npc_post(conn, s, "overdue")
    parts = rest.split()
    verb = parts[0].lower() if parts else "list"

    if verb == "list":
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            "SELECT * FROM ut_bounty WHERE status='open' ORDER BY created_at DESC LIMIT 12"
        )).fetchall()
        lines = ["«恩怨墙 — 钉满纸条的墙»",
                 "纸条上不写挂单人。只有目标、事情、价钱。", ""]
        if not rows:
            lines.append("（墙是空的。空墙最罕见，也最不安。）")
        for b in rows:
            tier_label = "偷" if b["tier"] == "steal" else "打"
            gilt = " ·烫金" if b["poster"] == "__npc__" else ""
            lines.append(f"  #{b['id']} 【{tier_label}】{b['target_name']} — 赏 {b['bounty']} 票{gilt}")
        lines.append("")
        lines.append("post steal|beat 名字 赏金 — 挂单（+20% 手续费，钱庄抽成）")
        lines.append("take 编号 — 接单（战力判定，打手自担风险）")
        lines.append("info 编号 — 侦查目标（打手的钱也是钱，掂量好了再接）")
        lines.append("burn 编号 — 销单（只有被挂的人能烧，赏金 ×1.1）")
        # ── 我的单（挂单人回执）──
        mine = await (await conn.execute(
            "SELECT * FROM ut_bounty WHERE poster_id=? AND status != 'open' ORDER BY created_at DESC LIMIT 5",
            (s["id"],),
        )).fetchall()
        if mine:
            lines.append("")
            lines.append("── 你的单 ──")
            for b in mine:
                status_label = {
                    "done": "已办结", "npc_done": "已办结（NPC 打手）", "burned": "被烧毁了——有人替它付了钱",
                }.get(b["status"], b["status"])
                lines.append(f"  #{b['id']} 【{b['target_name']}】{status_label}")
                if b["status"] == "burned":
                    lines.append("    " + utcopy.BOUNTY_BURNED_NOTICE.replace("\n", "\n    "))
        return "\n".join(lines)

    if verb == "info":
        if len(parts) < 2 or not parts[1].isdigit():
            raise ValueError("用法: undertide_ops bounty info 编号")
        conn.row_factory = aiosqlite.Row
        b = await (await conn.execute(
            "SELECT * FROM ut_bounty WHERE id=? AND status='open'", (int(parts[1]),)
        )).fetchone()
        if not b:
            raise ValueError("这张纸条不在了。")
        conn.row_factory = None
        row = await (await conn.execute(
            "SELECT health, energy, last_active_at FROM stewards WHERE id=?", (b["target_id"],)
        )).fetchone()
        health = row[0] if row else 100
        body_tier = "hard" if health >= 70 else ("ok" if health >= 40 else "weak")
        last_seen = row[2] if row else 0
        gap = db.now() - int(last_seen or 0)
        if gap < 3600 * 3:
            move_note = "最近几小时还活跃着——堵人不难"
        elif gap < 86400:
            move_note = "今天露过面"
        else:
            move_note = "很久没见人了——得等，或者去他常出没的地方蹲"
        lines = [
            f"«悬赏详情 #{b['id']}»",
            f"目标：{b['target_name']}",
            f"身体：{utcopy.BOUNTY_INFO_BODY[body_tier]}（body {health}）",
            f"动向：{move_note}",
            "",
            "（打手的钱也是钱——掂量好了再接。take 编号 接单。）",
        ]
        return "\n".join(lines)

    if verb == "burn":
        if len(parts) < 2 or not parts[1].isdigit():
            raise ValueError("用法: undertide_ops bounty burn 编号")
        conn.row_factory = aiosqlite.Row
        b = await (await conn.execute(
            "SELECT * FROM ut_bounty WHERE id=? AND status='open'", (int(parts[1]),)
        )).fetchone()
        if not b:
            raise ValueError("这张纸条不在了。")
        if b["target_id"] != s["id"]:
            raise ValueError("你只能烧针对自己的纸条。别人的恩怨，酒保不管。")
        cost = int(b["bounty"] * 1.1)
        cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
        if (await cur.fetchone())[0] < cost:
            raise ValueError(f"销单要 {cost} 票（赏金 ×1.1）。烧不起的话——只能多加小心了。")
        await conn.execute("UPDATE stewards SET tickets=tickets-? WHERE id=?", (cost, s["id"]))
        await conn.execute("UPDATE ut_bounty SET status='burned' WHERE id=?", (b["id"],))
        await conn.commit()
        return utcopy.BOUNTY_BURN + f"\n\n（−{cost} 票 · 纸条没了——挂单的人只会知道单子消失，不会知道是谁烧的）"

    if verb == "post":
        if len(parts) < 4:
            raise ValueError("用法: undertide_ops bounty post steal|beat 名字 赏金")
        tier = parts[1].lower()
        if tier not in utcfg.UT_BOUNTY_TIERS:
            raise ValueError("档位只有 steal（偷·毁一块作物，底价 60）或 beat（打一顿，底价 150）")
        name = parts[2]
        target = await db.get_steward_by_name(name)
        if not target:
            raise ValueError(f"档口查无此人：{name}")
        try:
            bounty = int(parts[3])
        except ValueError:
            raise ValueError("赏金须为数字")
        floor = utcfg.UT_BOUNTY_TIERS[tier]
        if bounty < floor:
            raise ValueError(f"{tier} 档底价 {floor} 票。仇恨是奢侈品。")
        total = int(bounty * (1 + utcfg.UT_BOUNTY_FEE))
        cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
        if (await cur.fetchone())[0] < total:
            raise ValueError(f"挂单实付 {total} 票（含 20% 抽成）。挂不起的仇，先记账。")
        # 同目标冷却
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT created_at FROM ut_bounty WHERE target_id=? AND status IN ('open','done','npc_done') "
            "AND created_at > ? ORDER BY created_at DESC LIMIT 1",
            (target["id"], db.now() - utcfg.UT_BOUNTY_COOLDOWN),
        )).fetchone()
        if row:
            raise ValueError(f"{target['name']} 最近 48 小时内已被挂过。凯斯不接连单——给人留口气。")
        await conn.execute("UPDATE stewards SET tickets=tickets-? WHERE id=?", (total, s["id"]))
        await conn.execute(
            """INSERT INTO ut_bounty (poster, poster_id, target_name, target_id, tier, bounty, status, expires_at, created_at)
               VALUES (?,?,?,?,?,?, 'open', ?, ?)""",
            (s["name"], s["id"], target["name"], target["id"], tier, bounty,
             db.now() + utcfg.UT_BOUNTY_NPC_TIMEOUT, db.now()),
        )
        await db.add_chronicle(
            "undertide",
            f"恩怨墙上钉了张新纸条。针对 {target['name']} 的。字迹很稳，手不抖。",
            None, conn=conn,
        )
        await conn.commit()
        tier_note = "毁他一块成熟作物" if tier == "steal" else "打一顿（body −15~25 + 病症）"
        return (
            f"酒保收下 {total} 票（赏金 {bounty} + 抽成），把纸条钉上墙。\n\n"
            f"72 小时内无人接单，NPC 打手自动办结——潮下的账不烂。\n"
            f"（{tier_note} · 同一目标 48h 内不可重复挂）"
        )

    if verb == "take":
        if len(parts) < 2 or not parts[1].isdigit():
            raise ValueError("用法: undertide_ops bounty take 编号")
        conn.row_factory = aiosqlite.Row
        b = await (await conn.execute(
            "SELECT * FROM ut_bounty WHERE id=? AND status='open'", (int(parts[1]),)
        )).fetchone()
        if not b:
            raise ValueError("这张纸条不在了。手慢了。")
        if b["target_id"] == s["id"]:
            raise ValueError("接自己的单。凯斯见过，但结局上了黑板。")
        target = await db.get_steward_by_id(b["target_id"])
        if not target:
            raise ValueError("目标已不在档口。")
        from . import undertide_muscle as um
        my_power = await um._my_power(conn, s["id"])
        # 目标战力（他当前的 body/energy 生效）
        cur = await conn.execute("SELECT health, energy FROM stewards WHERE id=?", (target["id"],))
        health, energy = (await cur.fetchone())
        their_power = int(health / 100 * 30 + energy / 100 * 15 + random.randint(1, 20))
        if my_power >= their_power:
            await conn.execute("UPDATE ut_bounty SET status='done' WHERE id=?", (b["id"],))
            await conn.execute("UPDATE stewards SET tickets=tickets+? WHERE id=?", (b["bounty"], s["id"]))
            from . import undertide as utmod
            is_npc_post = b["poster"] == "__npc__"
            await utmod._bump_rep(conn, s["id"], utcfg.UT_BOUNTY_NPC_EXEC_REP if is_npc_post else utcfg.UT_BOUNTY_EXEC_REP)
            # 真实执行（效果落地 + 目标通知走 unread_hits）
            _, effect_lines = await _execute_on_target(conn, dict(b))
            await db.add_chronicle(
                "undertide",
                f"{b['target_name']} 在后巷被人从背后按住，挨了一顿结结实实的。对方走的时候把他扶正了，让他靠着墙坐下。挺专业。",
                target["id"], conn=conn,
            )
            await conn.commit()
            rep_note = "+2（替潮下清理垃圾）" if is_npc_post else "−2（打人挣饭吃，潮下看得起但记账）"
            # 交手叙事（接单人视角：开局→中段→收尾）
            fight_story = (
                f"{utcopy.pick(utcopy.BOUNTY_FIGHT_OPENERS)}\n\n"
                f"{utcopy.pick(utcopy.BOUNTY_FIGHT_MID)}\n\n"
                f"{utcopy.pick(utcopy.BOUNTY_FIGHT_END)}"
            )
            from . import undertide_pit as _upt5
            await _upt5.pit_record(conn, s["id"], "bounty", "win", b["target_name"])
            return (
                fight_story + "\n\n——\n\n"
                + "\n".join(effect_lines)
                + f"\n（赏金 +{b['bounty']} · 影信 {rep_note}）"
            )
        # 打手失败
        await conn.execute("UPDATE ut_bounty SET status='open' WHERE id=?", (b["id"],))
        await conn.execute(
            "UPDATE stewards SET health=MAX(0,health-?) WHERE id=?",
            (random.randint(10, 15), s["id"]),
        )
        from . import undertide_pit as _upt4
        await _upt4.pit_record(conn, s["id"], "bounty", "lose", b["target_name"])
        await conn.commit()
        return (
            "你找错了人。练家子不好打——这句话你现在用身体理解了。\n\n"
            "（body 大跌 · 无赏 · 纸条回到墙上，等下一个人）"
        )

    raise ValueError("未知 bounty 指令（list/post/take）")
