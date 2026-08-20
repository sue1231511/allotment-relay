"""死人抽牌 — 黑潮骰 / 最后一盏灯 / 死人抽牌（二期）。天天侧。"""

from __future__ import annotations

import random
from typing import Any

import aiosqlite

from . import db
from . import undertide_config as utcfg
from . import undertide_copy as utcopy


def _day_id() -> int:
    return db.now() // 86400


async def _bet_cap(conn: aiosqlite.Connection, steward_id: int, rep: int) -> int:
    cap = 15
    for floor, c in utcfg.UT_BET_CAP:
        if rep >= floor:
            cap = c
    return cap


async def _record(
    conn: aiosqlite.Connection, steward_id: int, ut: dict[str, Any], net: int
) -> str:
    """净输赢记账 + 连输/后屋事件。返回附加文案。"""
    extra = ""
    day = _day_id()
    if int(ut.get("casino_day") or 0) != day:
        await conn.execute(
            "UPDATE steward_undertide SET casino_day=?, casino_net=0, casino_lose=0 WHERE steward_id=?",
            (day, steward_id),
        )
        ut = {**ut, "casino_day": day, "casino_net": 0, "casino_lose": 0}
    net_total = int(ut.get("casino_net") or 0) + net
    lose = int(ut.get("casino_lose") or 0) + (1 if net < 0 else 0)
    await conn.execute(
        "UPDATE steward_undertide SET casino_net=?, casino_lose=? WHERE steward_id=?",
        (net_total, lose, steward_id),
    )
    if net > 0 and net_total >= utcfg.UT_CASINO_HIGHLIGHT and net < utcfg.UT_CASINO_HIGHLIGHT:
        from . import undertide as utmod
        await utmod._bump_rep(conn, steward_id, 1)
        extra = "\n\n" + utcopy.CASINO_BACKROOM
    return extra


async def casino_ops(
    conn: aiosqlite.Connection, s: dict[str, Any], ut: dict[str, Any], verb: str, rest: str
) -> str:
    parts = rest.split()
    rep = int(ut["shadow_rep"])
    cap = await _bet_cap(conn, s["id"], rep)

    async def _take_bet(token: str) -> int:
        try:
            bet = int(token)
        except (ValueError, IndexError):
            raise ValueError("下注数额无效")
        if bet <= 0:
            raise ValueError("Silas 不收空注。")
        if bet > cap:
            raise ValueError(f"你的限额是 {cap} 票（影信档位决定）。想加大额度，先让潮下认得你。")
        cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
        if (await cur.fetchone())[0] < bet:
            raise ValueError("票不够。恶猫钱庄在楼下，但 Silas 不劝人借钱。")
        await conn.execute("UPDATE stewards SET tickets=tickets-? WHERE id=?", (bet, s["id"]))
        return bet

    # ── 黑潮骰 ──
    if verb == "dice":
        if len(parts) < 2 or parts[0] not in utcfg.UT_DICE_PAY or len(parts) < 2:
            raise ValueError("用法: undertide_ops dice small|big|black 注")
        choice = parts[0]
        bet = await _take_bet(parts[1])
        d1, d2 = random.randint(1, 6), random.randint(1, 6)
        total, pair = d1 + d2, d1 == d2
        head = utcopy.pick(utcopy.DICE_SHAKE) + f"\n\n骰盅揭开：{d1} + {d2} = {total}" + ("（对子）" if pair else "")
        if (choice == "small" and 2 <= total <= 6 and not pair) or \
           (choice == "big" and 8 <= total <= 12 and not pair):
            pay = bet * utcfg.UT_DICE_PAY[choice]
            await conn.execute("UPDATE stewards SET tickets=tickets+? WHERE id=?", (pay, s["id"]))
            extra = await _record(conn, s["id"], ut, pay - bet)
            await conn.commit()
            return f"{head}\n\n{utcopy.DICE_WIN}\n（-{bet} 注 → +{pay}，净 +{pay - bet}）{extra}"
        if choice == "black" and pair:
            pay = bet * utcfg.UT_DICE_PAY["black"]
            await conn.execute("UPDATE stewards SET tickets=tickets+? WHERE id=?", (pay, s["id"]))
            extra = await _record(conn, s["id"], ut, pay - bet)
            await conn.commit()
            return f"{head}\n\n黑潮。{utcopy.DICE_WIN}\n（-{bet} 注 → +{pay}，净 +{pay - bet}）{extra}"
        extra = await _record(conn, s["id"], ut, -bet)
        await conn.commit()
        return f"{head}\n\n{utcopy.pick(utcopy.DICE_LOSE)}\n（-{bet}）{extra}"

    # ── 最后一盏灯 ──
    if verb == "lantern":
        sub = parts[0] if parts else ""
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT * FROM ut_lantern WHERE steward_id=?", (s["id"],)
        )).fetchone()
        if sub.isdigit():
            if row:
                raise ValueError("你有一局没结束。lantern continue 或 lantern cash。")
            bet = await _take_bet(sub)
            await conn.execute(
                "INSERT INTO ut_lantern (steward_id, bet, stage, created_at) VALUES (?,?,0,?)",
                (s["id"], bet, db.now()),
            )
            await conn.commit()
            return utcopy.LANTERN_START + f"\n\n（已下注 {bet} 票 · 当前档 ×{utcfg.UT_LANTERN_LADDER[0]}）"
        if sub == "continue":
            if not row:
                raise ValueError("没有进行中的灯。lantern 注 开一局。")
            stage = int(row["stage"])
            if stage >= len(utcfg.UT_LANTERN_SURVIVE):
                raise ValueError("已经到顶了。lantern cash 收钱。")
            if random.random() < utcfg.UT_LANTERN_SURVIVE[stage]:
                await conn.execute(
                    "UPDATE ut_lantern SET stage=stage+1 WHERE steward_id=?", (s["id"],)
                )
                await conn.commit()
                new_stage = stage + 1
                mult = utcfg.UT_LANTERN_LADDER[new_stage]
                return (
                    f"{utcopy.pick(utcopy.LANTERN_SURVIVE)}\n\n"
                    f"（当前 ×{mult} · 灯还亮着 · lantern continue 继续 / lantern cash 收手）"
                )
            await conn.execute("DELETE FROM ut_lantern WHERE steward_id=?", (s["id"],))
            extra = await _record(conn, s["id"], ut, -int(row["bet"]))
            await conn.commit()
            return f"{utcopy.pick(utcopy.LANTERN_DEAD)}\n\n（-{row['bet']}）{extra}"
        if sub == "cash":
            if not row:
                raise ValueError("没有进行中的灯。")
            stage = int(row["stage"])
            mult = utcfg.UT_LANTERN_LADDER[max(0, stage - 1)] if stage > 0 else 1.0
            # stage=0 未过任何一轮：退回本金的一半（Silas 的开桌规矩）
            pay = int(int(row["bet"]) * mult) if stage > 0 else int(int(row["bet"]) * 0.5)
            await conn.execute("DELETE FROM ut_lantern WHERE steward_id=?", (s["id"],))
            await conn.execute("UPDATE stewards SET tickets=tickets+? WHERE id=?", (pay, s["id"]))
            extra = await _record(conn, s["id"], ut, pay - int(row["bet"]))
            await conn.commit()
            return f"{utcopy.LANTERN_CASH}\n\n（注 {row['bet']} × {mult} = {pay}）{extra}"
        raise ValueError("用法: lantern 注 / lantern continue / lantern cash")

    # ── 死人抽牌（指定停牌点数 12~20，一次结算）──
    if verb == "draw":
        if len(parts) < 2 or not parts[0].isdigit():
            raise ValueError("用法: undertide_ops draw 注 停牌点(12~20)")
        bet = await _take_bet(parts[0])
        try:
            stand_at = int(parts[1])
        except (ValueError, IndexError):
            stand_at = 17
        stand_at = max(12, min(20, stand_at))

        def draw_card() -> int:
            return random.randint(1, 11)

        mine, his = 0, 0
        while mine < stand_at:
            mine += draw_card()
        while his < utcfg.UT_DRAW_DEALER_STAND:
            his += draw_card()

        head = f"{utcopy.DRAW_START}\n\n你的牌点：{mine}（停牌 {stand_at}）· Silas：{his}"
        if mine > 21:
            extra = await _record(conn, s["id"], ut, -bet)
            await conn.commit()
            return f"{head}\n\n{utcopy.DRAW_BUST}\n（-{bet}）{extra}"
        if his > 21 or mine > his:
            pay = bet * 2
            await conn.execute("UPDATE stewards SET tickets=tickets+? WHERE id=?", (pay, s["id"]))
            extra = await _record(conn, s["id"], ut, bet)
            await conn.commit()
            return f"{head}\n\n{utcopy.DRAW_WIN}\n（-{bet} 注 → +{pay}，净 +{bet}）{extra}"
        if mine == his:
            await conn.execute("UPDATE stewards SET tickets=tickets+? WHERE id=?", (bet, s["id"]))
            await conn.commit()
            return f"{head}\n\n平局。Silas 把注推回来。今晚谁也不欠谁。"
        extra = await _record(conn, s["id"], ut, -bet)
        await conn.commit()
        return f"{head}\n\n{utcopy.DRAW_LOSE}\n（-{bet}）{extra}"

    raise ValueError("未知赌桌（dice/lantern/draw）")
