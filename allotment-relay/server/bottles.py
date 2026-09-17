"""漂流瓶 — 留话/捞瓶，带署名。"""

from __future__ import annotations

import random

import aiosqlite

from . import config, db, flavor
from .game import require_steward


def _day_id() -> int:
    return db.day_id()


def _rest_after_verb(command: str) -> str:
    parts = command.strip().split(None, 1)
    return parts[1] if len(parts) > 1 else ""


def _body_and_sig(text: str, default_sig: str) -> tuple[str, str]:
    body = (text or "").strip()
    signature = default_sig
    if " — " in body:
        body, signature = body.rsplit(" — ", 1)
    return body[:180], (signature or default_sig)[:40]


async def shore_view(conn: aiosqlite.Connection, steward_id: int) -> dict:
    """给 /island 海边漂流瓶栏摊开能点的。"""
    pending = (await (await conn.execute(
        "SELECT COUNT(*) FROM drift_bottles WHERE found_by IS NULL"
    )).fetchone())[0]
    day = _day_id()
    row = await (await conn.execute(
        "SELECT count FROM bottle_rolls WHERE steward_id=? AND day=?",
        (steward_id, day),
    )).fetchone()
    used = int(row[0] if row else 0)
    leave_left = max(0, int(config.BOTTLE_LEAVE_DAILY) - used)
    prev = conn.row_factory
    conn.row_factory = aiosqlite.Row
    try:
        found = await (await conn.execute(
            """
            SELECT b.id, b.body, b.signature, b.reply_at, a.name AS author_name
            FROM drift_bottles b
            JOIN stewards a ON a.id=b.author_id
            WHERE b.found_by=?
            ORDER BY b.found_at DESC LIMIT 5
            """,
            (steward_id,),
        )).fetchall()
        rows = [dict(r) for r in found]
    finally:
        conn.row_factory = prev
    return {
        "pending": int(pending or 0),
        "leave_left": leave_left,
        "found": rows,
    }


async def try_wash_ashore(s: dict) -> str | None:
    """翻沙偶尔冲上一只瓶。没缘分就当没看见，不盖过赶海正文。"""
    if random.random() > config.BOTTLE_WASH_CHANCE:
        return None
    async with db.connect() as conn:
        conn.row_factory = aiosqlite.Row
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
            return None
        bottle = dict(row)
        await conn.execute(
            "UPDATE drift_bottles SET found_by=?, found_at=? WHERE id=?",
            (s["id"], db.now(), bottle["id"]),
        )
        await conn.commit()
    sig = bottle.get("signature") or bottle.get("author_name", "?")
    await db.add_chronicle("bottle", f"{s['name']} 赶海捡到漂流瓶", s["id"])
    return f"潮线冲上一只瓶 #{bottle['id']}：「{bottle['body']}」— {sig}"


async def bottle_ops(key_id: int, command: str) -> str:
    s = await require_steward(key_id)
    raw = command.strip()
    parts = raw.split(maxsplit=2)
    verb = parts[0].lower() if parts else "scan"

    if verb in ("scan", "看", "扫瓶", "漂流瓶"):
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
        lines = [
            f"海上漂流瓶: {count} 只待捞",
            "投瓶 正文 — 署名 | 捞瓶 — 随机捞一只",
            "也可 alliance_ops bottle / tide_ops 漂流瓶。不要发明 bottle_ops",
        ]
        for r in recent:
            lines.append(f"  #{r['id']} {r['name']}→{r['signature']}: {r['body'][:40]}")
        return "\n".join(lines)

    if verb in ("leave", "投瓶", "投"):
        rest = _rest_after_verb(raw)
        if not rest:
            raise ValueError("投瓶 正文 — 可选署名。例子：投瓶 今晚浪很大")
        body, signature = _body_and_sig(rest, s["name"])
        if not body:
            raise ValueError("瓶子里要写一句。投瓶 正文 — 可选署名")
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

    if verb in ("fish", "捞瓶", "捞"):
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
                return "海上暂无漂流瓶 — 你来 投瓶 第一句？"
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

    if verb in ("read", "看瓶") and _rest_after_verb(raw):
        bid = int(_rest_after_verb(raw).split()[0])
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
        replied = ""
        if row["reply_at"]:
            replied = f"\n回瓶：{row['reply_body']}"
        return f"#{row['id']} {sig}: {row['body']}{finder}{replied}"

    if verb in ("reply", "回瓶", "回") and _rest_after_verb(raw):
        rest = _rest_after_verb(raw)
        rp = rest.split(maxsplit=1)
        if len(rp) < 2:
            raise ValueError("用法: 回瓶 编号 正文")
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
                raise ValueError("只有你捞到的瓶才能回给投瓶者")
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

    raise ValueError(
        f"未知漂流瓶指令: {command}（scan/投瓶/捞瓶/看瓶/回瓶）"
    )
