"""荒宅代管 — 离岛岛民的份地可被邻居付费代管。

代管不转移所有权：原主的地还是原主的，代管人只收走得没人管的
成熟露天作物。原主一回来，代管自动结束并收到一条纪事。押金进
潮汐基金，不进任何人口袋。
"""
from __future__ import annotations

from typing import Any

import aiosqlite

from . import config, db

ABSENT_DAYS = 21          # 离岛超过三周算荒宅
CARETAKEN_DAYS = 14       # 一次代管最长两周
CARETAKE_DEPOSIT = 30     # 押金（进潮汐基金）
CARETAKE_RAPPORT = 30     # 与原主的协作度门槛（菜篮同档）
HARVESTS_PER_DAY = 1      # 每天最多替一座荒宅收一次


def _absent_since(steward: dict[str, Any]) -> int:
    """最后一次活跃距今的秒数；enroll 时间兜底（没动过的新号不算荒宅）。"""
    last = max(int(steward.get("last_active_at") or 0), int(steward.get("created_at") or 0))
    return max(0, db.now() - last)


def is_absent(steward: dict[str, Any]) -> bool:
    return _absent_since(steward) > ABSENT_DAYS * 86400


async def _list_abandoned(conn: aiosqlite.Connection) -> list[dict[str, Any]]:
    conn.row_factory = aiosqlite.Row
    rows = await (await conn.execute(
        """
        SELECT s.id, s.name, s.last_active_at, s.created_at, s.hut_level,
               (SELECT COUNT(*) FROM parcels p
                WHERE p.steward_id=s.id AND p.crop IS NOT NULL) AS plots
        FROM stewards s
        WHERE s.enrolled=1
          AND MAX(s.last_active_at, s.created_at) < ?
        ORDER BY s.last_active_at ASC LIMIT 12
        """,
        (db.now() - ABSENT_DAYS * 86400,),
    )).fetchall()
    return [dict(r) for r in rows if int(r["plots"]) > 0]


async def caretaker_ops(key_id: int, command: str = "") -> str:
    from .game import require_steward
    from .multi import _get_rapport

    s = await require_steward(key_id)
    parts = (command or "").strip().split()
    verb = parts[0] if parts else "看"

    if verb in ("看", "荒宅", "list", "help", "?"):
        async with db.connect() as conn:
            homes = await _list_abandoned(conn)
        if not homes:
            return "岸上没有荒宅 — 大家都还在。" if not homes else ""
        lines = ["【荒宅名册】离岛三周以上、地里还种着东西的："]
        for h in homes:
            days = _absent_since(h) // 86400
            lines.append(
                f"  {h['name']} · 离岛 {days} 天 · 地里 {h['plots']} 块 · 屋 Lv{h['hut_level'] or 1}"
            )
        lines.append(
            f"代管：alliance_ops 代管 名字（押金 {CARETAKE_DEPOSIT} 票进潮汐基金，"
            f"要协作度 ≥{CARETAKE_RAPPORT}；代管 {CARETAKEN_DAYS} 天，期间成熟的露天作物归你收）"
        )
        return "\n".join(lines)

    if verb == "代管" and len(parts) >= 2:
        peer = await db.get_steward_by_name(parts[1])
        if not peer:
            raise ValueError("找不到这位岛民")
        if peer["id"] == s["id"]:
            raise ValueError("自己管自己地不算代管")
        if not is_absent(peer):
            raise ValueError(f"{peer['name']} 还在岛上（或离开不满 {ABSENT_DAYS} 天），轮不到代管")
        rapport = await _get_rapport(s["id"], peer["id"])
        if rapport < CARETAKE_RAPPORT:
            raise ValueError(
                f"代管要和原主协作度 ≥{CARETAKE_RAPPORT}（现在 {rapport}）；"
                "先处熟——送礼、打点、下馆子"
            )
        async with db.connect() as conn:
            cur = await conn.execute("SELECT tickets FROM stewards WHERE id=?", (s["id"],))
            if (await cur.fetchone())[0] < CARETAKE_DEPOSIT:
                raise ValueError(f"押金要 {CARETAKE_DEPOSIT} 票")
            await conn.execute(
                "UPDATE stewards SET tickets=tickets-? WHERE id=?",
                (CARETAKE_DEPOSIT, s["id"]),
            )
            from . import chaoshen as chaoshen_mod

            await chaoshen_mod.credit_fund(conn, CARETAKE_DEPOSIT)
            await conn.execute(
                "UPDATE home_caretakes SET active=0, ended_at=? WHERE owner_id=? AND active=1",
                (db.now(), peer["id"]),
            )
            await conn.execute(
                """
                INSERT INTO home_caretakes
                (owner_id, caretaker_id, started_at, active, harvest_count, last_harvest_day)
                VALUES (?,?,?,1,0,'')
                """,
                (peer["id"], s["id"], db.now()),
            )
            await db.add_chronicle(
                "caretake",
                f"{s['name']} 付 {CARETAKE_DEPOSIT} 票押金代管 {peer['name']} 的份地（离岛中）",
                s["id"], conn=conn,
            )
            await conn.commit()
        return (
            f"代管开始：{peer['name']} 的份地交你看 {CARETAKEN_DAYS} 天。"
            f"每天 alliance_ops 代管收 一次，地里成熟的露天作物归你；"
            f"原主一回来代管自动结束。押金 {CARETAKE_DEPOSIT} 票已入潮汐基金"
        )

    if verb == "代管收" or (verb == "代管" and len(parts) >= 2 and parts[1] == "收"):
        from .multi import _day_id

        day = _day_id()
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            tk = await (await conn.execute(
                "SELECT * FROM home_caretakes WHERE caretaker_id=? AND active=1 ORDER BY id DESC",
                (s["id"],),
            )).fetchone()
            if not tk:
                raise ValueError("你没有在代管的荒宅（先 alliance_ops 代管 名字）")
            ended = await _maybe_end(conn, dict(tk))
            if ended:
                await conn.commit()
                return ended
            if str(tk["last_harvest_day"] or "") == str(day):
                raise ValueError("今天收过了，明天再来")
            rows = await (await conn.execute(
                """
                SELECT * FROM parcels WHERE steward_id=? AND greenhouse=0 AND orchard=0
                  AND crop IS NOT NULL AND ready_at>0 AND ready_at<=?
                """,
                (tk["owner_id"], db.now()),
            )).fetchall()
            if not rows:
                raise ValueError("地里还没有熟的，过两天再看")
            from . import farming

            got: list[str] = []
            for plot in rows:
                item, qty, _keep = await farming.gather_yield(conn, s["id"], dict(plot))
                if qty > 0:
                    await db.add_item(conn, s["id"], item, qty)
                await conn.execute(
                    "UPDATE parcels SET crop=NULL, planted_at=NULL, ready_at=0, tended=0, "
                    "dove_yield_mult=1.0 WHERE id=?",
                    (plot["id"],),
                )
                got.append(f"{item} x{qty}")
            await conn.execute(
                "UPDATE home_caretakes SET harvest_count=harvest_count+1, last_harvest_day=? WHERE id=?",
                (str(day), tk["id"]),
            )
            owner = await db.get_steward_by_id(tk["owner_id"])
            oname = owner["name"] if owner else "?"
            await conn.commit()
        return f"替 {oname} 收了 {len(rows)} 块地：{'、'.join(got)}，都进了你的行囊"

    if verb in ("结束", "停", "end"):
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            tk = await (await conn.execute(
                "SELECT * FROM home_caretakes WHERE caretaker_id=? AND active=1 ORDER BY id DESC",
                (s["id"],),
            )).fetchone()
            if not tk:
                raise ValueError("没有在代管的荒宅")
            await conn.execute(
                "UPDATE home_caretakes SET active=0, ended_at=? WHERE id=?",
                (db.now(), tk["id"]),
            )
            owner = await db.get_steward_by_id(tk["owner_id"])
            note = (
                f"代管结束：{owner['name'] if owner else '?'} 的份地不再由你看管"
                f"（共收 {tk['harvest_count']} 次）"
            )
            await db.add_chronicle("caretake", note, s["id"], conn=conn)
            await conn.commit()
        return note

    raise ValueError("用法：荒宅 · 代管 名字 · 代管收 · 结束")


async def _maybe_end(conn: aiosqlite.Connection, tk: dict[str, Any]) -> str | None:
    """原主回来或到期，代管结束并给原主留纪事。"""
    owner = await db.get_steward_by_id(tk["owner_id"])
    started = int(tk["started_at"] or 0)
    expired = db.now() - started > CARETAKEN_DAYS * 86400
    owner_back = owner is not None and int(owner.get("last_active_at") or 0) >= started
    if not (expired or owner_back):
        return None
    await conn.execute(
        "UPDATE home_caretakes SET active=0, ended_at=? WHERE id=?",
        (db.now(), tk["id"]),
    )
    if owner:
        why = "原主回来了" if owner_back else "代管到期"
        await db.add_chronicle(
            "caretake",
            f"你不在的这些天，份地里的熟菜被代管邻居收走了 {tk['harvest_count']} 次（{why}，代管结束）",
            None, owner["id"], conn=conn,
        )
    return (
        f"代管已结束（{'原主回来了' if owner_back else '到期'}），"
        f"共收 {tk['harvest_count']} 次"
    )
