"""漂流瓶 — 留话/捞瓶，带署名。"""

from __future__ import annotations

import random

import aiosqlite

from . import config, db, flavor
from .game import require_steward


def _day_id() -> int:
    return db.now() // config.FORAGE_COOLDOWN_DAY


async def bottle_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    parts = command.strip().split(maxsplit=2)
    verb = parts[0].lower() if parts else "scan"

    if verb == "scan":
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            count = (await (await conn.execute(
                "SELECT COUNT(*) FROM drift_bottles WHERE found_by IS NULL"
            )).fetchone())[0]
            recent = await (await conn.execute(
                """
                SELECT b.id, b.body, b.signature, a.name
                FROM drift_bottles b
                JOIN stewards a ON a.id=b.author_id
                WHERE b.found_by IS NOT NULL
                ORDER BY b.found_at DESC LIMIT 5
                """
            )).fetchall()
        lines = [f"海上漂流瓶: {count} 只待捞", "leave 正文 — 署名 | fish — 随机捞一只"]
        for r in recent:
            lines.append(f"  #{r['id']} {r['name']}→{r['signature']}: {r['body'][:40]}")
        return "\n".join(lines)

    if verb == "leave":
        if len(parts) < 2:
            raise ValueError("leave 正文 — 可选署名")
        body = parts[1]
        signature = s["name"]
        if " — " in body:
            body, signature = body.rsplit(" — ", 1)
        body = body[:180]
        signature = signature[:40]
        day = _day_id()
        async with db.connect() as conn:
            cur = await conn.execute(
                "SELECT count FROM bottle_rolls WHERE steward_id=? AND day=?",
                (s["id"], day),
            )
            row = await cur.fetchone()
            if row and row[0] >= config.BOTTLE_LEAVE_DAILY:
                raise ValueError(f"今日投瓶上限 {config.BOTTLE_LEAVE_DAILY}")
            await conn.execute(
                """
                INSERT INTO drift_bottles (author_id, body, signature, created_at)
                VALUES (?,?,?,?)
                """,
                (s["id"], body, signature, db.now()),
            )
            await conn.execute(
                """
                INSERT INTO bottle_rolls (steward_id, day, count) VALUES (?,?,1)
                ON CONFLICT(steward_id, day) DO UPDATE SET count = count + 1
                """,
                (s["id"], day),
            )
            await conn.commit()
        return f"瓶已入海：「{body}」— {signature}"

    if verb == "fish":
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            if random.random() > config.BOTTLE_FISH_CHANCE + 0.25:
                await conn.commit()
                return flavor.pick([
                    "网底只有水草，瓶影一闪没了",
                    "潮线空瓶，缘分未到",
                    "捞个寂寞，但海风挺真",
                ])
            row = await (await conn.execute(
                """
                SELECT b.*, a.name AS author_name
                FROM drift_bottles b
                JOIN stewards a ON a.id=b.author_id
                WHERE b.found_by IS NULL AND b.author_id != ?
                ORDER BY RANDOM() LIMIT 1
                """,
                (s["id"],),
            )).fetchone()
            if not row:
                own = await (await conn.execute(
                    """
                    SELECT b.*, a.name FROM drift_bottles b
                    JOIN stewards a ON a.id=b.author_id
                    WHERE b.found_by IS NULL ORDER BY RANDOM() LIMIT 1
                    """
                )).fetchone()
                row = own
            if not row:
                return "海上暂无漂流瓶 — 你来 leave 第一句？"
            bottle = dict(row)
            await conn.execute(
                "UPDATE drift_bottles SET found_by=?, found_at=? WHERE id=?",
                (s["id"], db.now(), bottle["id"]),
            )
            await conn.commit()
        sig = bottle.get("signature") or bottle.get("author_name", "?")
        msg = f"捞到 #{bottle['id']}：「{bottle['body']}」— {sig}"
        msg += flavor.maybe_suffix(["瓶里话比网里鱼还难钓", "署名靠谱，内容随缘"])
        await db.add_chronicle("bottle", f"{s['name']} 捞到漂流瓶", s["id"])
        return msg

    if verb == "read" and len(parts) >= 2:
        bid = int(parts[1])
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            row = await (await conn.execute(
                """
                SELECT b.*, a.name AS author_name
                FROM drift_bottles b JOIN stewards a ON a.id=b.author_id
                WHERE b.id=?
                """,
                (bid,),
            )).fetchone()
        if not row:
            raise ValueError("没有这个瓶子")
        sig = row["signature"] or row["author_name"]
        finder = ""
        if row["found_by"]:
            fs = await db.get_steward_by_id(row["found_by"])
            finder = f"（已被 {fs['name'] if fs else '?'} 捞走）"
        return f"#{row['id']} {sig}: {row['body']}{finder}"

    if verb == "reply" and len(parts) >= 2:
        rest = command.strip()[len("reply"):].strip()
        rp = rest.split(maxsplit=1)
        if len(rp) < 2:
            raise ValueError("用法: bottle_ops reply 编号 正文")
        bid, body = int(rp[0]), rp[1][:180]
        async with db.connect() as conn:
            conn.row_factory = aiosqlite.Row
            row = await (await conn.execute(
                "SELECT * FROM drift_bottles WHERE id=?", (bid,)
            )).fetchone()
            if not row:
                raise ValueError("没有这个瓶子")
            bottle = dict(row)
            if bottle.get("reply_at"):
                raise ValueError("这只瓶已经回过话了")
            if bottle["found_by"] != s["id"]:
                raise ValueError("只有你捞到的瓶才能 reply 给投瓶者")
            await conn.execute(
                """
                UPDATE drift_bottles SET reply_body=?, reply_by=?, reply_at=?
                WHERE id=?
                """,
                (body, s["id"], db.now(), bid),
            )
            await conn.commit()
        author = await db.get_steward_by_id(bottle["author_id"])
        aname = author["name"] if author else "?"
        await db.add_chronicle(
            "bottle",
            f"{s['name']} 回瓶 #{bid} → {aname}",
            s["id"],
            bottle["author_id"],
        )
        return f"已回瓶 #{bid}：「{body}」（{aname} 下次 steward_sheet 可见）"

    raise ValueError(f"未知 bottle 指令: {command}（scan/leave/fish/read/reply）")
